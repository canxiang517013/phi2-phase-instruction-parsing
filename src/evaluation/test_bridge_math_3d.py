#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_bridge_math_3d.py — 3D 桥接数学与优化版 experiment_core_3d 的逐步对拍

同一 episode 内逐步比较：
  1. 20 维观测逐元素（env.obs() vs build_obs_3d）
  2. 四面体编队目标（env.targets() vs formation_offsets_3d + compute_targets_3d）
  3. 虚拟 leader 运动（env.update_leader vs VirtualLeader，含课程强制步数语义）
  4. 三轴速度指令（env.step 的 vel 积分 vs velocity_command_3d）
  5. 编队完成判定（env vs FormationTracker）
  6. 策略动作（torch actor vs NumpyActor）
并跑完整局，比较两端成功判定。

用法（Windows, phase-llm 环境）：
  python src/evaluation/test_bridge_math_3d.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "nodes" / "edge"))
import mappo_bridge_math as bm  # noqa: E402

ENV_FILE = ROOT / "src" / "training" / "experiment_core_3d.py"
CKPT = (ROOT / "返还主机_20261022" / "07_3D优化版_20261022" / "02_结果"
        / "results_3d" / "baseline_seed21" / "actor_best.pth")
NPZ = ROOT / "assets" / "mappo_3d_seed21_actor_best.npz"


def main() -> None:
    if not ENV_FILE.exists() or not CKPT.exists() or not NPZ.exists():
        print("SKIP: 缺少 3D 训练环境 / checkpoint / npz")
        return

    spec = importlib.util.spec_from_file_location("experiment_core_3d_pai", ENV_FILE)
    ec = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_3d_pai"] = ec
    spec.loader.exec_module(ec)

    cfg = dict(ec.BASE_CFG)
    cfg["episode_len"] = 600
    env = ec.MovingLeaderFormationEnv3D(cfg)
    obs_env, _ = env.reset()
    env.episode_index = 2500  # 课程末段：leader 10 m/s，t>=150 强制起步

    actor = bm.NumpyActor.from_npz(NPZ)
    print(f"actor: obs={actor.obs_dim}, action={actor.action_dim}")

    import torch
    torch_actor = ec.SquashedGaussianActor(obs_dim=obs_env.shape[1])
    torch_actor.load_state_dict(torch.load(str(CKPT), map_location="cpu",
                                           weights_only=True))
    torch_actor.eval()

    offsets = bm.formation_offsets_3d(cfg["formation_radius"])
    leader = bm.VirtualLeader(bm.BRIDGE_CFG_3D)
    tracker = bm.FormationTracker(bm.BRIDGE_CFG_3D)

    diffs = dict(obs=[], targets=[], leader_pos=[], leader_vel=[],
                 vel_cmd=[], action=[], pairwise=[])
    tracker_mismatch = 0

    for t in range(1, 601):
        targets_env = env.targets()
        targets_ours = bm.compute_targets_3d(env.leader_pos, offsets)
        diffs["targets"].append(float(np.max(np.abs(targets_env - targets_ours))))

        obs_ours = bm.build_obs_3d(
            env.pos, env.vel, targets_env, env.leader_pos, env.leader_vel,
            env.formation_phase, env.formation_complete)
        diffs["obs"].append(float(np.max(np.abs(obs_env - obs_ours))))

        action = actor.act(obs_ours)
        with torch.no_grad():
            ref = torch.tanh(torch_actor.net(torch.from_numpy(obs_ours))).numpy()
        diffs["action"].append(float(np.max(np.abs(action - ref))))

        leader.pos = env.leader_pos.copy()
        leader.vel = env.leader_vel.copy()
        leader.moving = env._leader_motion_allowed()
        leader.step()

        targets_new = bm.compute_targets_3d(leader.pos, offsets)
        errors = np.linalg.norm(env.pos - targets_new, axis=1)
        scales = np.array([[bm.near_target_scale(
            float(errors[i]), bool(env.formation_complete), bm.BRIDGE_CFG_3D)]
            for i in range(env.n)], dtype=np.float32)
        v_cmd = bm.velocity_command_3d(env.vel, action, scales, bm.BRIDGE_CFG_3D)

        obs_env, _, terminated, truncated, info = env.step(action.astype(np.float32))
        diffs["leader_pos"].append(float(np.max(np.abs(env.leader_pos - leader.pos))))
        diffs["leader_vel"].append(float(np.max(np.abs(env.leader_vel - leader.vel))))
        diffs["vel_cmd"].append(float(np.max(np.abs(env.vel - v_cmd))))
        per_agent, pair_global, _ = env.pairwise_metrics()
        _, our_pair, _ = bm.pairwise_metrics_3d(
            env.pos, offsets, cfg["collision_distance"])
        diffs["pairwise"].append(abs(pair_global - our_pair))

        tracker.update(float(info["max_position_error"]))
        if tracker.complete != env.formation_complete:
            tracker_mismatch += 1

        if terminated or truncated:
            break

    print(f"\nepisode 步数: {t}, terminated={terminated}, truncated={truncated}")
    tol = dict(obs=2e-5, targets=1e-4, leader_pos=1e-4, leader_vel=1e-4,
               vel_cmd=1e-4, action=1e-4, pairwise=1e-4)
    ok = True
    print(f"{'项目':<14}{'最大误差':>14}{'容差':>10}")
    for key, values in diffs.items():
        worst = max(values) if values else 0.0
        passed = worst <= tol[key]
        ok = ok and passed
        print(f"{key:<14}{worst:>14.3e}{tol[key]:>10.1e}  {'OK' if passed else 'FAIL'}")
    print(f"编队完成判定不一致步数: {tracker_mismatch}")

    result = bm.evaluate_episode(
        tracker.complete, bool(info["leader_reached_goal"]) or terminated,
        info["follow_step_count"], info["follow_valid_step_counts"],
        float(info["terminal_max_target_error"]), bm.BRIDGE_CFG_3D)
    print(f"\n桥接侧成功判定: {result['full_task_success']}  "
          f"(env: {info['full_task_success']})")
    print(f"跟随保持率 桥接={result['min_follow_retention']:.3f} "
          f"env={info['follow_retention_ratio']:.3f}")
    if not ok or tracker_mismatch:
        raise SystemExit("对拍失败，存在超差项")
    print("\n对拍全部通过：3D 桥接数学与优化版训练环境逐步一致。")


if __name__ == "__main__":
    main()
