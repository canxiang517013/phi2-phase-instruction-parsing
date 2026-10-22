#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evaluate_3d_actor.py — 诊断训练后的 3D actor 是否学会跟随速度前馈。

加载指定 checkpoint，用确定性动作跑若干 episode，统计编队完成后：
- 平均目标误差
- 平均速度 / leader 速度
- 速度在 leader 方向上的投影
- 三轴动作均值
如果“速度投影 ≈ leader 速度且误差恒定”，说明策略停在无前馈的稳态滞后上。
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "src" / "training" / "experiment_core_3d.py"


def load_module():
    spec = importlib.util.spec_from_file_location("experiment_core_3d", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_3d"] = module
    spec.loader.exec_module(module)
    return module


def evaluate(module, checkpoint, episodes, leader_z, leader_target_z, max_alt):
    cfg = dict(module.BASE_CFG)
    cfg["episodes"] = episodes
    cfg["episode_len"] = int(cfg.get("episode_len", 600))
    cfg["leader_start"] = [0.0, 0.0, leader_z]
    cfg["leader_target"] = [200.0, 200.0, leader_target_z]
    cfg["max_altitude"] = max_alt
    cfg["curriculum_static_episodes"] = 0
    cfg["device"] = "cpu"
    env = module.MovingLeaderFormationEnv3D(cfg)
    actor = module.SquashedGaussianActor(obs_dim=20).to("cpu")
    state = torch.load(checkpoint, map_location="cpu")
    actor.load_state_dict(state)
    actor.eval()

    rows = []
    with torch.no_grad():
        for ep in range(episodes):
            obs, _ = env.reset()
            acquired_step = None
            goal_step = None
            post = {"err": [], "speed": [], "leader_speed": [], "projection": [],
                    "action": []}
            for t in range(1, int(cfg["episode_len"]) + 1):
                obs_t = torch.tensor(obs, dtype=torch.float32)
                action = torch.tanh(actor.net(obs_t)).numpy().astype(np.float32)
                obs, _, terminated, truncated, info = env.step(action)
                if env.formation_complete and acquired_step is None:
                    acquired_step = t
                if env.formation_complete:
                    err = np.linalg.norm(env.pos - env.targets(), axis=1)
                    speed = np.linalg.norm(env.vel, axis=1)
                    lv = np.linalg.norm(env.leader_vel)
                    if lv > 0.5:
                        direction = env.leader_vel / lv
                        proj = env.vel @ direction
                    else:
                        proj = np.zeros(env.n)
                    post["err"].append(float(err.mean()))
                    post["speed"].append(float(speed.mean()))
                    post["leader_speed"].append(float(lv))
                    post["projection"].append(float(proj.mean()))
                    post["action"].append(action.mean(axis=0).tolist())
                if terminated:
                    goal_step = t
                    break
                if truncated:
                    break
            rows.append({
                "episode": ep,
                "acquired_step": acquired_step,
                "goal_step": goal_step,
                "post_err": float(np.mean(post["err"])) if post["err"] else None,
                "post_err_max": float(np.max(post["err"])) if post["err"] else None,
                "speed": float(np.mean(post["speed"])) if post["speed"] else None,
                "leader_speed": float(np.mean(post["leader_speed"])) if post["leader_speed"] else None,
                "projection": float(np.mean(post["projection"])) if post["projection"] else None,
                "action_mean": np.mean(post["action"], axis=0).round(3).tolist() if post["action"] else None,
                "final_err": np.round(np.linalg.norm(env.pos - env.targets(), axis=1), 1).tolist(),
                "collisions": int(info.get("episode_collision_count", 0)),
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--leader-z", type=float, default=None)
    parser.add_argument("--leader-target-z", type=float, default=None)
    parser.add_argument("--max-alt", type=float, default=None)
    args = parser.parse_args()

    module = load_module()
    config = module.BASE_CFG
    leader_z = args.leader_z if args.leader_z is not None else float(config["leader_start"][2])
    target_z = (args.leader_target_z if args.leader_target_z is not None
                else float(config["leader_target"][2]))
    max_alt = args.max_alt if args.max_alt is not None else float(config["max_altitude"])

    print(f"checkpoint={args.checkpoint}")
    print(f"leader_z={leader_z} target_z={target_z} max_alt={max_alt}")
    rows = evaluate(module, args.checkpoint, args.episodes, leader_z, target_z, max_alt)
    for row in rows:
        print("-" * 60)
        for key, value in row.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
