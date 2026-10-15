#!/bin/bash
# run_4drones.sh - 四机对抗仿真启动（红蓝各 2 台）
# 前提：Windows AirSim 已 Play（四机版 settings.json）+ Phi-2 server :8080
# 用法：在 WSL2 中执行 bash /mnt/d/2026-2027/Phi-2\ QLoRA/scripts/run_4drones.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "============================================"
echo "  四机对抗仿真 | 红×2 + 蓝×2"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'nl_command\|cloud_phase\|referee\|adv_phase' 2>/dev/null || true
sleep 2
echo "    清理完成"

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×4 实例 ----
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD

for i in 0 1 2 3; do
    TEAM=$( ["0","1"] =~ $i && echo "Red" || echo "Blue" )
    NUM=$((i % 2 + 1))
    echo "[2.$((i+1))] PX4 实例 $i（${TEAM}_${NUM}，/$( [ $i -eq 0 ] && echo 'fmu' || echo "px4_$((i-1))/fmu" )/）..."
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 10
done

# ---- 3. 验证话题 ----
echo "[3] 验证话题..."
TOTAL=0
for ns in /fmu /px4_1/fmu /px4_2/fmu /px4_3/fmu; do
    C=$(timeout 5 ros2 topic list 2>/dev/null | grep -c "^$ns/" || echo 0)
    echo "    $ns: $C 个话题"
    TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -lt 20 ]; then
    echo "    ⚠️ 话题数偏少（$TOTAL），可能部分 PX4 未连接 AirSim"
fi

# ---- 4. 对抗相位生成器 ----
echo "[4] 对抗相位生成器..."
ros2 run nl_command adversarial_phase_generator > /tmp/adv_phase.log 2>&1 &
sleep 3

# ---- 5. 裁判节点 ----
echo "[5] 裁判节点..."
ros2 run nl_command referee_node > /tmp/referee.log 2>&1 &
sleep 3

# ---- 6. P04 端侧节点 ×4 ----
echo "[6] 启动 4 个 P04 端侧节点..."

# Red_1（实例 0，/fmu/，target_system=1）
ros2 run nl_command nl_command_node_p04 --ros-args \
    -r __node:=p04_red1 \
    -p nl_topic:=/red1/nl_input \
    -p fmu_prefix:=/fmu \
    -p target_system:=1 \
    -p phase_topic:=/red/phase \
    -p heartbeat_topic:=/red/heartbeat \
    -p log_file:=/tmp/p04_red1_episode.jsonl \
    > /tmp/p04_red1.log 2>&1 &
sleep 2

# Red_2（实例 1，/px4_1/fmu/，target_system=2）
ros2 run nl_command nl_command_node_p04 --ros-args \
    -r __node:=p04_red2 \
    -p nl_topic:=/red2/nl_input \
    -p fmu_prefix:=/px4_1/fmu \
    -p target_system:=2 \
    -p phase_topic:=/red/phase \
    -p heartbeat_topic:=/red/heartbeat \
    -p log_file:=/tmp/p04_red2_episode.jsonl \
    > /tmp/p04_red2.log 2>&1 &
sleep 2

# Blue_1（实例 2，/px4_2/fmu/，target_system=3）
ros2 run nl_command nl_command_node_p04 --ros-args \
    -r __node:=p04_blue1 \
    -p nl_topic:=/blue1/nl_input \
    -p fmu_prefix:=/px4_2/fmu \
    -p target_system:=3 \
    -p phase_topic:=/blue/phase \
    -p heartbeat_topic:=/blue/heartbeat \
    -p log_file:=/tmp/p04_blue1_episode.jsonl \
    > /tmp/p04_blue1.log 2>&1 &
sleep 2

# Blue_2（实例 3，/px4_3/fmu/，target_system=4）
ros2 run nl_command nl_command_node_p04 --ros-args \
    -r __node:=p04_blue2 \
    -p nl_topic:=/blue2/nl_input \
    -p fmu_prefix:=/px4_3/fmu \
    -p target_system:=4 \
    -p phase_topic:=/blue/phase \
    -p heartbeat_topic:=/blue/heartbeat \
    -p log_file:=/tmp/p04_blue2_episode.jsonl \
    > /tmp/p04_blue2.log 2>&1 &
sleep 5

echo ""
echo "============================================"
echo "  四机对抗全链路已启动"
echo ""
echo "  操作步骤："
echo "  1. 发对抗态势："
echo "     python3 $SCRIPT_DIR/pub_situation.py 'blue intruders detected at (50,50)'"
echo "  2. 给红队发指令："
echo "     python3 $SCRIPT_DIR/pub_nl.py 'Red team, pursue the enemy' /red1/nl_input"
echo "  3. 给蓝队发指令："
echo "     python3 $SCRIPT_DIR/pub_nl.py 'Blue team, evade to safety' /blue1/nl_input"
echo "  4. 查看裁判："
echo "     tail -f /tmp/referee.log"
echo "============================================"
echo ""
echo "节点日志：/tmp/p04_{red1,red2,blue1,blue2}.log"
echo "Episode：/tmp/p04_{red1,red2,blue1,blue2}_episode.jsonl"
echo "按 Ctrl+C 停止"
echo ""

wait
