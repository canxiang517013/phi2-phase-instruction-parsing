#!/bin/bash
# archive_p04_logs.sh — 归档 P0-4 闭环的 episode 与指挥节点日志到仓库
set -e
DEST="/mnt/d/2026-2027/Phi-2 QLoRA/results/sim_bridge_2d"
python3 "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/analyze_p04_episode.py" \
    /tmp/mappo_p04_20261022_140334.jsonl | head -34
cp /tmp/mappo_p04_20261022_140334.jsonl "$DEST/"
cp /tmp/mappo_p04_20261022_135813.jsonl "$DEST/"
cp /tmp/mission_commander.jsonl "$DEST/p04_mission_commander.jsonl"
echo ARCHIVED
ls "$DEST" | tail -6
