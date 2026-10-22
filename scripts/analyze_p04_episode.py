#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_p04_episode.py — P0-4 闭环 episode 的关键事件与 leader 轨迹

用法: python3 analyze_p04_episode.py <jsonl>
"""
import json
import sys
from pathlib import Path

ALLOWED_ROOTS = ("/tmp", "/mnt/d")


def main():
    path = Path(sys.argv[1]).resolve()
    if not str(path).startswith(ALLOWED_ROOTS) or not path.is_file():
        raise SystemExit("只允许读取 /tmp 或 /mnt/d 下的日志")

    steps = []
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        ev = r.get("event")
        if ev == "step":
            steps.append(r)
        elif ev in ("primitive_applied", "primitive_reject", "episode_end",
                    "link_degraded", "link_recovered", "config", "phase"):
            keep = {k: r.get(k) for k in ("event", "type", "target", "reason",
                                          "nl", "phase", "from", "to",
                                          "formation_complete", "steps",
                                          "leader_reached_goal",
                                          "full_task_success") if k in r}
            print("EVT", json.dumps(keep, ensure_ascii=False)[:220])

    print("step 数:", len(steps))
    marks = [0, 100, 200, 300, 400, 500, 550, 600, len(steps) - 1]
    last = -1
    for m in marks:
        if 0 <= m < len(steps) and m > last:
            last = m
            s = steps[m]
            errs = [round(d["err"], 1) for d in s["drones"]]
            print(f"t={s['t']:>4} hold={s.get('hold')} "
                  f"leader=({s['leader'][0]:6.1f},{s['leader'][1]:6.1f}) "
                  f"errs={errs} phase={s.get('link_phase')}")

    moved = [s for s in steps if abs(s["leader"][0]) > 0.5 or abs(s["leader"][1]) > 0.5]
    if moved:
        print(f"leader 首次移动 t={moved[0]['t']}, 末端 t={steps[-1]['t']} "
              f"位置=({steps[-1]['leader'][0]:.1f},{steps[-1]['leader'][1]:.1f})")


if __name__ == "__main__":
    main()
