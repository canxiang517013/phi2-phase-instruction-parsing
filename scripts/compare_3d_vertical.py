#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_3d_vertical.py — 离线环境 vs 仿真日志的 agent1 垂直行为对比

离线：用同一 npz 策略跑 experiment_core_3d，打印 agent1 的 up/cmd_z/err；
仿真：读入 mappo_3d jsonl 打印同样字段。用于判断垂直偏差来源。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "nodes" / "edge"))
import mappo_bridge_math as bm  # noqa: E402

ENV_FILE = ROOT / "src" / "training" / "experiment_core_3d.py"
NPZ = ROOT / "assets" / "mappo_3d_seed21_actor_best.npz"


def offline_trace(n_steps=80, idx=1):
    spec = importlib.util.spec_from_file_location("ec3_for_trace", ENV_FILE)
    ec = importlib.util.module_from_spec(spec)
    sys.modules["ec3_for_trace"] = ec
    spec.loader.exec_module(ec)
    cfg = dict(ec.BASE_CFG)
    cfg["episode_len"] = n_steps
    env = ec.MovingLeaderFormationEnv3D(cfg)
    obs, _ = env.reset()
    env.episode_index = 2500
    actor = bm.NumpyActor.from_npz(NPZ)
    rows = []
    for t in range(n_steps):
        action = actor.act(obs)
        obs, _, term, trunc, info = env.step(action.astype(np.float32))
        rows.append((t, float(env.pos[idx][2]), float(env.vel[idx][2]),
                     float(action[idx][2]), float(info["max_position_error"])))
        if term or trunc:
            break
    return rows


def sim_trace(path, idx=1, n_steps=80):
    rows = []
    for line in Path(path).open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("event") != "step":
            continue
        d = next(x for x in r["drones"] if x["i"] == idx)
        rows.append((r["t"], d["up"], d["vel"][2], d["cmd"][2], d["err"]))
        if len(rows) >= n_steps:
            break
    return rows


def main():
    sim_path = sys.argv[1]
    off = offline_trace(len(sim_trace(sim_path)))
    sim = sim_trace(sim_path)
    print("   离线环境(env)          |   仿真桥接(sim)")
    print(" t |  up   vz   a_z  err |  up   vz  cmd_z err")
    for (t, u, v, a, e), (t2, u2, v2, c2, e2) in zip(off, sim):
        print("%3d | %5.2f %5.2f %5.2f %5.1f | %5.2f %5.2f %5.2f %5.1f"
              % (t, u, v, a, e, u2, v2, c2, e2))


if __name__ == "__main__":
    main()
