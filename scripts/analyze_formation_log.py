#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_formation_log.py — 分析 mappo_formation 的 episode JSONL 日志

用法: python3 analyze_formation_log.py /tmp/mappo_formation_xxx.jsonl
只允许读取 /tmp 或 /mnt/d 下的日志文件。
"""
import json
import sys
from pathlib import Path

import numpy as np

ALLOWED_ROOTS = ("/tmp", "/mnt/d")


def safe_log_path(raw: str) -> Path:
    path = Path(raw).resolve()
    if not path.is_file():
        raise SystemExit(f"日志不存在: {path}")
    if not str(path).startswith(ALLOWED_ROOTS):
        raise SystemExit("只允许分析 /tmp 或 /mnt/d 下的日志")
    return path


def main():
    path = safe_log_path(sys.argv[1])
    steps = [json.loads(l) for l in path.open(encoding="utf-8")
             if '"step"' in l]
    if not steps:
        print("无 step 记录")
        return
    comp_t = next((s["t"] for s in steps if s["formation_complete"]), None)
    print(f"steps={len(steps)} 编队完成tick={comp_t}")

    def series(i, field, lo, hi):
        return np.array([d[field] for s in steps if lo <= s["t"] <= hi
                         for d in s["drones"] if d["i"] == i], dtype=float)

    hi = steps[-1]["t"]
    comp = comp_t if comp_t is not None else hi
    print("drone | 集结max|v| 跟随max|v| 跟随max|cmd| 跟随P95|v|")
    for i in range(4):
        av = np.hypot(series(i, "vel", 0, comp)[:, 0], series(i, "vel", 0, comp)[:, 1]) \
            if comp > 0 else np.array([0.0])
        fv = np.hypot(series(i, "vel", comp, hi)[:, 0], series(i, "vel", comp, hi)[:, 1])
        fc = np.hypot(series(i, "cmd", comp, hi)[:, 0], series(i, "cmd", comp, hi)[:, 1])
        print(f"  {i}  | {av.max():8.1f} {fv.max():10.1f} {fc.max():11.1f} "
              f"{np.percentile(fv, 95):10.1f}")

    print("\n误差轨迹（关键 tick）:")
    by_t = {s["t"]: s for s in steps}
    ticks = [t for t in (0, 20, 40, 60, 80, 100, 120, 150, 200, 250, 300, 400, hi) if t in by_t]
    print(" tick |  err0   err1   err2   err3  |  max  | complete")
    for tk in ticks:
        s = by_t[tk]
        es = [d["err"] for d in s["drones"]]
        print(f"{tk:5d} | " + " ".join(f"{e:6.1f}" for e in es)
              + f" | {max(es):5.1f} | {s.get('formation_complete')}")

    late0 = min(comp + 50, hi - 10)
    if late0 < hi - 5:
        print(f"\n跟随后期(t>{late0}) east 轴 指令 vs 实际:")
        for i in range(4):
            cv = series(i, "cmd", late0, hi)[:, 0]
            vv = series(i, "vel", late0, hi)[:, 0]
            if len(cv):
                print(f"  drone{i}: cmd={cv.mean():6.1f}  act={vv.mean():6.1f}  "
                      f"差={cv.mean() - vv.mean():6.1f}")


if __name__ == "__main__":
    main()
