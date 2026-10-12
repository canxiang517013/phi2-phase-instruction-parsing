#!/usr/bin/env python3
"""Reproduction: E3 rule-based phase controller, 10 preregistered seeds (mirrors run_e3 cfg)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import time

import torch

torch.set_num_threads(8)

sys.path.insert(0, str(Path(__file__).parent / "src"))
from experiment_core import BASE_CFG, DEFAULT_SEEDS_10, json_dump, train_single_run

cfg = deepcopy(BASE_CFG)
cfg.update(
    controller_type="rule_based",
    results_dir="results_repro",
    episodes=BASE_CFG["episodes"],
    episode_len=BASE_CFG["episode_len"],
    device="cpu",
)
out = Path("results_repro")
out.mkdir(parents=True, exist_ok=True)
json_dump(out / "e3_rule_config.json", cfg | {"seeds": DEFAULT_SEEDS_10})

started = time.time()
for seed in DEFAULT_SEEDS_10:
    print(f"\n=== REPRO E3 Rule-Based Phase Controller | seed={seed} ===", flush=True)
    train_single_run("rule_based", seed, cfg, out)
print(f"Rule-based arm done in {(time.time() - started) / 3600.0:.2f} h", flush=True)
