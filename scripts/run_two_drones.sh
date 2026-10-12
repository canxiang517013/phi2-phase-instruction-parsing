#!/bin/bash
# run_two_drones.sh - 两机集群 Demo（八月任务 B 验收）
#
# 验收标准：两机同时 SITL 运行，状态互不干扰
#
# 前提：
#   1. Windows AirSim 已 Play，settings.json 已替换为两机版
#      （把 settings_two_drones.json 复制到 C:\Users\CanXiang\Documents\AirSim\settings.json）
#   2. Windows Phi-2 server 在跑（:8080）
#
# 用法：bash ~/run_two_drones.sh

echo "============================================"
echo "  两机集群 Demo（任务 B 验收）"
echo "============================================"

# ---- 0. 清理旧进程 ----
echo "[0] 清理旧进程..."
pkill -f "bin/px4" 2>/dev/null || true
pkill -f MicroXRCEAgent 2>/dev/null || true
pkill -f nl_command 2>/dev/null || true
sleep 2

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

# ---- 1. 启动 DDS Agent ----
echo "[1] 启动 DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. 启动 PX4 实例 1（连 AirSim Drone_1, TCP 4560）----
echo "[2] 启动 PX4 实例 1 (TCP 4560, instance 0)..."
cd ~/PX4-Autopilot
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  make px4_sitl_default none_iris > /tmp/px4_1.log 2>&1 &
PX4_PID_1=$!
sleep 15

echo "[3] 启动 PX4 实例 2 (TCP 4561, instance 1)..."
# 第二个实例：直接用 PX4 二进制 + -i 1（不能再用 make，否则报 "already running"）
# instance 1 会自动用 TCP 4561 + MAVLink 端口偏移
cd ~/PX4-Autopilot/build/px4_sitl_default
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  bin/px4 -i 1 ROMFS/px4fmu/init.d-posix/rcS > /tmp/px4_2.log 2>&1 &
PX4_PID_2=$!
sleep 15

# ---- 4. 验证连接 ----
echo "[4] 验证 PX4 连接..."
grep -q "Simulator connected" /tmp/px4_1.log 2>/dev/null \
  && echo "    ✅ Drone 1 连上 AirSim" \
  || echo "    ⚠️ Drone 1 待确认（tail -20 /tmp/px4_1.log）"
grep -q "Simulator connected" /tmp/px4_2.log 2>/dev/null \
  && echo "    ✅ Drone 2 连上 AirSim" \
  || echo "    ⚠️ Drone 2 待确认（tail -20 /tmp/px4_2.log）"

FMU=$(timeout 8 ros2 topic list 2>/dev/null | grep -c fmu)
echo "    FMU 话题数: $FMU"

# ---- 5. 启动 nl_command_node（单机版，先验证两 PX4 独立运行）----
echo ""
echo "[5] 启动 nl_command_node..."
ros2 run nl_command nl_command_node > /tmp/node_1.log 2>&1 &
NODE_PID_1=$!
sleep 4

echo ""
echo "============================================"
echo "  发送指令: UAV 1 fly to 10 0 5"
echo "  （观察两架机是否独立响应——只有 Drone 1 应动）"
echo "============================================"
timeout 12 python3 ~/send_nl.py "UAV 1 fly to 10 0 5" 2>&1 | head -3

echo ""
echo "节点持续运行中..."
echo "PX4 日志: /tmp/px4_1.log /tmp/px4_2.log"
echo "节点日志: /tmp/node_1.log"
echo ""
echo "观察 AirSim：Drone 1 起飞飞向 (10,0,5)，Drone 2 应保持不动"
echo "按 Ctrl+C 停止全部"
echo ""

wait

# 清理
kill $NODE_PID_1 $PX4_PID_1 $PX4_PID_2 2>/dev/null || true
