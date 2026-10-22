#!/bin/bash
# run_primitive_delivery_test.sh — 先起指挥节点，再跑送达探针
set -e
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

ros2 run uav_adversarial mission_commander --ros-args \
    -p log_file:=/tmp/mc_delivery_test.jsonl > /tmp/mc_delivery_test.log 2>&1 &
MC_PID=$!
sleep 3
python3 "/mnt/d/2026-2027/Phi-2 QLoRA/src/evaluation/test_primitive_delivery.py"
RC=$?
kill $MC_PID 2>/dev/null || true
echo "--- 指挥节点发出的原语数 ---"
grep -c '"event": "primitive"' /tmp/mc_delivery_test.jsonl || true
exit $RC
