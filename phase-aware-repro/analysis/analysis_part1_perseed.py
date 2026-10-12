#!/usr/bin/env python3
"""Part 1: 逐 seed 对比（mine vs reference）— 四方法全指标 + 相关性"""
import csv, json
import numpy as np
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).parent
REF = {}
with (ROOT / "results/E1_primary/per_seed_metrics.csv").open(encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        REF[(row["method"], int(row["seed"]))] = row

MINE = {}
for p in ROOT.glob("results_repro/*_seed*/results.json"):
    run_dir = p.parent.name
    m, s = run_dir.rsplit("_seed", 1)
    with p.open(encoding="utf-8") as f:
        MINE[(m, int(s))] = json.load(f)

SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]
METHODS = ["baseline", "random_matched", "uniform_matched", "phase_aware"]

print("=" * 100)
print("PART 1A  逐 seed 成功率对照（本机 vs 论文参考，%）")
print("=" * 100)
hdr = f"{'seed':>7} |" + "".join(f" {m.split('_')[0]:>12}/{'ref':>5}" for m in METHODS)
print(hdr)
for s in SEEDS:
    row = f"{s:>7} |"
    for m in METHODS:
        mine = MINE[(m, s)]["final_success_rate"]
        ref = float(REF[(m, s)]["final_success_rate"])
        flag = "" if abs(mine - ref) <= 10 else (" ←" if mine < ref else " ↑")
        row += f" {mine:>11.0f}/{ref:>5.0f}{flag}"
    print(row)

print()
print("=" * 100)
print("PART 1B  逐 seed 首次成功 episode 对照（本机 vs 论文参考；None=未达成，记 2501）")
print("=" * 100)
print(hdr)
for s in SEEDS:
    row = f"{s:>7} |"
    for m in METHODS:
        mine = MINE[(m, s)]["first_success_episode"] or 2501
        ref = float(REF[(m, s)]["first_success_episode"] or 2501)
        row += f" {mine:>11.0f}/{ref:>5.0f}"
    print(row)

print()
print("=" * 100)
print("PART 1C  逐 seed 指标相关性（Pearson r / Spearman ρ / p）——检验跨平台的 per-seed 难度排序是否一致")
print("=" * 100)
for m in METHODS:
    for metric, key in [("first_success", "first_success_episode"), ("final_SR", "final_success_rate"), ("follow_err", "final_follow_position_error"), ("pairwise_err", "final_pairwise_formation_error")]:
        mine_v, ref_v = [], []
        for s in SEEDS:
            mv = MINE[(m, s)].get(key)
            if key.endswith("episode") and mv is None:
                mv = 2501
            mine_v.append(float(mv))
            rv = REF[(m, s)].get(key)
            ref_v.append(float(rv if rv not in (None, "") else 2501))
        pr, pp = stats.pearsonr(mine_v, ref_v)
        sr, sp = stats.spearmanr(mine_v, ref_v)
        print(f"{m:<16} {metric:<14} Pearson r={pr:>6.3f} (p={pp:.3f})   Spearman ρ={sr:>6.3f} (p={sp:.3f})")

print()
print("=" * 100)
print("PART 1D  逐 seed 跟踪误差对照（本机 vs 参考，m）")
print("=" * 100)
print(hdr)
for s in SEEDS:
    row = f"{s:>7} |"
    for m in METHODS:
        mine = MINE[(m, s)]["final_follow_position_error"]
        ref = float(REF[(m, s)]["final_follow_position_error"])
        row += f" {mine:>11.2f}/{ref:>5.2f}"
    print(row)
