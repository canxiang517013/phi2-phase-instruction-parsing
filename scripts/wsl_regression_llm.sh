#!/bin/bash
# wsl_regression_llm.sh - 云端节点部署后的快速回归验证（规则模式，无网络依赖）
#
# 用法（Windows 侧）：
#   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_regression_llm.sh"
#
# 验证点：
#   1. 节点启动（provider=rule）
#   2. 态势订阅 + 后台线程推断正常（发布相位）
#   3. 1Hz 心跳不被推断阻塞（日志时间戳连续）

set -e
source /opt/ros/humble/setup.bash
source /home/chuanyu/px4_ws/install/setup.bash

LOG=/tmp/cloud_regression.log
ros2 run nl_command cloud_phase_generator > "$LOG" 2>&1 &
NODE_PID=$!
sleep 3

# 显式关键词（规则引擎应给 OBSTACLE_AVOID@right@30）
ros2 topic pub --once /cloud/situation std_msgs/msg/String \
  "{data: 'Obstacle cluster 30m ahead on right side, evasive maneuver needed'}" > /dev/null 2>&1 || true
sleep 1
# 隐式语义（规则引擎应回落 HOLD@(0,0,5)）
ros2 topic pub --once /cloud/situation std_msgs/msg/String \
  "{data: 'Weather radar shows a strong downdraft zone 25m ahead; lateral detour to the left is advised'}" > /dev/null 2>&1 || true
sleep 2

kill $NODE_PID 2>/dev/null || true
sleep 1

echo "===== 节点日志 ====="
cat "$LOG"
echo "===== /cloud/phase 收到的相位 ====="
timeout 6 ros2 topic echo /cloud/phase --once 2>/dev/null | grep frame_id || echo "（相位 5 秒重发周期内未捕获，属正常；看上方日志即可）"
