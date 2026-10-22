#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_obs_action_3d.py — 用仿真 t=0 的 4 机状态重建 obs，比较策略动作

对照：实验环境同初始位置下 t=0 的动作。定位策略在仿真中输出幅值偏小的原因。
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


def main():
    sim_path = sys.argv[1]
    spec = importlib.util.spec_from_file_location("ec3_dbg", ENV_FILE)
    ec = importlib.util.module_from_spec(spec)
    sys.modules["ec3_dbg"] = ec
    spec.loader.exec_module(ec)
    cfg = dict(ec.BASE_CFG)
    cfg["episode_len"] = 2
    env = ec.MovingLeaderFormationEnv3D(cfg)
    obs_env, _ = env.reset()

    actor = bm.NumpyActor.from_npz(NPZ)
    a_env = actor.act(obs_env)

    first = None
    for line in Path(sim_path).open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("event") == "step":
            first = r
            break
    drones = first["drones"]
    pos = np.array([d["pos"] for d in drones], dtype=np.float32)
    vel = np.array([d["vel"] for d in drones], dtype=np.float32)
    leader = np.array(first["leader"], dtype=np.float32)
    offsets = bm.formation_offsets_3d(cfg["formation_radius"])
    targets = bm.compute_targets_3d(leader, offsets)
    obs_sim = bm.build_obs_3d(pos, vel, targets, leader,
                              np.zeros(3, dtype=np.float32), True, False)
    a_sim = actor.act(obs_sim)

    print("env  t=0 观测(agent0):", obs_env[0].round(2))
    print("sim  t=0 观测(agent0):", obs_sim[0].round(2))
    print("观测差(agent0):", (obs_env[0] - obs_sim[0]).round(2))
    print()
    print("环境动作 (4x3):")
    print(a_env.round(2))
    print("仿真动作 (4x3):")
    print(a_sim.round(2))


if __name__ == "__main__":
    main()
