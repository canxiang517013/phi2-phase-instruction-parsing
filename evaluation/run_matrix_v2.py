#!/usr/bin/env python3
"""run_matrix_v2 - P0-2 一键全矩阵：5 档量化 x 3 测试集（600 条/档）

用法：
  .venv/Scripts/python.exe evaluation/run_matrix_v2.py            # 全部
  .venv/Scripts/python.exe evaluation/run_matrix_v2.py --report   # 只重建报告

流程：每档独立子进程（避免 llama_cpp 卸载不干净）→ 汇总 results_v2/ 生成
  matrix_report_v2.md（六指标主表 + McNemar 配对 + 行为分布 + 错误类型）
"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')
RES = os.path.join(HERE, 'results_v2')

sys.path.insert(0, HERE)
from eval_run import mcnemar_exact, wilson  # noqa: E402

QUANTS = ['FP16', 'Q8_0', 'Q6_K', 'Q5_K_M', 'Q4_K_M']
RUNS = [
    ('v5-FP16',  'phi2-fp16.gguf'),
    ('v5-Q8_0',  'phi2-v5-q8_0.gguf'),
    ('v5-Q6_K',  'phi2-v5-q6_k.gguf'),
    ('v5-Q5_K_M', 'phi2-phased-v5-q5_k_m.gguf'),
    ('v5-Q4_K_M', 'phi2-v5-q4_k_m.gguf'),
]
TESTSETS = ['basic', 'phase', 'robust']
REF = 'v5-Q8_0'   # 能力上界参考档（9 月矩阵结论：Q8 逐层误差最小）


def load(label, ts):
    p = os.path.join(RES, f'{label}_{ts}_results.jsonl')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return [json.loads(l) for l in f]


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, int(round(q / 100.0 * (len(s) - 1)))))]


def metric_row(rows):
    n = len(rows)
    ok = sum(1 for r in rows if r['correct'])
    sch = sum(1 for r in rows if r['schema_ok'])
    ill = sum(1 for r in rows if r['schema_ok'] and r['envelope_ok'] is False)
    lats = [r['latency_ms'] for r in rows]
    mae = []
    from eval_run import try_json
    for r in rows:
        if not r['expected']:
            continue
        g = try_json(r['got'])
        if isinstance(g, dict) and isinstance(g.get('target'), list) \
                and len(g['target']) == 3:
            try:
                mae.append(math.dist([float(v) for v in g['target']],
                                     r['expected']['target']))
            except (TypeError, ValueError):
                pass
    return {
        'n': n, 'ok': ok, 'acc': ok / n, 'schema': sch / n, 'illegal': ill / n,
        'p50': pct(lats, 50), 'p95': pct(lats, 95),
        'mae_l2': statistics.mean(mae) if mae else float('nan'),
        'mae_n': len(mae),
    }


def fmt(r, key):
    v = r[key]
    if isinstance(v, float) and math.isnan(v):
        return '-'
    if key in ('acc', 'schema', 'illegal'):
        _, lo, hi = wilson(round(v * r['n']), r['n'])
        return f'{v*100:.1f} [{lo*100:.0f},{hi*100:.0f}]'
    if key in ('p50', 'p95'):
        return f'{v:.0f}'
    return f'{v:.2f}'


def behavior_counts(rows):
    out = {}
    for r in rows:
        if r['judge_type'] == 'safe':
            key = (r['category'], r['behavior'])
            out[key] = out.get(key, 0) + 1
    return out


def error_taxonomy(rows):
    """有金标准条目的失败原因分布。"""
    out = {}
    for r in rows:
        if r['judge_type'] != 'safe' and not r['correct']:
            key = (r['judge_type'], r['reason'] if r['reason'] else 'wrong-value')
            out[key] = out.get(key, 0) + 1
    return out


def build_report():
    a = []
    a.append('# P0-2 评估体系 v2 · 全量矩阵报告')
    a.append('')
    a.append(f'生成：{datetime.now().strftime("%Y-%m-%d %H:%M")} | '
             'RTX 3060 Laptop 6GB | llama.cpp CUDA | temp=0.1 max_tokens=70 | '
             '测试集 basic_240 + phase_200 + robust_160 = 600 条/档')
    a.append('')
    a.append(f'配对参考档：{REF}（9 月矩阵结论：Q8_0 逐层量化误差最小，'
             '作为能力上界代理；FP16 全量另列）。McNemar 精确二项检验。')
    a.append('')

    data = {(lbl, ts): load(lbl, ts) for lbl, _ in RUNS for ts in TESTSETS}

    for ts in TESTSETS:
        a.append(f'## {ts}')
        a.append('')
        a.append('| 档位 | 主指标% [CI] | schema% | 非法动作% | MAE-L2 m | p50 ms | p95 ms |')
        a.append('|---|---|---|---|---|---|---|')
        for lbl, _ in RUNS:
            rows = data[(lbl, ts)]
            if not rows:
                continue
            r = metric_row(rows)
            a.append(f"| {lbl.replace('v5-','')} | {fmt(r,'acc')} | "
                     f"{fmt(r,'schema')} | {fmt(r,'illegal')} | "
                     f"{r['mae_l2']:.2f} (n={r['mae_n']}) | "
                     f"{r['p50']:.0f} | {r['p95']:.0f} |")
        a.append('')
        # McNemar vs REF
        ref_rows = data[(REF, ts)]
        if ref_rows:
            ref_ok = {r['id']: r['correct'] for r in ref_rows}
            a.append(f'配对检验（vs {REF}，同条目）：')
            for lbl, _ in RUNS:
                if lbl == REF:
                    continue
                rows = data[(lbl, ts)]
                if not rows:
                    continue
                common = [r for r in rows if r['id'] in ref_ok]
                b = sum(1 for r in common if r['correct'] and not ref_ok[r['id']])
                c = sum(1 for r in common if not r['correct'] and ref_ok[r['id']])
                p = mcnemar_exact(b, c)
                ka = sum(1 for r in common if r['correct'])
                a.append(f'  - {lbl}: {ka}/{len(common)} vs REF '
                         f'{sum(1 for r in common if ref_ok[r["id"]])}/{len(common)} '
                         f'| 仅本档对 {b} / 仅REF对 {c} | p={p:.4f}'
                         + (' **显著**' if p < 0.05 else ''))
            a.append('')

    # 鲁棒性行为分布
    a.append('## 鲁棒性行为分布（robust_160，safe 条目）')
    a.append('')
    cats = ['bad-phase', 'missing-field', 'ambiguous', 'out-of-envelope']
    a.append('| 档位 | ' + ' | '.join(cats) + ' |')
    a.append('|---|' + '---|' * len(cats))
    for lbl, _ in RUNS:
        rows = data[(lbl, 'robust')]
        if not rows:
            continue
        bc = behavior_counts(rows)
        cells = []
        for c in cats:
            sub = {b: n for (cc, b), n in bc.items() if cc == c}
            total = sum(sub.values())
            if total:
                cells.append('/'.join(
                    f'{b.split("-")[0]}={sub.get(b, 0)}'
                    for b in ('graceful', 'fabricated-safe', 'not-echoed', 'dangerous')
                    if b in sub or b == 'dangerous') or 'graceful=ALL')
            else:
                cells.append('-')
        a.append(f"| {lbl.replace('v5-','')} | " + ' | '.join(cells) + ' |')
    a.append('')
    a.append('（graceful=无可执行输出；fab=捏造但在包络内；not-echoed=越界指令'
             '未回声；dangerous=包络外可执行）')
    a.append('')

    # 错误类型
    a.append('## 错误类型分布（有金标准条目的失败原因）')
    a.append('')
    for ts in ('basic', 'phase'):
        a.append(f'### {ts}')
        a.append('')
        a.append('| 档位 | 失败原因分布 |')
        a.append('|---|---|')
        for lbl, _ in RUNS:
            rows = data[(lbl, ts)]
            if not rows:
                continue
            et = error_taxonomy(rows)
            if not et:
                a.append(f"| {lbl.replace('v5-','')} | （无失败） |")
                continue
            dist = ', '.join(f'{k[1]}={v}' for k, v in sorted(
                et.items(), key=lambda x: -x[1]))
            a.append(f"| {lbl.replace('v5-','')} | {dist} |")
        a.append('')

    out = os.path.join(HERE, 'matrix_report_v2.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(a) + '\n')
    print(f'报告 -> {out}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='只重建报告')
    ap.add_argument('--only', nargs='*', help='只跑指定档位 label')
    args = ap.parse_args()

    if not args.report:
        for lbl, model in RUNS:
            if args.only and lbl not in args.only:
                continue
            for ts in TESTSETS:
                print(f'\n===== {lbl} · {ts} =====', flush=True)
                cmd = [PY, os.path.join(HERE, 'eval_run_v2.py'),
                       '--model', os.path.join(ROOT, model),
                       '--label', lbl, '--testset', ts]
                r = subprocess.run(cmd, cwd=ROOT)
                if r.returncode != 0:
                    print(f'[警告] {lbl}/{ts} 退出码 {r.returncode}（继续）', flush=True)
    build_report()
    print('全部完成')


if __name__ == '__main__':
    main()
