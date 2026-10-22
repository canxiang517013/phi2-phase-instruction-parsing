#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_actor_npz.py — 把 torch 的 SquashedGaussianActor 权重导出为 numpy npz

目的：WSL 的 ROS2 环境只有 numpy 没有 torch；把三层 Linear 的权重导出后，
mappo_bridge_math.NumpyActor 用纯 numpy 前向即可推理，数值与 torch 一致。

checkpoint 用 weights_only=True 加载：只允许张量字典，禁止 pickle 任意代码执行；
对非本脚本产出的可疑 .pth 一律拒绝加载。

用法（Windows, phase-llm 环境）：
  python src/training/export_actor_npz.py \
    --checkpoint "phase-aware-llm-meta-controller/results_repro/baseline_seed555/actor_final.pth" \
    --output assets/mappo_2d_seed555_actor.npz
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch


def load_state_dict_safely(path: str) -> dict:
    """weights_only=True 加载；缺该参数的旧 torch 报错提示升级。"""
    try:
        state = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise RuntimeError(
            "当前 torch 版本不支持 weights_only，请升级 torch >= 2.0 后再导出"
        ) from exc
    if not isinstance(state, dict):
        raise ValueError(f"{path} 不是 state_dict 字典")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="actor_final.pth 路径")
    parser.add_argument("--output", required=True, help="输出 npz 路径")
    parser.add_argument("--seed", type=int, default=555, help="随机对拍用的种子")
    args = parser.parse_args()

    state = load_state_dict_safely(args.checkpoint)
    keys = {
        "w1": "net.0.weight", "b1": "net.0.bias",
        "w2": "net.2.weight", "b2": "net.2.bias",
        "w3": "net.4.weight", "b3": "net.4.bias",
    }
    arrays = {}
    for name, key in keys.items():
        if key not in state:
            raise KeyError(f"checkpoint 缺少 {key}，实际键: {list(state)}")
        tensor = state[key]
        if not isinstance(tensor, torch.Tensor):
            raise ValueError(f"{key} 不是张量，拒绝导出")
        arrays[name] = tensor.detach().cpu().numpy().astype(np.float32)
    for name in ("w1", "w2", "w3"):
        print(f"{name}: {arrays[name].shape}")

    w1, b1, w2, b2, w3, b3 = (arrays[k] for k in ("w1", "b1", "w2", "b2", "w3", "b3"))
    rng = np.random.default_rng(args.seed)
    obs = rng.normal(0.0, 1.0, size=(64, int(w1.shape[1]))).astype(np.float32)

    with torch.no_grad():
        h1 = torch.tanh(torch.nn.functional.linear(
            torch.from_numpy(obs), torch.from_numpy(w1), torch.from_numpy(b1)))
        h2 = torch.tanh(torch.nn.functional.linear(h1, torch.from_numpy(w2), torch.from_numpy(b2)))
        ref = torch.tanh(torch.nn.functional.linear(
            h2, torch.from_numpy(w3), torch.from_numpy(b3))).numpy()
    mine = np.tanh(np.tanh(np.tanh(obs @ w1.T + b1) @ w2.T + b2) @ w3.T + b3)
    diff = float(np.max(np.abs(ref - mine)))
    print(f"numpy 与 torch 前向最大误差: {diff:.3e}")
    if diff > 1e-5:
        raise SystemExit("误差过大，导出中止")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, **arrays)
    print(f"已写出: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
