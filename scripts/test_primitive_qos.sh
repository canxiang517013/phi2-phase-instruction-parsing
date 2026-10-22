#!/bin/bash
# test_primitive_qos.sh — /mission/primitive 送达测试
# 次序: 先起 volatile 订阅者(模拟 mappo) → 起指挥节点 → 发一条 HOLD 相位 → 看是否收到
set -x
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

timeout 14 ros2 topic echo /mission/primitive std_msgs/msg/String --once > /tmp/prim_echo.txt 2>&1 &
sleep 2
ros2 run uav_adversarial mission_commander --ros-args -p log_file:=/tmp/mc_qostest.jsonl > /tmp/mc_qostest.log 2>&1 &
sleep 3
ros2 topic pub -1 /cloud/phase std_msgs/msg/Header "{frame_id: 'HOLD@(0,0,5)'}" >/dev/null 2>&1
sleep 5
echo "=== echo 结果 ==="
head -5 /tmp/prim_echo.txt
echo "=== commander 是否发出 ==="
grep -c '"event": "primitive"' /tmp/mc_qostest.jsonl 2>/dev/null || echo 0
pkill -f "mission_commande[r]" 2>/dev/null
true
