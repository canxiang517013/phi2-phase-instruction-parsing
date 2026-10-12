#!/usr/bin/env python3
"""Reproduction: E1 baseline MAPPO arm, 10 preregistered seeds (mirrors run_e1 cfg)."""
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
    json_dump,
    train_single_run,
)

cfg = deepcopy(BASE_CFG)
cfg.update(
    controller_type="baseline",
    results_dir="results_repro",
    episodes=BASE_CFG["episodes"],
    episode_len=BASE_CFG["episode_len"],
    device="cpu",
    matched_schedule_source="phase_aware",
)
out = Path("results_repro")
out.mkdir(parents=True, exist_ok=True)
json_dump(out / "e1_config.json", cfg | {"seeds": DEFAULT_SEEDS_10})

started = time.time()
for seed in DEFAULT_SEEDS_10:
    print(f"\n=== REPRO E1 Baseline MAPPO | seed={seed} ===", flush=True)
    train_single_run("baseline", seed, cfg, out)
print(f"Baseline arm done in {(time.time() - started) / 3600.0:.2f} h", flush=True)
