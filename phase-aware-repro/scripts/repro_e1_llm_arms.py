#!/usr/bin/env python3
"""Reproduction: E1 LLM arms — phase_aware -> uniform_matched -> random_matched,
10 preregistered seeds each, into results_repro/ (baseline arm already complete).

Mirrors src/run_e1_primary_n10.py with ONE documented deviation:
  llm_timeout 120 -> 600. This machine runs deepseek-r1:14b with a 43% GPU /
  57% CPU layer split at ~125 s per consultation; the paper's 120 s read timeout
  would drop roughly half of the consultations and change method behaviour.
resume=True: completed runs (results.json present) are skipped, so the chain
can be restarted after interruption without redoing finished seeds.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import time

import torch

torch.set_num_threads(8)

sys.path.insert(0, str(Path(__file__).parent / "src"))
from experiment_core import (
    BASE_CFG,
    DEFAULT_SEEDS_10,
    METHOD_LABELS,
    collect_results,
    json_dump,
    plot_comparisons,
    train_single_run,
    write_reports,
)

OUT = Path("results_repro")
OUT.mkdir(parents=True, exist_ok=True)

cfg = deepcopy(BASE_CFG)
cfg.update(
    results_dir="results_repro",
    episodes=BASE_CFG["episodes"],
    episode_len=BASE_CFG["episode_len"],
    device="cpu",
    llm_timeout=600,
    matched_schedule_source="phase_aware",
)
json_dump(
    OUT / "e1_llm_arms_config.json",
    cfg
    | {
        "seeds": DEFAULT_SEEDS_10,
        "deviation_note": (
            "llm_timeout=600 (paper: 120). Local deepseek-r1:14b latency "
            "~125 s/call on 6 GB VRAM; paper platform measured 4.9 s/call."
        ),
    },
)

# Ours must run first: its accepted-intervention schedule is replayed by the
# two matched control arms (load_matched_schedule raises if missing).
ARM_ORDER = ["phase_aware", "uniform_matched", "random_matched"]
for method in ARM_ORDER:
    method_cfg = deepcopy(cfg)
    method_cfg["controller_type"] = method
    started = time.time()
    for seed in DEFAULT_SEEDS_10:
        print(f"\n=== REPRO E1 {METHOD_LABELS[method]} | seed={seed} ===", flush=True)
        train_single_run(method, seed, method_cfg, OUT, resume=True)
    print(f"[arm {method} finished in {(time.time() - started) / 3600.0:.2f} h]", flush=True)

order = ["baseline", "random_matched", "uniform_matched", "phase_aware"]
results = collect_results(OUT, order, DEFAULT_SEEDS_10)
write_reports(results, order, DEFAULT_SEEDS_10, OUT)
plot_comparisons(results, order, DEFAULT_SEEDS_10, OUT)
print("E1 four-arm reports + plots written to results_repro/", flush=True)
