#!/usr/bin/env python3
"""phase_generator_3v3 - 3v3 对抗相位生成器（六机分队+协同策略）

红队（3机）：质心围捕策略（包围圈收缩）
蓝队（3机）：分散规避策略（领机+扇形分散）

发布：/red/phase /red/heartbeat /blue/phase /blue/heartbeat
订阅：/battle/situation（裁判态势）、六机 NED 位置
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
    from ..common.phase_rules import validate_phase, DEFAULT_PHASE
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'common'))
    from phase_rules import validate_phase, DEFAULT_PHASE

N_DRONES = 6
DRONE_NAMESPACES = ['/fmu'] + [f'/px4_{i}/fmu' for i in range(1, N_DRONES)]
TEAM_MEMBERS = {'red': [0, 1, 2], 'blue': [3, 4, 5]}

DRONE_WORLD_OFFSETS = {
    0: (0.0, 0.0),     1: (5.0, 0.0),     2: (-5.0, 0.0),
    3: (60.0, 60.0),   4: (65.0, 60.0),   5: (55.0, 60.0),
}

CAPTURE_RADIUS = 15.0
SAFE_ZONE_CENTER = (85.0, 85.0)
SAFE_ZONE_RADIUS = 12.0
SWARM_SHRINK_TAU = 60.0  # 包围圈收缩时间常数（秒）


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class PhaseGenerator3v3(Node):

    def __init__(self):
        super().__init__('phase_generator_3v3')

        self._situation_sub = self.create_subscription(
            String, '/battle/situation', self._on_situation, 10)

        self._team_pubs = {}
        for team in ('red', 'blue'):
            self._team_pubs[team] = {
                'phase': self.create_publisher(Header, f'/{team}/phase', 10),
                'heartbeat': self.create_publisher(Header, f'/{team}/heartbeat', 10),
            }

        px4_qos = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._positions = [[0.0, 0.0, 0.0]] * N_DRONES
        self._alive = [True] * N_DRONES
        for i, ns in enumerate(DRONE_NAMESPACES):
            self.create_subscription(
                VehicleLocalPosition, f'{ns}/out/vehicle_local_position',
                lambda msg, idx=i: self._on_position(idx, msg), px4_qos)

        self._current_phases = {'red': DEFAULT_PHASE, 'blue': DEFAULT_PHASE}
        self._lock = threading.Lock()
        self._battle_start = None
        self._swarm_radius = None
        self._beat_count = 0

        self._hb_timer = self.create_timer(1.0, self._publish_heartbeats)
        self._phase_timer = self.create_timer(5.0, self._republish_phases)
        # 协同更新循环（比相位重发更频繁，驱动包围圈收缩）
        self._strategy_timer = self.create_timer(2.0, self._update_strategy)

        self.get_logger().info(
            '3v3 对抗相位生成器就绪 | 红=%s 蓝=%s | 等待态势'
            % (TEAM_MEMBERS['red'], TEAM_MEMBERS['blue']))

    def _on_position(self, idx, msg):
        local_enu = [msg.y, msg.x, -msg.z]
        offset = DRONE_WORLD_OFFSETS[idx]
        self._positions[idx] = [
            local_enu[0] + offset[0], local_enu[1] + offset[1], local_enu[2]]

    def _team_centroid(self, team, alive_only=True):
        members = [i for i in TEAM_MEMBERS[team] if (self._alive[i] or not alive_only)]
        if not members:
            return self._positions[TEAM_MEMBERS[team][0]]
        positions = [self._positions[i] for i in members]
        return [sum(p[d] for p in positions) / len(positions) for d in range(3)]

    def _on_situation(self, msg):
        situation = msg.data.strip().lower()
        self.get_logger().info('[态势] %s' % situation[:80])
        if self._battle_start is None:
            self._battle_start = time.time()
            self._swarm_radius = None

    def _update_strategy(self):
        """2Hz 协同策略更新：驱动包围圈收缩与分散规避。"""
        if self._battle_start is None:
            return
        elapsed = time.time() - self._battle_start

        # 红队：质心围捕（包围圈收缩）
        blue_centroid = self._team_centroid('blue')
        alive_red = [i for i in TEAM_MEMBERS['red'] if self._alive[i]]
        if alive_red and self._swarm_radius is None:
            r0 = max(
                dist2d(self._positions[i][:2], blue_centroid[:2])
                for i in alive_red
            )
            self._swarm_radius = max(r0, CAPTURE_RADIUS * 2)

        if alive_red and self._swarm_radius is not None:
            r = max(CAPTURE_RADIUS * 0.5,
                    self._swarm_radius * math.exp(-elapsed / SWARM_SHRINK_TAU))
            red_centroid = self._team_centroid('red')
            # 发布蜂群围捕相位（蓝队质心 + 当前收缩半径）
            phase = f'SWARM_PURSUE@({blue_centroid[0]:.0f},{blue_centroid[1]:.0f},{r:.0f})'
            with self._lock:
                self._current_phases['red'] = phase
                self._publish_phase('red', phase)

        # 蓝队：分散规避
        alive_blue = [i for i in TEAM_MEMBERS['blue'] if self._alive[i]]
        if alive_blue:
            blue_centroid = self._team_centroid('blue')
            red_centroid = self._team_centroid('red')
            dx = blue_centroid[0] - red_centroid[0]
            dy = blue_centroid[1] - red_centroid[1]
            d = math.hypot(dx, dy) or 1.0

            # 领机方向：远离红队
            lead_x = blue_centroid[0] + dx / d * 30
            lead_y = blue_centroid[1] + dy / d * 30

            # 检查是否到达安全区
            at_safe = dist2d(blue_centroid[:2], SAFE_ZONE_CENTER) < SAFE_ZONE_RADIUS
            if at_safe:
                phase = f'HOLD@({SAFE_ZONE_CENTER[0]:.0f},{SAFE_ZONE_CENTER[1]:.0f},5)'
            else:
                phase = f'SCATTER_EVADE@({lead_x:.0f},{lead_y:.0f},45)'
            with self._lock:
                self._current_phases['blue'] = phase
                self._publish_phase('blue', phase)

    def _publish_phase(self, team, phase):
        if not validate_phase(phase):
            self.get_logger().warn('[%s] 非法相位: %s' % (team, phase))
            return
        msg = Header()
        msg.stamp = self.get_clock().now().to_msg()
        msg.frame_id = phase
        self._team_pubs[team]['phase'].publish(msg)

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
    node = PhaseGenerator3v3()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
