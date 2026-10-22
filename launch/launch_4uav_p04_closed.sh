#!/bin/bash
# launch_4uav_p04_closed.sh — P0-4 完整闭环：相位云 → SLM 指挥 → MAPPO → PX4
# 链路: /cloud/situation → phase_gen(规则) → /cloud/phase+heartbeat
#       → mission_commander(Phi-2+安全层) → /mission/primitive → mappo_formation → PX4
# 前提：Windows 侧 AirSim 已 Play + llama.cpp Phi-2 server :8080 已启动
# 用法：WSL 中 bash "/mnt/d/2026-2027/Phi-2 QLoRA/launch/launch_4uav_p04_closed.sh"
set -e
set -o pipefail

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

LOG_JSONL=/tmp/mappo_p04_$(date +%Y%m%d_%H%M%S).jsonl

echo "============================================"
echo "  P0-4 闭环 | 相位→SLM→MAPPO→PX4 | 高度30m"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'mappo_formatio[n]\|mission_commande[r]\|phase_ge[n] ' 2>/dev/null || true
sleep 2

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×4 ----
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD
for i in 0 1 2 3; do
    echo "[2.$((i+1))] PX4 实例 $i..."
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        tail -f /dev/null | bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 12
done
cd - > /dev/null

# ---- 3. 验证话题 ----
echo "[3] 验证话题..."
TOTAL=0
for NS in /fmu /px4_1/fmu /px4_2/fmu /px4_3/fmu; do
    C=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^$NS/" || echo 0)
    TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -lt 20 ]; then
    echo "    ⚠️ 话题总数偏少（$TOTAL），检查 AirSim 是否已 Play"
    exit 1
fi
echo "    ✅ 话题正常（$TOTAL）"

# ---- 4. 云端相位生成器（规则引擎）----
echo "[4] 云端相位生成器（rule）..."
ros2 run uav_adversarial phase_gen > /tmp/p04_phase_gen.log 2>&1 &
sleep 2

# ---- 5. 任务指挥节点（Phi-2 + 安全层）----
echo "[5] 任务指挥节点..."
ros2 run uav_adversarial mission_commander --ros-args \
    -p log_file:=/tmp/mission_commander.jsonl \
    > /tmp/p04_commander.log 2>&1 &
sleep 2

# ---- 6. MAPPO 编队执行节点 ----
echo "[6] MAPPO 执行节点（require_phase_link=true，日志 $LOG_JSONL）..."
ros2 run uav_adversarial mappo_formation --ros-args \
    -p actor_npz:=/home/chuanyu/px4_ws/models/mappo_2d_seed555_actor.npz \
    -p 'namespaces:=["/fmu","/px4_1/fmu","/px4_2/fmu","/px4_3/fmu"]' \
    -p 'target_systems:=[1,2,3,4]' \
    -p 'spawn_east:=[0.0,0.0,0.0,60.0]' \
    -p 'spawn_north:=[0.0,5.0,-5.0,60.0]' \
    -p 'start_east:=[100.0,-100.0,-100.0,100.0]' \
    -p 'start_north:=[100.0,100.0,-100.0,-100.0]' \
    -p altitude:=30.0 \
    -p require_phase_link:=true \
    -p episode_ticks:=1500 \
    -p log_file:=$LOG_JSONL \
    2>&1 | tee /tmp/mappo_p04_stdout.log

echo
echo "Episode 日志: $LOG_JSONL"
echo "指挥节点日志: /tmp/mission_commander.jsonl"
