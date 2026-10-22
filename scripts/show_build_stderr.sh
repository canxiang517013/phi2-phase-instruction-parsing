#!/bin/bash
# show_build_stderr.sh — 查看 uav_adversarial colcon build 的 stderr 明细
source /opt/ros/humble/setup.bash
cd ~/px4_ws
colcon build --packages-select uav_adversarial --event-handlers console_direct+ 2>&1 \
  | grep -iE "error|warning|deprecated" | head -10
echo "--- done ---"
