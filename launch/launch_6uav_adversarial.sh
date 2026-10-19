#!/bin/bash
# launch_6uav_adversarial.sh - 3v3 六机对抗仿真启动
# 前提：Windows AirSim 已 Play（六机版 settings.json）+ Phi-2 server :8080
set -e

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "============================================"
echo "  3v3 六机对抗仿真 | 红×3 + 蓝×3"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理..."
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'edge_node\|phase_gen\|referee\|fault_proxy\|heartbeat' 2>/dev/null || true
sleep 2

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×6 实例 ----
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD

NAMESPACES=("/fmu" "/px4_1/fmu" "/px4_2/fmu" "/px4_3/fmu" "/px4_4/fmu" "/px4_5/fmu")
TEAMS=("Red_1" "Red_2" "Red_3" "Blue_1" "Blue_2" "Blue_3")

for i in 0 1 2 3 4 5; do
    echo "[2.$((i+1))] PX4 实例 $i（${TEAMS[$i]}，${NAMESPACES[$i]}/）..."
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 12
done

# ---- 3. 验证 ----
echo "[3] 验证话题..."
TOTAL=0
for i in 0 1 2 3 4 5; do
    C=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^${NAMESPACES[$i]}/" || echo 0)
    echo "    ${TEAMS[$i]}: $C 个话题"
    TOTAL=$((TOTAL + C))
done
echo "    总话题数: $TOTAL（六机正常约 144）"

# ---- 4. 3v3 相位生成器 ----
echo "[4] 3v3 相位生成器..."
ros2 run uav_adversarial phase_gen_3v3 > /tmp/adv_phase.log 2>&1 &
sleep 3
pgrep -f phase_gen_3v3 > /dev/null && echo "    ✅ PID=$(pgrep -f phase_gen_3v3 | head -1)" || echo "    ❌ 启动失败"

# ---- 5. 3v3 裁判 ----
echo "[5] 3v3 裁判..."
ros2 run uav_adversarial referee_3v3 > /tmp/referee.log 2>&1 &
sleep 3
pgrep -f referee_3v3 > /dev/null && echo "    ✅ PID=$(pgrep -f referee_3v3 | head -1)" || echo "    ❌ 启动失败"

# ---- 6. 端侧节点 ×6 ----
echo "[6] 启动 6 个端侧节点..."

start_node() {
    local NAME=$1 NL=$2 FMU=$3 SYS=$4 PH=$5 HB=$6 LOG=$7 OUT=$8
    ros2 run uav_adversarial edge_node --ros-args \
        -r __node:=$NAME \
        -p nl_topic:=$NL -p fmu_prefix:=$FMU -p target_system:=$SYS \
        -p phase_topic:=$PH -p heartbeat_topic:=$HB \
        -p log_file:=$LOG > $OUT 2>&1 &
    sleep 1.5
}

#               节点名       NL话题             FMU              SYS  相位           心跳              episode                    stdout
start_node    p04_red1    /red1/nl_input    /fmu              1   /red/phase    /red/heartbeat    /tmp/p04_red1.jsonl       /tmp/p04_red1.log
start_node    p04_red2    /red2/nl_input    /px4_1/fmu        2   /red/phase    /red/heartbeat    /tmp/p04_red2.jsonl       /tmp/p04_red2.log
start_node    p04_red3    /red3/nl_input    /px4_2/fmu        3   /red/phase    /red/heartbeat    /tmp/p04_red3.jsonl       /tmp/p04_red3.log
start_node    p04_blue1   /blue1/nl_input   /px4_3/fmu        4   /blue/phase   /blue/heartbeat   /tmp/p04_blue1.jsonl      /tmp/p04_blue1.log
start_node    p04_blue2   /blue2/nl_input   /px4_4/fmu        5   /blue/phase   /blue/heartbeat   /tmp/p04_blue2.jsonl      /tmp/p04_blue2.log
start_node    p04_blue3   /blue3/nl_input   /px4_5/fmu        6   /blue/phase   /blue/heartbeat   /tmp/p04_blue3.jsonl      /tmp/p04_blue3.log

sleep 5
NODE_COUNT=$(pgrep -c -f "edge_node\|phase_gen\|referee" 2>/dev/null || echo 0)
echo ""
echo "============================================"
echo "  3v3 六机对抗全链路已启动"
echo "  PX4: $(pgrep -c -f 'bin/px4' 2>/dev/null || echo 0)/6"
echo "  ROS 节点: $NODE_COUNT/8（相位+裁判+6×端侧）"
echo "============================================"
echo ""
echo "  操作："
echo "  1. 触发对抗：ros2 topic pub /battle/situation std_msgs/String \"data: start\" --once"
echo "  2. 红队追击：ros2 topic pub /red1/nl_input std_msgs/String \"data: UAV 1 pursue at (60,60,10)\" --once"
echo "  3. 蓝队规避：ros2 topic pub /blue1/nl_input std_msgs/String \"data: UAV 4 evade to (85,85,10)\" --once"
echo "  4. 查看裁判：tail -f /tmp/referee.log"
echo "  5. 查看评分：ros2 topic echo /battle/score"
echo "============================================"
echo ""

wait
