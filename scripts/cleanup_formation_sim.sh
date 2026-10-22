#!/bin/bash
# cleanup_formation_sim.sh — 停掉编队仿真的全部残留进程并清理巨型日志
# 模式用 [x] 写法防止 pkill -f 匹配到本脚本自身
set -x
pkill -9 -f 'bin/p[x]4' 2>/dev/null
pkill -9 -f 'mappo_formatio[n]' 2>/dev/null
pkill -9 -f 'MicroXRCEAgen[t]' 2>/dev/null
sleep 2
rm -f /tmp/px4_0.log /tmp/px4_1.log /tmp/px4_2.log /tmp/px4_3.log
ls /tmp/px4_*.log 2>/dev/null || echo LOGS_REMOVED
pgrep -f 'bin/p[x]4|mappo_formatio[n]' >/dev/null && echo PROCS_ALIVE || echo NO_PROCS
df -h / | tail -1
