#!/bin/bash
# pub_all_6uav.sh - 六机同时发指令（真实并发，无串行延迟）
# 用法：bash /mnt/d/2026-2027/Phi-2\ QLoRA/scripts/pub_all_6uav.sh
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "[1] 触发对抗态势..."
ros2 topic pub /battle/situation std_msgs/String \
    "data: start battle, blue intruders at (60,60), red team pursue" --once &

echo "[2] 六机同时发指令（并发）..."
# 红队三机（后台并发）
ros2 topic pub /red1/nl_input std_msgs/String \
    "data: UAV 1, pursue at (60, 60, 10)" --once &
ros2 topic pub /red2/nl_input std_msgs/String \
    "data: UAV 2, pursue at (65, 60, 10)" --once &
ros2 topic pub /red3/nl_input std_msgs/String \
    "data: UAV 3, pursue at (55, 60, 10)" --once &

# 蓝队三机（后台并发，与红队同时）
ros2 topic pub /blue1/nl_input std_msgs/String \
    "data: UAV 4, evade to (85, 85, 10)" --once &
ros2 topic pub /blue2/nl_input std_msgs/String \
    "data: UAV 5, evade to (88, 82, 10)" --once &
ros2 topic pub /blue3/nl_input std_msgs/String \
    "data: UAV 6, evade to (82, 88, 10)" --once &

# 等待所有发布完成
wait
echo ""
echo "[OK] 六机指令已同时发出"
echo "观察："
echo "  tail -f /tmp/referee.log"
echo "  ros2 topic echo /battle/score"
