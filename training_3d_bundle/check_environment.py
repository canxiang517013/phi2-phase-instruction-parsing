#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_environment.py — 3D 训练包环境自检

检查 Python/依赖/CUDA/磁盘，并用零动作跑 2 个环境步，确认观测与状态维度。
不进行任何训练，不访问网络。
"""
from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
REQUIRED = ["numpy", "torch", "matplotlib", "requests"]


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def main() -> None:
    print("=" * 68)
    print("3D MAPPO 训练环境自检")
    print("=" * 68)

    if sys.version_info < MIN_PYTHON:
        fail(f"需要 Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}，当前 {platform.python_version()}")
    print(f"[OK] Python {platform.python_version()} ({platform.platform()})")

    for name in REQUIRED:
        try:
            module = __import__(name)
        except ImportError as exc:
            fail(f"缺少依赖 {name}: {exc}. 请先 pip install -r requirements.txt")
        print(f"[OK] {name} {getattr(module, '__version__', 'unknown')}")

    import numpy as np
    import torch

    if torch.cuda.is_available():
        count = torch.cuda.device_count()
        names = ", ".join(torch.cuda.get_device_name(i) for i in range(count))
        print(f"[OK] CUDA 可用，GPU 数={count}: {names}")
        cap = torch.cuda.get_device_capability(0)
        print(f"     计算能力 {cap[0]}.{cap[1]}")
    else:
        print("[WARN] CUDA 不可用，训练会退回 CPU（速度明显变慢）")

    free_gb = shutil.disk_usage(Path.cwd()).free / (1024**3)
    print(f"[OK] 当前目录可用磁盘 {free_gb:.1f} GB")
    if free_gb < 10:
        print("[WARN] 可用空间不足 10 GB；5 个方法 × 多种子的日志/检查点可能不够")

    root = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "experiment_core_3d", root / "experiment_core_3d.py"
    )
    if spec is None or spec.loader is None:
        fail("无法加载 experiment_core_3d.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_3d"] = module
    spec.loader.exec_module(module)

    config = dict(module.BASE_CFG)
    config["episodes"] = 1
    config["episode_len"] = 5
    config["device"] = "cpu"
    env = module.MovingLeaderFormationEnv3D(config)
    obs, state = env.reset()
    actions = np.zeros((env.n, 3), dtype=np.float32)
    for _ in range(2):
        obs, rewards, terminated, truncated, info = env.step(actions)

    expected_obs = (env.n, 20)
    expected_state = (32,)
    if tuple(obs.shape) != expected_obs:
        fail(f"obs 维度 {obs.shape}，期望 {expected_obs}")
    if tuple(state.shape) != expected_state:
        fail(f"state 维度 {state.shape}，期望 {expected_state}")
    print(f"[OK] 环境步进正常: obs={tuple(obs.shape)}, state={tuple(state.shape)}, "
          f"action={tuple(actions.shape)}")
    print(f"[OK] leader_start={config['leader_start']} -> leader_target={config['leader_target']}")
    print(f"[OK] radius={config['formation_radius']} m, "
          f"vertical_speed_limit={config['max_vertical_speed']} m/s, "
          f"altitude_bounds=[{config['min_altitude']}, {config['max_altitude']}] m")
    print("\n自检通过。可以运行 run_smoke_check.sh 做一次短程训练。")


if __name__ == "__main__":
    main()
