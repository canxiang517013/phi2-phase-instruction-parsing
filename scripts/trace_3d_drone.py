#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace_3d_drone.py — 3D episode 某架机的垂直/水平轨迹

用法: python3 trace_3d_drone.py <jsonl> <drone_idx> [stride]
"""
import json
import sys
from pathlib import Path

ALLOWED_ROOTS = ("/tmp", "/mnt/d")


def main():
    path = Path(sys.argv[1]).resolve()
    if not str(path).startswith(ALLOWED_ROOTS) or not path.is_file():
        raise SystemExit("只允许读取 /tmp 或 /mnt/d 下的日志")
    idx = int(sys.argv[2])
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    steps = [json.loads(l) for l in path.open(encoding="utf-8")
             if '"event": "step"' in l]
    print(" t |  up   vz   cmdz |  ce   cn   ve   vn | err")
    for s in steps[::stride] + [steps[-1]]:
        d = next(x for x in s["drones"] if x["i"] == idx)
        print("%3d | %6.2f %6.2f %6.2f | %5.2f %5.2f %5.2f %5.2f | %5.1f" % (
            s["t"], d["up"], d["vel"][2], d["cmd"][2],
            d["cmd"][0], d["cmd"][1], d["vel"][0], d["vel"][1], d["err"]))


if __name__ == "__main__":
    main()
