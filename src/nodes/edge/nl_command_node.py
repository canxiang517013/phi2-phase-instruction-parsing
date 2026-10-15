#!/usr/bin/env python3
"""nl_command_node_p04 - P0-4 双机闭环端侧节点（安全层+TTL链路集成版）

在 8 月版 nl_command_node 基础上的三处升级（其余飞行状态机保持不变）：
  1. P04Link：timestamp+TTL+safe-fallback 链路状态机（心跳驱动新鲜度 +
     相位消息 stamp 陈旧性/单调性拒收；DEGRADED → 相位无关安全悬停，
     不重放缓存相位——旧相位比没有相位更危险）
  2. SafetyLayer：Phi-2 输出的确定性五层关卡（schema/包络/分轴数值溯源/
     相位一致性），拒绝 → 安全默认，绝不进 PX4
  3. 相位条件化 prompt（与 v5 训练格式一致）+ episode 级 JSONL 留痕

部署：scripts/deploy_p04.sh 复制到 WSL2 px4_ws 的 nl_command 包并 colcon build。
用法（与 nl_command_node 相同的参数 + log_file）：
  ros2 run nl_command nl_command_node_p04 --ros-args \
      -p nl_topic:=/drone1/nl_input -p fmu_prefix:=/fmu -p target_system:=1 \
      -p log_file:=/tmp/p04_drone1_episode.jsonl
"""
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.parse

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from rclpy.clock import Clock
from std_msgs.msg import String, Header
from px4_msgs.msg import (
    OffboardControlMode, TrajectorySetpoint, VehicleCommand,
    VehicleStatus, VehicleLocalPosition,
)

try:
    from .phase_rules import validate_phase
    from .safety_layer import SafetyLayer
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase_rules import validate_phase
    from safety_layer import SafetyLayer

FRESH, DEGRADED = 'FRESH', 'DEGRADED'
INSTR_BASE = 'Parse the user natural language command into a structured JSON for UAV DMPC.'
LINK_TTL_S = 2.0          # 相位消息 stamp 陈旧阈值
DEGRADE_DEADLINE_S = 3.0  # 心跳+相位全无新鲜信号的退化时限

# 部署主机白名单：Windows 宿主（llama.cpp server）/ 回环 / WSL 自身。
# 修改部署拓扑时在此扩展；节点不接受白名单外的任何服务端 URL（防 SSRF）。
ALLOWED_HOSTS = {'172.21.112.1', '127.0.0.1', 'localhost', '172.21.112.162'}


def validate_base_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'http' or parts.hostname not in ALLOWED_HOSTS:
        raise ValueError('phi2_base_url 非法（仅允许 http + %s）: %r'
                         % sorted(ALLOWED_HOSTS), url)
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 拒绝一切重定向


_OPENER = urllib.request.build_opener(_NoRedirect)


class P04Link:
    """部署版链路状态机（离线 pilot 的 phase_link.PhaseLink 加心跳通道）。

    - /cloud/heartbeat（1Hz）：链路层新鲜度；断流 >3s → DEGRADED
    - /cloud/phase（0.2Hz 重发）：内容通道；stamp 超过 TTL 2s 拒收（stale），
      stamp 非单调拒收（重放防御），非法语法拒收
    - DEGRADED 决策 = 相位无关安全悬停；恢复 = 心跳或新鲜相位到来
    """

    def __init__(self, node_logger):
        self._log = node_logger
        self.state = DEGRADED
        self.phase = None          # 最后被接受的相位内容
        self.last_phase_stamp = 0.0
        self._fresh_ts = 0.0       # max(心跳 rx, 相位接受) 的墙钟时刻
        self.stats = {'phase_accepted': 0, 'phase_stale': 0, 'phase_invalid': 0,
                      'phase_nonmonotonic': 0, 'degrade_events': 0,
                      'recover_events': 0}

    def on_heartbeat(self, now, frame):
        self._fresh_ts = max(self._fresh_ts, now)
        if self.state == DEGRADED:
            self.state = FRESH
            self.stats['recover_events'] += 1
            self._log('[链路·恢复] 心跳恢复（%s），相位内容=%s'
                      % (frame, self.phase or '无'))

    def on_phase(self, phase, stamp_s, now):
        if not validate_phase(phase):
            self.stats['phase_invalid'] += 1
            self._log('[链路·拒收] 非法相位语法: %r' % phase)
            return 'invalid'
        if now - stamp_s > LINK_TTL_S:
            self.stats['phase_stale'] += 1
            self._log('[链路·拒收] 陈旧相位(%.1fs>TTL%.0fs): %s'
                      % (now - stamp_s, LINK_TTL_S, phase))
            return 'stale'
        if stamp_s <= self.last_phase_stamp:
            self.stats['phase_nonmonotonic'] += 1
            self._log('[链路·拒收] 非单调/重放相位: %s' % phase)
            return 'non-monotonic'
        self.stats['phase_accepted'] += 1
        if phase != self.phase:
            self._log('[链路] 接受新相位: %s' % phase)
        self.phase = phase
        self.last_phase_stamp = stamp_s
        self._fresh_ts = max(self._fresh_ts, now)
        if self.state == DEGRADED:
            self.state = FRESH
            self.stats['recover_events'] += 1
            self._log('[链路·恢复] 新鲜相位恢复: %s' % phase)
        return 'accepted'

    def tick(self, now):
        if self.state == FRESH and now - self._fresh_ts > DEGRADE_DEADLINE_S:
            self.state = DEGRADED
            self.stats['degrade_events'] += 1
            self._log('[链路·断连] %.1fs 无新鲜信号，DEGRADED → 相位无关安全悬停（缓存相位 %s 不重放）'
                      % (now - self._fresh_ts, self.phase or '无'))
        return self.state


class NLCommandNodeP04(Node):

    def __init__(self):
        super().__init__('nl_command_node_p04')
        self.declare_parameter('phi2_base_url', 'http://172.21.112.1:8080/v1')
        self.declare_parameter('phi2_model', 'phi2-phased-v5-q5_k_m.gguf')
        self.declare_parameter('takeoff_altitude', 2.0)
        self.declare_parameter('fmu_prefix', '/fmu')
        self.declare_parameter('nl_topic', '/nl_input')
        self.declare_parameter('target_system', 1)
        self.declare_parameter('log_file', '/tmp/p04_episode.jsonl')
        self.declare_parameter('phase_topic', '/cloud/phase')
        self.declare_parameter('heartbeat_topic', '/cloud/heartbeat')
        self.phase_topic = self.get_parameter('phase_topic').value
        self.heartbeat_topic = self.get_parameter('heartbeat_topic').value
        self.base_url = validate_base_url(self.get_parameter('phi2_base_url').value)
        self.model = self.get_parameter('phi2_model').value
        self.takeoff_alt = self.get_parameter('takeoff_altitude').value
        self.fmu_prefix = self.get_parameter('fmu_prefix').value
        self.nl_topic = self.get_parameter('nl_topic').value
        self.target_system = int(self.get_parameter('target_system').value)
        self.log_file = self.get_parameter('log_file').value

        self.link = P04Link(self.get_logger().info)
        self.safety = SafetyLayer()
        self._episode = 0

        px4_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._ocm_pub = self.create_publisher(
            OffboardControlMode, self.fmu_prefix + '/in/offboard_control_mode', px4_qos)
        self._ts_pub = self.create_publisher(
            TrajectorySetpoint, self.fmu_prefix + '/in/trajectory_setpoint', px4_qos)
        self._vc_pub = self.create_publisher(
            VehicleCommand, self.fmu_prefix + '/in/vehicle_command', px4_qos)
        self._vs_sub = self.create_subscription(
            VehicleStatus, self.fmu_prefix + '/out/vehicle_status', self._on_status, px4_qos)
        self._vp_sub = self.create_subscription(
            VehicleLocalPosition, self.fmu_prefix + '/out/vehicle_local_position',
            self._on_position, px4_qos)
        self._nl_sub = self.create_subscription(
            String, self.nl_topic, self._on_nl_input, 10)
        self._hb_sub = self.create_subscription(
            Header, self.heartbeat_topic, self._on_heartbeat, 10)
        self._phase_sub = self.create_subscription(
            Header, self.phase_topic, self._on_phase_signal, 10)

        self._armed = False
        self._in_offboard = False
        self._current_target = None
        self._phase = 'idle'
        self._takeoff_target_ned = None
        self._has_position = False
        self._pos_ned = [0.0, 0.0, 0.0]
        self._offboard_retry_count = 0
        self._arm_retry_count = 0
        self._disarm_retry_count = 0
        self._done_logged = False
        self._done_start_time = 0.0
        self._disarm_success_logged = False
        self._processing = False
        self._hover_start_time = None
        self._home_point_ned = [0.0, 0.0, 0.0]

        self._timer = self.create_timer(0.05, self._control_loop)
        self._status_timer = self.create_timer(5.0, self._status_log)
        self.get_logger().info(
            'P04Node ready: Phi-2=%s model=%s nl=%s fmu=%s log=%s phase=%s hb=%s'
            % (self.base_url, self.model, self.nl_topic,
               self.fmu_prefix, self.log_file, self.phase_topic, self.heartbeat_topic))

    # ------------------------------------------------------------------
    # episode 留痕（JSONL，一行一事件；同时打到 stdout 便于 tee）
    # ------------------------------------------------------------------
    def _emit(self, event, **kw):
        rec = {'t': round(time.time(), 3), 'ep': self._episode,
               'event': event, 'drone': self.nl_topic}
        rec.update(kw)
        line = json.dumps(rec, ensure_ascii=False)
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError as e:
            self.get_logger().warn('日志写入失败: %s' % e)
        self.get_logger().info('P04LOG %s' % line)

    def _status_log(self):
        self._emit('status', state=self._phase, link=self.link.state,
                   armed=self._armed, offboard=self._in_offboard,
                   phase_content=self.link.phase,
                   ned=[round(v, 2) for v in self._pos_ned],
                   link_stats=dict(self.link.stats))

    # ------------------------------------------------------------------
    # 云端链路（P04Link）
    # ------------------------------------------------------------------
    def _on_heartbeat(self, msg: Header):
        now = time.time()
        stamp = msg.stamp.sec + msg.stamp.nanosec * 1e-9
        self.link.on_heartbeat(now, msg.frame_id)
        self._emit('heartbeat', age=round(now - stamp, 3), frame=msg.frame_id)

    def _on_phase_signal(self, msg: Header):
        now = time.time()
        stamp = msg.stamp.sec + msg.stamp.nanosec * 1e-9
        verdict = self.link.on_phase(msg.frame_id, stamp, now)
        self._emit('phase', content=msg.frame_id, stamp=round(stamp, 3),
                   rx=round(now, 3), verdict=verdict)

    # ------------------------------------------------------------------
    # Phi-2 调用 + SafetyLayer 关卡
    # ------------------------------------------------------------------
    def _on_nl_input(self, msg: String):
        if self._processing:
            self.get_logger().info('已有指令在处理中，忽略')
            return
        self._processing = True
        t = threading.Thread(target=self._process_nl, args=(msg.data,), daemon=True)
        t.start()

    def _process_nl(self, text):
        text = text.strip()
        self._episode += 1
        self._emit('nl_input', text=text)
        nl = chr(10)
        try:
            if self.link.state == FRESH and self.link.phase:
                instruction = 'Phase: %s. %s' % (self.link.phase, INSTR_BASE)
            else:
                instruction = INSTR_BASE
            prompt = ('### System:' + nl + instruction + nl + nl +
                      '### User:' + nl + text + nl + nl +
                      '### Response:' + nl)
            payload = json.dumps({
                'model': self.model, 'prompt': prompt,
                'temperature': 0.1, 'max_tokens': 64,
                'stop': ['<|endoftext|>', nl + '###'],
            }).encode('utf-8')
            req = urllib.request.Request(
                self.base_url + '/completions', data=payload,
                headers={'Content-Type': 'application/json'}, method='POST')
            t0 = time.time()
            with _OPENER.open(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            content = result['choices'][0]['text'].strip()
            latency_ms = round((time.time() - t0) * 1000, 1)
            self._emit('slm_raw', prompt_phase=self.link.phase, raw=content,
                       latency_ms=latency_ms)
        except Exception as e:
            self._emit('slm_error', error=str(e)[:200])
            self._processing = False
            return

        accepted, action, reason = self.safety.check(
            content, text, self.link.phase if self.link.state == FRESH else None)
        self._emit('safety', accepted=accepted, reason=reason,
                   action=action, raw=content)
        if not accepted:
            self.get_logger().warn('[安全层·拒绝] %s → hold' % reason)
            self._processing = False
            return

        tx, ty, tz = [float(v) for v in action['target']]
        self._current_target = [ty, tx, -tz]
        self._emit('target', enu=[tx, ty, tz],
                   ned=[round(v, 2) for v in self._current_target],
                   formation=action.get('formation'), ids=action.get('uav_ids'))
        if self._phase == 'idle':
            self._phase = 'taking_off'
            self._takeoff_target_ned = [0.0, 0.0, -self.takeoff_alt]
            if self._has_position:
                self._home_point_ned = [
                    self._pos_ned[0], self._pos_ned[1], -self.takeoff_alt]
            self._offboard_retry_count = 0
            self._arm_retry_count = 0
            self._hover_start_time = None
            self._emit('state', to='taking_off')
        self._processing = False

    # ------------------------------------------------------------------
    # 飞行状态机（8 月已验证逻辑 + P0-4 链路优先级）
    # ------------------------------------------------------------------
    def _on_status(self, msg: VehicleStatus):
        was_armed, was_off = self._armed, self._in_offboard
        self._armed = (msg.arming_state == 2)
        self._in_offboard = (msg.nav_state == 14)
        if self._in_offboard and not was_off:
            self._emit('px4', data='OFFBOARD confirmed')
        if self._armed and not was_armed:
            self._emit('px4', data='ARMED')

    def _on_position(self, msg: VehicleLocalPosition):
        self._has_position = True
        self._pos_ned = [msg.x, msg.y, msg.z]

    def _control_loop(self):
        self.link.tick(time.time())
        if self.link.state == DEGRADED:
            self._publish_offboard_heartbeat()
            if self._has_position:
                self._publish_setpoint([
                    self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]])
            return  # 降级期间暂停正常任务状态机（安全悬停优先）

        if self._phase != 'done':
            self._publish_offboard_heartbeat()
        if self._phase == 'idle':
            return

        if self._phase in ('taking_off', 'returning', 'landing'):
            target = self._takeoff_target_ned
        elif self._phase in ('cruising', 'hovering'):
            target = self._current_target
        elif self._phase == 'returning_home':
            target = self._home_point_ned
        else:
            target = None
        if target:
            self._publish_setpoint(target)

        if self._phase == 'done':
            self._done_disarm_flow()
            return
        if not self._in_offboard:
            self._offboard_retry_count += 1
            if self._offboard_retry_count % 10 == 0:
                self._engage_offboard()
            return
        if not self._armed:
            self._arm_retry_count += 1
            if self._arm_retry_count % 10 == 0:
                self._send_arm_command()
            return

        if self._phase == 'taking_off':
            if self._has_position and \
                    abs(self._pos_ned[2] - self._takeoff_target_ned[2]) < 0.5:
                self._phase = 'cruising'
                self._emit('state', to='cruising')
        elif self._phase == 'cruising':
            if self._current_target and self._has_position:
                dx = self._pos_ned[0] - self._current_target[0]
                dy = self._pos_ned[1] - self._current_target[1]
                dz = self._pos_ned[2] - self._current_target[2]
                if (dx * dx + dy * dy + dz * dz) ** 0.5 < 1.0:
                    self._phase = 'hovering'
                    self._emit('state', to='hovering')
        elif self._phase == 'hovering':
            if self._hover_start_time is None:
                self._hover_start_time = time.time()
            elif time.time() - self._hover_start_time > 5.0:
                self._phase = 'returning_home'
                self._emit('state', to='returning_home')
        elif self._phase == 'returning_home':
            if self._has_position:
                dx = self._pos_ned[0] - self._home_point_ned[0]
                dy = self._pos_ned[1] - self._home_point_ned[1]
                if (dx * dx + dy * dy) ** 0.5 < 1.0:
                    self._phase = 'landing'
                    self._takeoff_target_ned = [
                        self._home_point_ned[0], self._home_point_ned[1], 0.0]
                    self._emit('state', to='landing')
        elif self._phase == 'landing':
            if self._has_position and abs(self._pos_ned[2]) < 0.3:
                self._send_disarm_command()
                self._phase = 'done'
                self._emit('state', to='done')

    def _done_disarm_flow(self):
        if not self._done_logged:
            self._done_logged = True
            self._done_start_time = time.time()
            self._emit('state', to='done-wait-disarm')
        if not self._armed:
            if not self._disarm_success_logged:
                self._disarm_success_logged = True
                self._emit('px4', data='DISARMED ok')
            return
        if time.time() - self._done_start_time > 1.0:
            self._disarm_retry_count += 1
            if self._disarm_retry_count % 20 == 0:
                if self._in_offboard:
                    self._switch_to_hold_mode()
                else:
                    self._send_disarm_command()

    def _publish_offboard_heartbeat(self):
        msg = OffboardControlMode()
        msg.timestamp = self._now_us()
        msg.position = True
        self._ocm_pub.publish(msg)

    def _publish_setpoint(self, target_ned):
        nan = float('nan')
        msg = TrajectorySetpoint()
        msg.timestamp = self._now_us()
        msg.position = [float(target_ned[0]), float(target_ned[1]), float(target_ned[2])]
        msg.velocity = [nan, nan, nan]
        msg.acceleration = [nan, nan, nan]
        msg.jerk = [nan, nan, nan]
        msg.yaw = 0.0
        msg.yawspeed = nan
        self._ts_pub.publish(msg)

    def _engage_offboard(self):
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = VehicleCommand.VEHICLE_CMD_DO_SET_MODE
        msg.param1 = 1.0
        msg.param2 = 6.0
        msg.param3 = float('nan')
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)

    def _send_arm_command(self):
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
        msg.param1 = 1.0
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)

    def _switch_to_hold_mode(self):
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = VehicleCommand.VEHICLE_CMD_DO_SET_MODE
        msg.param1 = 1.0
        msg.param2 = 5.0
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)

    def _send_disarm_command(self):
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM
        msg.param1 = 0.0
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)
        self._emit('px4', data='DISARM sent')

    def _now_us(self):
        return int(Clock().now().nanoseconds / 1000)


def main(args=None):
    rclpy.init(args=args)
    node = NLCommandNodeP04()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
