#!/usr/bin/env python3
"""Part 5: 困难 seed（999/31415/789）五方法原始记录深挖"""
import json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent
SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]
ALL = ["baseline", "rule_based", "uniform_matched", "phase_aware", "random_matched"]

def load(m, s):
    with (ROOT / f"results_repro/{m}_seed{s}/results.json").open(encoding="utf-8") as f:
        return json.load(f)

for seed in [999, 31415, 789]:
    print("=" * 105)
    print(f"PART 5  seed {seed} 五方法深挖")
    print("=" * 105)
    print(f"{'方法':<16} {'首次编队ep':>10} {'首次成功ep':>10} {'相位切换ep':>22} {'终局保持率%':>11} {'终局误差m':>10} {'follow_m':>9}")
    for m in ALL:
        r = load(m, seed)
        trans = [t["episode"] for t in r["phase_transitions"] if t["to"] in ("mid", "late")]
        print(f"{m:<16} {str(r['first_acquisition_episode']):>10} {str(r['first_success_episode']):>10} "
              f"{('→'.join(map(str, trans)) if trans else '-'):>22} "
              f"{r['final_follow_retention_ratio']:>11.1f} {r['final_terminal_max_target_error']:>10.2f} {r['final_follow_position_error']:>9.2f}")
    # phase_aware 的参数轨迹与干预时间线
    r = load("phase_aware", seed)
    ph = r["param_history"]
    print(f"\n  phase_aware 参数轨迹分段值（每 500 ep）:")
    for name in ["w_position", "w_formation", "w_success", "entropy_coef"]:
        vals = [ph[name][i] for i in range(0, 2500, 500)]
        print(f"    {name:<14}: " + " → ".join(f"{v:.4f}" for v in vals))
    print(f"  干预事件（episode, phase, 参数变化数）: " +
          ", ".join(f"ep{e['episode']}({e['phase']},{e['n_parameter_updates']})" for e in r["intervention_history"][:12]) +
          (" ..." if len(r["intervention_history"]) > 12 else ""))
    # 误差轨迹对比（各方法 5 段均值）
    print(f"\n  跟踪误差 500ep 分段均值（base/rule/uniform/pa/random）:")
    for i, lo in enumerate(range(0, 2500, 500)):
        row = []
        for m in ALL:
            h = load(m, seed)["follow_error_history"]
            row.append(np.mean(h[lo:lo+500]))
        print(f"    ep{lo+1:>4}-{lo+500:>4}: " + " | ".join(f"{v:>6.1f}" for v in row))
    print()
