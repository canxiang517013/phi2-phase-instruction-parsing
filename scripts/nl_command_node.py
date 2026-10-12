#!/usr/bin/env python3
"""NL -> Phi-2 -> JSON -> PX4 Offboard demo node.

Workflow:
  1. Subscribe /nl_input (String) - natural language command
  2. Call Phi-2 (via completion API) to parse into JSON
  3. arm + offboard + takeoff
  4. Fly to target (ENU -> NED conversion + TrajectorySetpoint)
  5. Hover on arrival

Coordinate frames:
  Phi-2 outputs ENU (x=East, y=North, z=Up)
  PX4 uses NED (x=North, y=East, z=Down)
  Conversion: NED = (y_enu, x_enu, -z_enu)
"""
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from rclpy.clock import Clock

from std_msgs.msg import String, Header
from px4_msgs.msg import (
    OffboardControlMode, TrajectorySetpoint, VehicleCommand,
    VehicleStatus, VehicleLocalPosition,
)


class NLCommandNode(Node):

    def __init__(self):
        super().__init__('nl_command_node')

        self.declare_parameter('phi2_base_url', 'http://172.21.112.1:8080/v1')
        self.declare_parameter('phi2_model', 'phi2-dmpc-q6_k.gguf')
        self.declare_parameter('takeoff_altitude', 2.0)
        self.declare_parameter('fmu_prefix', '/fmu')  # 命名空间隔离用：/fmu 或 /px4_1/fmu
        self.declare_parameter('nl_topic', '/nl_input')  # 两机用不同 NL 输入话题
        self.declare_parameter('target_system', 1)  # PX4 MAV_SYS_ID（多实例时 instance+1，如实例2=2）
        self.base_url = self.get_parameter('phi2_base_url').value
        self.model = self.get_parameter('phi2_model').value
        self.takeoff_alt = self.get_parameter('takeoff_altitude').value
        self.fmu_prefix = self.get_parameter('fmu_prefix').value
        self.nl_topic = self.get_parameter('nl_topic').value
        self.target_system = int(self.get_parameter('target_system').value)

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
        self.get_logger().info('已订阅 %s' % self.nl_topic)

        # ---- 云端心跳监听（创新点3：断连降级）----
        self._hb_sub = self.create_subscription(
            Header, '/cloud/heartbeat', self._on_heartbeat, 10)
        self._phase_sub = self.create_subscription(
            Header, '/cloud/phase', self._on_phase_signal, 10)
        self._link_status = 'DISCONNECTED'  # DISCONNECTED / CONNECTED / DEGRADED
        self._last_heartbeat_time = 0.0
        self._heartbeat_timeout = 3.0  # 3秒无心跳判定断连
        self._cached_phase = None  # 最后收到的云端相位缓存
        self._degraded_log_count = 0

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
        # 状态反馈定时器：每 5 秒打印一次当前状态，避免终端"看起来卡死"
        self._status_timer = self.create_timer(5.0, self._status_log)

        self.get_logger().info(
            'NLCommandNode ready: Phi-2=%s  waiting for /nl_input' % self.base_url)

    def _status_log(self):
        if self._phase != 'idle':
            self.get_logger().info(
                '[状态] phase=%s link=%s armed=%s offboard=%s cached_phase=%s'
                % (self._phase, self._link_status, self._armed,
                   self._in_offboard, self._cached_phase or '无'))

    # ------------------------------------------------------------------
    # 云端心跳与相位信号（创新点3：断连降级）
    # ------------------------------------------------------------------
    def _on_heartbeat(self, msg: Header):
        now = time.time()
        was = self._link_status
        self._last_heartbeat_time = now
        if self._link_status != 'CONNECTED':
            self._link_status = 'CONNECTED'
            if was == 'DEGRADED':
                self.get_logger().info(
                    '[恢复] 云端链路恢复，重新对齐相位（缓存=%s）'
                    % (self._cached_phase or '无'))
            else:
                # 首次连接（DISCONNECTED→CONNECTED）也打印一条，便于验证
                self.get_logger().info('[云端] 链路已连接（心跳: %s）' % msg.frame_id)

    def _on_phase_signal(self, msg: Header):
        # 相位信号来自云端（低频），缓存最新值供降级时使用
        if msg.frame_id != self._cached_phase:
            self.get_logger().info('[云端] 相位信号: %s' % msg.frame_id)
        self._cached_phase = msg.frame_id

    def _check_link_degradation(self):
        """在控制循环中调用：超时无心跳 → 进入降级模式。"""
        if self._link_status == 'CONNECTED':
            if time.time() - self._last_heartbeat_time > self._heartbeat_timeout:
                self._link_status = 'DEGRADED'
                self.get_logger().warn(
                    '[断连] %.1f秒无心跳，进入降级模式！使用缓存相位自主维持（缓存=%s）'
                    % (time.time() - self._last_heartbeat_time,
                       self._cached_phase or '无'))

    def _degraded_behavior(self):
        """降级行为：依据缓存相位的相位目标自主维持（创新点3核心）。

        相位缓存格式（与 v4 微调模型一致）：
          ASSEMBLE@(gx,gy)       → 飞往 (gx,gy,高度5)
          HOLD@(px,py,pz)        → 飞往 (px,py,pz)
          OBSTACLE_AVOID@L@N     → 飞往 (-N,0,15)
          OBSTACLE_AVOID@R@N     → 飞往 (N,0,15)
          RECON@(tx,ty)          → 飞往 (tx,ty,15)
          RECONFIGURE@form       → 飞往 (15,15,8)
        无法解析时退回安全悬停。
        """
        target = self._parse_cached_phase_target()

        if target is not None:
            # 端侧自主飞往相位目标（ENU→NED 转换）
            ned = [target[1], target[0], -target[2]]
            self._publish_setpoint(ned)
            self._degraded_log_count += 1
            if self._degraded_log_count % 100 == 0:
                self.get_logger().warn(
                    '[降级·相位维持] 缓存=%s → 目标ENU=%s 当前NED=(%.1f,%.1f,%.1f)'
                    % (self._cached_phase, target,
                       self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]))
        else:
            # 无有效缓存相位 → 安全悬停（保底行为）
            if self._has_position:
                self._publish_setpoint([
                    self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]])
            self._degraded_log_count += 1
            if self._degraded_log_count % 100 == 0:
                self.get_logger().warn(
                    '[降级·安全悬停] 无有效相位缓存，位置保持 NED(%.1f,%.1f,%.1f)'
                    % (self._pos_ned[0], self._pos_ned[1], self._pos_ned[2]))

    def _parse_cached_phase_target(self):
        """解析缓存相位字符串为 ENU 坐标目标。返回 [x,y,z] 或 None。"""
        if not self._cached_phase:
            return None
        p = self._cached_phase.strip()
        try:
            if p.startswith('ASSEMBLE@(') and p.endswith(')'):
                inner = p[len('ASSEMBLE@('):-1]
                x, y = [float(v) for v in inner.split(',')]
                return [x, y, 5.0]
            if p.startswith('HOLD@(') and p.endswith(')'):
                inner = p[len('HOLD@('):-1]
                x, y, z = [float(v) for v in inner.split(',')]
                return [x, y, z]
            if p.startswith('OBSTACLE_AVOID@left@'):
                n = float(p[len('OBSTACLE_AVOID@left@'):])
                return [-n, 0.0, 15.0]
            if p.startswith('OBSTACLE_AVOID@right@'):
                n = float(p[len('OBSTACLE_AVOID@right@'):])
                return [n, 0.0, 15.0]
            if p.startswith('RECON@(') and p.endswith(')'):
                inner = p[len('RECON@('):-1]
                x, y = [float(v) for v in inner.split(',')]
                return [x, y, 15.0]
            if p.startswith('RECONFIGURE@'):
                return [15.0, 15.0, 8.0]
        except (ValueError, IndexError):
            return None
        return None

    def _on_status(self, msg: VehicleStatus):
        was_armed = self._armed
        was_offboard = self._in_offboard
        self._armed = (msg.arming_state == 2)
        self._in_offboard = (msg.nav_state == 14)
        if self._in_offboard and not was_offboard:
            self.get_logger().info('PX4 confirmed OFFBOARD mode!')
        if self._armed and not was_armed:
            self.get_logger().info('PX4 ARMED successfully!')

    def _on_position(self, msg: VehicleLocalPosition):
        self._has_position = True
        self._pos_ned = [msg.x, msg.y, msg.z]

    def _on_nl_input(self, msg: String):
        # 放到独立线程执行，避免 HTTP 调用阻塞 executor（否则收不到 PX4 状态）
        if self._processing:
            self.get_logger().info('已有指令在处理中，忽略重复指令')
            return
        self._processing = True
        t = threading.Thread(target=self._process_nl, args=(msg.data,), daemon=True)
        t.start()

    def _process_nl(self, text):
        text = text.strip()
        self.get_logger().info('NL input: %s' % text)

        import json
        import urllib.request
        nl = chr(10)
        prompt = (
            '### System:' + nl +
            'Parse the user natural language command into a structured JSON for UAV DMPC.'
            + nl + nl +
            '### User:' + nl + text + nl + nl +
            '### Response:' + nl
        )
        payload = json.dumps({
            'model': self.model,
            'prompt': prompt,
            'temperature': 0.1,
            'max_tokens': 64,
            'stop': ['<|endoftext|>', nl + '###'],
        }).encode('utf-8')

        url = self.base_url + '/completions'
        req = urllib.request.Request(
            url, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST')

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            content = result['choices'][0]['text'].strip()
            self.get_logger().info('Phi-2 output: %s' % content)
            parsed = json.loads(content)
        except Exception as e:
            self.get_logger().error('Phi-2 parse failed: %s' % e)
            self._processing = False
            return

        target = parsed.get('target')
        if target is None:
            self.get_logger().error('No target field in Phi-2 output')
            return

        if isinstance(target, dict):
            tx, ty, tz = float(target['x']), float(target['y']), float(target['z'])
        elif isinstance(target, list):
            tx, ty, tz = float(target[0]), float(target[1]), float(target[2])
        else:
            self.get_logger().error('Unknown target format: %s' % type(target))
            return

        self._current_target = [ty, tx, -tz]
        self.get_logger().info(
            'Target ENU=(%.1f,%.1f,%.1f) -> NED=(%.1f,%.1f,%.1f)'
            % (tx, ty, tz, ty, tx, -tz))

        if self._phase == 'idle':
            self._phase = 'taking_off'
            self._takeoff_target_ned = [0.0, 0.0, -self.takeoff_alt]
            # 记录起飞点（home）：水平位置取当前，高度取起飞高度
            if self._has_position:
                self._home_point_ned = [
                    self._pos_ned[0], self._pos_ned[1], -self.takeoff_alt]
            self._offboard_retry_count = 0
            self._arm_retry_count = 0
            self._hover_start_time = None
            self.get_logger().info(
                'Starting takeoff sequence -> alt %.1f m, home=%.1f,%.1f'
                % (self.takeoff_alt, self._home_point_ned[0], self._home_point_ned[1]))
        self._processing = False

    def _control_loop(self):
        # 0. 云端链路检查（创新点3）+ 降级行为优先于正常任务
        self._check_link_degradation()
        if self._link_status == 'DEGRADED':
            self._publish_offboard_heartbeat()  # PX4 offboard 心跳不能停
            self._degraded_behavior()
            return  # 降级期间暂停正常任务状态机

        # 1. offboard heartbeat（done 阶段停止发送，让 PX4 退出 offboard）
        if self._phase != 'done':
            self._publish_offboard_heartbeat()

        if self._phase == 'idle':
            return

        # 2. Always publish the current setpoint target (PX4 needs setpoint
        #    streaming BEFORE it will accept offboard mode)
        # done 阶段不发 setpoint（停止 offboard 让 PX4 接受 DISARM）
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

        # 3. Send offboard mode command repeatedly until PX4 confirms it's in offboard
        # done 阶段：跳过 offboard/arm 重试（我们正要退出 offboard + 上锁）
        if self._phase == 'done':
            self._done_disarm_flow()
            return

        if not self._in_offboard:
            self._offboard_retry_count += 1
            if self._offboard_retry_count % 10 == 0:  # every 0.5s at 20Hz
                self._engage_offboard()
            return  # wait until offboard confirmed before trying arm

        # 4. Once in offboard, send arm command periodically until armed
        if not self._armed:
            self._arm_retry_count += 1
            if self._arm_retry_count % 10 == 0:  # every 0.5s
                self._send_arm_command()
            return

        # 5. Phase transitions once armed
        if self._phase == 'taking_off':
            if self._has_position:
                err = abs(self._pos_ned[2] - self._takeoff_target_ned[2])
                if err < 0.5:
                    self.get_logger().info('Reached takeoff alt, cruising')
                    self._phase = 'cruising'

        elif self._phase == 'cruising':
            if self._current_target and self._has_position:
                dx = self._pos_ned[0] - self._current_target[0]
                dy = self._pos_ned[1] - self._current_target[1]
                dz = self._pos_ned[2] - self._current_target[2]
                dist = (dx * dx + dy * dy + dz * dz) ** 0.5
                if dist < 1.0:
                    self.get_logger().info(
                        'Reached target (dist %.2f m), hovering' % dist)
                    self._phase = 'hovering'

        elif self._phase == 'hovering':
            # 在目标点悬停 5 秒，然后返回起飞点
            if self._hover_start_time is None:
                self._hover_start_time = time.time()
                self.get_logger().info('到达目标，悬停 5 秒后返回')
            elif time.time() - self._hover_start_time > 5.0:
                self.get_logger().info('悬停完成，返回起飞点 (%.1f, %.1f)'
                                       % (self._home_point_ned[0], self._home_point_ned[1]))
                self._phase = 'returning_home'

        elif self._phase == 'returning_home':
            # 飞回起飞点（水平），到达后开始降落
            if self._has_position:
                dx = self._pos_ned[0] - self._home_point_ned[0]
                dy = self._pos_ned[1] - self._home_point_ned[1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < 1.0:
                    self.get_logger().info('回到起飞点，开始降落')
                    self._phase = 'landing'
                    self._takeoff_target_ned = [
                        self._home_point_ned[0], self._home_point_ned[1], 0.0]

        elif self._phase == 'landing':
            # 降落到地面（z=0），落地后上锁
            if self._has_position:
                if abs(self._pos_ned[2]) < 0.3:
                    self.get_logger().info('已落地，上锁')
                    self._send_disarm_command()
                    self._phase = 'done'

        elif self._phase == 'landing':
            if self._has_position:
                if abs(self._pos_ned[2]) < 0.3:
                    self.get_logger().info('已落地，上锁')
                    self._send_disarm_command()
                    self._phase = 'done'
                    # done 的后续处理由 _done_disarm_flow() 接管

    def _done_disarm_flow(self):
        """done 阶段的上锁流程（不在此发 offboard heartbeat / setpoint / ARM）。

        流程：停止 offboard 输出 → 等 PX4 退出 offboard → DISARM。
        PX4 在 offboard 模式且持续收到 setpoint 时会拒绝 DISARM（安全机制）。
        """
        if not self._done_logged:
            self.get_logger().info(
                '[done] 停止 offboard 输出，等待 PX4 退出 offboard 模式...')
            self._done_logged = True
            self._done_start_time = time.time()

        # 已成功上锁
        if not self._armed:
            if not self._disarm_success_logged:
                self.get_logger().info('[done] ✅ DISARM 成功，任务完成')
                self._disarm_success_logged = True
            return

        # 等 1 秒让 PX4 检测到 offboard 超时并退出
        if time.time() - self._done_start_time > 1.0:
            self._disarm_retry_count += 1
            if self._disarm_retry_count % 20 == 0:
                if self._in_offboard:
                    self.get_logger().info('PX4 仍在 offboard，先切 POSCTL...')
                    self._switch_to_hold_mode()
                else:
                    self._send_disarm_command()

    def _publish_offboard_heartbeat(self):
        msg = OffboardControlMode()
        msg.timestamp = self._now_us()
        msg.position = True
        msg.velocity = False
        msg.acceleration = False
        msg.attitude = False
        msg.body_rate = False
        self._ocm_pub.publish(msg)

    def _publish_setpoint(self, target_ned):
        nan = float('nan')
        msg = TrajectorySetpoint()
        msg.timestamp = self._now_us()
        msg.position = [
            float(target_ned[0]), float(target_ned[1]), float(target_ned[2])]
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
        msg.param1 = 1.0   # 1 = use PX4 custom mode
        msg.param2 = 6.0   # 6 = PX4_CUSTOM_MAIN_MODE_OFFBOARD
        msg.param3 = float('nan')
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)
        self.get_logger().info('Sent OFFBOARD mode command (param2=6)')

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
        self.get_logger().info(
            'Sent ARM command (attempt %d)' % self._arm_retry_count)

    def _switch_to_hold_mode(self):
        """切换 PX4 到 HOLD 模式（脱离 offboard，让 DISARM 能被接受）。"""
        msg = VehicleCommand()
        msg.timestamp = self._now_us()
        msg.command = VehicleCommand.VEHICLE_CMD_DO_SET_MODE
        msg.param1 = 1.0
        msg.param2 = 5.0   # PX4 CUSTOM_MAIN_MODE: 5 = POSCTL (位置保持)
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
        msg.param1 = 0.0   # 0 = disarm
        msg.target_system = self.target_system
        msg.target_component = 1
        msg.source_system = 1
        msg.source_component = 1
        msg.from_external = True
        self._vc_pub.publish(msg)
        self.get_logger().info('Sent DISARM command (任务完成)')

    def _now_us(self):
        return int(Clock().now().nanoseconds / 1000)


def main(args=None):
    rclpy.init(args=args)
    node = NLCommandNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
