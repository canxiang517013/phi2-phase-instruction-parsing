#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3D multi-UAV MAPPO comparison experiment (extended from 2D).

Main corrections relative to the original script:
1. Ten preregistered random seeds and sample standard deviation (ddof=1).
2. Per-seed final success rate is computed from raw success flags in the last
   100 episodes; final errors are also last-100-episode means.
3. Defines success as completion of the full task: all-agent formation
   acquisition, continuous per-agent tracking, and leader arrival.
4. Reports both First Full-Task Success and a persistent Stable Breakthrough.
5. Separates LLM consultations, intervention events, and parameter updates.
6. Uses matched intervention schedules for Uniform-LLM and Random baselines.
7. Makes w_formation effective in the reward and fixes the unreachable
   one-time success reward.
8. Uses acquisition success for Early-to-Mid and acquisition reliability plus
   following error for Mid-to-Late phase detection.
9. Implements actual smoothing, clipping, whitelisting, and logging of every
   meta-control decision.
10. Corrects terminal bootstrapping and critic value clipping in PPO.
11. Gives followers speed margin over the leader, applies smooth leader
    acceleration, and exposes leader velocity to the actor and critic.
12. Fails fast when Ollama is unavailable instead of silently replacing an
    LLM method with the baseline.

The script intentionally writes detailed JSON/CSV artifacts so every reported
paper statistic can be audited without rerunning training.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import requests
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal

try:
    from torch.utils.tensorboard import SummaryWriter
except ModuleNotFoundError:
    class SummaryWriter:  # type: ignore[override]
        """No-op fallback when the optional tensorboard package is absent."""
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            print("WARNING: tensorboard is not installed; TensorBoard logging is disabled.")

        def add_scalar(self, *args: Any, **kwargs: Any) -> None:
            return None

        def close(self) -> None:
            return None


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_CFG: Dict[str, Any] = dict(
    n_agents=4,
    episode_len=600,
    episodes=2500,
    final_window=100,

    # Reproducibility and environment variants. env_seed is overwritten for
    # every run so paired methods see the same stochastic stream.
    env_seed=0,
    leader_start=[0.0, 0.0, 40.0],
    leader_target=[200.0, 200.0, 45.0],
    randomize_start_positions=False,
    start_position_jitter=0.0,
    start_position_bounds=[-120.0, 120.0, -120.0, 120.0, 2.0, 100.0],
    start_min_separation=20.0,
    observation_noise_std=0.0,
    action_noise_std=0.0,
    collision_free_success_required=False,
    collision_penalty=0.0,
    controller_type=None,
    matched_schedule_source='phase_aware',
    initial_actor_path=None,
    gamma=0.99,
    gae_lambda=0.95,
    ppo_epochs=4,
    actor_lr=1e-4,
    critic_lr=3e-4,
    dt=0.1,
    max_speed=15.0,
    max_vertical_speed=8.0,
    min_altitude=2.0,
    max_altitude=100.0,
    leader_speed=10.0,
    leader_acceleration=2.0,
    act_scale=15.0,
    formation_radius=60.0,
    formation_threshold=25.0,
    formation_stable_steps=5,
    # Nearest-quadrant assignment for the regular tetrahedron. The raw vertex
    # order sends two followers across the whole formation (192 m initial
    # error) and was a major source of collisions.
    formation_offset_order=[0, 2, 3, 1],

    # Full-task success definition. After all followers acquire their own
    # targets, each follower is evaluated independently during the moving-target
    # stage. An episode succeeds only if the leader reaches its destination,
    # every follower meets the configured retention fraction, and all followers
    # satisfy the terminal target-error threshold.
    follow_error_threshold=30.0,
    follow_retention_threshold=0.80,
    terminal_follow_error_threshold=30.0,

    collision_distance=10.0,
    device="cuda" if torch.cuda.is_available() else "cpu",
    clip_param=0.2,
    # Returns are normalised by a running reward std, so the old 0.5 value
    # clip would throttle the critic. 0 disables value clipping entirely.
    value_clip=0.0,
    entropy_coef=0.002,
    entropy_coef_max=0.003,
    max_grad_norm=1.0,
    log_std_init=-0.5,
    critic_hidden=256,
    minibatch_size=256,
    reward_normalization=True,
    reward_clip=100.0,

    # Reward scales. The four adjustable quantities are w_position,
    # w_formation, w_success, and entropy_coef.
    # Core task reward only: target tracking, geometric formation, and success.
    # Collision is logged as an auxiliary diagnostic, but is not optimized and
    # is not shown to the LLM. Velocity matching is intentionally excluded.
    reward_scales=dict(
        position=0.5,
        formation=0.2,
        success_event=10.0,
        success_maintenance=5.0,
    ),
    # 3-D-only shaping: penalise velocity mismatch with the moving leader.
    # Pure position feedback has a steady-state lag of leader_speed/kp
    # (about 66 m in the diagnostic PD controller). A feedforward signal is
    # needed for the policy to track the leader without that lag.
    velocity_reward_weight=0.08,

    # Leader-motion curriculum: the leader stays still for the first stage,
    # then starts moving at a fixed step even if formation is not acquired.
    # This prevents the "no acquisition -> never see a moving leader" trap.
    curriculum_enabled=True,
    curriculum_static_episodes=600,
    curriculum_forced_start_step=150,
    curriculum_speed_schedule=[(600, 5.0), (1400, 8.0), (2000, 10.0)],

    # Phase detection: monotonic early -> mid -> late.
    phase_detection_mode="metrics",  # "metrics" or "fixed"
    phase_window=100,
    phase_patience=5,
    phase_boundaries={"early_end": 800, "mid_end": 1800},
    phase_episode_fallback={"mid": 800, "late": 1800},
    early_to_mid=dict(min_episode=200, acquisition_rate=0.05, mean_error=60.0),
    mid_to_late=dict(
        min_episode=600,
        acquisition_rate=0.80,
        mean_follow_error=30.0,
    ),

    phase_consult_intervals={"early": 30, "mid": 50, "late": 100},
    phase_param_whitelist={
        "early": ["entropy_coef", "w_position", "w_formation"],
        "mid": ["w_position", "w_formation", "w_success", "entropy_coef"],
        "late": ["w_position", "w_formation"],
        "uniform": ["w_position", "w_formation", "w_success", "entropy_coef"],
    },
    phase_max_adjustments={"early": 2, "mid": 2, "late": 1, "uniform": 2},
    phase_smoothing={"early": 0.80, "mid": 0.50, "late": 0.25, "uniform": 0.50},
    phase_adjustment_multipliers={
        "early": {
            "轻微": {"增加": 1.20, "减少": 0.80},
            "中等": {"增加": 1.35, "减少": 0.65},
            "显著": {"增加": 1.50, "减少": 0.50},
        },
        "mid": {
            "轻微": {"增加": 1.10, "减少": 0.90},
            "中等": {"增加": 1.20, "减少": 0.80},
            "显著": {"增加": 1.30, "减少": 0.70},
        },
        "late": {
            "轻微": {"增加": 1.03, "减少": 0.97},
            "中等": {"增加": 1.05, "减少": 0.95},
            "显著": {"增加": 1.08, "减少": 0.92},
        },
        # Uniform LLM intentionally uses one fixed rule in all phases.
        "uniform": {
            "轻微": {"增加": 1.10, "减少": 0.90},
            "中等": {"增加": 1.20, "减少": 0.80},
            "显著": {"增加": 1.30, "减少": 0.70},
        },
    },
    param_stability={
        "w_position": {"min": 0.3, "max": 2.0, "default": 1.0},
        "w_formation": {"min": 0.3, "max": 2.0, "default": 0.8},
        "w_success": {"min": 5.0, "max": 30.0, "default": 10.0},
        "entropy_coef": {"min": 0.001, "max": 0.003, "default": 0.002},
    },
    param_min_update_interval=100,
    save_best_checkpoint=True,
    min_effective_change_pct=1.0,

    # Persistent stable-breakthrough definition used for paper reporting.
    stable_breakthrough_window=100,
    stable_breakthrough_rate=0.80,
    stable_breakthrough_hold=50,

    llm_model="deepseek-r1:14b",
    ollama_base_url="http://localhost:11434",
    llm_timeout=120,
    llm_temperature=0.0,

    tensorboard_log_interval=10,
    save_model_interval=500,
    results_dir="comparison_results_3d",
)

DEFAULT_SEEDS_10: List[int] = [
    21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888
]

FIXED_START_POSITIONS = np.array(
    [[100.0, 100.0, 10.0], [-100.0, 100.0, 10.0],
     [-100.0, -100.0, 10.0], [100.0, -100.0, 10.0]],
    dtype=np.float32,
)

# 3D tetrahedral formation offsets (normalized to unit sphere)
TETRAHEDRON_OFFSETS = np.array(
    [[ 1.0,  1.0,  1.0],
     [ 1.0, -1.0, -1.0],
     [-1.0,  1.0, -1.0],
     [-1.0, -1.0,  1.0]],
    dtype=np.float32,
) / np.sqrt(3.0)

def fibonacci_sphere(n: int) -> np.ndarray:
    """N points approximately uniform on a unit sphere."""
    pts = np.zeros((n, 3), dtype=np.float32)
    golden = np.pi * (3.0 - np.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / max(n - 1, 1)) * 2.0
        r = np.sqrt(max(1.0 - y * y, 0.0))
        theta = golden * i
        pts[i] = [np.cos(theta) * r, np.sin(theta) * r, y]
    return pts

METHOD_LABELS = {
    'baseline': 'Baseline MAPPO',
    'phase_aware': 'Phase-Aware LLM (Ours)',
    'uniform_matched': 'Uniform LLM (Schedule-Matched)',
    'random_matched': 'Random Meta-Control (Schedule-and-Budget-Matched)',
    'rule_based': 'Rule-Based Phase Controller',
}

METHOD_COLORS = {
    'baseline': '#6B7280',
    'random_matched': '#F59E0B',
    'uniform_matched': '#8B5CF6',
    'phase_aware': '#10B981',
    'rule_based': '#2563EB',
}


# -----------------------------------------------------------------------------
# Utilities and statistics
# -----------------------------------------------------------------------------
def set_global_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    # Deterministic settings improve reproducibility. Some CUDA operations may
    # still vary by platform/version; the run metadata records the environment.
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def sample_std(values: Sequence[float]) -> float:
    arr = np.asarray(values, dtype=float)
    return float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0


def mean_std(values: Sequence[float]) -> Tuple[float, float]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return float("nan"), float("nan")
    return float(np.mean(arr)), sample_std(arr)


def rolling_mean(values: Sequence[float], window: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return np.array([], dtype=float)
    if arr.size < window:
        return np.array([float(np.mean(arr))], dtype=float)
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(arr, kernel, mode="valid")


def stable_breakthrough_episode(
    success_history: Sequence[int],
    window: int,
    threshold: float,
    hold: int,
) -> Optional[int]:
    """Return a 1-based persistent breakthrough episode.

    A candidate is the end of the first rolling window whose success rate is at
    least threshold and remains at least threshold for the following `hold`
    rolling-window endpoints. This rejects a one-off lucky success burst.
    """
    success = np.asarray(success_history, dtype=float)
    if success.size < window:
        return None
    rates = np.convolve(success, np.ones(window) / window, mode="valid")
    last_start = len(rates) - hold
    for i in range(max(0, last_start)):
        if np.all(rates[i : i + hold + 1] >= threshold):
            # rates[0] ends at episode `window` in 1-based indexing.
            return int(i + window)
    return None


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
class MovingLeaderFormationEnv3D:
    """Continuous 3-D moving-leader formation benchmark.

    The primary experiment remains identical to the original configuration.
    Route, initial-position, observation-noise, action-noise, agent-count, and
    collision-aware-success switches are exposed only for controlled follow-up
    experiments.
    """

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.n = int(cfg["n_agents"])
        self.dt = float(cfg["dt"])
        self.max_speed = float(cfg["max_speed"])
        self.leader_speed = float(cfg["leader_speed"])
        self.leader_acceleration = float(cfg["leader_acceleration"])
        if self.leader_speed >= self.max_speed:
            raise ValueError(
                "leader_speed must be strictly lower than max_speed so followers "
                "retain velocity margin for target-error correction."
            )
        if self.leader_acceleration <= 0.0:
            raise ValueError("leader_acceleration must be positive.")
        self.radius = float(cfg["formation_radius"])
        self.formation_threshold = float(cfg["formation_threshold"])
        self.angles = np.linspace(0, 2 * np.pi, self.n, endpoint=False)  # kept for compat
        if self.n == 4:
            order = self.cfg.get("formation_offset_order")
            if order is None:
                order = [0, 1, 2, 3]
            if sorted(int(x) for x in order) != [0, 1, 2, 3]:
                raise ValueError(
                    "formation_offset_order must be a permutation of [0, 1, 2, 3]."
                )
            self.formation_offsets = TETRAHEDRON_OFFSETS[list(order)].copy()
        else:
            self.formation_offsets = fibonacci_sphere(self.n)
        self.base_seed = int(cfg.get("env_seed", 0))
        self.reset_index = -1
        self.episode_index = 0
        self.rng = np.random.default_rng(self.base_seed)
        self.nominal_start_positions = self._build_nominal_start_positions()
        self.reward_weights = {
            "position": 1.0,
            "formation": 0.8,
            "success": 10.0,
        }
        self.reset()

    def _build_nominal_start_positions(self) -> np.ndarray:
        supplied = self.cfg.get("start_positions")
        if supplied is not None:
            arr = np.asarray(supplied, dtype=np.float32)
            if arr.shape != (self.n, 3):
                raise ValueError(
                    f"start_positions must have shape {(self.n, 3)}, got {arr.shape}."
                )
            return arr.copy()
        if self.n == 4:
            return FIXED_START_POSITIONS.copy()
        radius = max(100.0, 1.8 * float(self.cfg["formation_radius"]))
        return (radius * fibonacci_sphere(self.n)).astype(np.float32)

    def _sample_random_start_positions(self) -> np.ndarray:
        bounds = [float(x) for x in self.cfg["start_position_bounds"]]
        if len(bounds) != 6:
            raise ValueError("start_position_bounds must be [xmin,xmax,ymin,ymax,zmin,zmax].")
        xmin, xmax, ymin, ymax, zmin, zmax = bounds
        min_sep = float(self.cfg.get("start_min_separation", 0.0))
        points: List[np.ndarray] = []
        for _agent in range(self.n):
            for _attempt in range(5000):
                candidate = np.array(
                    [self.rng.uniform(xmin, xmax), self.rng.uniform(ymin, ymax),
                     self.rng.uniform(zmin, zmax)],
                    dtype=np.float32,
                )
                if all(float(np.linalg.norm(candidate - p)) >= min_sep for p in points):
                    points.append(candidate)
                    break
            else:
                raise RuntimeError(
                    "Could not sample collision-separated start positions. "
                    "Increase the bounds or lower start_min_separation."
                )
        return np.asarray(points, dtype=np.float32)

    def reset(self) -> Tuple[np.ndarray, np.ndarray]:
        # Episode-specific RNG prevents different termination times from shifting
        # the random stream of later paired episodes.
        self.reset_index += 1
        self.episode_index = self.reset_index + 1
        self.rng = np.random.default_rng(
            np.random.SeedSequence([self.base_seed, self.reset_index])
        )
        if bool(self.cfg.get("randomize_start_positions", False)):
            self.pos = self._sample_random_start_positions()
        else:
            jitter = float(self.cfg.get("start_position_jitter", 0.0))
            self.pos = self.nominal_start_positions.copy()
            if jitter > 0.0:
                self.pos += self.rng.uniform(
                    -jitter, jitter, size=self.pos.shape
                ).astype(np.float32)
        self.vel = np.zeros((self.n, 3), dtype=np.float32)
        self.leader_pos = np.asarray(
            self.cfg.get("leader_start", [0.0, 0.0, 20.0]), dtype=np.float32
        ).copy()
        self.leader_vel = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.leader_target = np.asarray(
            self.cfg.get("leader_target", [200.0, 200.0, 25.0]), dtype=np.float32
        ).copy()
        if self.leader_target.shape != (3,):
            raise ValueError("leader_target must contain exactly three coordinates.")
        self.formation_stable_count = 0
        self.formation_complete = False
        self.formation_phase = True
        self.formation_acquired_step: Optional[int] = None
        self.follow_step_count = 0
        self.follow_valid_step_counts = np.zeros(self.n, dtype=np.int64)
        self.follow_position_error_sum = 0.0
        self.follow_pairwise_error_sum = 0.0
        self.episode_collision_count = 0
        self.episode_had_collision = False
        self.t = 0
        return self.obs(), self.global_state()

    def targets(self) -> np.ndarray:
        offsets = self.radius * self.formation_offsets
        return (self.leader_pos[None, :] + offsets).astype(np.float32)

    def obs(self) -> np.ndarray:
        targets = self.targets()
        observations = []
        for i in range(self.n):
            observations.append(
                np.concatenate(
                    [
                        self.pos[i],
                        self.vel[i],
                        targets[i] - self.pos[i],
                        targets[i],
                        [float(self.formation_phase)],
                        [float(self.formation_complete)],
                        self.leader_pos - self.pos[i],
                        self.leader_vel,
                    ]
                )
            )
        obs = np.asarray(observations, dtype=np.float32)
        sigma = float(self.cfg.get("observation_noise_std", 0.0))
        if sigma > 0.0:
            obs = obs + self.rng.normal(0.0, sigma, size=obs.shape).astype(np.float32)
        return obs

    def global_state(self) -> np.ndarray:
        return np.concatenate(
            [
                self.pos.flatten(),
                self.vel.flatten(),
                self.leader_pos,
                self.leader_vel,
                [float(self.formation_phase)],
                [float(self.formation_complete)],
            ]
        ).astype(np.float32)

    def _leader_speed_for_episode(self) -> float:
        if not bool(self.cfg.get("curriculum_enabled", False)):
            return self.leader_speed
        speed = self.leader_speed
        for start_episode, stage_speed in self.cfg.get("curriculum_speed_schedule", []):
            if self.episode_index >= int(start_episode):
                speed = float(stage_speed)
        return speed

    def _leader_motion_allowed(self) -> bool:
        if not bool(self.cfg.get("curriculum_enabled", False)):
            return self.formation_complete
        if self.episode_index <= int(self.cfg.get("curriculum_static_episodes", 0)):
            return self.formation_complete
        # After the static stage the leader moves at a fixed step even when the
        # formation is incomplete, so the policy always receives tracking data.
        forced_step = int(self.cfg.get("curriculum_forced_start_step", 10**9))
        return self.formation_complete or self.t >= forced_step

    def update_leader(self) -> None:
        if not self._leader_motion_allowed():
            self.leader_vel = np.zeros(3, dtype=np.float32)
            return
        direction = self.leader_target - self.leader_pos
        distance = float(np.linalg.norm(direction))
        if distance <= 1e-8:
            self.leader_pos = self.leader_target.copy()
            self.leader_vel = np.zeros(3, dtype=np.float32)
            return
        speed_limit = self._leader_speed_for_episode()
        desired_speed = min(speed_limit, distance / self.dt)
        desired_velocity = direction / distance * desired_speed
        delta_v = desired_velocity - self.leader_vel
        delta_norm = float(np.linalg.norm(delta_v))
        max_delta = self.leader_acceleration * self.dt
        if delta_norm > max_delta:
            delta_v = delta_v / delta_norm * max_delta
        self.leader_vel = (self.leader_vel + delta_v).astype(np.float32)
        next_pos = self.leader_pos + self.leader_vel * self.dt
        remaining = self.leader_target - next_pos
        if float(np.dot(direction, remaining)) <= 0.0:
            self.leader_pos = self.leader_target.copy()
            self.leader_vel = np.zeros(3, dtype=np.float32)
        else:
            self.leader_pos = next_pos.astype(np.float32)

    def pairwise_metrics(self) -> Tuple[np.ndarray, float, np.ndarray]:
        per_agent_errors: List[List[float]] = [[] for _ in range(self.n)]
        collision_counts = np.zeros(self.n, dtype=np.float32)
        all_pair_errors: List[float] = []
        for i in range(self.n):
            for j in range(i + 1, self.n):
                actual = float(np.linalg.norm(self.pos[i] - self.pos[j]))
                diff = float(np.linalg.norm(
                    self.formation_offsets[i] - self.formation_offsets[j]))
                desired = diff * self.radius
                pair_error = abs(actual - desired)
                all_pair_errors.append(pair_error)
                per_agent_errors[i].append(pair_error)
                per_agent_errors[j].append(pair_error)
                if actual < float(self.cfg["collision_distance"]):
                    collision_counts[i] += 1.0
                    collision_counts[j] += 1.0
        per_agent_mean = np.array(
            [np.mean(x) if x else 0.0 for x in per_agent_errors], dtype=np.float32
        )
        global_mean = float(np.mean(all_pair_errors)) if all_pair_errors else 0.0
        return per_agent_mean, global_mean, collision_counts

    def update_completion(self, max_position_error: float) -> bool:
        was_complete = self.formation_complete
        if max_position_error <= self.formation_threshold:
            self.formation_stable_count += 1
        else:
            self.formation_stable_count = 0
        if self.formation_stable_count >= int(self.cfg["formation_stable_steps"]):
            self.formation_complete = True
            if not was_complete:
                self.formation_acquired_step = self.t
        self.formation_phase = not self.formation_complete
        return bool(self.formation_complete and not was_complete)

    def calculate_rewards(
        self,
        position_errors: np.ndarray,
        pairwise_errors: np.ndarray,
        collision_counts: np.ndarray,
        just_completed: bool,
    ) -> np.ndarray:
        w = self.reward_weights
        scale = self.cfg["reward_scales"]
        rewards = (
            -float(scale["position"]) * w["position"] * position_errors
            -float(scale["formation"]) * w["formation"] * pairwise_errors
        ).astype(np.float32)
        rewards += np.where(position_errors < 20.0, 2.0, 0.0)
        rewards += np.where(position_errors < 10.0, 5.0, 0.0)
        rewards += np.where(position_errors < 5.0, 10.0, 0.0)
        rewards += np.where(position_errors < 2.0, 20.0, 0.0)
        collision_penalty = float(self.cfg.get("collision_penalty", 0.0))
        if collision_penalty > 0.0:
            rewards -= collision_penalty * collision_counts
        if just_completed:
            rewards += float(scale["success_event"]) * w["success"]
        if self.formation_complete and float(np.max(position_errors)) < 5.0:
            rewards += float(scale["success_maintenance"]) * w["success"]
        vel_weight = float(self.cfg.get("velocity_reward_weight", 0.0))
        leader_moving = float(np.linalg.norm(self.leader_vel)) > 0.1
        if vel_weight > 0.0 and (self.formation_complete or leader_moving):
            velocity_error = np.linalg.norm(
                self.vel - self.leader_vel[None, :], axis=1
            )
            rewards -= vel_weight * velocity_error ** 2
        reward_clip = float(self.cfg.get("reward_clip", 0.0))
        if reward_clip > 0.0:
            rewards = np.clip(rewards, -reward_clip, reward_clip)
        return rewards.astype(np.float32)

    def step(
        self, actions: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, bool, bool, Dict[str, Any]]:
        self.t += 1
        following_active = bool(self.formation_complete)
        self.update_leader()
        actions = np.asarray(actions, dtype=np.float32)
        action_sigma = float(self.cfg.get("action_noise_std", 0.0))
        if action_sigma > 0.0:
            actions = actions + self.rng.normal(
                0.0, action_sigma, size=actions.shape
            ).astype(np.float32)
        actions = np.clip(actions, -1.0, 1.0)
        targets_before_motion = self.targets()
        action_scales = np.ones_like(actions)
        for i in range(self.n):
            error = float(np.linalg.norm(self.pos[i] - targets_before_motion[i]))
            if not following_active and error < 10.0:
                action_scales[i] = max(0.1, error / 10.0)
        self.vel += actions * float(self.cfg["act_scale"]) * action_scales * self.dt
        # 3D: horizontal/vertical split-axis speed limiting
        h_speed = np.linalg.norm(self.vel[:, :2], axis=1, keepdims=True)
        safe_h = np.maximum(h_speed, 1e-8)
        self.vel[:, :2] = np.where(
            h_speed > self.max_speed,
            self.vel[:, :2] / safe_h * self.max_speed,
            self.vel[:, :2],
        )
        max_v = float(self.cfg.get("max_vertical_speed", 8.0))
        self.vel[:, 2] = np.clip(self.vel[:, 2], -max_v, max_v)
        self.pos += self.vel * self.dt
        # 3D: altitude hard bounds
        min_alt = float(self.cfg.get("min_altitude", 0.0))
        max_alt = float(self.cfg.get("max_altitude", 1e9))
        self.pos[:, 2] = np.clip(self.pos[:, 2], min_alt, max_alt)
        targets = self.targets()
        position_errors = np.linalg.norm(self.pos - targets, axis=1)
        avg_position_error = float(np.mean(position_errors))
        max_position_error = float(np.max(position_errors))
        pairwise_per_agent, pairwise_global, collision_counts = self.pairwise_metrics()
        step_collisions = int(np.sum(collision_counts) / 2)
        self.episode_collision_count += step_collisions
        self.episode_had_collision = self.episode_had_collision or step_collisions > 0
        just_completed = self.update_completion(max_position_error)
        if following_active:
            self.follow_step_count += 1
            self.follow_position_error_sum += avg_position_error
            self.follow_pairwise_error_sum += pairwise_global
            self.follow_valid_step_counts += (
                position_errors <= float(self.cfg["follow_error_threshold"])
            ).astype(np.int64)
        rewards = self.calculate_rewards(
            position_errors, pairwise_per_agent, collision_counts, just_completed
        )
        leader_distance = float(np.linalg.norm(self.leader_pos - self.leader_target))
        terminated = leader_distance < 5.0
        truncated = self.t >= int(self.cfg["episode_len"])
        leader_reached_goal = bool(terminated)
        if self.follow_step_count > 0:
            per_agent_follow_retention = (
                self.follow_valid_step_counts.astype(np.float64)
                / float(self.follow_step_count)
            )
            follow_retention_ratio = float(np.min(per_agent_follow_retention))
            mean_follow_retention_ratio = float(np.mean(per_agent_follow_retention))
        else:
            per_agent_follow_retention = np.zeros(self.n, dtype=np.float64)
            follow_retention_ratio = 0.0
            mean_follow_retention_ratio = 0.0
        avg_follow_position_error = (
            self.follow_position_error_sum / float(self.follow_step_count)
            if self.follow_step_count > 0
            else avg_position_error
        )
        avg_follow_pairwise_error = (
            self.follow_pairwise_error_sum / float(self.follow_step_count)
            if self.follow_step_count > 0
            else pairwise_global
        )
        task_success_without_safety = bool(
            self.formation_complete
            and leader_reached_goal
            and self.follow_step_count > 0
            and follow_retention_ratio
            >= float(self.cfg["follow_retention_threshold"])
            and max_position_error
            <= float(self.cfg["terminal_follow_error_threshold"])
        )
        safe_full_task_success = bool(
            task_success_without_safety and not self.episode_had_collision
        )
        full_task_success = (
            safe_full_task_success
            if bool(self.cfg.get("collision_free_success_required", False))
            else task_success_without_safety
        )
        info = {
            "avg_position_error": avg_position_error,
            "max_position_error": max_position_error,
            "avg_pairwise_formation_error": pairwise_global,
            "collision_count": step_collisions,
            "episode_collision_count": int(self.episode_collision_count),
            "episode_had_collision": bool(self.episode_had_collision),
            "formation_complete": bool(self.formation_complete),
            "formation_acquired": bool(self.formation_complete),
            "formation_acquired_step": self.formation_acquired_step,
            "just_completed": bool(just_completed),
            "formation_stable_count": int(self.formation_stable_count),
            "leader_reached_goal": leader_reached_goal,
            "follow_step_count": int(self.follow_step_count),
            "follow_valid_step_count": int(np.min(self.follow_valid_step_counts)),
            "follow_valid_step_counts": self.follow_valid_step_counts.astype(int).tolist(),
            "per_agent_follow_retention": per_agent_follow_retention.astype(float).tolist(),
            "follow_retention_ratio": follow_retention_ratio,
            "mean_follow_retention_ratio": mean_follow_retention_ratio,
            "avg_follow_position_error": float(avg_follow_position_error),
            "avg_follow_pairwise_error": float(avg_follow_pairwise_error),
            "terminal_max_target_error": max_position_error,
            "task_success_without_safety": task_success_without_safety,
            "safe_full_task_success": safe_full_task_success,
            "full_task_success": full_task_success,
            "positions": self.pos.astype(float).tolist(),
            "leader_pos": self.leader_pos.astype(float).tolist(),
        }
        return self.obs(), rewards, terminated, truncated, info

    def update_reward_weights(self, new_weights: Dict[str, float]) -> None:
        for key, value in new_weights.items():
            if key in self.reward_weights:
                self.reward_weights[key] = float(value)


# -----------------------------------------------------------------------------
# Networks and PPO
# -----------------------------------------------------------------------------
class SquashedGaussianActor(nn.Module):
    def __init__(self, obs_dim: int, log_std_init: float = 0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 64),
            nn.Tanh(),
            nn.Linear(64, 64),
            nn.Tanh(),
            nn.Linear(64, 3),
        )
        self.log_std = nn.Parameter(torch.full((3,), float(log_std_init)))

    def distribution(self, obs: torch.Tensor) -> Normal:
        mean = self.net(obs)
        std = torch.exp(torch.clamp(self.log_std, -5.0, 2.0))
        return Normal(mean, std)

    def sample_action(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        dist = self.distribution(obs)
        raw = dist.rsample()
        action = torch.tanh(raw)
        log_prob = dist.log_prob(raw) - torch.log(1.0 - action.pow(2) + 1e-6)
        return action, log_prob.sum(dim=-1)

    def evaluate_actions(
        self, obs: torch.Tensor, actions: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        clipped = torch.clamp(actions, -0.999999, 0.999999)
        raw = 0.5 * (torch.log1p(clipped) - torch.log1p(-clipped))
        dist = self.distribution(obs)
        log_prob = dist.log_prob(raw) - torch.log(1.0 - clipped.pow(2) + 1e-6)
        entropy_proxy = dist.entropy().sum(dim=-1)
        return log_prob.sum(dim=-1), entropy_proxy


class CentralizedCritic(nn.Module):
    def __init__(self, state_dim: int, n_agents: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, n_agents),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state)


@dataclass
class Rollout:
    observations: np.ndarray
    states: np.ndarray
    actions: np.ndarray
    old_log_probs: np.ndarray
    rewards: np.ndarray
    values: np.ndarray
    terminated: np.ndarray
    last_state: np.ndarray
    last_terminated: bool


def compute_gae(
    rewards: np.ndarray,
    values: np.ndarray,
    terminated: np.ndarray,
    last_value: np.ndarray,
    gamma: float,
    gae_lambda: float,
) -> Tuple[np.ndarray, np.ndarray]:
    t_steps, n_agents = rewards.shape
    advantages = np.zeros_like(rewards, dtype=np.float32)
    gae = np.zeros(n_agents, dtype=np.float32)
    for t in reversed(range(t_steps)):
        if t == t_steps - 1:
            next_value = last_value
            nonterminal = 0.0 if terminated[t] else 1.0
        else:
            next_value = values[t + 1]
            nonterminal = 0.0 if terminated[t] else 1.0
        delta = rewards[t] + gamma * next_value * nonterminal - values[t]
        gae = delta + gamma * gae_lambda * nonterminal * gae
        advantages[t] = gae
    returns = advantages + values
    return advantages, returns


class RunningStat:
    """Running mean/variance (Welford) for reward normalisation."""

    def __init__(self) -> None:
        self.mean = 0.0
        self.m2 = 0.0
        self.count = 1e-4

    def update(self, values: np.ndarray) -> None:
        x = np.asarray(values, dtype=np.float64).reshape(-1)
        n = int(x.size)
        if n == 0:
            return
        batch_mean = float(x.mean())
        batch_m2 = float(((x - batch_mean) ** 2).sum())
        total = self.count + n
        delta = batch_mean - self.mean
        self.mean += delta * n / total
        self.m2 += batch_m2 + delta ** 2 * self.count * n / total
        self.count = total

    @property
    def std(self) -> float:
        return float(np.sqrt(self.m2 / self.count + 1e-8))


def ppo_update(
    actor: SquashedGaussianActor,
    critic: CentralizedCritic,
    actor_optimizer: optim.Optimizer,
    critic_optimizer: optim.Optimizer,
    rollout: Rollout,
    entropy_coef: float,
    cfg: Dict[str, Any],
) -> Dict[str, float]:
    device = cfg["device"]
    with torch.no_grad():
        if rollout.last_terminated:
            last_value = np.zeros(cfg["n_agents"], dtype=np.float32)
        else:
            last_state_t = torch.tensor(
                rollout.last_state[None, :], dtype=torch.float32, device=device
            )
            last_value = critic(last_state_t)[0].cpu().numpy().astype(np.float32)

    advantages, returns = compute_gae(
        rollout.rewards,
        rollout.values,
        rollout.terminated,
        last_value,
        float(cfg["gamma"]),
        float(cfg["gae_lambda"]),
    )
    adv_flat = advantages.reshape(-1)
    adv_flat = (adv_flat - adv_flat.mean()) / (adv_flat.std() + 1e-8)

    obs_t = torch.tensor(
        rollout.observations.reshape(-1, rollout.observations.shape[-1]),
        dtype=torch.float32,
        device=device,
    )
    actions_t = torch.tensor(
        rollout.actions.reshape(-1, rollout.actions.shape[-1]),
        dtype=torch.float32,
        device=device,
    )
    old_logp_t = torch.tensor(
        rollout.old_log_probs.reshape(-1), dtype=torch.float32, device=device
    )
    adv_t = torch.tensor(adv_flat, dtype=torch.float32, device=device)

    states_t = torch.tensor(rollout.states, dtype=torch.float32, device=device)
    old_values_t = torch.tensor(rollout.values, dtype=torch.float32, device=device)
    returns_t = torch.tensor(returns, dtype=torch.float32, device=device)

    n_actor = int(obs_t.shape[0])
    n_critic = int(states_t.shape[0])
    batch_size = int(cfg.get("minibatch_size", 0) or 0)
    if batch_size <= 0:
        actor_batch = n_actor
        critic_batch = n_critic
    else:
        actor_batch = min(batch_size, n_actor)
        critic_batch = min(batch_size, n_critic)
    value_clip = float(cfg.get("value_clip", 0.0))

    actor_loss_sum = 0.0
    critic_loss_sum = 0.0
    actor_samples = 0
    critic_samples = 0
    for _ in range(int(cfg["ppo_epochs"])):
        actor_perm = torch.randperm(n_actor, device=device)
        for start in range(0, n_actor, actor_batch):
            idx = actor_perm[start:start + actor_batch]
            new_logp, entropy = actor.evaluate_actions(obs_t[idx], actions_t[idx])
            ratio = torch.exp(new_logp - old_logp_t[idx])
            surrogate_1 = ratio * adv_t[idx]
            surrogate_2 = torch.clamp(
                ratio, 1.0 - float(cfg["clip_param"]), 1.0 + float(cfg["clip_param"])
            ) * adv_t[idx]
            actor_loss = -torch.min(surrogate_1, surrogate_2).mean()
            actor_loss -= float(entropy_coef) * entropy.mean()

            actor_optimizer.zero_grad(set_to_none=True)
            actor_loss.backward()
            nn.utils.clip_grad_norm_(actor.parameters(), float(cfg["max_grad_norm"]))
            actor_optimizer.step()
            actor_loss_sum += float(actor_loss.detach().cpu()) * int(idx.numel())
            actor_samples += int(idx.numel())

        critic_perm = torch.randperm(n_critic, device=device)
        for start in range(0, n_critic, critic_batch):
            idx = critic_perm[start:start + critic_batch]
            values_pred = critic(states_t[idx])
            if value_clip > 0.0:
                values_clipped = old_values_t[idx] + torch.clamp(
                    values_pred - old_values_t[idx], -value_clip, value_clip
                )
                loss_unclipped = (values_pred - returns_t[idx]).pow(2)
                loss_clipped = (values_clipped - returns_t[idx]).pow(2)
                critic_loss = 0.5 * torch.max(loss_unclipped, loss_clipped).mean()
            else:
                critic_loss = 0.5 * (values_pred - returns_t[idx]).pow(2).mean()

            critic_optimizer.zero_grad(set_to_none=True)
            critic_loss.backward()
            nn.utils.clip_grad_norm_(critic.parameters(), float(cfg["max_grad_norm"]))
            critic_optimizer.step()
            critic_loss_sum += float(critic_loss.detach().cpu()) * int(idx.numel())
            critic_samples += int(idx.numel())

    return {
        "actor_loss": actor_loss_sum / max(actor_samples, 1),
        "critic_loss": critic_loss_sum / max(critic_samples, 1),
    }


# -----------------------------------------------------------------------------
# Meta-controller and LLM handling
# -----------------------------------------------------------------------------
class OllamaClient:
    def __init__(self, cfg: Dict[str, Any]):
        self.base_url = str(cfg["ollama_base_url"])
        self.model = str(cfg["llm_model"])
        self.timeout = int(cfg["llm_timeout"])
        self.temperature = float(cfg["llm_temperature"])

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_completion(self, prompt: str) -> Tuple[Optional[str], Dict[str, Any]]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": 0.9,
                "num_predict": 1000,
            },
        }
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
            text = str(body.get("response", "")) or None
            return text, {
                "latency_seconds": time.perf_counter() - started,
                "http_status": int(response.status_code),
                "error": None,
                "ollama_total_duration_ns": body.get("total_duration"),
                "ollama_eval_count": body.get("eval_count"),
            }
        except (requests.RequestException, ValueError) as exc:
            return None, {
                "latency_seconds": time.perf_counter() - started,
                "http_status": None,
                "error": f"{type(exc).__name__}: {exc}",
                "ollama_total_duration_ns": None,
                "ollama_eval_count": None,
            }


class TrainingMonitor:
    def __init__(self, cfg: Dict[str, Any], env: MovingLeaderFormationEnv3D):
        self.cfg = cfg
        self.env = env
        self.metrics_history: List[Dict[str, Any]] = []
        self.current_params = {
            name: float(bounds["default"])
            for name, bounds in cfg["param_stability"].items()
        }
        self.training_phase = "early"
        self.phase_transition_history: List[Dict[str, Any]] = [
            {"episode": 1, "from": None, "to": "early", "reason": "initial"}
        ]
        self.phase_patience_counter = 0
        self.last_consultation_episode = 0
        self.consultation_history: List[Dict[str, Any]] = []
        self.intervention_history: List[Dict[str, Any]] = []
        self.parameter_update_count = 0
        self.last_param_update_episode: Dict[str, int] = {}
        self.first_acquisition_episode: Optional[int] = None
        self.first_success_episode: Optional[int] = None

    def collect_metrics(self, episode: int, info: Dict[str, Any]) -> None:
        acquisition_success = int(bool(info["formation_acquired"]))
        full_task_success = int(bool(info["full_task_success"]))
        if acquisition_success and self.first_acquisition_episode is None:
            self.first_acquisition_episode = episode
        if full_task_success and self.first_success_episode is None:
            self.first_success_episode = episode
        self.metrics_history.append(
            {
                "episode": episode,
                "avg_position_error": float(info["avg_position_error"]),
                "avg_pairwise_formation_error": float(
                    info["avg_pairwise_formation_error"]
                ),
                "avg_follow_position_error": float(
                    info["avg_follow_position_error"]
                ),
                "follow_retention_ratio": float(info["follow_retention_ratio"]),
                "mean_follow_retention_ratio": float(
                    info["mean_follow_retention_ratio"]
                ),
                "follow_step_count": int(info["follow_step_count"]),
                "acquisition_success": acquisition_success,
                "full_task_success": full_task_success,
                "collision_count": int(bool(info.get("episode_had_collision", False))),
            }
        )
        self._update_training_phase(episode)

    def recent_summary(self, window: Optional[int] = None) -> Dict[str, float]:
        if not self.metrics_history:
            return {
                "mean_position_error": 0.0,
                "mean_pairwise_error": 0.0,
                "mean_follow_position_error": 0.0,
                "mean_follow_retention_ratio": 0.0,
                "mean_agent_follow_retention_ratio": 0.0,
                "acquisition_success_rate": 0.0,
                "full_task_success_rate": 0.0,
                "success_rate": 0.0,
                "collision_rate": 0.0,
            }
        n = int(window or self.cfg["phase_window"])
        recent = self.metrics_history[-n:]
        full_task_rate = float(
            np.mean([x["full_task_success"] for x in recent])
        )
        following_recent = [x for x in recent if x["follow_step_count"] > 0]
        if following_recent:
            mean_follow_error = float(
                np.mean([x["avg_follow_position_error"] for x in following_recent])
            )
            mean_follow_retention = float(
                np.mean([x["follow_retention_ratio"] for x in following_recent])
            )
            mean_agent_retention = float(
                np.mean(
                    [x["mean_follow_retention_ratio"] for x in following_recent]
                )
            )
        else:
            mean_follow_error = float(
                np.mean([x["avg_position_error"] for x in recent])
            )
            mean_follow_retention = 0.0
            mean_agent_retention = 0.0
        return {
            "mean_position_error": float(
                np.mean([x["avg_position_error"] for x in recent])
            ),
            "mean_pairwise_error": float(
                np.mean([x["avg_pairwise_formation_error"] for x in recent])
            ),
            "mean_follow_position_error": mean_follow_error,
            "mean_follow_retention_ratio": mean_follow_retention,
            "mean_agent_follow_retention_ratio": mean_agent_retention,
            "acquisition_success_rate": float(
                np.mean([x["acquisition_success"] for x in recent])
            ),
            "full_task_success_rate": full_task_rate,
            # Backward-compatible alias used by the prompt builder.
            "success_rate": full_task_rate,
            "collision_rate": float(
                np.mean([int(x["collision_count"] > 0) for x in recent])
            ),
        }

    def _transition(self, episode: int, new_phase: str, reason: str) -> None:
        old = self.training_phase
        if new_phase == old:
            return
        self.training_phase = new_phase
        self.phase_patience_counter = 0
        self.phase_transition_history.append(
            {"episode": episode, "from": old, "to": new_phase, "reason": reason}
        )

    def _update_training_phase(self, episode: int) -> None:
        if self.cfg["phase_detection_mode"] == "fixed":
            if episode <= int(self.cfg["phase_boundaries"]["early_end"]):
                phase = "early"
            elif episode <= int(self.cfg["phase_boundaries"]["mid_end"]):
                phase = "mid"
            else:
                phase = "late"
            self._transition(episode, phase, "fixed episode boundary")
            return

        summary = self.recent_summary(int(self.cfg["phase_window"]))
        fallback = self.cfg.get("phase_episode_fallback") or {}
        if fallback and self.training_phase != "late":
            late_episode = int(fallback.get("late", 10**9))
            mid_episode = int(fallback.get("mid", 10**9))
            if episode >= late_episode:
                self._transition(episode, "late", "episode-count fallback")
                return
            if episode >= mid_episode and self.training_phase == "early":
                self._transition(episode, "mid", "episode-count fallback")
                return
        patience = int(self.cfg["phase_patience"])
        if self.training_phase == "early":
            rule = self.cfg["early_to_mid"]
            condition = (
                episode >= int(rule["min_episode"])
                and (
                    summary["acquisition_success_rate"]
                    >= float(rule["acquisition_rate"])
                    or summary["mean_position_error"] <= float(rule["mean_error"])
                )
            )
            self.phase_patience_counter = self.phase_patience_counter + 1 if condition else 0
            if self.phase_patience_counter >= patience:
                self._transition(
                    episode,
                    "mid",
                    f"rolling acquisition={summary['acquisition_success_rate']:.3f}, "
                    f"position_error={summary['mean_position_error']:.3f}",
                )
        elif self.training_phase == "mid":
            rule = self.cfg["mid_to_late"]
            condition = (
                episode >= int(rule["min_episode"])
                and summary["acquisition_success_rate"]
                >= float(rule["acquisition_rate"])
                and summary["mean_follow_position_error"]
                <= float(rule["mean_follow_error"])
            )
            self.phase_patience_counter = self.phase_patience_counter + 1 if condition else 0
            if self.phase_patience_counter >= patience:
                self._transition(
                    episode,
                    "late",
                    f"rolling acquisition={summary['acquisition_success_rate']:.3f}, "
                    f"follow_error={summary['mean_follow_position_error']:.3f}",
                )

    def should_consult_phase_aware(self, episode: int) -> Tuple[bool, str]:
        interval = int(self.cfg["phase_consult_intervals"][self.training_phase])
        elapsed = episode - self.last_consultation_episode
        if elapsed < interval:
            return False, ""
        summary = self.recent_summary(20)
        if self.training_phase == "early":
            return True, "scheduled early exploration consultation"
        if self.training_phase == "mid":
            if len(self.metrics_history) >= 20:
                recent = [x["avg_position_error"] for x in self.metrics_history[-20:]]
                degradation = (recent[-1] - recent[0]) / (abs(recent[0]) + 1e-8)
                if degradation > 0.25:
                    return True, "mid-phase performance degradation"
            return elapsed >= 2 * interval, "scheduled mid-phase consultation"
        if len(self.metrics_history) >= 15:
            recent = [x["avg_position_error"] for x in self.metrics_history[-15:]]
            degradation = (recent[-1] - recent[-5]) / (abs(recent[-5]) + 1e-8)
            if degradation > 0.15:
                return True, "late-phase performance degradation"
        return elapsed >= math.ceil(1.5 * interval), "scheduled late-phase consultation"

    def register_consultation(
        self,
        episode: int,
        method: str,
        reason: str,
        response: Optional[str],
        parse_count: int,
        llm_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.last_consultation_episode = episode
        meta = llm_meta or {}
        self.consultation_history.append(
            {
                "episode": episode,
                "method": method,
                "phase": self.training_phase,
                "reason": reason,
                "response_received": bool(response),
                "parsed_suggestion_count": int(parse_count),
                "latency_seconds": meta.get("latency_seconds"),
                "http_status": meta.get("http_status"),
                "error": meta.get("error"),
            }
        )

    def apply_safe_adjustment_audited(
        self,
        param_name: str,
        adjustment_type: str,
        magnitude: str,
        episode: int,
        rule_phase: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        phase = rule_phase or self.training_phase
        audit: Dict[str, Any] = {
            "episode": episode,
            "monitor_phase": self.training_phase,
            "rule_phase": phase,
            "param_name": param_name,
            "adjustment_type": adjustment_type,
            "magnitude": magnitude,
            "accepted": False,
            "rejection_reason": None,
        }
        if param_name not in self.current_params:
            audit["rejection_reason"] = "unknown_parameter"
            return None, audit
        min_interval = int(self.cfg.get("param_min_update_interval", 0))
        last_episode = self.last_param_update_episode.get(param_name)
        if (
            min_interval > 0
            and last_episode is not None
            and episode - last_episode < min_interval
        ):
            audit["rejection_reason"] = (
                f"minimum_update_interval({min_interval})"
            )
            return None, audit
        bounds = self.cfg["param_stability"][param_name]
        multiplier = self.cfg["phase_adjustment_multipliers"][phase][magnitude][
            adjustment_type
        ]
        old_value = float(self.current_params[param_name])
        raw_candidate = old_value * multiplier
        candidate = float(np.clip(raw_candidate, bounds["min"], bounds["max"]))
        alpha = float(self.cfg["phase_smoothing"][phase])
        smoothed = (1.0 - alpha) * old_value + alpha * candidate
        new_value = float(np.clip(smoothed, bounds["min"], bounds["max"]))
        change_pct = abs(new_value - old_value) / (abs(old_value) + 1e-8) * 100.0
        audit.update(
            {
                "old_value": old_value,
                "raw_candidate_value": float(raw_candidate),
                "candidate_value": candidate,
                "candidate_was_clipped": bool(abs(candidate - raw_candidate) > 1e-12),
                "smoothing_alpha": alpha,
                "new_value": new_value,
                "change_pct": change_pct,
            }
        )
        if change_pct < float(self.cfg["min_effective_change_pct"]):
            audit["rejection_reason"] = "minimum_effective_change"
            return None, audit
        self.current_params[param_name] = new_value
        self.last_param_update_episode[param_name] = episode
        self.parameter_update_count += 1
        self.env.update_reward_weights(
            {
                "position": self.current_params["w_position"],
                "formation": self.current_params["w_formation"],
                "success": self.current_params["w_success"],
            }
        )
        update = {
            "episode": episode,
            "phase": self.training_phase,
            "rule_phase": phase,
            "param_name": param_name,
            "adjustment_type": adjustment_type,
            "magnitude": magnitude,
            "old_value": old_value,
            "raw_candidate_value": float(raw_candidate),
            "candidate_value": candidate,
            "candidate_was_clipped": audit["candidate_was_clipped"],
            "smoothing_alpha": alpha,
            "new_value": new_value,
            "change_pct": change_pct,
        }
        audit["accepted"] = True
        return update, audit

    def apply_safe_adjustment(
        self,
        param_name: str,
        adjustment_type: str,
        magnitude: str,
        episode: int,
        rule_phase: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        update, _ = self.apply_safe_adjustment_audited(
            param_name, adjustment_type, magnitude, episode, rule_phase
        )
        return update

    def record_intervention(
        self,
        episode: int,
        method: str,
        reason: str,
        updates: List[Dict[str, Any]],
    ) -> None:
        if not updates:
            return
        self.intervention_history.append(
            {
                "episode": episode,
                "method": method,
                "phase": self.training_phase,
                "reason": reason,
                "n_parameter_updates": len(updates),
                "updates": updates,
                "params_after": dict(self.current_params),
            }
        )


class LLMPromptBuilder:
    PARAM_ALIASES = {
        "w_position": ["w_position", "position", "位置误差权重", "位置"],
        "w_formation": ["w_formation", "formation", "编队结构", "编队"],
        "w_success": ["w_success", "success", "成功奖励", "成功"],
        "entropy_coef": ["entropy_coef", "entropy", "探索系数", "熵系数"],
    }

    @staticmethod
    def build(monitor: TrainingMonitor, episode: int, uniform: bool) -> str:
        phase = "uniform" if uniform else monitor.training_phase
        summary = monitor.recent_summary(20)
        allowed = monitor.cfg["phase_param_whitelist"][phase]
        max_adjustments = monitor.cfg["phase_max_adjustments"][phase]
        if uniform:
            role = "你是强化学习参数调节器。所有训练阶段使用同一套规则，不使用阶段角色信息。"
        elif phase == "early":
            role = "你是探索引导者。目标是扩大有效探索，同时避免过早强化成功奖励。"
        elif phase == "mid":
            role = "你是突破加速器。目标是强化有效编队经验并促进形成稳定成功行为。"
        else:
            role = "你是稳定性守护者。目标是以保守的小幅调整减少后期性能退化。"
        params = "\n".join(
            f"{name}={monitor.current_params[name]:.6f} "
            f"[{'allowed' if name in allowed else 'not_allowed'}]"
            for name in monitor.current_params
        )
        return f"""{role}

Episode: {episode}/{monitor.cfg['episodes']}
Recent mean position error: {summary['mean_position_error']:.3f} m
Recent mean pairwise formation error: {summary['mean_pairwise_error']:.3f} m
Recent mean following error: {summary['mean_follow_position_error']:.3f} m
Recent formation-acquisition rate: {summary['acquisition_success_rate'] * 100:.1f}%
Recent full-task success rate: {summary['full_task_success_rate'] * 100:.1f}%

Current parameters:
{params}

Output at most {max_adjustments} lines using exactly this format:
1. parameter_name: 增加 幅度: 轻微
2. parameter_name: 减少 幅度: 中等
Allowed magnitude words: 轻微, 中等, 显著
"""

    @classmethod
    def parse(cls, response: Optional[str]) -> List[Dict[str, str]]:
        if not response:
            return []
        cleaned = re.sub(r"```[\s\S]*?```", "", response)
        pattern = (
            r"(?:\d+[\.\:]\s*)?([\w_\u4e00-\u9fff]+)[:：]\s*"
            r"(增加|减少)(?:\s*幅度[:：]\s*(轻微|中等|显著))?"
        )
        suggestions: List[Dict[str, str]] = []
        for param_text, direction, magnitude in re.findall(pattern, cleaned, re.I):
            normalized = None
            for key, aliases in cls.PARAM_ALIASES.items():
                if param_text.lower() in [x.lower() for x in aliases]:
                    normalized = key
                    break
            if normalized:
                suggestions.append(
                    {
                        "param_name": normalized,
                        "adjustment_type": direction,
                        "magnitude": magnitude or "轻微",
                    }
                )
        return suggestions


def execute_llm_consultation(
    monitor: TrainingMonitor,
    client: OllamaClient,
    episode: int,
    method: str,
    reason: str,
    run_dir: Path,
    *,
    uniform: bool = False,
) -> List[Dict[str, Any]]:
    prompt = LLMPromptBuilder.build(monitor, episode, uniform=uniform)
    response, llm_meta = client.get_completion(prompt)
    parsed_raw = LLMPromptBuilder.parse(response)
    monitor.register_consultation(
        episode, method, reason, response, len(parsed_raw), llm_meta
    )

    rule_phase = "uniform" if uniform else monitor.training_phase
    allowed = set(monitor.cfg["phase_param_whitelist"][rule_phase])
    max_adjustments = int(monitor.cfg["phase_max_adjustments"][rule_phase])
    authorized = [x for x in parsed_raw if x["param_name"] in allowed]
    unauthorized = [x for x in parsed_raw if x["param_name"] not in allowed]
    selected = authorized[:max_adjustments]
    over_budget = authorized[max_adjustments:]

    updates: List[Dict[str, Any]] = []
    safety_decisions: List[Dict[str, Any]] = []
    for suggestion in selected:
        update, audit = monitor.apply_safe_adjustment_audited(
            suggestion["param_name"],
            suggestion["adjustment_type"],
            suggestion["magnitude"],
            episode,
            rule_phase=rule_phase,
        )
        safety_decisions.append(audit)
        if update:
            updates.append(update)
    monitor.record_intervention(episode, method, reason, updates)
    append_jsonl(
        run_dir / "llm_calls.jsonl",
        {
            "episode": episode,
            "method": method,
            "monitor_phase": monitor.training_phase,
            "rule_phase": rule_phase,
            "reason": reason,
            "prompt": prompt,
            "response": response,
            "llm_meta": llm_meta,
            "parsed_suggestions_raw": parsed_raw,
            "unauthorized_suggestions": unauthorized,
            "over_budget_suggestions": over_budget,
            "selected_suggestions": selected,
            "safety_decisions": safety_decisions,
            "applied_updates": updates,
        },
    )
    return updates


def execute_matched_random_intervention(
    monitor: TrainingMonitor,
    episode: int,
    phase: str,
    requested_updates: int,
    reason: str,
    run_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Apply the accepted-update count of the corresponding Ours event."""
    allowed = list(monitor.cfg["phase_param_whitelist"][phase])
    updates: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    attempts = 0
    max_attempts = max(20, requested_updates * 20)
    while len(updates) < requested_updates and attempts < max_attempts:
        attempts += 1
        param = random.choice(allowed)
        direction = random.choice(["增加", "减少"])
        magnitude = random.choice(["轻微", "中等", "显著"])
        update, audit = monitor.apply_safe_adjustment_audited(
            param, direction, magnitude, episode, rule_phase=phase
        )
        decisions.append(audit)
        if update:
            updates.append(update)
    if len(updates) != requested_updates:
        raise RuntimeError(
            f"Could not match {requested_updates} parameter updates at episode "
            f"{episode}; only {len(updates)} were effective after {attempts} attempts."
        )
    monitor.record_intervention(episode, "random_matched", reason, updates)
    if run_dir is not None:
        append_jsonl(
            run_dir / "random_calls.jsonl",
            {
                "episode": episode,
                "phase": phase,
                "requested_updates": requested_updates,
                "attempts": attempts,
                "safety_decisions": decisions,
                "applied_updates": updates,
            },
        )
    return updates


def build_rule_based_suggestions(monitor: TrainingMonitor) -> List[Dict[str, str]]:
    """Frozen expert controller used to test whether the LLM is necessary.

    The rules use only the compact statistics available to the LLM and never
    inspect prior LLM recommendations. Keep this function unchanged once the
    preregistered E3 experiment begins.
    """
    phase = monitor.training_phase
    summary = monitor.recent_summary(20)
    suggestions: List[Dict[str, str]] = []
    if phase == "early":
        if summary["acquisition_success_rate"] < 0.05:
            suggestions.append(
                {"param_name": "entropy_coef", "adjustment_type": "增加", "magnitude": "轻微"}
            )
        if summary["mean_position_error"] > 60.0:
            suggestions.append(
                {"param_name": "w_position", "adjustment_type": "增加", "magnitude": "轻微"}
            )
    elif phase == "mid":
        follow_norm = summary["mean_follow_position_error"] / max(
            float(monitor.cfg["follow_error_threshold"]), 1e-8
        )
        formation_norm = summary["mean_pairwise_error"] / max(
            float(monitor.cfg["formation_threshold"]), 1e-8
        )
        if follow_norm >= formation_norm:
            suggestions.append(
                {"param_name": "w_position", "adjustment_type": "增加", "magnitude": "轻微"}
            )
        else:
            suggestions.append(
                {"param_name": "w_formation", "adjustment_type": "增加", "magnitude": "轻微"}
            )
        if summary["acquisition_success_rate"] >= 0.50:
            suggestions.append(
                {"param_name": "entropy_coef", "adjustment_type": "减少", "magnitude": "轻微"}
            )
    else:
        if len(monitor.metrics_history) >= 15:
            recent_follow = [
                x["avg_follow_position_error"] for x in monitor.metrics_history[-15:]
            ]
            recent_pair = [
                x["avg_pairwise_formation_error"] for x in monitor.metrics_history[-15:]
            ]
            follow_degradation = recent_follow[-1] - float(np.mean(recent_follow[:5]))
            pair_degradation = recent_pair[-1] - float(np.mean(recent_pair[:5]))
            if follow_degradation > 0.0 or pair_degradation > 0.0:
                param = "w_position" if follow_degradation >= pair_degradation else "w_formation"
                suggestions.append(
                    {"param_name": param, "adjustment_type": "增加", "magnitude": "轻微"}
                )
    return suggestions


def execute_rule_based_intervention(
    monitor: TrainingMonitor,
    episode: int,
    method: str,
    reason: str,
    run_dir: Path,
) -> List[Dict[str, Any]]:
    suggestions = build_rule_based_suggestions(monitor)
    phase = monitor.training_phase
    allowed = set(monitor.cfg["phase_param_whitelist"][phase])
    max_adjustments = int(monitor.cfg["phase_max_adjustments"][phase])
    selected = [x for x in suggestions if x["param_name"] in allowed][:max_adjustments]
    updates: List[Dict[str, Any]] = []
    decisions: List[Dict[str, Any]] = []
    for suggestion in selected:
        update, audit = monitor.apply_safe_adjustment_audited(
            suggestion["param_name"],
            suggestion["adjustment_type"],
            suggestion["magnitude"],
            episode,
            rule_phase=phase,
        )
        decisions.append(audit)
        if update:
            updates.append(update)
    monitor.register_consultation(
        episode, method, reason, response="RULE_BASED", parse_count=len(suggestions)
    )
    monitor.record_intervention(episode, method, reason, updates)
    append_jsonl(
        run_dir / "rule_calls.jsonl",
        {
            "episode": episode,
            "phase": phase,
            "reason": reason,
            "generated_suggestions": suggestions,
            "selected_suggestions": selected,
            "safety_decisions": decisions,
            "applied_updates": updates,
        },
    )
    return updates


# -----------------------------------------------------------------------------
# Training and result extraction
# -----------------------------------------------------------------------------
def build_rollout(
    env: MovingLeaderFormationEnv3D,
    actor: SquashedGaussianActor,
    critic: CentralizedCritic,
    cfg: Dict[str, Any],
) -> Tuple[Rollout, Dict[str, Any], float]:
    obs, state = env.reset()
    obs_buffer: List[np.ndarray] = []
    state_buffer: List[np.ndarray] = []
    action_buffer: List[np.ndarray] = []
    logp_buffer: List[np.ndarray] = []
    reward_buffer: List[np.ndarray] = []
    value_buffer: List[np.ndarray] = []
    terminated_buffer: List[bool] = []
    episode_rewards: List[float] = []
    final_info: Dict[str, Any] = {}
    last_terminated = False

    for _ in range(int(cfg["episode_len"])):
        obs_t = torch.tensor(obs, dtype=torch.float32, device=cfg["device"])
        state_t = torch.tensor(state[None, :], dtype=torch.float32, device=cfg["device"])
        with torch.no_grad():
            actions_t, logp_t = actor.sample_action(obs_t)
            values_t = critic(state_t)[0]
        actions = actions_t.cpu().numpy().astype(np.float32)
        next_obs, rewards, terminated, truncated, info = env.step(actions)
        next_state = env.global_state()

        obs_buffer.append(obs.copy())
        state_buffer.append(state.copy())
        action_buffer.append(actions.copy())
        logp_buffer.append(logp_t.cpu().numpy().astype(np.float32))
        reward_buffer.append(np.asarray(rewards, dtype=np.float32))
        value_buffer.append(values_t.cpu().numpy().astype(np.float32))
        terminated_buffer.append(bool(terminated))
        episode_rewards.append(float(np.mean(rewards)))

        obs = next_obs
        state = next_state
        final_info = info
        last_terminated = bool(terminated)
        if terminated or truncated:
            break

    rollout = Rollout(
        observations=np.asarray(obs_buffer, dtype=np.float32),
        states=np.asarray(state_buffer, dtype=np.float32),
        actions=np.asarray(action_buffer, dtype=np.float32),
        old_log_probs=np.asarray(logp_buffer, dtype=np.float32),
        rewards=np.asarray(reward_buffer, dtype=np.float32),
        values=np.asarray(value_buffer, dtype=np.float32),
        terminated=np.asarray(terminated_buffer, dtype=bool),
        last_state=np.asarray(state, dtype=np.float32),
        last_terminated=last_terminated,
    )
    return rollout, final_info, float(np.mean(episode_rewards))


def load_matched_schedule(
    results_dir: Path, seed: int, source_method: str = "phase_aware"
) -> List[Dict[str, Any]]:
    path = results_dir / f"{source_method}_seed{seed}" / "matched_schedule.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Matched schedule not found: {path}. Run {source_method} for this seed first."
        )
    with path.open("r", encoding="utf-8") as f:
        schedule = json.load(f)
    if not isinstance(schedule, list):
        raise ValueError(f"Invalid matched schedule format: {path}")
    return schedule


def train_single_run(
    method: str,
    seed: int,
    cfg: Dict[str, Any],
    results_dir: Path,
    resume: bool = False,
) -> Dict[str, Any]:
    """Train one method/seed run.

    `method` is the run-directory label. `cfg['controller_type']` selects the
    actual controller and allows clean ablations to have unique names while
    reusing the same implementation.
    """
    run_dir = results_dir / f"{method}_seed{seed}"
    result_path = run_dir / "results.json"
    if resume and result_path.exists():
        with result_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    local_cfg = deepcopy(cfg)
    local_cfg["env_seed"] = int(seed)
    controller_type = str(local_cfg.get("controller_type") or method)
    set_global_seed(seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_dump(run_dir / "config_snapshot.json", local_cfg)
    writer = SummaryWriter(str(run_dir / "tensorboard"))
    env = MovingLeaderFormationEnv3D(local_cfg)
    monitor = TrainingMonitor(local_cfg, env)

    obs0, state0 = env.reset()
    actor = SquashedGaussianActor(
        obs0.shape[1], log_std_init=float(local_cfg.get("log_std_init", 0.0))
    ).to(local_cfg["device"])
    critic = CentralizedCritic(
        state0.shape[0], env.n, hidden=int(local_cfg.get("critic_hidden", 128))
    ).to(local_cfg["device"])
    initial_actor_path = local_cfg.get("initial_actor_path")
    if initial_actor_path:
        actor.load_state_dict(
            torch.load(str(initial_actor_path), map_location=local_cfg["device"])
        )
    actor_optimizer = optim.Adam(actor.parameters(), lr=float(local_cfg["actor_lr"]))
    critic_optimizer = optim.Adam(critic.parameters(), lr=float(local_cfg["critic_lr"]))

    llm_client: Optional[OllamaClient] = None
    if controller_type in {"phase_aware", "uniform_matched"}:
        llm_client = OllamaClient(local_cfg)
        if not llm_client.test_connection():
            writer.close()
            raise RuntimeError(
                f"Ollama is unavailable for method={method}. The run is aborted; "
                "it will not be silently relabeled as baseline."
            )

    matched_schedule: Dict[int, Dict[str, Any]] = {}
    if controller_type in {"uniform_matched", "random_matched"}:
        source_method = str(local_cfg.get("matched_schedule_source", "phase_aware"))
        for event in load_matched_schedule(results_dir, seed, source_method):
            matched_schedule[int(event["episode"])] = event

    error_history: List[float] = []
    pairwise_error_history: List[float] = []
    reward_history: List[float] = []
    collision_history: List[int] = []
    collision_count_history: List[int] = []
    acquisition_history: List[int] = []
    leader_goal_history: List[int] = []
    follow_retention_history: List[float] = []
    follow_mean_retention_history: List[float] = []
    per_agent_follow_retention_history: List[List[float]] = []
    follow_error_history: List[float] = []
    terminal_max_target_error_history: List[float] = []
    task_success_without_safety_history: List[int] = []
    safe_success_history: List[int] = []
    success_history: List[int] = []
    param_history = {name: [] for name in monitor.current_params}
    phase_history: List[str] = []
    reward_stats = RunningStat()
    best_score: Optional[Tuple[float, float]] = None
    best_episode: Optional[int] = None
    start_time = time.time()

    for episode in range(1, int(local_cfg["episodes"]) + 1):
        rollout, info, mean_reward = build_rollout(env, actor, critic, local_cfg)
        if bool(local_cfg.get("reward_normalization", False)):
            reward_stats.update(rollout.rewards)
            rollout.rewards = (
                rollout.rewards / max(reward_stats.std, 1e-3)
            ).astype(np.float32)
        entropy_coef = min(
            float(monitor.current_params["entropy_coef"]),
            float(local_cfg.get("entropy_coef_max", 1e9)),
        )
        losses = ppo_update(
            actor,
            critic,
            actor_optimizer,
            critic_optimizer,
            rollout,
            entropy_coef,
            local_cfg,
        )

        acquisition_success = int(bool(info["formation_acquired"]))
        leader_goal_success = int(bool(info["leader_reached_goal"]))
        raw_success = int(bool(info["task_success_without_safety"]))
        safe_success = int(bool(info["safe_full_task_success"]))
        success = int(bool(info["full_task_success"]))
        error_history.append(float(info["avg_position_error"]))
        pairwise_error_history.append(float(info["avg_pairwise_formation_error"]))
        reward_history.append(mean_reward)
        collision_history.append(int(bool(info["episode_had_collision"])))
        collision_count_history.append(int(info["episode_collision_count"]))
        acquisition_history.append(acquisition_success)
        leader_goal_history.append(leader_goal_success)
        follow_retention_history.append(float(info["follow_retention_ratio"]))
        follow_mean_retention_history.append(float(info["mean_follow_retention_ratio"]))
        per_agent_follow_retention_history.append(
            [float(x) for x in info["per_agent_follow_retention"]]
        )
        follow_error_history.append(float(info["avg_follow_position_error"]))
        terminal_max_target_error_history.append(float(info["terminal_max_target_error"]))
        task_success_without_safety_history.append(raw_success)
        safe_success_history.append(safe_success)
        success_history.append(success)
        monitor.collect_metrics(episode, info)

        if controller_type == "phase_aware" and llm_client is not None:
            should_consult, reason = monitor.should_consult_phase_aware(episode)
            if should_consult:
                execute_llm_consultation(
                    monitor, llm_client, episode, method, reason, run_dir, uniform=False
                )
        elif controller_type == "uniform_matched" and llm_client is not None:
            event = matched_schedule.get(episode)
            if event:
                execute_llm_consultation(
                    monitor,
                    llm_client,
                    episode,
                    method,
                    "matched to the proposed method's accepted-intervention episode",
                    run_dir,
                    uniform=True,
                )
        elif controller_type == "random_matched":
            event = matched_schedule.get(episode)
            if event:
                execute_matched_random_intervention(
                    monitor,
                    episode,
                    str(event["phase"]),
                    int(event["n_parameter_updates"]),
                    "matched to the proposed method's accepted-intervention event",
                    run_dir,
                )
        elif controller_type == "rule_based":
            should_consult, reason = monitor.should_consult_phase_aware(episode)
            if should_consult:
                execute_rule_based_intervention(
                    monitor, episode, method, reason, run_dir
                )

        for name in param_history:
            param_history[name].append(float(monitor.current_params[name]))
        phase_history.append(monitor.training_phase)

        if bool(local_cfg.get("save_best_checkpoint", False)):
            window = min(int(local_cfg["final_window"]), len(success_history))
            score = (
                float(np.mean(success_history[-window:])),
                -float(np.mean(follow_error_history[-window:])),
            )
            if best_score is None or score > best_score:
                best_score = score
                best_episode = episode
                torch.save(actor.state_dict(), run_dir / "actor_best.pth")
                json_dump(
                    run_dir / "best_checkpoint.json",
                    {
                        "episode": episode,
                        "rolling_success_rate": score[0] * 100.0,
                        "rolling_follow_error": -score[1],
                        "window": window,
                    },
                )

        if episode % int(local_cfg["tensorboard_log_interval"]) == 0 or episode == 1:
            final_window = int(local_cfg["final_window"])
            writer.add_scalar("Train/PositionError", error_history[-1], episode)
            writer.add_scalar("Train/PairwiseFormationError", pairwise_error_history[-1], episode)
            writer.add_scalar("Train/Reward", reward_history[-1], episode)
            writer.add_scalar("Train/EpisodeHadCollision", collision_history[-1], episode)
            writer.add_scalar("Train/EpisodeCollisionCount", collision_count_history[-1], episode)
            writer.add_scalar("Train/FormationAcquired", acquisition_success, episode)
            writer.add_scalar("Train/LeaderReachedGoal", leader_goal_success, episode)
            writer.add_scalar("Train/FullTaskSuccess", success, episode)
            writer.add_scalar("Train/SafeFullTaskSuccess", safe_success, episode)
            writer.add_scalar("Train/FollowRetentionRatio", follow_retention_history[-1], episode)
            writer.add_scalar("Train/MeanFollowPositionError", follow_error_history[-1], episode)
            writer.add_scalar("Train/TerminalMaxTargetError", terminal_max_target_error_history[-1], episode)
            writer.add_scalar(
                "Performance/RollingFullTaskSuccessRate",
                float(np.mean(success_history[-final_window:])) * 100.0,
                episode,
            )
            writer.add_scalar(
                "Performance/RollingSafeSuccessRate",
                float(np.mean(safe_success_history[-final_window:])) * 100.0,
                episode,
            )
            writer.add_scalar(
                "Performance/RollingAcquisitionRate",
                float(np.mean(acquisition_history[-final_window:])) * 100.0,
                episode,
            )
            writer.add_scalar("Loss/Actor", losses["actor_loss"], episode)
            writer.add_scalar("Loss/Critic", losses["critic_loss"], episode)
            writer.add_scalar("Meta/Consultations", len(monitor.consultation_history), episode)
            writer.add_scalar("Meta/InterventionEvents", len(monitor.intervention_history), episode)
            writer.add_scalar("Meta/ParameterUpdates", monitor.parameter_update_count, episode)
            phase_code = {"early": 0, "mid": 1, "late": 2}[monitor.training_phase]
            writer.add_scalar("Phase/Current", phase_code, episode)
            for name, value in monitor.current_params.items():
                writer.add_scalar(f"Params/{name}", value, episode)

        if episode % 100 == 0 or episode == 1 or episode == int(local_cfg["episodes"]):
            rolling_sr = np.mean(success_history[-int(local_cfg["final_window"]):]) * 100.0
            rolling_safe = np.mean(safe_success_history[-int(local_cfg["final_window"]):]) * 100.0
            rolling_acq = np.mean(acquisition_history[-int(local_cfg["final_window"]):]) * 100.0
            print(
                f"[{method:24s}] seed={seed:5d} ep={episode:4d} "
                f"phase={monitor.training_phase:5s} error={error_history[-1]:7.2f}m "
                f"follow={follow_error_history[-1]:7.2f}m pair={pairwise_error_history[-1]:7.2f}m "
                f"ACQ100={rolling_acq:6.1f}% FULL100={rolling_sr:6.1f}% "
                f"SAFE100={rolling_safe:6.1f}% calls={len(monitor.consultation_history):3d} "
                f"events={len(monitor.intervention_history):3d} updates={monitor.parameter_update_count:3d}"
            )

        if episode % int(local_cfg["save_model_interval"]) == 0 or episode == int(local_cfg["episodes"]):
            torch.save(actor.state_dict(), run_dir / f"actor_ep{episode}.pth")
            torch.save(critic.state_dict(), run_dir / f"critic_ep{episode}.pth")

    writer.close()
    elapsed = time.time() - start_time
    final_window = int(local_cfg["final_window"])
    stable_ep = stable_breakthrough_episode(
        success_history,
        int(local_cfg["stable_breakthrough_window"]),
        float(local_cfg["stable_breakthrough_rate"]),
        int(local_cfg["stable_breakthrough_hold"]),
    )
    safe_stable_ep = stable_breakthrough_episode(
        safe_success_history,
        int(local_cfg["stable_breakthrough_window"]),
        float(local_cfg["stable_breakthrough_rate"]),
        int(local_cfg["stable_breakthrough_hold"]),
    )
    first_safe_success = next(
        (i + 1 for i, flag in enumerate(safe_success_history) if flag), None
    )

    phase_counts = {phase: phase_history.count(phase) for phase in ["early", "mid", "late"]}
    calls_by_phase = {phase: 0 for phase in ["early", "mid", "late"]}
    for call in monitor.consultation_history:
        calls_by_phase[str(call["phase"])] += 1
    events_by_phase = {phase: 0 for phase in ["early", "mid", "late"]}
    for event in monitor.intervention_history:
        events_by_phase[str(event["phase"])] += 1
    latencies = [
        float(call["latency_seconds"])
        for call in monitor.consultation_history
        if call.get("latency_seconds") is not None
    ]

    results: Dict[str, Any] = {
        "schema_version": 7,
        "method": method,
        "controller_type": controller_type,
        "seed": seed,
        "episode_indexing": "1-based",
        "n_episodes": int(local_cfg["episodes"]),
        "final_window": final_window,
        "best_checkpoint_episode": best_episode,
        "best_checkpoint_score": list(best_score) if best_score is not None else None,
        "reward_normalization_std": float(reward_stats.std),
        "optimization_profile": {
            "episode_len": int(local_cfg["episode_len"]),
            "leader_start": list(local_cfg["leader_start"]),
            "leader_target": list(local_cfg["leader_target"]),
            "max_altitude": float(local_cfg["max_altitude"]),
            "formation_offset_order": list(
                local_cfg.get("formation_offset_order", [0, 1, 2, 3])
            ),
            "curriculum_enabled": bool(local_cfg.get("curriculum_enabled", False)),
            "curriculum_static_episodes": int(
                local_cfg.get("curriculum_static_episodes", 0)
            ),
            "curriculum_forced_start_step": int(
                local_cfg.get("curriculum_forced_start_step", 0)
            ),
            "curriculum_speed_schedule": list(
                local_cfg.get("curriculum_speed_schedule", [])
            ),
            "velocity_reward_weight": float(
                local_cfg.get("velocity_reward_weight", 0.0)
            ),
            "reward_normalization": bool(
                local_cfg.get("reward_normalization", False)
            ),
            "value_clip": float(local_cfg.get("value_clip", 0.0)),
            "minibatch_size": int(local_cfg.get("minibatch_size", 0)),
            "log_std_init": float(local_cfg.get("log_std_init", 0.0)),
            "critic_hidden": int(local_cfg.get("critic_hidden", 128)),
        },
        "error_history": error_history,
        "pairwise_error_history": pairwise_error_history,
        "reward_history": reward_history,
        "collision_history": collision_history,
        "collision_count_history": collision_count_history,
        "acquisition_history": acquisition_history,
        "leader_goal_history": leader_goal_history,
        "follow_retention_history": follow_retention_history,
        "follow_mean_retention_history": follow_mean_retention_history,
        "per_agent_follow_retention_history": per_agent_follow_retention_history,
        "follow_error_history": follow_error_history,
        "terminal_max_target_error_history": terminal_max_target_error_history,
        "task_success_without_safety_history": task_success_without_safety_history,
        "safe_success_history": safe_success_history,
        "success_history": success_history,
        "success_definition": (
            "formation acquisition, leader arrival, per-agent tracking retention, "
            "and terminal target error; collision-free success is also reported separately"
        ),
        "first_acquisition_episode": monitor.first_acquisition_episode,
        "first_success_episode": monitor.first_success_episode,
        "stable_breakthrough_episode": stable_ep,
        "first_safe_success_episode": first_safe_success,
        "safe_stable_breakthrough_episode": safe_stable_ep,
        "final_success_rate": float(np.mean(success_history[-final_window:])) * 100.0,
        "final_task_success_without_safety_rate": float(
            np.mean(task_success_without_safety_history[-final_window:])
        ) * 100.0,
        "final_safe_success_rate": float(np.mean(safe_success_history[-final_window:])) * 100.0,
        "final_acquisition_rate": float(np.mean(acquisition_history[-final_window:])) * 100.0,
        "final_leader_goal_rate": float(np.mean(leader_goal_history[-final_window:])) * 100.0,
        "final_follow_retention_ratio": float(np.mean(follow_retention_history[-final_window:])) * 100.0,
        "final_follow_mean_retention_ratio": float(np.mean(follow_mean_retention_history[-final_window:])) * 100.0,
        "final_follow_position_error": float(np.mean(follow_error_history[-final_window:])),
        "final_terminal_max_target_error": float(np.mean(terminal_max_target_error_history[-final_window:])),
        "final_position_error": float(np.mean(error_history[-final_window:])),
        "final_pairwise_formation_error": float(np.mean(pairwise_error_history[-final_window:])),
        "final_collision_episode_rate": float(np.mean(collision_history[-final_window:])) * 100.0,
        "final_mean_collision_count": float(np.mean(collision_count_history[-final_window:])),
        "llm_consultation_count": len(monitor.consultation_history),
        "intervention_event_count": len(monitor.intervention_history),
        "parameter_update_count": monitor.parameter_update_count,
        "llm_latency_mean_seconds": float(np.mean(latencies)) if latencies else None,
        "llm_latency_median_seconds": float(np.median(latencies)) if latencies else None,
        "llm_latency_p95_seconds": float(np.percentile(latencies, 95)) if latencies else None,
        "consultations_by_phase": calls_by_phase,
        "interventions_by_phase": events_by_phase,
        "episodes_by_phase": phase_counts,
        "phase_transitions": monitor.phase_transition_history,
        "consultation_history": monitor.consultation_history,
        "intervention_history": monitor.intervention_history,
        "param_history": param_history,
        "phase_history": phase_history,
        "elapsed_seconds": elapsed,
        "config_snapshot": local_cfg,
        "software": {
            "python_torch_version": torch.__version__,
            "numpy_version": np.__version__,
            "device": str(local_cfg["device"]),
        },
    }
    json_dump(result_path, results)
    torch.save(actor.state_dict(), run_dir / "actor_final.pth")
    torch.save(critic.state_dict(), run_dir / "critic_final.pth")

    source_method = str(local_cfg.get("matched_schedule_source", "phase_aware"))
    if controller_type == "phase_aware" and method == source_method:
        schedule = [
            {
                "episode": int(event["episode"]),
                "phase": str(event["phase"]),
                "n_parameter_updates": int(event["n_parameter_updates"]),
            }
            for event in monitor.intervention_history
        ]
        json_dump(run_dir / "matched_schedule.json", schedule)

    return results


def evaluate_saved_actor(
    actor_path: Path,
    cfg: Dict[str, Any],
    seed: int,
    n_episodes: int = 100,
    deterministic: bool = True,
) -> Dict[str, Any]:
    """Evaluate a shared actor without a critic, enabling zero-shot N-agent tests."""
    local_cfg = deepcopy(cfg)
    local_cfg["env_seed"] = int(seed)
    set_global_seed(seed)
    env = MovingLeaderFormationEnv3D(local_cfg)
    obs, _ = env.reset()
    actor = SquashedGaussianActor(obs.shape[1]).to(local_cfg["device"])
    actor.load_state_dict(torch.load(str(actor_path), map_location=local_cfg["device"]))
    actor.eval()
    rows: List[Dict[str, Any]] = []
    with torch.no_grad():
        for episode in range(1, n_episodes + 1):
            obs, _ = env.reset()
            info: Dict[str, Any] = {}
            for _ in range(int(local_cfg["episode_len"])):
                obs_t = torch.tensor(obs, dtype=torch.float32, device=local_cfg["device"])
                if deterministic:
                    action = torch.tanh(actor.net(obs_t))
                else:
                    action, _ = actor.sample_action(obs_t)
                obs, _, terminated, truncated, info = env.step(
                    action.cpu().numpy().astype(np.float32)
                )
                if terminated or truncated:
                    break
            rows.append(
                {
                    "episode": episode,
                    "full_task_success": int(bool(info["full_task_success"])),
                    "safe_full_task_success": int(bool(info["safe_full_task_success"])),
                    "avg_follow_position_error": float(info["avg_follow_position_error"]),
                    "avg_pairwise_formation_error": float(info["avg_pairwise_formation_error"]),
                    "episode_had_collision": int(bool(info["episode_had_collision"])),
                    "episode_collision_count": int(info["episode_collision_count"]),
                }
            )
    return {
        "actor_path": str(actor_path),
        "seed": seed,
        "n_eval_episodes": n_episodes,
        "n_agents": int(local_cfg["n_agents"]),
        "leader_target": local_cfg["leader_target"],
        "observation_noise_std": float(local_cfg.get("observation_noise_std", 0.0)),
        "action_noise_std": float(local_cfg.get("action_noise_std", 0.0)),
        "full_task_success_rate": float(np.mean([r["full_task_success"] for r in rows])) * 100.0,
        "safe_full_task_success_rate": float(np.mean([r["safe_full_task_success"] for r in rows])) * 100.0,
        "mean_follow_position_error": float(np.mean([r["avg_follow_position_error"] for r in rows])),
        "mean_pairwise_formation_error": float(np.mean([r["avg_pairwise_formation_error"] for r in rows])),
        "collision_episode_rate": float(np.mean([r["episode_had_collision"] for r in rows])) * 100.0,
        "mean_collision_count": float(np.mean([r["episode_collision_count"] for r in rows])),
        "episodes": rows,
    }


# -----------------------------------------------------------------------------
# Reporting and figures
# -----------------------------------------------------------------------------
def collect_results(
    results_dir: Path, methods: Sequence[str], seeds: Sequence[int]
) -> Dict[str, Dict[int, Dict[str, Any]]]:
    collected: Dict[str, Dict[int, Dict[str, Any]]] = {
        method: {} for method in methods
    }
    for method in methods:
        for seed in seeds:
            path = results_dir / f"{method}_seed{seed}" / "results.json"
            if not path.exists():
                raise FileNotFoundError(f"Missing result file: {path}")
            with path.open("r", encoding="utf-8") as f:
                collected[method][seed] = json.load(f)
    return collected


def format_mean_std(values: Sequence[float], decimals: int = 1) -> str:
    mean, std = mean_std(values)
    if not np.isfinite(mean):
        return "N/A"
    return f"{mean:.{decimals}f} ± {std:.{decimals}f}"


def write_reports(
    all_results: Dict[str, Dict[int, Dict[str, Any]]],
    methods: Sequence[str],
    seeds: Sequence[int],
    results_dir: Path,
) -> None:
    metrics = [
        "first_success_episode",
        "stable_breakthrough_episode",
        "final_acquisition_rate",
        "final_leader_goal_rate",
        "final_follow_retention_ratio",
        "final_follow_mean_retention_ratio",
        "final_follow_position_error",
        "final_terminal_max_target_error",
        "final_position_error",
        "final_pairwise_formation_error",
        "final_success_rate",
        "final_task_success_without_safety_rate",
        "final_safe_success_rate",
        "final_collision_episode_rate",
        "final_mean_collision_count",
        "llm_consultation_count",
        "intervention_event_count",
        "parameter_update_count",
        "llm_latency_mean_seconds",
        "llm_latency_median_seconds",
        "llm_latency_p95_seconds",
        "elapsed_seconds",
    ]

    per_seed_path = results_dir / "per_seed_metrics.csv"
    with per_seed_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["method", "seed"] + metrics)
        writer.writeheader()
        for method in methods:
            for seed in seeds:
                result = all_results[method][seed]
                writer.writerow(
                    {"method": method, "seed": seed}
                    | {metric: result.get(metric) for metric in metrics}
                )

    summary_rows: List[Dict[str, Any]] = []
    for method in methods:
        row: Dict[str, Any] = {
            "method": method,
            "method_label": METHOD_LABELS.get(method, method),
            "n_seeds": len(seeds),
        }
        for metric in metrics:
            values = []
            reached = 0
            for seed in seeds:
                result = all_results[method][seed]
                value = result.get(metric)
                if metric in {"first_success_episode", "stable_breakthrough_episode"}:
                    if value is None:
                        value = int(result["n_episodes"]) + 1
                    else:
                        reached += 1
                elif value is None:
                    continue
                values.append(value)
            row[f"{metric}_n"] = len(values)
            if metric in {"first_success_episode", "stable_breakthrough_episode"}:
                row[f"{metric}_events_reached"] = reached
            if values:
                row[f"{metric}_mean"] = float(np.mean(values))
                row[f"{metric}_sample_std"] = sample_std(values)
            else:
                row[f"{metric}_mean"] = None
                row[f"{metric}_sample_std"] = None
        summary_rows.append(row)

    summary_path = results_dir / "summary_metrics.csv"
    fieldnames = list(dict.fromkeys(key for row in summary_rows for key in row.keys()))
    with summary_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
    json_dump(results_dir / "summary_metrics.json", summary_rows)

    print(f"\nPaper statistics: mean ± sample std over {len(seeds)} seeds")
    header = (
        f"{'Method':<40} {'First full success':<20} {'Stable breakthrough':<20} "
        f"{'Follow err (m)':<18} {'Final pair err (m)':<21} "
        f"{'Full-task SR (%)':<18} {'Events':<14}"
    )
    print(header)
    print("-" * len(header))
    for method in methods:
        results = [all_results[method][seed] for seed in seeds]
        first_reached = sum(r["first_success_episode"] is not None for r in results)
        stable_reached = sum(r["stable_breakthrough_episode"] is not None for r in results)
        first = [r["first_success_episode"] if r["first_success_episode"] is not None else r["n_episodes"] + 1 for r in results]
        stable = [r["stable_breakthrough_episode"] if r["stable_breakthrough_episode"] is not None else r["n_episodes"] + 1 for r in results]
        print(
            f"{METHOD_LABELS.get(method, method):<40} "
            f"{format_mean_std(first, 1):<18} "
            f"{format_mean_std(stable, 1):<20} "
            f"{format_mean_std([r['final_follow_position_error'] for r in results], 1):<18} "
            f"{format_mean_std([r['final_pairwise_formation_error'] for r in results], 1):<21} "
            f"{format_mean_std([r['final_success_rate'] for r in results], 1):<18} "
            f"{format_mean_std([r['intervention_event_count'] for r in results], 1):<14}"
        )
        if first_reached != len(seeds) or stable_reached != len(seeds):
            print(
                f"  NOTE: First/Stable events reached = {first_reached}/{len(seeds)} and "
                f"{stable_reached}/{len(seeds)}. Unreached events are represented as "
                "max_episode + 1 rather than dropped."
            )


def setup_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.linestyle": "--",
        }
    )


def save_figure(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_comparisons(
    all_results: Dict[str, Dict[int, Dict[str, Any]]],
    methods: Sequence[str],
    seeds: Sequence[int],
    results_dir: Path,
) -> None:
    setup_plot_style()
    window = 20

    fig, ax = plt.subplots(figsize=(11, 6.5))
    for method in methods:
        curves = []
        for seed in seeds:
            errors = all_results[method][seed]["error_history"]
            curves.append(rolling_mean(errors, window))
        min_len = min(len(x) for x in curves)
        stack = np.stack([x[:min_len] for x in curves])
        mean = stack.mean(axis=0)
        std = stack.std(axis=0, ddof=1) if len(seeds) > 1 else np.zeros_like(mean)
        x = np.arange(window, window + min_len)
        color = METHOD_COLORS.get(method)
        ax.plot(x, mean, label=METHOD_LABELS.get(method, method), color=color, linewidth=2.2)
        ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.18)
    ax.axhline(
        float(BASE_CFG["formation_threshold"]),
        linestyle="--",
        linewidth=1.5,
        color="#EF4444",
        label="Formation threshold",
    )
    ax.set_xlabel("Episode")
    ax.set_ylabel("Average target-position error (m)")
    ax.set_title(f"Training convergence (mean ± sample std, n={len(seeds)})")
    ax.legend(fontsize=8)
    save_figure(fig, results_dir / "fig_training_position_error.png")

    metric_specs = [
        (
            "first_success_episode",
            "First full-task success episode",
            "fig_first_success.png",
        ),
        (
            "stable_breakthrough_episode",
            "Stable breakthrough episode",
            "fig_stable_breakthrough.png",
        ),
        (
            "final_success_rate",
            "Final full-task success rate (%)",
            "fig_final_success_rate.png",
        ),
        (
            "final_safe_success_rate",
            "Final collision-free success rate (%)",
            "fig_final_safe_success_rate.png",
        ),
        (
            "final_follow_position_error",
            "Final following target error (m)",
            "fig_final_follow_error.png",
        ),
        (
            "final_position_error",
            "Final target-position error (m)",
            "fig_final_position_error.png",
        ),
        (
            "final_pairwise_formation_error",
            "Final pairwise formation error (m)",
            "fig_final_pairwise_error.png",
        ),
        (
            "intervention_event_count",
            "Meta-control intervention events",
            "fig_intervention_events.png",
        ),
    ]
    for metric, ylabel, filename in metric_specs:
        fig, ax = plt.subplots(figsize=(10, 6))
        means, stds = [], []
        for method in methods:
            values = []
            for seed in seeds:
                result = all_results[method][seed]
                value = result.get(metric)
                if metric in {"first_success_episode", "stable_breakthrough_episode"} and value is None:
                    value = int(result["n_episodes"]) + 1
                if value is not None:
                    values.append(value)
            mean, std = mean_std(values)
            means.append(mean if np.isfinite(mean) else 0.0)
            stds.append(std if np.isfinite(std) else 0.0)
        x = np.arange(len(methods))
        bars = ax.bar(
            x,
            means,
            yerr=stds,
            capsize=5,
            color=[METHOD_COLORS.get(m, f"C{i}") for i, m in enumerate(methods)],
            edgecolor="black",
            linewidth=0.8,
        )
        for bar, mean, std in zip(bars, means, stds):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{mean:.1f}±{std:.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.set_xticks(x)
        ax.set_xticklabels([METHOD_LABELS.get(m, m) for m in methods], rotation=12, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{ylabel} (mean ± sample std, n={len(seeds)})")
        save_figure(fig, results_dir / filename)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", default=BASE_CFG["results_dir"], help="Output directory"
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=[
            "baseline",
            "phase_aware",
            "uniform_matched",
            "random_matched",
            "rule_based",
        ],
        default=[
            "phase_aware",
            "baseline",
            "uniform_matched",
            "random_matched",
            "rule_based",
        ],
        help="Methods to run; matched baselines still execute after phase_aware",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=DEFAULT_SEEDS_10,
        help="Independent random seeds (paper protocol requires at least ten)",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=BASE_CFG["episodes"],
        help="Training episodes per run",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Torch device, e.g. cuda or cpu (default: auto-detect)",
    )
    parser.add_argument(
        "--ollama-url",
        default=BASE_CFG["ollama_base_url"],
        help="Ollama base URL used by the LLM methods",
    )
    parser.add_argument(
        "--llm-model",
        default=BASE_CFG["llm_model"],
        help="Ollama model name used by the LLM methods",
    )
    parser.add_argument(
        "--no-curriculum",
        action="store_true",
        help="Disable the staged leader-motion curriculum",
    )
    parser.add_argument(
        "--curriculum-static-episodes",
        type=int,
        default=None,
        help="Episodes with a stationary leader before the curriculum starts",
    )
    parser.add_argument(
        "--curriculum-forced-start-step",
        type=int,
        default=None,
        help="Step at which the leader starts moving even without acquisition",
    )
    parser.add_argument(
        "--no-reward-norm",
        action="store_true",
        help="Disable running reward normalisation",
    )
    parser.add_argument(
        "--velocity-weight",
        type=float,
        default=None,
        help="Velocity-matching reward weight after formation (3-D only)",
    )
    parser.add_argument(
        "--log-std-init",
        type=float,
        default=None,
        help="Initial actor log standard deviation",
    )
    parser.add_argument(
        "--critic-hidden",
        type=int,
        default=None,
        help="Hidden width of the centralised critic",
    )
    parser.add_argument(
        "--ppo-epochs",
        type=int,
        default=None,
        help="PPO optimisation epochs per episode",
    )
    parser.add_argument(
        "--minibatch-size",
        type=int,
        default=None,
        help="PPO minibatch size (0 keeps the full batch)",
    )
    parser.add_argument(
        "--actor-lr",
        type=float,
        default=None,
        help="Actor learning rate",
    )
    parser.add_argument(
        "--critic-lr",
        type=float,
        default=None,
        help="Critic learning rate",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse an existing results.json for an already completed run",
    )
    parser.add_argument(
        "--phase-mode",
        choices=["metrics", "fixed"],
        default=BASE_CFG["phase_detection_mode"],
    )
    parser.add_argument(
        "--episode-len",
        type=int,
        default=BASE_CFG["episode_len"],
        help="Maximum environment steps per training episode",
    )
    parser.add_argument(
        "--max-speed",
        type=float,
        default=BASE_CFG["max_speed"],
        help="Follower speed limit (m/s)",
    )
    parser.add_argument(
        "--leader-speed",
        type=float,
        default=BASE_CFG["leader_speed"],
        help="Leader cruise speed after formation acquisition (m/s)",
    )
    parser.add_argument(
        "--leader-acceleration",
        type=float,
        default=BASE_CFG["leader_acceleration"],
        help="Leader acceleration limit (m/s^2)",
    )
    parser.add_argument(
        "--follow-error-threshold",
        type=float,
        default=BASE_CFG["follow_error_threshold"],
        help="Maximum per-follower target error for a valid following step (m)",
    )
    parser.add_argument(
        "--follow-retention-threshold",
        type=float,
        default=BASE_CFG["follow_retention_threshold"],
        help="Required fraction of valid following steps in a successful episode",
    )
    parser.add_argument(
        "--terminal-follow-error-threshold",
        type=float,
        default=BASE_CFG["terminal_follow_error_threshold"],
        help="Maximum follower target error when the leader reaches the goal (m)",
    )
    parser.add_argument(
        "--mid-late-error-threshold",
        type=float,
        default=BASE_CFG["mid_to_late"]["mean_follow_error"],
        help="Rolling mean following-error threshold for Mid-to-Late transition (m)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if len(args.seeds) < 1:
        raise ValueError("At least one seed is required.")
    if len(args.seeds) < 10:
        print(
            f"WARNING: only {len(args.seeds)} seed(s) requested. "
            "The primary paper protocol requires at least ten."
        )
    if args.episodes <= 0:
        raise ValueError("--episodes must be positive.")
    if args.device and args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(
            "--device requests CUDA, but torch.cuda.is_available() is False."
        )
    if not 0.0 <= args.follow_retention_threshold <= 1.0:
        raise ValueError("--follow-retention-threshold must be between 0 and 1.")
    if args.episode_len <= 0:
        raise ValueError("--episode-len must be positive.")
    if args.max_speed <= 0.0 or args.leader_speed <= 0.0:
        raise ValueError("--max-speed and --leader-speed must be positive.")
    if args.leader_speed >= args.max_speed:
        raise ValueError("--leader-speed must be strictly lower than --max-speed.")
    if args.leader_acceleration <= 0.0:
        raise ValueError("--leader-acceleration must be positive.")
    for name, value in {
        "--follow-error-threshold": args.follow_error_threshold,
        "--terminal-follow-error-threshold": args.terminal_follow_error_threshold,
        "--mid-late-error-threshold": args.mid_late_error_threshold,
    }.items():
        if value <= 0.0:
            raise ValueError(f"{name} must be positive.")

    cfg = deepcopy(BASE_CFG)
    cfg["results_dir"] = args.results_dir
    cfg["episodes"] = args.episodes
    cfg["phase_detection_mode"] = args.phase_mode
    cfg["episode_len"] = args.episode_len
    cfg["max_speed"] = args.max_speed
    cfg["leader_speed"] = args.leader_speed
    cfg["leader_acceleration"] = args.leader_acceleration
    cfg["follow_error_threshold"] = args.follow_error_threshold
    cfg["follow_retention_threshold"] = args.follow_retention_threshold
    cfg["terminal_follow_error_threshold"] = args.terminal_follow_error_threshold
    cfg["mid_to_late"]["mean_follow_error"] = args.mid_late_error_threshold
    cfg["ollama_base_url"] = args.ollama_url
    cfg["llm_model"] = args.llm_model
    if args.device:
        cfg["device"] = args.device
    if args.no_curriculum:
        cfg["curriculum_enabled"] = False
    if args.curriculum_static_episodes is not None:
        cfg["curriculum_static_episodes"] = int(args.curriculum_static_episodes)
    if args.curriculum_forced_start_step is not None:
        cfg["curriculum_forced_start_step"] = int(args.curriculum_forced_start_step)
    if args.no_reward_norm:
        cfg["reward_normalization"] = False
    if args.velocity_weight is not None:
        cfg["velocity_reward_weight"] = float(args.velocity_weight)
    if args.log_std_init is not None:
        cfg["log_std_init"] = float(args.log_std_init)
    if args.critic_hidden is not None:
        cfg["critic_hidden"] = int(args.critic_hidden)
    if args.ppo_epochs is not None:
        cfg["ppo_epochs"] = int(args.ppo_epochs)
    if args.minibatch_size is not None:
        cfg["minibatch_size"] = int(args.minibatch_size)
    if args.actor_lr is not None:
        cfg["actor_lr"] = float(args.actor_lr)
    if args.critic_lr is not None:
        cfg["critic_lr"] = float(args.critic_lr)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    json_dump(results_dir / "experiment_config.json", cfg)
    print(
        f"Device: {cfg['device']} | episodes/run: {cfg['episodes']} | seeds: {args.seeds} | "
        f"curriculum={cfg['curriculum_enabled']} | reward_norm={cfg['reward_normalization']} | "
        f"velocity_weight={cfg['velocity_reward_weight']} | ppo_epochs={cfg['ppo_epochs']} | "
        f"minibatch={cfg['minibatch_size']}"
    )

    # The proposed method must run first because it creates the matched schedule
    # consumed by the two controlled baselines.
    requested = set(args.methods)
    execution_order = [
        method
        for method in [
            "phase_aware",
            "baseline",
            "uniform_matched",
            "random_matched",
            "rule_based",
        ]
        if method in requested
    ]
    report_order = [
        method
        for method in [
            "baseline",
            "random_matched",
            "uniform_matched",
            "rule_based",
            "phase_aware",
        ]
        if method in requested
    ]
    matched_methods = requested & {"uniform_matched", "random_matched"}
    if matched_methods and "phase_aware" not in requested:
        missing = [
            str(results_dir / f"phase_aware_seed{seed}" / "matched_schedule.json")
            for seed in args.seeds
            if not (
                results_dir / f"phase_aware_seed{seed}" / "matched_schedule.json"
            ).exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Matched baselines need the phase_aware schedules first. "
                "Add phase_aware to --methods or run it beforehand. Missing:\n"
                + "\n".join(missing)
            )

    start = time.time()
    for method in execution_order:
        for seed in args.seeds:
            print(f"\n=== Running {METHOD_LABELS[method]} | seed={seed} ===")
            train_single_run(method, seed, cfg, results_dir, resume=args.resume)

    all_results = collect_results(results_dir, report_order, args.seeds)
    write_reports(all_results, report_order, args.seeds, results_dir)
    plot_comparisons(all_results, report_order, args.seeds, results_dir)
    print(f"\nTotal wall-clock time: {(time.time() - start) / 3600.0:.2f} hours")
    print(f"Results written to: {results_dir.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExperiment interrupted by user.")
        raise SystemExit(130)
