#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare_formation_runs.py — 汇总多个 mappo_formation episode 日志

用法: python3 compare_formation_runs.py /tmp/mappo_formation_*.jsonl
输出每集: 完成tick / leader到达 / 保持率 / terminal误差 / 平均误差 / 成功
"""
import json
import sys
from pathlib import Path

ALLOWED_ROOTS = ("/tmp", "/mnt/d")


def load(path: str):
    p = Path(path).resolve()
    if not str(p).startswith(ALLOWED_ROOTS) or not p.is_file():
        return None
    end, comp_tick, n_steps = None, None, 0
    for line in p.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("event") == "step":
            n_steps += 1
            if comp_tick is None and r.get("formation_complete"):
                comp_tick = r["t"]
        elif r.get("event") == "episode_end":
            end = r
    if end is None:
        return None
    return p.name, comp_tick, end, n_steps


def main():
    rows = []
    for arg in sys.argv[1:]:
        item = load(arg)
        if item:
            rows.append(item)
    if not rows:
        raise SystemExit("没有可用的 episode 日志")
    print(f"{'日志':<38}{'完成tick':>8}{'leader到':>8}{'min保持率':>9}"
          f"{'terminal':>9}{'avgErr':>8}{'成功':>5}")
    for name, comp, end, _ in rows:
        ret = end.get("per_agent_follow_retention", [])
        min_ret = min(ret) if ret else 0.0
        print(f"{name:<38}{str(comp):>8}{str(end['leader_reached_goal']):>8}"
              f"{min_ret:>9.2f}{end['terminal_max_target_error']:>9.1f}"
              f"{end['avg_position_error']:>8.1f}"
              f"{str(end['full_task_success']):>5}")
        print(f"{'':<38}  保持率={[round(x, 2) for x in ret]} 步数={end['steps']}")


if __name__ == "__main__":
    main()
