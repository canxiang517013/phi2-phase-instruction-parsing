#!/usr/bin/env python3
"""Compare reproduction runs (results_repro/) against the repository's shipped
paper artifacts (results/E1_primary, results/E3_rule_baseline)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
REPRO = ROOT / "results_repro"
SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]

METRICS = [
    "first_success_episode",
    "stable_breakthrough_episode",
    "final_acquisition_rate",
    "final_success_rate",
    "final_follow_position_error",
    "final_pairwise_formation_error",
]


def load_repro(method: str) -> dict[int, dict]:
    out = {}
    for seed in SEEDS:
        p = REPRO / f"{method}_seed{seed}" / "results.json"
        if p.exists():
            with p.open(encoding="utf-8") as f:
                out[seed] = json.load(f)
    return out


def load_reference_per_seed(method: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for src in [ROOT / "results" / "E1_primary" / "per_seed_metrics.csv"]:
        with src.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row["method"] == method:
                    out[int(row["seed"])] = row
    return out


def mean_std(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return "—"
    sd = arr.std(ddof=1) if arr.size > 1 else 0.0
    return f"{arr.mean():.2f} ± {sd:.2f}"


def main() -> None:
    lines: list[str] = ["# 复现 vs 仓库论文结果对比", ""]
    for method in ["baseline", "rule_based"]:
        repro = load_repro(method)
        if not repro:
            lines += [f"## {method}: 无已完成 seed", ""]
            continue
        lines += [
            f"## {method}（复现 {len(repro)}/10 seeds）",
            "",
            "| 指标 | 复现 (mean±std) | 仓库参考 (mean±std) |",
            "|---|---|---|",
        ]
        ref_per_seed = load_reference_per_seed(method)
        for metric in METRICS:
            mine = [r[metric] for r in repro.values() if r.get(metric) is not None]
            if metric.endswith("_episode"):
                mine = [
                    r[metric] if r.get(metric) is not None else r["n_episodes"] + 1
                    for r in repro.values()
                ]
            if ref_per_seed:
                ref = [float(ref_per_seed[s][metric]) for s in ref_per_seed if s in {x for x in repro}]
                ref_all = [float(v[metric]) for v in ref_per_seed.values()]
                ref_str = f"{mean_std(ref_all)} (N=10)"
            else:
                # rule_based: only aggregate reference from paper table
                ref_defaults = {
                    "first_success_episode": "884.40 ± 302.49",
                    "stable_breakthrough_episode": "1684.30 ± 418.99",
                    "final_acquisition_rate": None,
                    "final_success_rate": "98.20 ± 3.36",
                    "final_follow_position_error": "4.80 ± 1.91",
                    "final_pairwise_formation_error": "5.27 ± 3.30",
                }
                ref_str = ref_defaults.get(metric) or "—"
            lines.append(f"| {metric} | {mean_std(mine)} | {ref_str} |")
        lines.append("")

        if ref_per_seed:
            lines += ["### baseline per-seed 明细（复现 vs 参考）", "",
                      "| seed | 复现 first_success | 参考 first_success | 复现 final_SR% | 参考 final_SR% |",
                      "|---|---|---|---|---|"]
            for seed in SEEDS:
                if seed not in repro:
                    continue
                r, ref = repro[seed], ref_per_seed.get(seed)
                if ref is None:
                    continue
                mine_fs = r.get("first_success_episode")
                mine_fs = mine_fs if mine_fs is not None else 2501
                lines.append(
                    f"| {seed} | {mine_fs} | {ref['first_success_episode']} "
                    f"| {r['final_success_rate']:.1f} | {float(ref['final_success_rate']):.1f} |"
                )
            lines.append("")

    out = ROOT / "repro_docs" / "repro_vs_paper.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
