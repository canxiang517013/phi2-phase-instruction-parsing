#!/usr/bin/env python3
"""referee_3v3 - 3v3 对抗裁判（六机同步+实时评分+多条件胜负）

评分体系：
  红队：捕获蓝机 +10/机，蓝队全灭 +20 额外
  蓝队：到达安全区 +5/机，全部到达 +10 额外，存活到超时 +15
  惩罚：红机出禁区 -5，碰撞 -10
"""
import json
import math
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
from std_msgs.msg import String
from px4_msgs.msg import VehicleLocalPosition

N_DRONES = 6
DRONE_NAMESPACES = ['/fmu'] + [f'/px4_{i}/fmu' for i in range(1, N_DRONES)]
TEAM_MEMBERS = {'red': [0, 1, 2], 'blue': [3, 4, 5]}

DRONE_WORLD_OFFSETS = {
    0: (0.0, 0.0),     1: (5.0, 0.0),     2: (-5.0, 0.0),
    3: (60.0, 60.0),   4: (65.0, 60.0),   5: (55.0, 60.0),
}

CAPTURE_RADIUS = 15.0
TIME_LIMIT_S = 300.0
GRACE_PERIOD_S = 15.0
SAFE_ZONE_CENTER = (85.0, 85.0)
SAFE_ZONE_RADIUS = 12.0
ARENA_BOUNDARY = 200.0


def dist2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Referee3v3(Node):

    def __init__(self):
        super().__init__('referee_3v3')

        px4_qos = QoSProfile(
            depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self._positions = [[0.0, 0.0, 0.0]] * N_DRONES
        self._alive = [True] * N_DRONES
        self._captured = set()
        self._safe_arrived = set()
        self._pos_received = [False] * N_DRONES

        for i, ns in enumerate(DRONE_NAMESPACES):
            self.create_subscription(
                VehicleLocalPosition, f'{ns}/out/vehicle_local_position',
                lambda msg, idx=i: self._on_position(idx, msg), px4_qos)

        self._situation_pub = self.create_publisher(String, '/battle/situation', 10)
        self._score_pub = self.create_publisher(String, '/battle/score', 10)
        self._timer = self.create_timer(1.0, self._evaluate)
        self._log_file = f'/tmp/referee_3v3_{int(time.time())}.jsonl'

        self._battle_start = None
        self._game_over = False
        self._tick = 0
        self.score = {'red': 0.0, 'blue': 0.0, 'captures': 0, 'escapes': 0}

        self.get_logger().info(
            '3v3 裁判就绪 | 捕获=%.0fm 时限=%.0fs 安全区=(%.0f,%.0f) r=%.0f'
            % (CAPTURE_RADIUS, TIME_LIMIT_S, SAFE_ZONE_CENTER[0],
               SAFE_ZONE_CENTER[1], SAFE_ZONE_RADIUS))

    def _on_position(self, idx, msg):
        local_enu = [msg.y, msg.x, -msg.z]
        offset = DRONE_WORLD_OFFSETS[idx]
        self._positions[idx] = [
            local_enu[0] + offset[0], local_enu[1] + offset[1], local_enu[2]]
        self._pos_received[idx] = True
        if self._battle_start is None and all(self._pos_received):
            blue_centroid = self._team_centroid('blue')
            if dist2d(blue_centroid[:2], (60, 60)) < 30:
                self._battle_start = time.time()
                self.get_logger().info('六机位置就绪（蓝队在 (%.0f,%.0f)），对抗开始'
                                       % (blue_centroid[0], blue_centroid[1]))
            else:
                for i in range(N_DRONES):
                    self._pos_received[i] = False

    def _team_centroid(self, team):
        members = [i for i in TEAM_MEMBERS[team] if self._alive[i]]
        if not members:
            members = TEAM_MEMBERS[team]
        positions = [self._positions[i] for i in members]
        return [sum(p[d] for p in positions) / len(positions) for d in range(3)]

    def _log(self, event, **kw):
        rec = {'t': round(time.time(), 3), 'event': event}
        rec.update(kw)
        with open(self._log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def _evaluate(self):
        if self._game_over or self._battle_start is None:
            return
        self._tick += 1
        elapsed = time.time() - self._battle_start

        if elapsed < GRACE_PERIOD_S:
            if self._tick % 5 == 0:
                self.get_logger().info('[宽限期] %.0fs/%.0fs' % (elapsed, GRACE_PERIOD_S))
            return

        alive_red = [i for i in TEAM_MEMBERS['red'] if self._alive[i]]
        alive_blue = [i for i in TEAM_MEMBERS['blue'] if self._alive[i]]

        # 1. 捕获判定
        for r in alive_red:
            for b in alive_blue:
                if b in self._captured:
                    continue
                d = dist2d(self._positions[r][:2], self._positions[b][:2])
                if d < CAPTURE_RADIUS:
                    self._captured.add(b)
                    self._alive[b] = False
                    self.score['red'] += 10
                    self.score['captures'] += 1
                    self.get_logger().info(
                        '[捕获] Red_%d 捕获 Blue_%d（%.1fm）红队 +10' %
                        (r % 3 + 1, b % 3 + 1, d))
                    self._log('capture', red=r, blue=b, distance=round(d, 1))

        # 2. 安全区判定
        for b in alive_blue:
            if b in self._safe_arrived:
                continue
            d = dist2d(self._positions[b][:2], SAFE_ZONE_CENTER)
            if d < SAFE_ZONE_RADIUS:
                self._safe_arrived.add(b)
                self.score['blue'] += 5
                self.score['escapes'] += 1
                self.get_logger().info(
                    '[安全] Blue_%d 到达安全区 蓝队 +5' % (b % 3 + 1))

        # 3. 胜负判定
        if not alive_blue:
            self.score['red'] += 20
            self._end('red_wins', 'all blue captured', elapsed)
            return
        if len(self._safe_arrived) == len(alive_blue) and alive_blue:
            self.score['blue'] += 10
            self._end('blue_wins', 'all surviving blue at safe zone', elapsed)
            return
        if elapsed > TIME_LIMIT_S:
            self.score['blue'] += 15
            self._end('blue_wins', 'timeout with survivors', elapsed)
            return

        # 4. 发布态势
        min_dist = min(
            dist2d(self._positions[r][:2], self._positions[b][:2])
            for r in alive_red for b in alive_blue) if alive_red and alive_blue else 999
        situation = (
            f"battle: red({len(alive_red)} alive) vs blue({len(alive_blue)} alive), "
            f"nearest {min_dist:.0f}m, "
            f"elapsed {elapsed:.0f}s, score R{self.score['red']:.0f}/B{self.score['blue']:.0f}")
        self._situation_pub.publish(String(data=situation))
        self._score_pub.publish(String(data=json.dumps(self.score)))

        if self._tick % 10 == 0:
            self.get_logger().info(
                '[裁判] %.0fs | 存活 R%d/B%d | 最近 %.0fm | 比分 R%.0f/B%.0f'
                % (elapsed, len(alive_red), len(alive_blue), min_dist,
                   self.score['red'], self.score['blue']))
            self._log('tick', elapsed=round(elapsed, 1), min_dist=round(min_dist, 1),
                      alive_red=len(alive_red), alive_blue=len(alive_blue),
                      score=dict(self.score))

    def _end(self, result, reason, elapsed):
        self._game_over = True
        self.get_logger().info(
            '=== 对抗结束: %s (%s) | %.0fs | 最终比分 R%.0f/B%.0f ==='
            % (result, reason, elapsed, self.score['red'], self.score['blue']))
        self._log('game_over', result=result, reason=reason,
                  elapsed=round(elapsed, 1), score=dict(self.score))
        self._situation_pub.publish(
            String(data=f'game over: {result}, {reason}'))


def main(args=None):
    rclpy.init(args=args)
    node = Referee3v3()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
