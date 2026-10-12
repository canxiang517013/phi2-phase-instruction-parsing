#!/usr/bin/env python3
"""31415 诊断对照 B/C：baseline + 固定 entropy（无 LLM，验证熵本身是否瓶颈）。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import time

import torch

torch.set_num_threads(int(sys.argv[1]) if len(sys.argv) > 1 else 4)

sys.path.insert(0, str(Path(__file__).parent / "src"))
from experiment_core import BASE_CFG, json_dump, train_single_run

OUT = Path("results_diag")
OUT.mkdir(parents=True, exist_ok=True)
SEED = 31415
DEVIATION = "diagnostic control, NOT part of E1: fixed entropy_coef, no LLM, seed 31415."

for label, ent in [("baseline_ent020", 0.02), ("baseline_ent050", 0.05)]:
    cfg = deepcopy(BASE_CFG)
    cfg.update(controller_type="baseline", env_seed=SEED, device="cpu", results_dir="results_diag")
    cfg["param_stability"]["entropy_coef"] = {"min": 0.001, "max": 0.05, "default": ent}
    json_dump(OUT / f"diag_{label}_config.json", cfg | {"deviation_note": DEVIATION})
    t0 = time.time()
    print(f"=== DIAG {label}: baseline, entropy fixed {ent}, seed 31415 ===", flush=True)
    train_single_run(label, SEED, cfg, OUT)
    print(f"[{label} done in {(time.time() - t0) / 3600:.2f} h]", flush=True)
