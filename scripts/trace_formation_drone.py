#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace_formation_drone.py — 打印某架机的逐 tick 明细（诊断振荡用）

用法: python3 trace_formation_drone.py <jsonl> <drone_idx> <t0> <t1>
"""
import json
import sys
from pathlib import Path

import numpy as np

ALLOWED_ROOTS = ("/tmp", "/mnt/d")


def main():
    path = Path(sys.argv[1]).resolve()
    if not str(path).startswith(ALLOWED_ROOTS) or not path.is_file():
        raise SystemExit("只允许读取 /tmp 或 /mnt/d 下的日志")
    idx, t0, t1 = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    rows = []
    for line in path.open(encoding="utf-8"):
        r = json.loads(line)
        if r.get("event") == "step" and t0 <= r["t"] <= t1:
            d = next(x for x in r["drones"] if x["i"] == idx)
            rows.append((r["t"], r["leader"], d))
    if not rows:
        raise SystemExit("区间内无记录")
    print(" tick | target_e target_n |  pos_e   pos_n | err |  cmd_e   cmd_n |cmd| |  vel_e   vel_n |vel|")
    for t, leader, d in rows:
        te, tn = leader[0] + 60.0 * [1, 0, -1, 0][idx], leader[1] + 60.0 * [0, 1, 0, -1][idx]
        ce, cn = d["cmd"]
        ve, vn = d["vel"]
        print(f"{t:5d} | {te:8.1f} {tn:7.1f} | {d['pos'][0]:7.1f} {d['pos'][1]:7.1f} "
              f"| {d['err']:4.1f} | {ce:7.1f} {cn:7.1f} |{np.hypot(ce, cn):4.1f}| "
              f"| {ve:7.1f} {vn:7.1f} |{np.hypot(ve, vn):4.1f}|")


if __name__ == "__main__":
    main()
