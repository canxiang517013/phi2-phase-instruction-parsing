#!/bin/bash
# launch_4uav_formation_3d.sh — 四机 3D 四面体编队（20 维观测策略上仿真）
# 前置：AirSim 已 Play；建议 settings.json 为 4 机加
#       "MPC_Z_VEL_MAX": 8.0（训练垂直速度上限 8 m/s，默认 3 m/s 会明显滞后）
# 用法：WSL 中 bash "/mnt/d/2026-2027/Phi-2 QLoRA/launch/launch_4uav_formation_3d.sh"
set -e
set -o pipefail

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

LOG_JSONL=/tmp/mappo_3d_$(date +%Y%m%d_%H%M%S).jsonl

echo "============================================"
echo "  四机 3D 四面体编队 | 20D obs -> 3D action"
echo "============================================"

# ---- 0. 清理 ----
pkill -9 -f 'bin/px4' 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f 'mappo_formatio[n]' 2>/dev/null || true
sleep 2

# ---- 1. DDS Agent ----
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 ×4 ----
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD
for i in 0 1 2 3; do
    PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
        tail -f /dev/null | bin/px4 -i $i > /tmp/px4_$i.log 2>&1 &
    sleep 12
done

# ---- 3. 话题检查 ----
TOTAL=0
for NS in /fmu /px4_1/fmu /px4_2/fmu /px4_3/fmu; do
    C=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^$NS/" || echo 0)
    TOTAL=$((TOTAL + C))
done
if [ "$TOTAL" -lt 20 ]; then
    echo "⚠️ 话题偏少（$TOTAL），检查 AirSim 是否已 Play"
    exit 1
fi

# ---- 4. 3D 策略节点 ----
# altitude=10 对应训练初始位置 z=10m；leader 起点在 (0,0,40)，
# 槽位 z = 40 ± 34.6（5.4~74.6m，环境包络 2~100m 内）
echo "3D 编队节点启动（日志 $LOG_JSONL）..."
ros2 run uav_adversarial mappo_formation --ros-args \
    -p actor_npz:=/home/chuanyu/px4_ws/models/mappo_3d_seed21_actor_best.npz \
    -p policy_dim:=3 \
    -p 'namespaces:=["/fmu","/px4_1/fmu","/px4_2/fmu","/px4_3/fmu"]' \
    -p 'target_systems:=[1,2,3,4]' \
    -p 'spawn_east:=[0.0,0.0,0.0,60.0]' \
    -p 'spawn_north:=[0.0,5.0,-5.0,60.0]' \
    -p 'start_east:=[100.0,-100.0,-100.0,100.0]' \
    -p 'start_north:=[100.0,100.0,-100.0,-100.0]' \
    -p altitude:=10.0 \
    -p episode_ticks:=900 \
    -p leader_force_move_step:=850 \
    -p log_file:=$LOG_JSONL \
    2>&1 | tee /tmp/mappo_3d_stdout.log

echo
echo "Episode 日志: $LOG_JSONL"
