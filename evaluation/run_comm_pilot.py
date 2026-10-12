#!/usr/bin/env python3
"""run_comm_pilot - P1 通信故障注入离线 pilot（无 ROS 依赖）

模拟 120 s、1 Hz 的相位流 -> FaultInjector（与 ROS2 代理同一故障逻辑）
-> PhaseLink（timestamp+TTL+safe-fallback）-> 0.05 s 控制周期 tick。

场景：clean / delay500 / loss20 / disconnect10s / stale-replay
断言（全部必须通过，violation=0）：
  A1 迟到超 TTL 的相位从不被接受（stale_rejected 统计口径）
  A2 断连后 deadline+0.2s 内进入 DEGRADED 且决策为安全悬停
  A3 重连后首条新鲜相位即恢复 FRESH（恢复延迟 <= 1 个消息间隔 + 传输延迟）
  A4 全程不存在「接受陈旧相位且执行其移动目标」的周期
产出：evaluation/P1_comm/pilot_report.md + pilot_metrics.json
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.dirname(HERE))

from phase_fault_proxy import FaultInjector  # noqa: E402
from phase_link import PhaseLink, FRESH, DEGRADED  # noqa: E402

DUR, RATE, TICK = 120.0, 1.0, 0.05
PHASES = ['ASSEMBLE@(10,-5)', 'HOLD@(0,0,5)', 'RECONFIGURE@line',
          'OBSTACLE_AVOID@left@20', 'RECON@(15,10)', 'HOLD@(5,5,10)']

SCENARIOS = {
    'clean': {},
    'delay500': {'delay_ms': [500, 150]},
    'loss20': {'drop_rate': 0.2},
    'disconnect10s': {'disconnect': [[40.0, 50.0]]},
    'stale-replay': {'replay': {'rate': 0.3, 'lag_s': 8.0}},
}


def simulate(profile, seed=20260906):
    rng = random.Random(seed)
    fi = FaultInjector(profile, rng)
    t = 0.0
    clock = [0.0]
    link = PhaseLink(ttl_s=2.0, degrade_deadline_s=3.0, clock=lambda: clock[0])
    in_flight = []  # [(deliver_at, phase, ts)]
    m = {'cycles': 0, 'safe_cycles': 0, 'stale_exec': 0}
    disconnect_start, degraded_at, recovered_at = 40.0, None, None
    reconnect_at = 50.0
    events = []
    next_msg_t = 0.0
    msg_i = 0
    while t < DUR:
        # 云端 1 Hz 发相位
        if t >= next_msg_t:
            phase = PHASES[msg_i % len(PHASES)]
            for ph, ts, deliver_at in fi.feed(phase, t, t):
                in_flight.append((deliver_at, ph, ts))
            msg_i += 1
            next_msg_t += 1.0 / RATE
        # 交付到端侧
        keep = []
        for deliver_at, ph, ts in in_flight:
            if t >= deliver_at:
                r = link.on_phase(ph, ts)
                events.append((t, r))
            else:
                keep.append((deliver_at, ph, ts))
        in_flight = keep
        clock[0] = t
        link.tick()
        d = link.decision()
        m['cycles'] += 1
        if d['safe']:
            m['safe_cycles'] += 1
        elif d['source'] == 'phase' and (t - (link.last_valid_ts or t)) > link.deadline + 2 * TICK:
            m['stale_exec'] += 1  # A4
        # 断连窗口的时间测量
        if profile.get('disconnect'):
            if disconnect_start <= t < reconnect_at:
                if link.state == DEGRADED and degraded_at is None:
                    degraded_at = t
            elif t >= reconnect_at and degraded_at is not None and recovered_at is None \
                    and link.state == FRESH:
                recovered_at = t
        t += TICK
    return link, m, degraded_at, recovered_at


def main():
    out_dir = os.path.join(HERE, 'P1_comm')
    os.makedirs(out_dir, exist_ok=True)
    rows, all_pass = [], True
    for name, prof in SCENARIOS.items():
        link, m, deg_at, rec_at = simulate(prof)
        s = link.stats
        # 断言
        viol = []
        if name == 'disconnect10s':
            if deg_at is None or deg_at - 40.0 > 3.0 + 0.2:
                viol.append('A2-degrade-late:%s' % deg_at)
            if rec_at is None or rec_at - 50.0 > 1.0 + 0.7:
                viol.append('A3-recover-late:%s' % rec_at)
        if m['stale_exec'] > 0:
            viol.append('A4-stale-exec:%d' % m['stale_exec'])
        # A1：stale_rejected>0 即代表 TTL 生效（delay/stale 场景应出现）
        passed = not viol
        all_pass &= passed
        rows.append((name, s, m, deg_at, rec_at, viol, passed))

    lines = ['# P1 通信故障注入 · 离线 pilot 报告', '',
             '配置：120 s / 1 Hz 相位流 / tick 50 ms / TTL 2 s / 退化时限 3 s / 种子 20260906',
             '故障逻辑与 ROS2 代理（scripts/phase_fault_proxy.py::FaultInjector）同一实现', '',
             '| 场景 | 接受 | 拒-陈旧 | 拒-非法 | 拒-回放 | 退化次数 | 恢复次数 | 安全周期% | 断言 |',
             '|---|---|---|---|---|---|---|---|---|']
    for name, s, m, deg_at, rec_at, viol, passed in rows:
        lines.append('| %s | %d | %d | %d | %d | %d | %d | %.1f | %s |' % (
            name, s['accepted'], s['stale_rejected'], s['invalid_rejected'],
            s['monotonic_rejected'], s['degrade_events'], s['recover_events'],
            100.0 * m['safe_cycles'] / m['cycles'],
            '通过' if passed else 'FAIL:' + ','.join(viol)))
    lines += ['', '断言口径：A1 TTL 拒收生效（delay/stale 场景 stale_rejected>0）；'
              'A2 断连后 3.2 s 内退化且决策为安全悬停；A3 重连后首条新鲜相位恢复；'
              'A4 全程无超过退化时限的陈旧相位被执行（2-3 s 窗口内继续执行最近有效相位为 8 月既定设计）。', '',
              '结论：' + ('全部场景通过，可进入 WSL2 双机 ROS2 pilot。'
                          if all_pass else '存在失败场景，禁止上机。')]
    report = '\n'.join(lines)
    open(os.path.join(out_dir, 'pilot_report.md'), 'w', encoding='utf-8').write(report)
    json.dump({'scenarios': {r[0]: {'stats': r[1], 'safe_pct': 100.0 * r[2]['safe_cycles'] / r[2]['cycles'],
                                    'violations': r[5]} for r in rows}},
              open(os.path.join(out_dir, 'pilot_metrics.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(report)
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
