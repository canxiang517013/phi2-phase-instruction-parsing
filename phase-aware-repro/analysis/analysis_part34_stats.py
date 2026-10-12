#!/usr/bin/env python3
"""Part 3: CI 重叠分析；Part 4: 配对统计逐条 side-by-side"""
import csv, json
import numpy as np
from pathlib import Path
from scipy import stats as st

ROOT = Path(__file__).parent
SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]
METHODS = ["baseline", "random_matched", "uniform_matched", "phase_aware"]

REF_SUM = {}
with (ROOT / "results/E1_primary/method_summary_with_ci.csv").open(encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        REF_SUM[(row["method"], row["metric"])] = row

MINE = {}
for p in ROOT.glob("results_repro/*_seed*/results.json"):
    m, s = p.parent.name.rsplit("_seed", 1)
    with p.open(encoding="utf-8") as f:
        MINE[(m, int(s))] = json.load(f)

rng = np.random.default_rng(20260725)
def boot_ci(vals, b=20000):
    arr = np.asarray(vals, float)
    idx = rng.integers(0, len(arr), size=(b, len(arr)))
    means = arr[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

def get(m, s, metric):
    v = MINE[(m, s)].get(metric)
    if metric.endswith("_episode") and v is None:
        return 2501.0
    return float(v)

print("=" * 105)
print("PART 3  关键指标的 bootstrap 95% CI 重叠检验（本机 vs 论文，逐方法）")
print("=" * 105)
for metric in ["final_success_rate", "final_follow_position_error", "final_pairwise_formation_error", "first_success_episode"]:
    print(f"\n--- {metric} ---")
    for m in METHODS:
        vals = [get(m, s, metric) for s in SEEDS]
        lo, hi = boot_ci(vals)
        r = REF_SUM.get((m, metric))
        if not r:
            continue
        rlo, rhi = float(r["ci95_low"]), float(r["ci95_high"])
        overlap = "重叠" if (lo <= rhi and rlo <= hi) else "不重叠"
        print(f"  {m:<16} 本机 [{lo:>8.2f},{hi:>8.2f}]  参考 [{rlo:>8.2f},{rhi:>8.2f}]  → {overlap}")

print()
print("=" * 105)
print("PART 4  配对统计逐条 side-by-side（reference=phase_aware，Wilcoxon 原始 p 与 Holm 后 p）")
print("=" * 105)
REF_PAIR = {}
with (ROOT / "results/E1_primary/paired_statistics.csv").open(encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        REF_PAIR[(row["metric"], row["baseline"])] = row
MINE_PAIR = {}
with (ROOT / "results_repro/statistics_e1_full/paired_statistics.csv").open(encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        MINE_PAIR[(row["metric"], row["baseline"])] = row

sig = lambda p: "**" if p < 0.05 else "  "
print(f"{'指标':<34} {'对照':<15} {'均值差(参考)':>12} {'均值差(本机)':>12} {'方向':>4} {'p 参考':>8} {'p 本机':>8} {'Holm 参考':>9} {'Holm 本机':>9}")
for metric in ["first_success_episode", "stable_breakthrough_episode", "final_follow_position_error",
               "final_pairwise_formation_error", "final_success_rate", "final_safe_success_rate", "final_collision_episode_rate"]:
    for comp in ["baseline", "random_matched", "uniform_matched"]:
        rp, mp = REF_PAIR.get((metric, comp)), MINE_PAIR.get((metric, comp))
        if not (rp and mp):
            continue
        rd = float(rp["mean_difference_reference_minus_baseline"])
        md = float(mp["mean_difference_reference_minus_baseline"])
        rp_, mp_ = float(rp["wilcoxon_p"]), float(mp["wilcoxon_p"])
        rh, mh = float(rp["holm_adjusted_p_within_metric"]), float(mp["holm_adjusted_p_within_metric"])
        agree = "一致" if np.sign(rd) == np.sign(md) else "相反"
        print(f"{metric:<34} {comp:<15} {rd:>12.2f} {md:>12.2f} {agree:>4} "
              f"{sig(rp_)}{rp_:>6.3f} {sig(mp_)}{mp_:>6.3f} {rh:>9.3f} {mh:>9.3f}")
print("\n(** 标记原始 p<0.05；Holm 为组内校正后)")
