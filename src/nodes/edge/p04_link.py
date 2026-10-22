#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""p04_link - 心跳+相位双通道链路状态机（从 nl_command_node 提取的公共实现）

- 心跳（/cloud/heartbeat, 1Hz）：链路层新鲜度；断流 >3s → DEGRADED
- 相位（/cloud/phase, 低频重发）：内容通道；stamp 超 TTL 2s 拒收（stale）、
  非单调拒收（重放防御）、非法语法拒收
- DEGRADED 决策 = 相位无关安全悬停；不重放缓存的移动相位

纯 stdlib + phase_rules，供 mission_commander / mappo_policy_node 复用；
nl_command_node 内仍保留一份同构实现（已验证，不动）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from uav_adversarial.common.phase_rules import validate_phase
except ImportError:
    from phase_rules import validate_phase  # type: ignore

FRESH, DEGRADED = 'FRESH', 'DEGRADED'
LINK_TTL_S = 2.0          # 相位消息 stamp 陈旧阈值
DEGRADE_DEADLINE_S = 3.0  # 心跳+相位全无新鲜信号的退化时限


class P04Link:
    """on_heartbeat / on_phase 收消息，tick(now) 每控制周期驱动。"""

    def __init__(self, node_logger):
        self._log = node_logger
        self.state = DEGRADED
        self.phase = None
        self.last_phase_stamp = 0.0
        self._fresh_ts = 0.0
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
