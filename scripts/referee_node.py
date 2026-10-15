#!/usr/bin/env python3
"""referee_node - 对抗裁判：判定胜负、生成交战态势、驱动相位切换

功能：
  1. 订阅 4 机位置（PX4 NED → ENU）
  2. 实时计算红蓝距离、判定胜负（捕获/超时/到达安全区）
  3. 发布自然语言态势 /battle/situation（供对抗相位生成器消费）
  4. 记录对抗日志（jsonl）

部署：deploy_p04.sh 复制到 WSL2 px4_ws 并 colcon build。
用法：ros2 run nl_command referee_node
"""
import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from std_msgs.msg import String
from px4_msgs.msg import VehicleLocalPosition

DRONE_NAMESPACES = ['/fmu', '/px4_1/fmu', '/px4_2/fmu', '/px4_3/fmu']
TEAM_MEMBERS = {'red': [0, 1], 'blue': [2, 3]}
CAPTURE_RADIUS = 15.0
TIME_LIMIT_S = 300.0
SAFE_ZONE_CENTER = (80.0, 80.0)
SAFE_ZONE_RADIUS = 15.0


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class RefereeNode(Node):

    def __init__(self):
        super().__init__('referee_node')

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

        self._situation_pub = self.create_publisher(String, '/battle/situation', 10)
        self._timer = self.create_timer(1.0, self._evaluate)
        self._log_file = f'/tmp/referee_{int(time.time())}.jsonl'

        self._battle_start = None
        self._game_over = False
        self._tick_count = 0

        self.get_logger().info(
            '裁判就绪 | 捕获半径=%.0fm 时限=%.0fs 安全区=(%.0f,%.0f) r=%.0f'
            % (CAPTURE_RADIUS, TIME_LIMIT_S, SAFE_ZONE_CENTER[0],
               SAFE_ZONE_CENTER[1], SAFE_ZONE_RADIUS))

    def _on_position(self, idx, msg):
        self._positions[idx] = [msg.y, msg.x, -msg.z]
        self._pos_received[idx] = True
        if self._battle_start is None and all(self._pos_received):
            self._battle_start = time.time()
            self.get_logger().info('全部 4 机位置就绪，对抗计时开始')

    def _log(self, event, **kw):
        rec = {'t': round(time.time(), 3), 'event': event}
        rec.update(kw)
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def _evaluate(self):
        if self._game_over or self._battle_start is None:
            return
        self._tick_count += 1
        elapsed = time.time() - self._battle_start

        red = [self._positions[i] for i in TEAM_MEMBERS['red']]
        blue = [self._positions[i] for i in TEAM_MEMBERS['blue']]
        min_dist = min(dist2d(r[:2], b[:2]) for r in red for b in blue)

        # 蓝队是否到达安全区
        blue_at_safe = all(
            dist2d(b[:2], SAFE_ZONE_CENTER) < SAFE_ZONE_RADIUS for b in blue)

        # 判定胜负
        if min_dist < CAPTURE_RADIUS:
            self._end_game('red_wins', f'capture at {min_dist:.1f}m')
            return
        if elapsed > TIME_LIMIT_S:
            self._end_game('blue_wins', f'timeout {elapsed:.0f}s')
            return
        if blue_at_safe:
            self._end_game('blue_wins', 'blue reached safe zone')
            return

        # 生成交战态势（自然语言，供相位生成器消费）
        situation = (
            f"battle ongoing: red team at "
            f"({red[0][0]:.0f},{red[0][1]:.0f}) and ({red[1][0]:.0f},{red[1][1]:.0f}), "
            f"blue team at "
            f"({blue[0][0]:.0f},{blue[0][1]:.0f}) and ({blue[1][0]:.0f},{blue[1][1]:.0f}), "
            f"nearest distance {min_dist:.0f}m, "
            f"elapsed {elapsed:.0f}s"
        )
        msg = String()
        msg.data = situation
        self._situation_pub.publish(msg)

        if self._tick_count % 10 == 0:
            self.get_logger().info(
                '[裁判] %.0fs | 最近距离 %.0fm | 蓝→安全区 %.0fm'
                % (elapsed, min_dist,
                   min(dist2d(b[:2], SAFE_ZONE_CENTER) for b in blue)))
            self._log('tick', elapsed=round(elapsed, 1),
                      min_dist=round(min_dist, 1),
                      red_pos=[[round(v, 1) for v in p] for p in red],
                      blue_pos=[[round(v, 1) for v in p] for p in blue])

    def _end_game(self, result, reason):
        self._game_over = True
        self.get_logger().info('=== 对抗结束: %s (%s) ===' % (result, reason))
        self._log('game_over', result=result, reason=reason)
        # 发布最终态势
        msg = String()
        msg.data = f'game over: {result}, {reason}'
        self._situation_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RefereeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
