#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mappo_bridge_math.py — 2D MAPPO 策略 → PX4 仿真的桥接数学（纯 numpy）

与师兄 2D 环境（experiment_core.py 的 MovingLeaderFormationEnv）逐条对齐：
- 14 维观测的构造顺序（pos, vel, rel_target, target, 两个标志, rel_leader, leader_vel）
- 编队目标 = leader + radius*[cos(a), sin(a)]，N=4 时为菱形
- 虚拟 leader 运动：编队完成后以 leader_speed 巡航、leader_accel 限幅、过冲即夹断
- 动作语义：v_cmd = v_actual + a * act_scale * dt * near_scale，速度范数截断
- 编队完成判定：max 位置误差 <= threshold 连续 stable_steps 步
- 成功判定：编队完成 + leader 到达 + 跟随保持率与终端误差阈值

坐标系约定：本模块用 env 平面坐标 (x=east, y=north)，与训练一致；
调用方（ROS 节点）负责 PX4 NED 与 ENU 之间的转换。

不 import rclpy / torch，便于在 Windows 上与 2D 环境离线对拍。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np

# 与 results_repro/baseline_seed555/config_snapshot.json 逐项核对过的 2D 训练配置
BRIDGE_CFG: Dict[str, float] = dict(
    n_agents=4,
    dt=0.1,
    max_speed=15.0,
    act_scale=15.0,
    formation_radius=60.0,
    formation_threshold=20.0,
    formation_stable_steps=5,
    leader_start=(0.0, 0.0),
    leader_target=(200.0, 200.0),
    leader_speed=10.0,
    leader_acceleration=2.0,
    follow_error_threshold=30.0,
    follow_retention_threshold=0.80,
    terminal_follow_error_threshold=30.0,
    episode_len=500,
    leader_goal_radius=5.0,
    near_target_radius=10.0,
    near_target_floor=0.1,
)


class NumpyActor:
    """torch SquashedGaussianActor 的 numpy 等价实现（确定性前向）。

    权重来自 export_actor_npz.py 导出的 npz：w1/b1, w2/b2, w3/b3。
    确定性动作 = tanh(net(obs))，与 evaluate_saved_actor 的用法一致。
    """

    def __init__(self, w1, b1, w2, b2, w3, b3):
        self.w1, self.b1 = w1.astype(np.float32), b1.astype(np.float32)
        self.w2, self.b2 = w2.astype(np.float32), b2.astype(np.float32)
        self.w3, self.b3 = w3.astype(np.float32), b3.astype(np.float32)
        self.obs_dim = int(w1.shape[1])
        self.action_dim = int(w3.shape[0])

    @classmethod
    def from_npz(cls, path) -> "NumpyActor":
        data = np.load(str(path))
        return cls(
            data["w1"], data["b1"], data["w2"], data["b2"], data["w3"], data["b3"]
        )

    def act(self, obs: np.ndarray) -> np.ndarray:
        """obs: (n, obs_dim) -> 动作 (n, action_dim)，范围 (-1, 1)。"""
        obs = np.atleast_2d(np.asarray(obs, dtype=np.float32))
        if obs.shape[1] != self.obs_dim:
            raise ValueError(
                f"obs 维度 {obs.shape[1]} 与权重 {self.obs_dim} 不符"
            )
        h1 = np.tanh(obs @ self.w1.T + self.b1)
        h2 = np.tanh(h1 @ self.w2.T + self.b2)
        return np.tanh(h2 @ self.w3.T + self.b3)


def formation_angles(n: int) -> np.ndarray:
    return np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)


def target_offsets(radius: float, n: int) -> np.ndarray:
    """(n, 2) 编队偏移，与 env.targets() 的 cos/sin 公式一致。"""
    angles = formation_angles(n)
    return np.stack(
        [radius * np.cos(angles), radius * np.sin(angles)], axis=1
    ).astype(np.float32)


def offsets_for(formation: str, radius: float, n: int) -> np.ndarray:
    """RECONFIGURE 支持的编队几何。circle 即训练时的菱形（N=4）；
    line/column 是部署期扩展，策略未在这些几何上训练，仅作演示。"""
    if formation == 'circle':
        return target_offsets(radius, n)
    if formation in ('line', 'column'):
        span = np.linspace(-radius, radius, n)
        if formation == 'line':
            return np.stack([span, np.zeros(n)], axis=1).astype(np.float32)
        return np.stack([np.zeros(n), span], axis=1).astype(np.float32)
    raise ValueError('不支持的编队几何: %r' % formation)


SUPPORTED_FORMATIONS = ('circle', 'line', 'column')


def compute_targets(leader_pos: np.ndarray, radius: float, n: int,
                    formation: str = 'circle') -> np.ndarray:
    return (np.asarray(leader_pos, dtype=np.float32)[None, :]
            + offsets_for(formation, radius, n)).astype(np.float32)


def build_obs(
    pos: np.ndarray,
    vel: np.ndarray,
    targets: np.ndarray,
    leader_pos: np.ndarray,
    leader_vel: np.ndarray,
    formation_phase: bool,
    formation_complete: bool,
) -> np.ndarray:
    """(n,14) 观测，字段顺序与 env.obs() 完全一致。"""
    n = pos.shape[0]
    rows = []
    for i in range(n):
        rows.append(np.concatenate([
            pos[i],
            vel[i],
            targets[i] - pos[i],
            targets[i],
            [float(formation_phase)],
            [float(formation_complete)],
            np.asarray(leader_pos, dtype=np.float32) - pos[i],
            np.asarray(leader_vel, dtype=np.float32),
        ]))
    return np.asarray(rows, dtype=np.float32)


def near_target_scale(error: float, following_active: bool, cfg=None) -> float:
    """接近目标时的动作阻尼，与 env.step() 的 action_scales 一致。"""
    cfg = cfg or BRIDGE_CFG
    if following_active:
        return 1.0
    radius = float(cfg["near_target_radius"])
    if error < radius:
        return max(float(cfg["near_target_floor"]), error / radius)
    return 1.0


def velocity_command(
    v_actual: np.ndarray,
    action: np.ndarray,
    near_scale: np.ndarray,
    cfg=None,
) -> np.ndarray:
    """v_cmd = clip(v_actual + a * act_scale * dt * near_scale, max_speed)。

    near_scale: (n,1) 数组，由调用方按各机 near_target_scale() 算好传入。
    """
    cfg = cfg or BRIDGE_CFG
    v_cmd = v_actual + action * float(cfg["act_scale"]) * float(cfg["dt"]) * near_scale
    speed = np.linalg.norm(v_cmd, axis=-1, keepdims=True)
    limit = float(cfg["max_speed"])
    factor = np.minimum(1.0, limit / np.maximum(speed, 1e-8))
    return (v_cmd * factor).astype(np.float32)


def desired_pair_distance(radius: float, n: int, i: int, j: int) -> float:
    """env.pairwise_metrics() 的期望间距：2*r*sin(angle_diff/2)。"""
    angles = formation_angles(n)
    diff = abs(float(angles[i] - angles[j]))
    angle_diff = min(diff, 2.0 * np.pi - diff)
    return float(2.0 * radius * np.sin(angle_diff / 2.0))


def pairwise_metrics(pos: np.ndarray, radius: float, collision_distance: float = 10.0):
    """返回 (per_agent_mean, global_mean, collision_counts)，与 env 相同口径。"""
    n = pos.shape[0]
    per_agent = [[] for _ in range(n)]
    collisions = np.zeros(n, dtype=np.float32)
    all_errors = []
    for i in range(n):
        for j in range(i + 1, n):
            actual = float(np.linalg.norm(pos[i] - pos[j]))
            desired = desired_pair_distance(radius, n, i, j)
            err = abs(actual - desired)
            all_errors.append(err)
            per_agent[i].append(err)
            per_agent[j].append(err)
            if actual < collision_distance:
                collisions[i] += 1.0
                collisions[j] += 1.0
    per_agent_mean = np.array(
        [np.mean(x) if x else 0.0 for x in per_agent], dtype=np.float32
    )
    global_mean = float(np.mean(all_errors)) if all_errors else 0.0
    return per_agent_mean, global_mean, collisions


class VirtualLeader:
    """虚拟 leader，逐步复刻 env.update_leader() 的运动学。

    moving 由外部 FormationTracker 的 complete 标志驱动（env 里 leader
    只在 formation_complete 后运动；complete 是单向的）。
    """

    def __init__(self, cfg=None):
        cfg = cfg or BRIDGE_CFG
        self.cfg = cfg
        self.pos = np.asarray(cfg["leader_start"], dtype=np.float32).copy()
        self.vel = np.zeros(2, dtype=np.float32)
        self.target = np.asarray(cfg["leader_target"], dtype=np.float32)
        self.moving = False

    def step(self) -> None:
        if not self.moving:
            self.vel = np.zeros(2, dtype=np.float32)
            return
        dt = float(self.cfg["dt"])
        direction = self.target - self.pos
        distance = float(np.linalg.norm(direction))
        if distance <= 1e-8:
            self.pos = self.target.copy()
            self.vel = np.zeros(2, dtype=np.float32)
            return
        desired_speed = min(float(self.cfg["leader_speed"]), distance / dt)
        desired_velocity = direction / distance * desired_speed
        delta_v = desired_velocity - self.vel
        delta_norm = float(np.linalg.norm(delta_v))
        max_delta = float(self.cfg["leader_acceleration"]) * dt
        if delta_norm > max_delta:
            delta_v = delta_v / delta_norm * max_delta
        self.vel = (self.vel + delta_v).astype(np.float32)
        next_pos = self.pos + self.vel * dt
        if float(np.dot(direction, self.target - next_pos)) <= 0.0:
            self.pos = self.target.copy()
            self.vel = np.zeros(2, dtype=np.float32)
        else:
            self.pos = next_pos.astype(np.float32)

    @property
    def reached_goal(self) -> bool:
        return float(np.linalg.norm(self.pos - self.target)) < float(
            self.cfg["leader_goal_radius"]
        )


class FormationTracker:
    """复刻 env.update_completion()：阈值内连续 N 步 → complete（单向）。"""

    def __init__(self, cfg=None):
        cfg = cfg or BRIDGE_CFG
        self.cfg = cfg
        self.stable_count = 0
        self.complete = False
        self.just_completed = False

    def update(self, max_position_error: float) -> bool:
        was = self.complete
        if max_position_error <= float(self.cfg["formation_threshold"]):
            self.stable_count += 1
        else:
            self.stable_count = 0
        if self.stable_count >= int(self.cfg["formation_stable_steps"]):
            self.complete = True
        self.just_completed = bool(self.complete and not was)
        return self.just_completed

    @property
    def phase_flag(self) -> bool:
        return not self.complete


def evaluate_episode(
    formation_complete: bool,
    leader_reached: bool,
    follow_step_count: int,
    per_agent_valid_steps,
    terminal_max_error: float,
    cfg=None,
) -> Dict[str, object]:
    """按 env 的 full_task_success 口径汇总一次 episode 的结果。"""
    cfg = cfg or BRIDGE_CFG
    if follow_step_count > 0:
        retention = [
            float(v) / float(follow_step_count) for v in per_agent_valid_steps
        ]
        min_retention = float(min(retention))
    else:
        retention = [0.0] * len(per_agent_valid_steps)
        min_retention = 0.0
    success = bool(
        formation_complete
        and leader_reached
        and follow_step_count > 0
        and min_retention >= float(cfg["follow_retention_threshold"])
        and terminal_max_error <= float(cfg["terminal_follow_error_threshold"])
    )
    return {
        "formation_complete": bool(formation_complete),
        "leader_reached_goal": bool(leader_reached),
        "follow_step_count": int(follow_step_count),
        "per_agent_follow_retention": retention,
        "min_follow_retention": min_retention,
        "terminal_max_target_error": float(terminal_max_error),
        "full_task_success": success,
    }
