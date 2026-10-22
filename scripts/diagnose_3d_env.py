#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose_3d_env.py — 用手写 PD 控制器诊断 3D 环境可达性。

不训练，只回答三个问题：
1. 当前四面体目标分配下，各机初始距离和碰撞风险；
2. 目标 z 是否低于 min_altitude 导致不可达；
3. 换用“就近分配 + 抬高 leader 高度”后，环境能否稳定编队并跟随。

用法：
  python scripts/diagnose_3d_env.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

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


def run_pd(module, perm, leader_z, leader_target_z, max_alt, steps=500, feedforward=False):
    cfg = dict(module.BASE_CFG)
    cfg["episodes"] = 1
    cfg["episode_len"] = steps
    cfg["leader_start"] = [0.0, 0.0, leader_z]
    cfg["leader_target"] = [200.0, 200.0, leader_target_z]
    cfg["max_altitude"] = max_alt
    cfg["env_seed"] = 7
    env = module.MovingLeaderFormationEnv3D(cfg)
    if perm is not None:
        env.formation_offsets = module.TETRAHEDRON_OFFSETS[list(perm)].copy()

    obs, state = env.reset()
    initial_errors = np.linalg.norm(env.pos - env.targets(), axis=1)
    initial_targets = env.targets().copy()

    kp, kd = 0.15, 2.0
    acquired_step = None
    leader_goal_step = None
    collision_steps = 0
    min_z = float(env.pos[:, 2].min())
    max_z = float(env.pos[:, 2].max())

    for t in range(1, steps + 1):
        targets = env.targets()
        desired_v = (targets - env.pos) * kp
        if feedforward:
            desired_v = desired_v + env.leader_vel[None, :]
        desired_v = np.clip(desired_v, -env.max_speed, env.max_speed)
        desired_v[:, 2] = np.clip(desired_v[:, 2], -cfg["max_vertical_speed"],
                                  cfg["max_vertical_speed"])
        accel = (desired_v - env.vel) * kd
        action = np.clip(accel / float(cfg["act_scale"]), -1.0, 1.0).astype(np.float32)
        _, rewards, terminated, truncated, info = env.step(action)
        collision_steps += int(info["episode_had_collision"] and info["collision_count"] > 0)
        min_z = min(min_z, float(env.pos[:, 2].min()))
        max_z = max(max_z, float(env.pos[:, 2].max()))
        if env.formation_complete and acquired_step is None:
            acquired_step = t
        if terminated and leader_goal_step is None:
            leader_goal_step = t
        if terminated or truncated:
            break

    final_errors = np.linalg.norm(env.pos - env.targets(), axis=1)
    return {
        "perm": perm,
        "leader_z": leader_z,
        "max_alt": max_alt,
        "feedforward": feedforward,
        "initial_targets": initial_targets,
        "initial_errors": initial_errors,
        "final_errors": final_errors,
        "final_mean": float(final_errors.mean()),
        "final_max": float(final_errors.max()),
        "acquired_step": acquired_step,
        "leader_goal_step": leader_goal_step,
        "follow_retention": info.get("follow_retention_ratio", 0.0),
        "collisions": info.get("episode_collision_count", 0),
        "collision_steps": collision_steps,
        "min_z": min_z,
        "max_z": max_z,
        "leader_pos": env.leader_pos.copy(),
    }


def report(name, r):
    print(f"\n=== {name} ===")
    print(f"offsets perm={r['perm']} leader_z={r['leader_z']} max_alt={r['max_alt']} "
          f"feedforward={r['feedforward']}")
    print("initial targets:")
    for i, (tgt, err) in enumerate(zip(r["initial_targets"], r["initial_errors"])):
        print(f"  agent{i} target=({tgt[0]:7.1f},{tgt[1]:7.1f},{tgt[2]:7.1f})  dist={err:6.1f} m")
    print("final per-agent errors:", np.round(r["final_errors"], 1))
    print(f"final mean/max = {r['final_mean']:.1f} / {r['final_max']:.1f} m")
    print(f"acquired_step={r['acquired_step']} leader_goal_step={r['leader_goal_step']} "
          f"follow_retention={r['follow_retention']:.3f}")
    print(f"collisions={r['collisions']} collision_steps={r['collision_steps']} "
          f"z_range=[{r['min_z']:.1f}, {r['max_z']:.1f}]")
    print(f"leader final={np.round(r['leader_pos'], 1)}")


def main():
    module = load_module()
    print("TETRAHEDRON_OFFSETS:")
    print(np.round(module.TETRAHEDRON_OFFSETS, 4))
    print("FIXED_START_POSITIONS:")
    print(module.FIXED_START_POSITIONS)

    report("A. 当前配置：原始顺序 + leader z=20 + max_alt=80",
           run_pd(module, None, 20.0, 25.0, 80.0))

    report("B. 仅重排目标：就近分配 + leader z=20",
           run_pd(module, [0, 2, 3, 1], 20.0, 25.0, 80.0))

    report("C. 重排 + 抬高 leader z=40→45 + max_alt=100",
           run_pd(module, [0, 2, 3, 1], 40.0, 45.0, 100.0))

    report("D. 原始顺序 + 抬高 leader z=40→45（对照）",
           run_pd(module, None, 40.0, 45.0, 100.0))

    report("E. 重排 + leader z=40→45 + 速度前馈",
           run_pd(module, [0, 2, 3, 1], 40.0, 45.0, 100.0, feedforward=True))

    report("F. 原始顺序 + leader z=20 + 速度前馈（仅验证可跟踪性）",
           run_pd(module, None, 20.0, 25.0, 80.0, feedforward=True))


if __name__ == "__main__":
    main()
