#!/usr/bin/env python3
"""adversarial_phase_generator - 分队对抗相位生成器

红队（追击方）与蓝队（规避方）各获得独立的相位流。
接收全局态势 /battle/situation（由裁判节点发布），为两队分别推断相位。

发布话题：
  /red/phase, /red/heartbeat     红队相位 + 心跳（1Hz）
  /blue/phase, /blue/heartbeat   蓝队相位 + 心跳（1Hz）

部署：deploy_p04.sh 复制到 WSL2 px4_ws 并 colcon build。
用法：ros2 run nl_command adversarial_phase_generator
"""
import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from std_msgs.msg import String, Header
from px4_msgs.msg import VehicleLocalPosition

try:
    from .phase_rules import validate_phase, DEFAULT_PHASE
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phase_rules import validate_phase, DEFAULT_PHASE

# 四机命名空间（与 run_4drones.sh 对应）
DRONE_NAMESPACES = ['/fmu', '/px4_1/fmu', '/px4_2/fmu', '/px4_3/fmu']
TEAM_MEMBERS = {'red': [0, 1], 'blue': [2, 3]}

# 对抗参数
CAPTURE_RADIUS = 15.0
SAFE_ZONE_CENTER = (80.0, 80.0)
SAFE_ZONE_RADIUS = 15.0


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class AdversarialPhaseGenerator(Node):

    def __init__(self):
        super().__init__('adversarial_phase_generator')

        # 全局态势输入（来自裁判）
        self._situation_sub = self.create_subscription(
            String, '/battle/situation', self._on_situation, 10)

        # 每队独立的 phase + heartbeat 发布者
        self._team_pubs = {}
        for team in ('red', 'blue'):
            self._team_pubs[team] = {
                'phase': self.create_publisher(Header, f'/{team}/phase', 10),
                'heartbeat': self.create_publisher(Header, f'/{team}/heartbeat', 10),
            }

        # 订阅所有无人机位置（NED 坐标）
        px4_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._positions = [[0.0, 0.0, 0.0]] * 4
        self._pos_received = [False] * 4
        for i, ns in enumerate(DRONE_NAMESPACES):
            self.create_subscription(
                VehicleLocalPosition, f'{ns}/out/vehicle_local_position',
                lambda msg, idx=i: self._on_position(idx, msg), px4_qos)

        # 状态
        self._current_phases = {'red': DEFAULT_PHASE, 'blue': DEFAULT_PHASE}
        self._lock = threading.Lock()
        self._beat_count = 0

        # 心跳 1Hz（每队独立计数）
        self._hb_timer = self.create_timer(1.0, self._publish_heartbeats)
        # 相位低频重发 0.2Hz
        self._phase_timer = self.create_timer(5.0, self._republish_phases)

        self.get_logger().info(
            '对抗相位生成器就绪 | 红队=%s 蓝队=%s | 等待态势: /battle/situation'
            % (TEAM_MEMBERS['red'], TEAM_MEMBERS['blue']))

    # ------------------------------------------------------------------
    # 位置收集
    # ------------------------------------------------------------------
    def _on_position(self, idx, msg):
        # PX4 用 NED（x=北，y=东，z=下），转为 ENU 供对抗逻辑使用
        self._positions[idx] = [msg.y, msg.x, -msg.z]  # ENU
        self._pos_received[idx] = True

    def _team_centroid(self, team):
        members = TEAM_MEMBERS[team]
        positions = [self._positions[i] for i in members]
        n = len(positions)
        return [sum(p[d] for p in positions) / n for d in range(3)]

    def _nearest_enemy_distance(self, team):
        enemy = 'blue' if team == 'red' else 'red'
        own = [self._positions[i] for i in TEAM_MEMBERS[team]]
        foe = [self._positions[i] for i in TEAM_MEMBERS[enemy]]
        return min(dist2d(o[:2], f[:2]) for o in own for f in foe)

    # ------------------------------------------------------------------
    # 态势 → 分队相位推断
    # ------------------------------------------------------------------
    def _on_situation(self, msg):
        situation = msg.data.strip().lower()
        self.get_logger().info('[态势] %s' % situation[:80])

        red_phase = self._infer_phase('red', situation)
        blue_phase = self._infer_phase('blue', situation)

        with self._lock:
            if red_phase and red_phase != self._current_phases['red']:
                self._current_phases['red'] = red_phase
                self._publish_phase('red', red_phase)
            if blue_phase and blue_phase != self._current_phases['blue']:
                self._current_phases['blue'] = blue_phase
                self._publish_phase('blue', blue_phase)

    def _infer_phase(self, team, situation):
        """基于角色和态势为指定队推断对抗相位。"""
        enemy_centroid = self._team_centroid('blue' if team == 'red' else 'red')
        nearest = self._nearest_enemy_distance(team)

        # 通用规则（两队共用）
        if 'retreat' in situation or 'withdraw' in situation:
            home = (0, 0) if team == 'red' else (50, 50)
            return f'RETREAT@({home[0]:.0f},{home[1]:.0f})'

        if team == 'red':
            # 红队 = 追击方
            if 'enemy' in situation or 'intruder' in situation:
                if nearest > CAPTURE_RADIUS * 3:
                    # 距离远 → 集结后追击
                    return f'PURSUE@({enemy_centroid[0]:.0f},{enemy_centroid[1]:.0f})'
                else:
                    # 距离近 → 直接拦截
                    return f'INTERCEPT@({enemy_centroid[0]:.0f},{enemy_centroid[1]:.0f},10)'
            if 'formation' in situation or 'patrol' in situation:
                return 'RECONFIGURE@wedge'
            return None  # 维持当前相位

        else:
            # 蓝队 = 规避方
            if nearest < CAPTURE_RADIUS * 2:
                # 被逼近 → 规避（远离红队质心）
                own_centroid = self._team_centroid('blue')
                dx = own_centroid[0] - enemy_centroid[0]
                dy = own_centroid[1] - enemy_centroid[1]
                d = math.hypot(dx, dy) or 1.0
                evade_x = own_centroid[0] + dx / d * 30
                evade_y = own_centroid[1] + dy / d * 30
                return f'EVADE@({evade_x:.0f},{evade_y:.0f})'
            # 安全 → 飞向安全区
            if 'safe' in situation:
                return (f'DEFEND_ZONE@({SAFE_ZONE_CENTER[0]:.0f},'
                        f'{SAFE_ZONE_CENTER[1]:.0f},{SAFE_ZONE_RADIUS:.0f})')
            return None  # 维持当前相位

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    def _publish_phase(self, team, phase):
        if not validate_phase(phase):
            self.get_logger().warn('[%s] 非法相位: %s' % (team, phase))
            return
        msg = Header()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = phase
        self._team_pubs[team]['phase'].publish(msg)
        self.get_logger().info('[%s→端侧] 相位: %s' % (team, phase))

    def _republish_phases(self):
        with self._lock:
            for team in ('red', 'blue'):
                self._publish_phase(team, self._current_phases[team])

    def _publish_heartbeats(self):
        self._beat_count += 1
        for team in ('red', 'blue'):
            msg = Header()
            msg.stamp = self.get_clock().now().to_msg()
            msg.frame_id = f'{team}_beat_{self._beat_count}'
            self._team_pubs[team]['heartbeat'].publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = AdversarialPhaseGenerator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
