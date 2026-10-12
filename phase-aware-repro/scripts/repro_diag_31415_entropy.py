#!/usr/bin/env python3
"""31415 扩界单点实验：区分 phase_aware 失败是"探索预算不足"还是"权限/调度不足"。

A: pa_wide_entropy     phase_aware + entropy 上界 0.02->0.05（LLM 动态调度，扩权）
B: baseline_ent020     baseline + entropy 固定 0.02（高熵恒定对照）
C: baseline_ent050     baseline + entropy 固定 0.05（更高熵恒定对照）

解读矩阵：
- A 成功而原 pa(0.0194 顶界)失败      -> 预算不足（上界是约束）
- B 或 C 成功而 A 失败                -> 熵本身是关键，动态调度反而低效
- 三者全败                            -> 瓶颈不在熵（指向 w_position 或任务本身）
写入 results_diag/，与 E1 正式数据隔离。
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import time

import torch

torch.set_num_threads(int(sys.argv[1]) if len(sys.argv) > 1 else 8)

sys.path.insert(0, str(Path(__file__).parent / "src"))
from experiment_core import BASE_CFG, json_dump, train_single_run

OUT = Path("results_diag")
OUT.mkdir(parents=True, exist_ok=True)
SEED = 31415
DEVIATION = (
    "diagnostic run, NOT part of E1: entropy_coef upper bound or fixed value "
    "varied on seed 31415 to test exploration-budget vs authorization hypotheses; "
    "llm_timeout=600 as in the LLM-arm repro."
)

# A: phase_aware + 扩界
cfg_a = deepcopy(BASE_CFG)
cfg_a.update(
    controller_type="phase_aware",
    env_seed=SEED,
    llm_timeout=600,
    device="cpu",
    results_dir="results_diag",
)
cfg_a["param_stability"]["entropy_coef"]["max"] = 0.05
json_dump(OUT / "diag_a_config.json", cfg_a | {"deviation_note": DEVIATION})
t0 = time.time()
print("=== DIAG A: phase_aware, entropy max 0.05, seed 31415 ===", flush=True)
train_single_run("pa_wide_entropy", SEED, cfg_a, OUT)
print(f"[A done in {(time.time() - t0) / 3600:.2f} h]", flush=True)
