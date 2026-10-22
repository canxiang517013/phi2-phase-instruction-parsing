#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_bridge_math.py — 桥接数学与师兄 2D 环境的逐步离线对拍

同一 episode 内，每一步比较：
  1. 观测 14 维逐元素（env.obs() vs build_obs）
  2. 编队目标（env.targets() vs compute_targets）
  3. 虚拟 leader 运动（env.update_leader 结果 vs VirtualLeader.step）
  4. 速度指令（env.step 内部的 vel 积分 vs velocity_command）
  5. 编队完成判定（env.formation_complete vs FormationTracker）
  6. 期望间距/碰撞口径（env.pairwise_metrics vs pairwise_metrics）

前提：本地存在师兄克隆 phase-aware-llm-meta-controller/（被 gitignore，
仅本地可用）；缺失时整包跳过。

用法（Windows, phase-llm 环境）：
  python src/evaluation/test_bridge_math.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "nodes" / "edge"))
import mappo_bridge_math as bm  # noqa: E402

ENV_FILE = ROOT / "phase-aware-llm-meta-controller" / "src" / "experiment_core.py"
RUN_DIR = (ROOT / "phase-aware-llm-meta-controller" / "results_repro"
           / "baseline_seed555")
NPZ = ROOT / "assets" / "mappo_2d_seed555_actor.npz"
N_STEPS = 500


def load_2d_module():
    spec = importlib.util.spec_from_file_location("experiment_core_2d_pai", ENV_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_2d_pai"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if not ENV_FILE.exists() or not RUN_DIR.exists() or not NPZ.exists():
        print("SKIP: 缺少 2D 克隆 / seed555 运行目录 / npz 权重，跳过对拍")
        return

    ec = load_2d_module()
    actor = bm.NumpyActor.from_npz(NPZ)
    print(f"actor: obs={actor.obs_dim}, action={actor.action_dim}")

    cfg = json.loads((RUN_DIR / "config_snapshot.json").read_text(encoding="utf-8"))
    env = ec.MovingLeaderFormationEnv(cfg)
    obs_env, _ = env.reset()

    leader = bm.VirtualLeader(bm.BRIDGE_CFG)
    tracker = bm.FormationTracker(bm.BRIDGE_CFG)

    diffs = dict(obs=[], targets=[], leader_pos=[], leader_vel=[],
                 vel_cmd=[], pairwise=[])
    tracker_lag_steps = 0
    complete_mismatch = 0

    for t in range(1, N_STEPS + 1):
        targets_env = env.targets()
        targets_ours = bm.compute_targets(
            env.leader_pos, cfg["formation_radius"], env.n)
        diffs["targets"].append(float(np.max(np.abs(targets_env - targets_ours))))

        obs_ours = bm.build_obs(
            env.pos, env.vel, targets_env, env.leader_pos, env.leader_vel,
            env.formation_phase, env.formation_complete)
        diffs["obs"].append(float(np.max(np.abs(obs_env - obs_ours))))

        per_agent, global_mean, collisions = env.pairwise_metrics()
        our_pa, our_gm, our_col = bm.pairwise_metrics(
            env.pos, cfg["formation_radius"], cfg["collision_distance"])
        diffs["pairwise"].append(max(
            float(np.max(np.abs(per_agent - our_pa))),
            abs(global_mean - our_gm),
            float(np.max(np.abs(collisions - our_col)))))

        action = actor.act(obs_ours)

        leader.pos = env.leader_pos.copy()
        leader.vel = env.leader_vel.copy()
        leader.moving = bool(env.formation_complete)
        leader.step()

        errors = np.linalg.norm(env.pos - targets_env, axis=1)
        scales = np.array([[bm.near_target_scale(
            float(errors[i]), bool(env.formation_complete), bm.BRIDGE_CFG)]
            for i in range(env.n)], dtype=np.float32)
        v_cmd = bm.velocity_command(env.vel, action, scales, bm.BRIDGE_CFG)

        obs_env, _, terminated, truncated, info = env.step(
            action.astype(np.float32))
        diffs["leader_pos"].append(float(np.max(np.abs(env.leader_pos - leader.pos))))
        diffs["leader_vel"].append(float(np.max(np.abs(env.leader_vel - leader.vel))))
        diffs["vel_cmd"].append(float(np.max(np.abs(env.vel - v_cmd))))

        tracker.update(float(info["max_position_error"]))
        if tracker.complete != env.formation_complete:
            complete_mismatch += 1
            tracker_lag_steps = max(tracker_lag_steps, 1)

        if terminated or truncated:
            break

    print(f"\nepisode 步数: {t}, terminated={terminated}, truncated={truncated}")
    print(f"{'项目':<14}{'最大误差':>14}{'容差':>10}")
    tol = dict(obs=2e-5, targets=1e-4, leader_pos=1e-4, leader_vel=1e-4,
               vel_cmd=1e-4, pairwise=1e-4)
    ok = True
    for key, values in diffs.items():
        worst = max(values)
        passed = worst <= tol[key]
        ok = ok and passed
        print(f"{key:<14}{worst:>14.3e}{tol[key]:>10.1e}  {'OK' if passed else 'FAIL'}")
    print(f"formation complete 滞后/不一致步数: {tracker_lag_steps}")

    result = bm.evaluate_episode(
        tracker.complete,
        bool(info["leader_reached_goal"]) or terminated,
        info["follow_step_count"],
        info["follow_valid_step_counts"],
        float(info["terminal_max_target_error"]),
        bm.BRIDGE_CFG)
    print(f"\n桥接侧成功判定: {result['full_task_success']}  "
          f"(env: {info['full_task_success']})")
    print(f"跟随保持率 桥接={result['min_follow_retention']:.3f} "
          f"env={info['follow_retention_ratio']:.3f}")
    if not ok:
        raise SystemExit("对拍失败，存在超差项")
    print("\n对拍全部通过：桥接数学与 2D 环境逐步一致。")


if __name__ == "__main__":
    main()
