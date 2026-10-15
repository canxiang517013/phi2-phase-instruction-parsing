#!/bin/bash
# p04_step3.sh - 发态势 + NL 指令（在 WSL2 中运行）
# 用法：bash /mnt/d/2026-2027/Phi-2\ QLoRA/scripts/p04_step3.sh
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

SCRIPT_DIR="/mnt/d/2026-2027/Phi-2 QLoRA/scripts"

echo "[1/2] 发态势..."
python3 "$SCRIPT_DIR/pub_situation.py" "enemy detected, assemble immediately at (15, 20)"
sleep 2

echo "[2/2] 发 NL 指令..."
python3 "$SCRIPT_DIR/pub_nl.py" "UAV 1, assemble at (15, 20, 5)" /drone1/nl_input
