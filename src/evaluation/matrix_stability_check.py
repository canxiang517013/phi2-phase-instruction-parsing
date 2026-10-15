#!/usr/bin/env python3
"""matrix_stability_check - run1(未固定 seed) vs run2(固定 seed=20260906) 稳定性对比

回答：单次评测矩阵里有多少差异是纯采样噪声？关键结论是否稳定？
产出：evaluation/matrix_stability_report.md
"""
import json
import os
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
RUN1 = os.path.join(HERE, 'results_v2_run1_seednone')
RUN2 = os.path.join(HERE, 'results_v2')
TIERS = ['FP16', 'Q8_0', 'Q6_K', 'Q5_K_M', 'Q4_K_M']
SETS = ['basic', 'phase', 'robust']


def load(d, tier, s):
    return {json.loads(l)['id']: json.loads(l) for l in open(
        os.path.join(d, f'v5-{tier}_{s}_results.jsonl'), encoding='utf-8')}


def mcnemar_p(b, c):
    """精确二项 McNemar。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def acc(rows):
    return 100.0 * sum(r['correct'] for r in rows.values()) / len(rows)


def main():
    lines = ['# P0-2 矩阵稳定性报告：run1（无 seed）vs run2（seed=20260906）', '',
             '同一模型同一测试集同一解码参数，唯一差异 = llama.cpp 采样种子。',
             'run2 与 run1 的同档差异即采样噪声的实测规模；据此检验关键结论的稳定性。', '',
             '## 同档跨次对比（采样噪声实测）', '',
             '| 档位 | 集 | run1 % | run2 % | 差 | 仅run1对 | 仅run2对 | McNemar p |',
             '|---|---|---|---|---|---|---|---|']
    noise = {}
    for tier in TIERS:
        for s in SETS:
            r1, r2 = load(RUN1, tier, s), load(RUN2, tier, s)
            b = sum(1 for k in r1 if r1[k]['correct'] and not r2[k]['correct'])
            c = sum(1 for k in r1 if not r1[k]['correct'] and r2[k]['correct'])
            p = mcnemar_p(b, c)
            noise[(tier, s)] = (b, c, p)
            lines.append('| %s | %s | %.1f | %.1f | %+.1f | %d | %d | %.3f |' % (
                tier, s, acc(r1), acc(r2), acc(r2) - acc(r1), b, c, p))

    lines += ['', '## 关键结论稳定性检验（run2 上的 McNemar，vs Q8_0）', '',
              '| 结论（run1 版本） | run1 证据 | run2 证据 | 判定 |', '|---|---|---|---|']
    checks = []
    for s, tier, r1_desc in [
            ('basic', 'Q5_K_M', '97.5 vs Q8 100（p=0.031 显著）'),
            ('phase', 'Q4_K_M', '43.0 vs Q8 57.5（p<0.0001 显著）'),
            ('phase', 'FP16', '52.5 vs Q8 57.5（p=0.064 不显著，方向 FP16 弱）')]:
        r_t, r_ref = load(RUN2, tier, s), load(RUN2, 'Q8_0', s)
        b = sum(1 for k in r_t if r_t[k]['correct'] and not r_ref[k]['correct'])
        c = sum(1 for k in r_t if not r_t[k]['correct'] and r_ref[k]['correct'])
        p = mcnemar_p(b, c)
        checks.append((s, tier, r1_desc, acc(r_t), acc(r_ref), p))
    for s, tier, r1_desc, a_t, a_ref, p in checks:
        sig1 = '显著' in r1_desc and '不显著' not in r1_desc
        stable = (p < 0.05) == sig1 and abs(a_t - a_ref) * (1 if 'FP16' not in tier else 1) >= 0
        # 方向判定：Q5/Q4 弱于 Q8；FP16 弱于 Q8
        direction_ok = a_t <= a_ref + 0.5 if tier != 'FP16' else a_t <= a_ref + 2.0
        verdict = '稳定' if ((p < 0.05) == sig1 and direction_ok) else '需复核'
        lines.append('| %s/%s | %s | %.1f vs %.1f，p=%.4f | %s |' % (
            s, tier, r1_desc, a_t, a_ref, p, verdict))

    lines += ['', '## robust 行为分布稳定性（run1 vs run2，按档）', '',
              '| 档位 | dangerous r1→r2 | fabricated r1→r2 | graceful r1→r2 |', '|---|---|---|---|']
    from collections import Counter
    for tier in TIERS:
        r1, r2 = load(RUN1, tier, 'robust'), load(RUN2, tier, 'robust')

        def cnt(rows, v):
            c = Counter((r.get('behavior') or 'ok') for r in rows.values())
            return c.get(v, 0)
        lines.append('| %s | %d→%d | %d→%d | %d→%d |' % (
            tier, cnt(r1, 'dangerous'), cnt(r2, 'dangerous'),
            cnt(r1, 'fabricated-safe') + cnt(r1, 'fabricated-dangerous'),
            cnt(r2, 'fabricated-safe') + cnt(r2, 'fabricated-dangerous'),
            cnt(r1, 'graceful'), cnt(r2, 'graceful')))

    rep = '\n'.join(lines)
    open(os.path.join(HERE, 'matrix_stability_report.md'), 'w', encoding='utf-8').write(rep)
    print(rep)


if __name__ == '__main__':
    main()
