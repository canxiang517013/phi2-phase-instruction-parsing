#!/usr/bin/env python3
"""phase_fault_proxy - 云-边相位信道的故障注入代理（P1，ROS2 双机用）

位于 cloud_phase_generator 与 nl_command_node 之间：
  订阅 /phase_signal -> 按 profile 注入故障 -> 加发送端时间戳 -> 发布 /phase_signal_fi

故障 profile（JSON 配置，--profile 指定）：
  delay_ms:   [mean, sigma] 高斯延迟（截断到 >=0）
  drop_rate:  0..1 随机丢包
  disconnect: [[start_s, end_s], ...] 从代理启动起算的断连窗口（窗口内全部丢弃）
  replay:     {rate: 0..1, lag_s: N} 以 rate 概率把 lag_s 秒前的旧消息重发
              （制造"旧 phase 比没有 phase 更危险"场景）

FaultInjector 类不依赖 ROS（离线 pilot 复用同一故障逻辑，保证离线/在线一致）。
实际 ROS2 用法（WSL2）：
  python3 phase_fault_proxy.py --profile fi_delay500.json --in /phase_signal --out /phase_signal_fi
"""

import argparse
import json
import random
import time


class FaultInjector:
    """纯 Python 故障注入器：feed(phase, ts) -> list[(phase, ts)]（0..2 条输出）。"""

    def __init__(self, profile, rng=None):
        p = profile or {}
        d = p.get('delay_ms', [0, 0])
        self.delay_mean, self.delay_sigma = float(d[0]), float(d[1])
        self.drop_rate = float(p.get('drop_rate', 0.0))
        self.disconnect_windows = [(float(a), float(b)) for a, b in p.get('disconnect', [])]
        self.replay = p.get('replay', {'rate': 0.0, 'lag_s': 0.0})
        self.rng = rng or random.Random(20260906)
        self.history = []  # [(arrival_ts, phase, ts)]
        self.t0 = None

    def _in_disconnect(self, now):
        if self.t0 is None:
            self.t0 = now
        return any(a <= now - self.t0 <= b for a, b in self.disconnect_windows)

    def feed(self, phase, ts, now=None):
        """返回此刻应交付端侧的消息列表（已含延迟后的投递时刻语义由调用方调度）。"""
        now = time.monotonic() if now is None else now
        self.history.append((now, phase, ts))
        out = []
        if self._in_disconnect(now):
            return out
        if self.rng.random() < self.drop_rate:
            return out
        delay = max(0.0, self.rng.gauss(self.delay_mean, self.delay_sigma)) / 1000.0
        out.append((phase, ts, now + delay))
        if self.rng.random() < float(self.replay.get('rate', 0.0)):
            lag = float(self.replay.get('lag_s', 0.0))
            old = [(a, p, t) for a, p, t in self.history if now - a >= lag]
            if old:
                a, p, t = self.rng.choice(old)
                out.append((p, t, now + delay))  # 旧时间戳原样重发
        return out


def main():
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String
    except ImportError:
        print('rclpy 不可用：请在 WSL2 ROS2 环境运行，或先用离线 pilot'
              '（evaluation/run_comm_pilot.py）验证故障逻辑')
        raise SystemExit(2)

    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', required=True)
    ap.add_argument('--in', dest='intopic', default='/phase_signal')
    ap.add_argument('--out', dest='outtopic', default='/phase_signal_fi')
    args = ap.parse_args()
    profile = json.load(open(args.profile, encoding='utf-8'))
    fi = FaultInjector(profile)

    class Proxy(Node):
        def __init__(self):
            super().__init__('phase_fault_proxy')
            self.pub = self.create_publisher(String, args.outtopic, 10)
            self.sub = self.create_subscription(
                String, args.intopic, self.on_msg, 10)
            self.pending = []  # [(deliver_at, phase, ts)]
            self.tm = self.create_timer(0.02, self.pump)
            self.get_logger().info('fault proxy: %s' % json.dumps(profile))

        def on_msg(self, msg):
            now = time.time()
            for phase, ts, deliver_at in fi.feed(msg.data, now, now):
                self.pending.append((deliver_at, phase, ts))

        def pump(self):
            now = time.time()
            keep = []
            for deliver_at, phase, ts in self.pending:
                if now >= deliver_at:
                    m = String()
                    m.data = '%s|%s' % (phase, ts)
                    self.pub.publish(m)
                else:
                    keep.append((deliver_at, phase, ts))
            self.pending = keep

    rclpy.init()
    rclpy.spin(Proxy())


if __name__ == '__main__':
    main()
