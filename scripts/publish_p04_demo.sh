#!/bin/bash
# publish_p04_demo.sh — P0-4 闭环演示的指令时间线
# 在 launch_4uav_p04_closed.sh 运行期间另开 WSL 终端执行本脚本。
# 注意：HOLD 态势文本不能含 obstacle 类关键词（threat/danger 等），
#       否则规则引擎会判成 OBSTACLE_AVOID；HOLD 是无关键词的默认回落。
#       目标选 (-100,100)：实测 Phi-2 对该坐标转写稳定；(-150,150) 类
#       会被丢位转写成 -15（安全层数值溯源拦截，已留档为证据）。
# 时间线（相对脚本启动；在执行节点进入 FORMATION 后立即启动本脚本）：
#   +2s   态势 → ASSEMBLE@(0,0)            （链路 FRESH，编队集结）
#   +18s  NL  → SLM → LEADER_TARGET(-100,100)（改派目标，leader 起步）
#   +26s  态势 → HOLD                       （飞行中冻结 leader）
#   +32s  态势 → RECON@(-100,100)          （云端解除 HOLD）
#   +35s  NL  → SLM → LEADER_TARGET(-100,100)（操作员细化目标，恢复运动）
set -e
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

say() { echo "[$(date +%H:%M:%S)] $1"; }

say "态势: 集结"
ros2 topic pub -1 /cloud/situation std_msgs/msg/String \
    "data: Assemble formation near (0,0)." > /dev/null

sleep 16
say "自然语言指令: 前往 (-100,100) 侦察（高度30，供数值溯源）"
ros2 topic pub -1 /nl_input std_msgs/msg/String \
    "data: 编队前往坐标(-100,100)执行侦察，高度30" > /dev/null

sleep 8
say "态势: HOLD（飞行中冻结）"
ros2 topic pub -1 /cloud/situation std_msgs/msg/String \
    "data: All units hold position and wait." > /dev/null

sleep 6
say "态势: 解除 HOLD，转入 RECON"
ros2 topic pub -1 /cloud/situation std_msgs/msg/String \
    "data: Proceed to recon point (-100,100)." > /dev/null

sleep 3
say "自然语言指令: 继续任务"
ros2 topic pub -1 /nl_input std_msgs/msg/String \
    "data: 编队继续前往坐标(-100,100)侦察，高度30" > /dev/null

say "演示时间线结束"
