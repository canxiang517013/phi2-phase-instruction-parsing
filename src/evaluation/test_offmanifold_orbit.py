#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_offmanifold_orbit.py — 用仿真观测到的状态注入 2D 环境，验证环绕极限环

从 mappo_formation 的某个 step 记录取 4 机 pos/vel，重置 2D 环境到该状态
（leader 原点、未完成编队），用同一 npz 策略步进 300 tick。
若误差不收敛而维持大误差环绕 → 证明是策略的离流形极限环，非桥接 bug。
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
RUN_DIR = ROOT / "phase-aware-llm-meta-controller" / "results_repro" / "baseline_seed555"
NPZ = ROOT / "assets" / "mappo_2d_seed555_actor.npz"


def main() -> None:
    log_path = Path(sys.argv[1]).resolve()
    inject_t = int(sys.argv[2])
    spec = importlib.util.spec_from_file_location("experiment_core_2d_orbit", ENV_FILE)
    ec = importlib.util.module_from_spec(spec)
    sys.modules["experiment_core_2d_orbit"] = ec
    spec.loader.exec_module(ec)

    actor = bm.NumpyActor.from_npz(NPZ)
    cfg = json.loads((RUN_DIR / "config_snapshot.json").read_text(encoding="utf-8"))
    env = ec.MovingLeaderFormationEnv(cfg)
    env.reset()

    step_rec = None
    for line in log_path.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("event") == "step" and r["t"] == inject_t:
            step_rec = r
            break
    if step_rec is None:
        raise SystemExit(f"tick {inject_t} 不存在")

    env.pos = np.array([d["pos"] for d in step_rec["drones"]], dtype=np.float32)
    env.vel = np.array([d["vel"] for d in step_rec["drones"]], dtype=np.float32)
    env.leader_pos = np.array(step_rec["leader"], dtype=np.float32)
    env.leader_vel = np.zeros(2, dtype=np.float32)
    env.formation_complete = bool(step_rec.get("formation_complete", False))
    env.formation_phase = not env.formation_complete
    env.formation_stable_count = int(step_rec.get("stable_count", 0))
    env.t = 0

    errs_hist = []
    obs = env.obs()
    for t in range(1, 301):
        action = actor.act(obs)
        obs, _, terminated, truncated, info = env.step(
            action.astype(np.float32))
        errs_hist.append(float(info["max_position_error"]))
        if terminated or truncated:
            break

    e = np.array(errs_hist)
    print(f"注入 tick={inject_t}, 初始 max_err={e[0]:.1f}")
    for frac in (0.1, 0.3, 0.5, 0.7, 0.9):
        i = min(int(e.size * frac), e.size - 1)
        print(f"  t={i * 10 / 10:>3}0% 处 max_err={e[i]:6.1f}")
    print(f"  末端 max_err={e[-1]:.1f}, 完成编队={env.formation_complete}, "
          f"terminated={terminated}, truncated={truncated}")
    if e[-1] > 20.0 and not env.formation_complete:
        print("结论：纯 2D 环境内同样无法收敛 → 策略离流形极限环（非桥接 bug）")
    else:
        print("结论：纯 2D 环境可恢复收敛 → 问题在平台动力学（桥接/参数侧）")


if __name__ == "__main__":
    main()
