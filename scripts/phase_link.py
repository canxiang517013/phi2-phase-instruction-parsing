#!/usr/bin/env python3
"""phase_link - 相位链路的 timestamp+TTL+safe-fallback 状态机（P1 通信鲁棒性核心）

部署位置：端侧 nl_command_node 内（每控制周期 tick 一次）。
设计要点（对应任务书知识点"为什么旧 phase 可能比没有 phase 更危险"）：
  - 每条相位消息带发送端时间戳；超过 TTL 的消息即使迟到也拒绝（旧相位语义
    可能已失效，执行它比重悬停更危险）
  - 超过退化时限仍无新鲜相位 -> DEGRADED：回退到与相位无关的安全悬停，
    而不是继续执行缓存的移动相位
  - 心跳恢复后重新对齐（收到新鲜合法相位即恢复 FRESH）

纯 stdlib，无 ROS 依赖；自检：python phase_link.py --selftest
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase_rules import DEFAULT_PHASE, validate_phase  # noqa: E402

FRESH, DEGRADED = 'FRESH', 'DEGRADED'


class PhaseLink:
    """on_phase() 收消息，tick() 每周期驱动，decision() 给当前应执行动作。"""

    def __init__(self, ttl_s=2.0, degrade_deadline_s=3.0, clock=lambda: 0.0):
        self.ttl = float(ttl_s)
        self.deadline = float(degrade_deadline_s)
        self.clock = clock
        self.state = DEGRADED  # 启动时无相位即处于退化态（安全默认）
        self.last_valid_phase = None
        self.last_valid_ts = None
        self.last_any_ts = None
        self.degraded_since = clock()
        self.stats = {'accepted': 0, 'stale_rejected': 0, 'invalid_rejected': 0,
                      'monotonic_rejected': 0, 'degrade_events': 0, 'recover_events': 0}

    def on_phase(self, phase, ts):
        """云端相位消息到达（ts 为发送端时间戳）。返回 'accepted'|拒绝原因。"""
        now = self.clock()
        self.last_any_ts = now
        if not validate_phase(phase):
            self.stats['invalid_rejected'] += 1
            return 'invalid'
        if now - ts > self.ttl:
            self.stats['stale_rejected'] += 1
            return 'stale'  # 迟到超过 TTL：旧相位比没有相位更危险，拒收
        if self.last_valid_ts is not None and ts <= self.last_valid_ts:
            self.stats['monotonic_rejected'] += 1
            return 'non-monotonic'  # 时钟回放/重复消息
        self.last_valid_phase, self.last_valid_ts = phase, ts
        self.stats['accepted'] += 1
        if self.state == DEGRADED:
            self.stats['recover_events'] += 1
        self.state = FRESH
        return 'accepted'

    def tick(self):
        """每控制周期调用：驱动 TTL/退化状态转移。"""
        now = self.clock()
        if self.state == FRESH:
            age = now - (self.last_valid_ts if self.last_valid_ts is not None else now)
            if age > self.deadline:
                self.state = DEGRADED
                self.degraded_since = now
                self.stats['degrade_events'] += 1
        return self.state

    def decision(self):
        """当前应执行的动作：新鲜相位 或 安全悬停（相位无关，非缓存相位回放）。"""
        if self.state == FRESH and self.last_valid_phase:
            return {'source': 'phase', 'phase': self.last_valid_phase,
                    'safe': False}
        return {'source': 'safety_fallback', 'phase': DEFAULT_PHASE,
                'safe': True}


def selftest():
    t = [0.0]

    def clock():
        return t[0]
    link = PhaseLink(ttl_s=2.0, degrade_deadline_s=3.0, clock=clock)
    ok = []

    def chk(name, cond):
        ok.append(bool(cond))
        print('%s %s' % ('PASS' if cond else 'FAIL', name))

    chk('启动即退化态（安全默认）', link.decision()['safe'] is True)
    chk('新鲜相位被接受', link.on_phase('ASSEMBLE@(10,-5)', t[0]) == 'accepted')
    chk('执行该相位', link.decision() == {'source': 'phase', 'phase': 'ASSEMBLE@(10,-5)', 'safe': False})
    t[0] += 1.0
    chk('TTL 内保持 FRESH', link.tick() == FRESH)
    t[0] += 2.5  # 距上次有效相位 3.5s > 退化时限 3s
    chk('超时触发退化', link.tick() == DEGRADED)
    chk('退化后安全悬停（非缓存相位回放）', link.decision()['safe'] is True)
    t[0] += 1.0
    chk('迟到相位被拒（旧相位更危险）', link.on_phase('RECON@(5,5)', 0.0) == 'stale')
    chk('非法相位被拒', link.on_phase('OBSTACLE_AVOID@up@30', t[0]) == 'invalid')
    chk('新鲜相位触发恢复', link.on_phase('HOLD@(0,0,5)', t[0]) == 'accepted')
    chk('恢复后执行新相位', link.decision()['safe'] is False)
    chk('时钟回放被拒（TTL 内的回退时间戳）', link.on_phase('HOLD@(1,1,5)', t[0] - 1) == 'non-monotonic')
    return all(ok)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(0 if selftest() else 1)
