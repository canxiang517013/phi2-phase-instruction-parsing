#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mappo_policy_node.py — 2D MAPPO 编队策略 → PX4 SITL/AirSim 桥接节点

单节点控制 4 架跟随者（每个 PX4 实例一路话题），虚拟 leader 由本节点积分。
阶段流程：
  INIT(等状态) → STREAM(流式 setpoint) → OFFBOARD → ARMED
  → TAKEOFF(升到 altitude) → PREPOS(位置控制预定位到四角)
  → FORMATION(10 Hz 策略，速度 setpoint) → HOVER(3 s) → LAND → DISARM → DONE

坐标约定：
  PX4 local NED (x=北, y=东, z=下) → 世界 ENU (东, 北, 上)：
    east  = msg.y + spawn_east[i]
    north = msg.x + spawn_north[i]
    up    = -msg.z
  env 平面坐标 (x=east, y=north)，与 2D 训练一致（见 mappo_bridge_math）。

安全：任一机位置/状态数据超过 stale_timeout 视为失联 → 悬停并冻结策略；
高度偏差超过 ±10 m 中止；全程 JSONL 留痕。

依赖：numpy（不需要 torch，权重用 npz 纯 numpy 前向）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from std_msgs.msg import Header, String

from px4_msgs.msg import (
    OffboardControlMode, TrajectorySetpoint, VehicleCommand,
    VehicleLocalPosition, VehicleStatus,
)

try:
    from uav_adversarial.edge import mappo_bridge_math as bm
    from uav_adversarial.edge.p04_link import DEGRADED, FRESH, P04Link
except ImportError:
    import mappo_bridge_math as bm
    from p04_link import DEGRADED, FRESH, P04Link  # type: ignore


PH_INIT = 'init'
PH_STREAM = 'stream'
PH_OFFBOARD = 'offboard'
PH_ARMED = 'armed'
PH_TAKEOFF = 'takeoff'
PH_PREPOS = 'prepos'
PH_FORMATION = 'formation'
PH_HOVER = 'hover'
PH_LAND = 'land'
PH_DISARM = 'disarm'
PH_DONE = 'done'


class MappoFormationNode(Node):

    def __init__(self):
        super().__init__('mappo_formation_node')

        self.declare_parameter('actor_npz', '')
        self.declare_parameter('namespaces',
                               ['/fmu', '/px4_1/fmu', '/px4_2/fmu', '/px4_3/fmu'])
        self.declare_parameter('target_systems', [1, 2, 3, 4])
        self.declare_parameter('spawn_east', [0.0, 0.0, 0.0, 60.0])
        self.declare_parameter('spawn_north', [0.0, 5.0, -5.0, 60.0])
        self.declare_parameter('start_east', [100.0, -100.0, -100.0, 100.0])
        self.declare_parameter('start_north', [100.0, 100.0, -100.0, -100.0])
        self.declare_parameter('altitude', 30.0)
        self.declare_parameter('policy_rate', 10.0)
        self.declare_parameter('control_rate', 20.0)
        self.declare_parameter('stale_timeout', 0.5)
        self.declare_parameter('max_flight_seconds', 300.0)
        self.declare_parameter('prepos_accept_radius', 3.0)
        # 发送给 PX4 的速度指令单 tick 最大变化量（m/s）。
        # 策略假设速度瞬时生效，而 PX4 速度环有 ~0.2 s 滞后；不限幅时
        # 动作翻转（每 tick 最多 3 m/s）会激励闭环形成 15 m/s 环绕极限环。
        # 取 MPC_ACC_HOR_MAX(8 m/s^2) × dt(0.1 s) = 0.8，保证指令可跟踪。
        self.declare_parameter('max_cmd_delta', 0.8)
        # 集结阶段（leader 未动）的水平指令限速。训练环境的策略依赖
        # "速度矢量可瞬时旋转"的动力学；PX4 以 15 m/s 飞行时转弯半径
        # v^2/a ≈ 60-70 m，接近槽位后无法及时转向，会形成稳定环绕。
        # 集结限速 11.5 m/s 让转弯半径降到可收敛范围；跟随（追赶 leader）
        # 阶段仍允许 15 m/s。
        self.declare_parameter('assemble_speed_cap', 11.5)
        # leader 放行门槛。默认 20m/5tick 与 env 的完成判定等价（完成即放行，
        # 即 run4 语义）。实验证明收紧到 10m/20tick 会退化：静态槽位保持
        # 在旋转滞后下反而最难（无人机会在槽位附近游走 40m+），动态追踪
        # 更稳。保留参数是为了记录这一结论，不建议收紧。
        self.declare_parameter('leader_release_error', 20.0)
        self.declare_parameter('leader_release_steps', 5)
        # P0-4 闭环：相位链路（心跳+相位，TTL/退化语义见 p04_link）
        self.declare_parameter('phase_topic', '/cloud/phase')
        self.declare_parameter('heartbeat_topic', '/cloud/heartbeat')
        self.declare_parameter('mission_primitive_topic', '/mission/primitive')
        self.declare_parameter('require_phase_link', False)
        # 初始编队几何（circle=训练菱形；line/column 仅演示用）
        self.declare_parameter('formation', 'circle')
        # 策略 tick 上限。默认 500 与 env episode_len 一致（基准测试语义）；
        # P0-4 任务演示用 1500（150s），容纳 NL 指令时间线。
        self.declare_parameter('episode_ticks', 0)
        self.declare_parameter('log_file', '/tmp/mappo_formation.jsonl')

        self.actor_npz = str(self.get_parameter('actor_npz').value)
        self.n = len(list(self.get_parameter('namespaces').value))
        self.namespaces = [str(x) for x in self.get_parameter('namespaces').value]
        self.target_systems = [int(x) for x in self.get_parameter('target_systems').value]
        self.spawn_east = [float(x) for x in self.get_parameter('spawn_east').value]
        self.spawn_north = [float(x) for x in self.get_parameter('spawn_north').value]
        self.start_east = [float(x) for x in self.get_parameter('start_east').value]
        self.start_north = [float(x) for x in self.get_parameter('start_north').value]
        self.altitude = float(self.get_parameter('altitude').value)
        self.stale_timeout = float(self.get_parameter('stale_timeout').value)
        self.max_flight_s = float(self.get_parameter('max_flight_seconds').value)
        self.prepos_radius = float(self.get_parameter('prepos_accept_radius').value)
        self.max_cmd_delta = float(self.get_parameter('max_cmd_delta').value)
        self.assemble_cap = float(self.get_parameter('assemble_speed_cap').value)
        self.release_error = float(self.get_parameter('leader_release_error').value)
        self.release_steps = int(self.get_parameter('leader_release_steps').value)
        self.require_link = bool(self.get_parameter('require_phase_link').value)
        self._formation_param = str(self.get_parameter('formation').value)
        if self._formation_param not in bm.SUPPORTED_FORMATIONS:
            raise ValueError('formation 必须是 %s' % (bm.SUPPORTED_FORMATIONS,))
        self.log_path = Path(str(self.get_parameter('log_file').value))

        self.actor = bm.NumpyActor.from_npz(self.actor_npz)
        self.cfg = dict(bm.BRIDGE_CFG)
        self.cfg['n_agents'] = self.n
        self.cfg['formation_name'] = self._formation_param
        ticks_override = int(self.get_parameter('episode_ticks').value)
        if ticks_override > 0:
            self.cfg['episode_len'] = ticks_override

        px4_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        self.drones = []
        for i, ns in enumerate(self.namespaces):
            drone = {
                'idx': i, 'ns': ns,
                'pos_ned': [0.0, 0.0, 0.0], 'vel_ned': [0.0, 0.0, 0.0],
                'pos_stamp': 0.0, 'status_stamp': 0.0,
                'armed': False, 'offboard': False, 'landed': False,
                'home_ned': None,
                'cmd_env': np.zeros(2, dtype=np.float32),
                'cmd_vz_up': 0.0,
            }
            drone['ocm_pub'] = self.create_publisher(
                OffboardControlMode, ns + '/in/offboard_control_mode', px4_qos)
            drone['ts_pub'] = self.create_publisher(
                TrajectorySetpoint, ns + '/in/trajectory_setpoint', px4_qos)
            drone['vc_pub'] = self.create_publisher(
                VehicleCommand, ns + '/in/vehicle_command', 10)
            self.create_subscription(
                VehicleLocalPosition, ns + '/out/vehicle_local_position',
                lambda msg, d=drone: self._on_position(d, msg), px4_qos)
            self.create_subscription(
                VehicleStatus, ns + '/out/vehicle_status',
                lambda msg, d=drone: self._on_status(d, msg), px4_qos)
            self.drones.append(drone)

        self.phase = PH_INIT
        self.phase_t0 = time.time()
        self.flight_t0 = None

        # P0-4 闭环：链路状态机 + 任务原语
        self.link = P04Link(self.get_logger().info)
        self.hold_requested = False
        self.link_logged_degraded = False
        self.create_subscription(
            Header, str(self.get_parameter('phase_topic').value),
            self._on_phase_signal, 10)
        self.create_subscription(
            Header, str(self.get_parameter('heartbeat_topic').value),
            self._on_heartbeat, 10)
        self.create_subscription(
            String, str(self.get_parameter('mission_primitive_topic').value),
            self._on_primitive, 10)

        self._log_fh = self.log_path.open('a', encoding='utf-8')
        self._emit('node_start', actor=self.actor_npz, n=self.n,
                   namespaces=self.namespaces,
                   spawn_east=self.spawn_east, spawn_north=self.spawn_north,
                   altitude=self.altitude)

        # episode 状态
        self.leader = bm.VirtualLeader(self.cfg)
        self.tracker = bm.FormationTracker(self.cfg)
        self.release_count = 0
        self.leader_released = False
        self.ep_t = 0
        self.follow_steps = 0
        self.follow_valid = np.zeros(self.n, dtype=np.int64)
        self.err_sum = 0.0
        self.pair_sum = 0.0
        self.terminal_max_err = None
        self.episode_summarized = False
        self.stale_logged = False
        self.land_cmd_sent = False
        self._done_logged = False

        control_period = 1.0 / float(self.get_parameter('control_rate').value)
        policy_period = 1.0 / float(self.get_parameter('policy_rate').value)
        self.create_timer(control_period, self._control_tick)
        self.create_timer(policy_period, self._policy_tick)
        self.get_logger().info(
            'mappo_formation 就绪: n=%d actor=%s 高度=%.0f m'
            % (self.n, self.actor_npz, self.altitude))

    # ------------------------------------------------------------------
    # 回调与坐标转换
    # ------------------------------------------------------------------
    def _on_position(self, drone, msg: VehicleLocalPosition):
        drone['pos_ned'] = [float(msg.x), float(msg.y), float(msg.z)]
        drone['vel_ned'] = [float(msg.vx), float(msg.vy), float(msg.vz)]
        drone['pos_stamp'] = time.time()

    def _on_status(self, drone, msg: VehicleStatus):
        drone['armed'] = (msg.arming_state == 2)
        drone['offboard'] = (msg.nav_state == 14)
        drone['status_stamp'] = time.time()

    # ------------------------------------------------------------------
    # P0-4 闭环输入：相位链路 + 任务原语
    # ------------------------------------------------------------------
    def _now(self):
        return time.time()

    def _on_heartbeat(self, msg: Header):
        self.link.on_heartbeat(self._now(), msg.frame_id)

    def _on_phase_signal(self, msg: Header):
        stamp_s = msg.stamp.sec + msg.stamp.nanosec * 1e-9
        self.link.on_phase(msg.frame_id, stamp_s, self._now())

    def _on_primitive(self, msg: String):
        try:
            prim = json.loads(msg.data)
        except (json.JSONDecodeError, ValueError):
            self._emit('primitive_reject', reason='unparseable-json',
                       raw=msg.data[:120])
            return
        ptype = prim.get('type')
        if ptype == 'LEADER_TARGET':
            try:
                x, y = float(prim['target'][0]), float(prim['target'][1])
            except (KeyError, TypeError, ValueError, IndexError):
                self._emit('primitive_reject', reason='bad-target', prim=prim)
                return
            if not (abs(x) <= 300.0 and abs(y) <= 300.0):
                self._emit('primitive_reject', reason='out-of-envelope',
                           target=[x, y])
                return
            self.leader.target = np.array([x, y], dtype=np.float32)
            self.hold_requested = False  # 新任务解除冻结
            self._emit('primitive_applied', type=ptype, target=[x, y],
                       alt_note=prim.get('alt_note'), nl=prim.get('nl'),
                       phase=prim.get('phase'),
                       slm_latency_ms=prim.get('slm_latency_ms'))
        elif ptype == 'HOLD':
            self.hold_requested = True
            self._emit('primitive_applied', type=ptype, nl=prim.get('nl'),
                       phase=prim.get('phase'))
        elif ptype == 'RESUME':
            self.hold_requested = False
            self._emit('primitive_applied', type=ptype)
        elif ptype == 'RECONFIGURE':
            formation = str(prim.get('formation', ''))
            if formation not in bm.SUPPORTED_FORMATIONS:
                self._emit('primitive_reject', reason='formation-unsupported',
                           formation=formation)
                return
            self.cfg['formation_name'] = formation
            self._emit('primitive_applied', type=ptype, formation=formation)
        else:
            self._emit('primitive_reject', reason='unknown-type', prim=prim)

    def _world_pos(self, i):
        """第 i 架机的 env 平面坐标 (x=east, y=north) 与高度。"""
        d = self.drones[i]
        east = d['pos_ned'][1] + self.spawn_east[i]
        north = d['pos_ned'][0] + self.spawn_north[i]
        up = -d['pos_ned'][2]
        return np.array([east, north], dtype=np.float32), up

    def _world_vel(self, i):
        d = self.drones[i]
        return np.array([d['vel_ned'][1], d['vel_ned'][0]], dtype=np.float32)

    # ------------------------------------------------------------------
    # PX4 指令
    # ------------------------------------------------------------------
    def _now_us(self):
        return int(time.time() * 1e6)

    def _publish_mode(self, drone, velocity_mode: bool):
        msg = OffboardControlMode()
        msg.timestamp = self._now_us()
        msg.position = not velocity_mode
        msg.velocity = velocity_mode
        drone['ocm_pub'].publish(msg)

    def _publish_position_sp(self, drone, ned_xyz):
        nan = float('nan')
        msg = TrajectorySetpoint()
        msg.timestamp = self._now_us()
        msg.position = [float(v) for v in ned_xyz]
        msg.velocity = [nan, nan, nan]
        msg.acceleration = [nan, nan, nan]
        msg.jerk = [nan, nan, nan]
        msg.yaw = 0.0
        msg.yawspeed = nan
        drone['ts_pub'].publish(msg)

    def _publish_velocity_sp(self, drone, v_env, vz_up):
        nan = float('nan')
        msg = TrajectorySetpoint()
        msg.timestamp = self._now_us()
        msg.position = [nan, nan, nan]
        # env (x=east, y=north) -> NED (北, 东, 下)
        msg.velocity = [float(v_env[1]), float(v_env[0]), -float(vz_up)]
        msg.acceleration = [nan, nan, nan]
        msg.jerk = [nan, nan, nan]
        msg.yaw = nan
        msg.yawspeed = nan
        drone['ts_pub'].publish(msg)

    def _vehicle_command(self, drone, command, **params):
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = command
        for name in ('param1', 'param2', 'param3', 'param4', 'param5', 'param6', 'param7'):
            if name in params:
                setattr(msg, name, float(params[name]))
        msg.target_system = self.target_systems[drone['idx']]
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        drone['vc_pub'].publish(msg)

    def _engage_offboard(self, drone):
        self._vehicle_command(drone, VehicleCommand.VEHICLE_CMD_DO_SET_MODE,
                              param1=1.0, param2=6.0)

    def _send_arm(self, drone):
        self._vehicle_command(drone, VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
                              param1=1.0)

    def _send_disarm(self, drone):
        self._vehicle_command(drone, VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM,
                              param1=0.0)

    def _send_land(self, drone):
        self._vehicle_command(drone, VehicleCommand.VEHICLE_CMD_NAV_LAND)

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def _emit(self, event, **kw):
        rec = {'t': round(time.time(), 3), 'event': event}
        rec.update(kw)
        line = json.dumps(rec, ensure_ascii=False, default=float)
        self._log_fh.write(line + '\n')
        self._log_fh.flush()
        self.get_logger().info('[%s] %s' % (event, json.dumps(kw, default=str)[:180]))

    def _set_phase(self, phase):
        self._emit('phase', **{'from': self.phase, 'to': phase})
        self.phase = phase
        self.phase_t0 = time.time()

    # ------------------------------------------------------------------
    # 20 Hz 控制心跳
    # ------------------------------------------------------------------
    def _control_tick(self):
        now = time.time()

        if self.phase == PH_INIT:
            ready = all(d['pos_stamp'] > 0 and d['status_stamp'] > 0
                        for d in self.drones)
            if ready:
                for d in self.drones:
                    d['home_ned'] = list(d['pos_ned'])
                    self._publish_mode(d, velocity_mode=False)
                self._set_phase(PH_STREAM)
            return

        if self.flight_t0 is None:
            self.flight_t0 = now

        if self.phase in (PH_STREAM, PH_OFFBOARD, PH_ARMED):
            for d in self.drones:
                self._publish_mode(d, velocity_mode=False)
                self._publish_position_sp(
                    d, [d['home_ned'][0], d['home_ned'][1], -self.altitude])
            if self.phase == PH_STREAM and now - self.phase_t0 > 1.0:
                self._set_phase(PH_OFFBOARD)
            elif self.phase == PH_OFFBOARD:
                if now - self.phase_t0 > 0.5:
                    self.phase_t0 = now
                    for d in self.drones:
                        if not d['offboard']:
                            self._engage_offboard(d)
                if all(d['offboard'] for d in self.drones):
                    self._set_phase(PH_ARMED)
            elif self.phase == PH_ARMED:
                if now - self.phase_t0 > 0.5:
                    self.phase_t0 = now
                    for d in self.drones:
                        if not d['armed']:
                            self._send_arm(d)
                if all(d['armed'] for d in self.drones):
                    self._set_phase(PH_TAKEOFF)
                    self._emit('px4', data='all armed, taking off')
            return

        if self.phase == PH_TAKEOFF:
            for d in self.drones:
                self._publish_mode(d, velocity_mode=False)
                self._publish_position_sp(
                    d, [d['home_ned'][0], d['home_ned'][1], -self.altitude])
            ups = [-d['pos_ned'][2] for d in self.drones]
            if all(u >= self.altitude - 1.5 for u in ups):
                self._set_phase(PH_PREPOS)
            return

        if self.phase == PH_PREPOS:
            arrived = True
            for i, d in enumerate(self.drones):
                self._publish_mode(d, velocity_mode=False)
                target_ned = [
                    self.start_north[i] - self.spawn_north[i],
                    self.start_east[i] - self.spawn_east[i],
                    -self.altitude,
                ]
                self._publish_position_sp(d, target_ned)
                d['prepos_target_ned'] = target_ned
                d_err = ((d['pos_ned'][0] - target_ned[0]) ** 2
                         + (d['pos_ned'][1] - target_ned[1]) ** 2) ** 0.5
                a_err = abs(-d['pos_ned'][2] - self.altitude)
                if d_err > self.prepos_radius or a_err > 1.5:
                    arrived = False
            if arrived and now - self.phase_t0 > 3.0:
                self._start_episode()
            return

        if self.phase == PH_FORMATION:
            for d in self.drones:
                self._publish_mode(d, velocity_mode=True)
                self._publish_velocity_sp(d, d['cmd_env'], d['cmd_vz_up'])
            return

        if self.phase == PH_HOVER:
            for d in self.drones:
                self._publish_mode(d, velocity_mode=True)
                vz = self._altitude_vz(-d['pos_ned'][2])
                self._publish_velocity_sp(d, np.zeros(2, dtype=np.float32), vz)
            if now - self.phase_t0 > 3.0:
                self.land_cmd_sent = False
                self._set_phase(PH_LAND)
            return

        if self.phase == PH_LAND:
            if not self.land_cmd_sent:
                self.land_cmd_sent = True
                for d in self.drones:
                    self._send_land(d)
                self._emit('px4', data='NAV_LAND sent to all')
            landed = all(-d['pos_ned'][2] < 0.3 for d in self.drones)
            if landed:
                self._set_phase(PH_DISARM)
            return

        if self.phase == PH_DISARM:
            if now - self.phase_t0 > 1.0:
                self.phase_t0 = now
                for d in self.drones:
                    if d['armed']:
                        self._send_disarm(d)
            if not any(d['armed'] for d in self.drones):
                self._emit('px4', data='all disarmed')
                self._set_phase(PH_DONE)
            return

        if self.phase == PH_DONE:
            if not self._done_logged:
                self._done_logged = True
                self._emit('done', data='episode complete')
                self.get_logger().info('全部完成，节点退出')
                # rclpy.shutdown() 在 Humble 的 timer 回调里偶发死锁不退出，
                # 该节点是末端叶子（日志已逐行落盘），确定性退出即可。
                self._log_fh.flush()
                os._exit(0)
            return

    def _altitude_vz(self, up):
        kp = 0.6
        err = self.altitude - up
        if abs(err) < 0.3:
            return 0.0
        return float(np.clip(kp * err, -1.5, 1.5))

    def _send_cmd(self, drone, desired_env, vz_up):
        """对发送给 PX4 的水平指令做加速度可行性限幅后写入。"""
        delta = desired_env - drone['cmd_env']
        norm = float(np.linalg.norm(delta))
        if norm > self.max_cmd_delta:
            delta = delta / norm * self.max_cmd_delta
        drone['cmd_env'] = (drone['cmd_env'] + delta).astype(np.float32)
        drone['cmd_vz_up'] = vz_up

    # ------------------------------------------------------------------
    # 10 Hz 策略
    # ------------------------------------------------------------------
    def _start_episode(self):
        # 任务状态（SLM/相位设置的目标、冻结请求）跨越 episode 初始化保留；
        # 只有 leader 的运动学状态归零。否则编队开始瞬间会把已下达的
        # 改派目标重置回 cfg 默认值（2026-10-22 闭环调试实测踩过的坑）。
        mission_target = self.leader.target.copy()
        mission_hold = self.hold_requested
        self.leader = bm.VirtualLeader(self.cfg)
        self.leader.target = mission_target
        self.hold_requested = mission_hold
        self.tracker = bm.FormationTracker(self.cfg)
        self.release_count = 0
        self.leader_released = False
        self.ep_t = 0
        self.follow_steps = 0
        self.follow_valid = np.zeros(self.n, dtype=np.int64)
        self.err_sum = 0.0
        self.pair_sum = 0.0
        self.terminal_max_err = None
        self.episode_summarized = False
        self.ep_t0 = time.time()
        for d in self.drones:
            d['cmd_env'] = np.zeros(2, dtype=np.float32)
            d['cmd_vz_up'] = self._altitude_vz(-d['pos_ned'][2])
        self._emit('config', cfg={k: list(v) if isinstance(v, tuple) else v
                                  for k, v in self.cfg.items()},
                   start_east=self.start_east, start_north=self.start_north,
                   altitude=self.altitude)
        self._set_phase(PH_FORMATION)

    def _stale(self):
        now = time.time()
        return any(now - d['pos_stamp'] > self.stale_timeout for d in self.drones)

    def _policy_tick(self):
        if self.phase != PH_FORMATION:
            return
        now = time.time()
        if now - self.flight_t0 > self.max_flight_s:
            self._emit('abort', reason='max_flight_seconds')
            self._summarize_episode(leader_reached=False)
            self._set_phase(PH_HOVER)
            return
        if self._stale():
            if not self.stale_logged:
                self.stale_logged = True
                self._emit('warn', data='position stale, policy frozen, hovering')
            for d in self.drones:
                self._send_cmd(d, np.zeros(2, dtype=np.float32),
                               self._altitude_vz(-d['pos_ned'][2]))
            return
        self.stale_logged = False

        self.link.tick(now)
        if self.require_link and self.link.state == DEGRADED:
            if not self.link_logged_degraded:
                self.link_logged_degraded = True
                self._emit('link_degraded',
                           action='freeze leader + hover (phase-independent)')
            for d in self.drones:
                self._send_cmd(d, np.zeros(2, dtype=np.float32),
                               self._altitude_vz(-d['pos_ned'][2]))
            return
        if self.link_logged_degraded:
            self.link_logged_degraded = False
            self._emit('link_recovered', phase=self.link.phase)

        for i, d in enumerate(self.drones):
            up = -d['pos_ned'][2]
            if abs(up - self.altitude) > 10.0:
                self._emit('abort', reason='altitude_out_of_band', drone=i, up=up)
                self._summarize_episode(leader_reached=False)
                self._set_phase(PH_HOVER)
                return

        pos = np.stack([self._world_pos(i)[0] for i in range(self.n)])
        vel = np.stack([self._world_vel(i) for i in range(self.n)])
        ups = np.array([-self.drones[i]['pos_ned'][2] for i in range(self.n)])

        # 与 env 的采样语义一致：obs 用上一 tick 末的 leader/标志
        targets_old = bm.compute_targets(
            self.leader.pos, self.cfg['formation_radius'], self.n,
            self.cfg['formation_name'])
        obs = bm.build_obs(pos, vel, targets_old, self.leader.pos, self.leader.vel,
                           self.tracker.phase_flag, self.tracker.complete)
        action = self.actor.act(obs)

        following_active = bool(self.tracker.complete)
        released = self.leader_released
        self.leader.moving = released and not self.hold_requested
        self.leader.step()
        targets = bm.compute_targets(
            self.leader.pos, self.cfg['formation_radius'], self.n,
            self.cfg['formation_name'])

        errors = np.linalg.norm(pos - targets, axis=1)
        near = np.array([[bm.near_target_scale(float(errors[i]), following_active,
                                               self.cfg)] for i in range(self.n)],
                        dtype=np.float32)
        v_cmd = bm.velocity_command(vel, action, near, self.cfg)
        for i, d in enumerate(self.drones):
            desired = v_cmd[i]
            if not released:
                speed = float(np.linalg.norm(desired))
                if speed > self.assemble_cap > 0.0:
                    desired = desired / speed * self.assemble_cap
            self._send_cmd(d, desired, self._altitude_vz(float(ups[i])))

        max_err = float(np.max(errors))
        self.tracker.update(max_err)
        if not self.leader_released and self.tracker.complete:
            if max_err <= self.release_error:
                self.release_count += 1
            else:
                self.release_count = 0
            if self.release_count >= self.release_steps:
                self.leader_released = True
                self._emit('phase', **{'from': 'settling', 'to': 'leader_released'})
        if following_active:
            self.follow_steps += 1
            self.follow_valid += (errors <= self.cfg['follow_error_threshold']).astype(np.int64)
        self.err_sum += float(np.mean(errors))
        _, pair_global, _ = bm.pairwise_metrics(
            pos, self.cfg['formation_radius'], self.cfg.get('collision_distance', 10.0))
        self.pair_sum += pair_global
        self.terminal_max_err = float(np.max(errors))

        self._emit('step', t=self.ep_t, leader=[float(self.leader.pos[0]),
                                                float(self.leader.pos[1])],
                   drones=[{'i': i, 'pos': pos[i].tolist(), 'vel': vel[i].tolist(),
                            'cmd': v_cmd[i].tolist(), 'err': float(errors[i]),
                            'up': float(ups[i])} for i in range(self.n)],
                   formation_complete=bool(self.tracker.complete),
                   stable_count=int(self.tracker.stable_count),
                   released=bool(self.leader_released),
                   hold=bool(self.hold_requested),
                   link_phase=self.link.phase if not self.require_link
                   or self.link.state == FRESH else None,
                   pairwise=pair_global)

        self.ep_t += 1
        leader_reached = self.leader.reached_goal
        if leader_reached or self.ep_t >= int(self.cfg['episode_len']):
            self._summarize_episode(leader_reached)
            self._set_phase(PH_HOVER)

    def _summarize_episode(self, leader_reached):
        if self.episode_summarized:
            return
        self.episode_summarized = True
        steps = max(1, self.ep_t)
        result = bm.evaluate_episode(
            self.tracker.complete, leader_reached, self.follow_steps,
            self.follow_valid.tolist(), self.terminal_max_err or 1e9, self.cfg)
        result.update({
            'steps': self.ep_t,
            'avg_position_error': self.err_sum / steps,
            'avg_pairwise_error': self.pair_sum / steps,
            'elapsed_seconds': round(time.time() - self.ep_t0, 2),
        })
        self._emit('episode_end', **result)

    def shutdown(self):
        try:
            self._log_fh.close()
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = MappoFormationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
