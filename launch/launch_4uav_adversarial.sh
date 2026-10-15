#!/bin/bash
# launch_4uav_adversarial.sh - 四机对抗仿真启动（红蓝各 2 台）
# 前提：Windows AirSim 已 Play（四机版 settings.json）+ Phi-2 server :8080
# 用法：在 WSL2 中执行 bash "/mnt/d/2026-2027/Phi-2 QLoRA/launch/launch_4uav_adversarial.sh"
set -e

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "============================================"
echo "  四机对抗仿真 | 红×2 + 蓝×2 | v2.0 (uav_adversarial)"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'edge_node\|phase_gen\|referee\|fault_proxy\|heartbeat' 2>/dev/null || true
sleep 2
echo "    清理完成"

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×4 实例 ----
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD

# 实例 0 = Red_1 (/fmu/)，实例 1 = Red_2 (/px4_1/fmu/)
# 实例 2 = Blue_1 (/px4_2/fmu/)，实例 3 = Blue_2 (/px4_3/fmu/)
NAMESPACES=("/fmu" "/px4_1/fmu" "/px4_2/fmu" "/px4_3/fmu")
TEAM_NAMES=("Red_1" "Red_2" "Blue_1" "Blue_2")

for i in 0 1 2 3; do
    echo "[2.$((i+1))] PX4 实例 $i（${TEAM_NAMES[$i]}，${NAMESPACES[$i]}/）..."
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 12
done

# ---- 3. 验证话题 ----
echo "[3] 验证话题..."
TOTAL=0
for i in 0 1 2 3; do
    NS=${NAMESPACES[$i]}
    C=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^$NS/" || echo 0)
    echo "    ${TEAM_NAMES[$i]} ($NS): $C 个话题"
    TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -lt 20 ]; then
    echo "    ⚠️ 话题总数偏少（$TOTAL），部分 PX4 可能未连接 AirSim"
    echo "    检查：grep -i 'error\|fail' /tmp/px4_*.log"
else
    echo "    ✅ 四机话题正常（共 $TOTAL 个）"
fi

# ---- 4. 对抗相位生成器 ----
echo "[4] 对抗相位生成器..."
ros2 run uav_adversarial phase_gen_adv > /tmp/adv_phase.log 2>&1 &
sleep 3
if ! pgrep -f phase_gen_adv > /dev/null; then
    echo "    ❌ 相位生成器启动失败！检查 /tmp/adv_phase.log"
    cat /tmp/adv_phase.log | tail -5
    exit 1
fi
echo "    ✅ PID=$(pgrep -f phase_gen_adv | head -1)"

# ---- 5. 裁判节点 ----
echo "[5] 裁判节点..."
ros2 run uav_adversarial referee > /tmp/referee.log 2>&1 &
sleep 3
if ! pgrep -f "uav_adversarial.*referee" > /dev/null; then
    echo "    ❌ 裁判启动失败！检查 /tmp/referee.log"
    cat /tmp/referee.log | tail -5
    exit 1
fi
echo "    ✅ PID=$(pgrep -f 'uav_adversarial.*referee' | head -1)"

# ---- 6. 端侧节点 ×4 ----
echo "[6] 启动 4 个端侧节点（edge_node）..."

start_node() {
    local NODE_NAME=$1 NL_TOPIC=$2 FMU_PREFIX=$3 TARGET_SYS=$4 PHASE_TOPIC=$5 HB_TOPIC=$6 LOG_FILE=$7 LOG_OUT=$8
    ros2 run uav_adversarial edge_node --ros-args \
        -r __node:=$NODE_NAME \
        -p nl_topic:=$NL_TOPIC \
        -p fmu_prefix:=$FMU_PREFIX \
        -p target_system:=$TARGET_SYS \
        -p phase_topic:=$PHASE_TOPIC \
        -p heartbeat_topic:=$HB_TOPIC \
        -p log_file:=$LOG_FILE \
        > $LOG_OUT 2>&1 &
    sleep 2
    if pgrep -f "__name:=$NODE_NAME\|__node:=$NODE_NAME" > /dev/null 2>&1; then
        echo "    ✅ $NODE_NAME (PID=$(pgrep -f "__node:=$NODE_NAME" | head -1))"
    else
        echo "    ⚠️ $NODE_NAME 可能未启动，检查 $LOG_OUT"
        tail -3 $LOG_OUT
    fi
}

#              节点名      NL话题         FMU前缀         SYS_ID  相位话题         心跳话题            episode日志               stdout日志
start_node    p04_red1    /red1/nl_input   /fmu            1      /red/phase      /red/heartbeat      /tmp/p04_red1_episode.jsonl   /tmp/p04_red1.log
start_node    p04_red2    /red2/nl_input   /px4_1/fmu      2      /red/phase      /red/heartbeat      /tmp/p04_red2_episode.jsonl   /tmp/p04_red2.log
start_node    p04_blue1   /blue1/nl_input  /px4_2/fmu      3      /blue/phase     /blue/heartbeat     /tmp/p04_blue1_episode.jsonl  /tmp/p04_blue1.log
start_node    p04_blue2   /blue2/nl_input  /px4_3/fmu      4      /blue/phase     /blue/heartbeat     /tmp/p04_blue2_episode.jsonl  /tmp/p04_blue2.log

sleep 5

# ---- 7. 最终状态汇总 ----
echo ""
echo "============================================"
echo "  四机对抗全链路状态"
echo "============================================"
NODE_COUNT=$(pgrep -c -f "edge_node\|phase_gen\|referee" || echo 0)
PX4_COUNT=$(pgrep -c -f "bin/px4" || echo 0)
echo "  PX4 实例: $PX4_COUNT/4"
echo "  ROS 节点: $NODE_COUNT/6（相位+裁判+4×端侧）"
echo ""
echo "  操作步骤："
echo "  1. 发对抗态势：ros2 topic pub /battle/situation std_msgs/String 'data: \"blue intruders detected\"' --once"
echo "  2. 发红队指令：ros2 topic pub /red1/nl_input std_msgs/String 'data: \"Red team pursue the enemy\"' --once"
echo "  3. 发蓝队指令：ros2 topic pub /blue1/nl_input std_msgs/String 'data: \"Blue team evade\"' --once"
echo "  4. 查看裁判：tail -f /tmp/referee.log"
echo "  5. 查看红队：tail -f /tmp/p04_red1.log"
echo "============================================"
echo ""
echo "按 Ctrl+C 停止全部"
echo ""

wait
