#!/bin/bash
# launch_4uav_formation.sh — 四机 2D-MAPPO 编队桥接仿真（Step 1，不接 SLM）
# 前提：Windows AirSim 已 Play（当前 6 机 settings.json 即可，用前 4 架）
# 用法：在 WSL2 中执行 bash "/mnt/d/2026-2027/Phi-2 QLoRA/launch/launch_4uav_formation.sh"
set -e

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

LOG_JSONL=/tmp/mappo_formation_$(date +%Y%m%d_%H%M%S).jsonl

echo "============================================"
echo "  四机 2D-MAPPO 编队桥接 | 高度 30 m"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'mappo_formation' 2>/dev/null || true
sleep 2

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×4 实例（0=Red_1 /fmu, 1=Red_2, 2=Red_3, 3=Blue_1）----
# stdin 用 tail -f /dev/null 喂住：非交互 stdin 遇 EOF 会让 pxh 控制台
# 死循环刷提示符，几分钟写满数 GB 日志。
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD
for i in 0 1 2 3; do
    echo "[2.$((i+1))] PX4 实例 $i..."
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        tail -f /dev/null | bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 12
done

# ---- 3. 验证话题 ----
echo "[3] 验证话题..."
TOTAL=0
for NS in /fmu /px4_1/fmu /px4_2/fmu /px4_3/fmu; do
    C=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^$NS/" || echo 0)
    echo "    $NS: $C 个话题"
    TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -lt 20 ]; then
    echo "    ⚠️ 话题总数偏少（$TOTAL），检查 AirSim 是否已 Play、/tmp/px4_*.log"
    exit 1
fi

# ---- 4. MAPPO 编队节点 ----
echo "[4] MAPPO 编队节点（日志: $LOG_JSONL）..."
ros2 run uav_adversarial mappo_formation --ros-args \
    -p actor_npz:=/home/chuanyu/px4_ws/models/mappo_2d_seed555_actor.npz \
    -p 'namespaces:=["/fmu","/px4_1/fmu","/px4_2/fmu","/px4_3/fmu"]' \
    -p 'target_systems:=[1,2,3,4]' \
    -p 'spawn_east:=[0.0,0.0,0.0,60.0]' \
    -p 'spawn_north:=[0.0,5.0,-5.0,60.0]' \
    -p 'start_east:=[100.0,-100.0,-100.0,100.0]' \
    -p 'start_north:=[100.0,100.0,-100.0,-100.0]' \
    -p altitude:=30.0 \
    -p log_file:=$LOG_JSONL \
    2>&1 | tee /tmp/mappo_formation_stdout.log

echo
echo "Episode 日志: $LOG_JSONL"
echo "快速统计: grep -c '\"event\": \"step\"' $LOG_JSONL"
