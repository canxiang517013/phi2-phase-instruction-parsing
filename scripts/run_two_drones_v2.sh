#!/bin/bash
# run_two_drones_v2.sh - 两机独立控制 Demo（命名空间隔离版）
#
# 核心改进：PX4 实例 2 的 DDS 话题用 /drone2/fmu/... 命名空间
# 这样 nl_command_node 可以分别控制两架无人机
#
# 前提：
#   1. Windows AirSim 已 Play（两机版 settings.json）
#   2. Windows Phi-2 server 在跑（:8080）
#
# 用法：bash ~/run_two_drones_v2.sh

echo "============================================"
echo "  两机独立控制 Demo（命名空间隔离版）"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f "bin/px4" 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f nl_command 2>/dev/null || true
sleep 2
# 二次确认清理干净（避免 Agent 重复实例抢端口）
if pgrep -f MicroXRCEAgent > /dev/null 2>&1; then
  pkill -9 -f MicroXRCEAgent 2>/dev/null || true
  sleep 1
fi
echo "    清理完成: PX4=$(pgrep -c -f bin/px4 2>/dev/null || echo 0) Agent=$(pgrep -c -f MicroXRCEAgent 2>/dev/null || echo 0)"

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

# ---- 1. DDS Agent ----
echo "[1] 启动 DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

# ---- 2. PX4 实例 1（默认命名空间 /fmu）----
echo "[2] PX4 实例 1 (instance 0, 话题 /fmu/...)"
cd ~/PX4-Autopilot
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  make px4_sitl_default none_iris > /tmp/px4_1.log 2>&1 &
PX4_PID_1=$!
sleep 15

# ---- 3. PX4 实例 2（自动命名空间 /px4_1/fmu）----
echo "[3] PX4 实例 2 (instance 1, 自动命名空间 /px4_1/fmu/...)"
# 关键发现：PX4 -i 1 自动把话题命名为 /px4_1/fmu/...（官方多实例隔离机制）
# 不需要手动重启 DDS client（手动重启会丢失 in 方向 reader，导致 PX4 收不到命令）
PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
cd $PX4_BUILD
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  bin/px4 -i 1 > /tmp/px4_2.log 2>&1 &
PX4_PID_2=$!
sleep 15

# ---- 4. 验证命名空间隔离 ----
echo "[4] 验证话题隔离..."
FMU_DEFAULT=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^/fmu/")
FMU_DRONE2=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^/px4_1/fmu/")
echo "    /fmu/ 话题数: $FMU_DEFAULT (实例1)"
echo "    /px4_1/fmu/ 话题数: $FMU_DRONE2 (实例2)"

if [ "$FMU_DEFAULT" -gt 0 ] && [ "$FMU_DRONE2" -gt 0 ]; then
    echo "    ✅ 命名空间隔离成功！"
else
    echo "    ⚠️ 隔离未生效，检查 /tmp/px4_2.log"
    echo "    （可能需要手动在 pxh 里执行 uxrce_dds_client stop + start -n drone2）"
fi

# ---- 5. 启动两个 nl_command_node ----
echo ""
echo "[5] 启动两个 nl_command_node..."
# 节点 1：控制实例 1（默认 /fmu）
# 注意：-p 参数必须跟在 --ros-args 后面，否则被解释为 remap（不生效）
ros2 run nl_command nl_command_node --ros-args \
  -p nl_topic:=/drone1/nl_input \
  > /tmp/node_1.log 2>&1 &
NODE_PID_1=$!
sleep 2

# 节点 2：控制实例 2（自动命名空间 /px4_1/fmu）
# 注意：PX4 实例 1（-i 1）的 MAV_SYS_ID 自动 +1 变成 2，必须传 target_system:=2
ros2 run nl_command nl_command_node --ros-args \
  -r __node:=nl_command_drone2 \
  -p nl_topic:=/drone2/nl_input \
  -p fmu_prefix:=/px4_1/fmu \
  -p target_system:=2 \
  > /tmp/node_2.log 2>&1 &
NODE_PID_2=$!
sleep 3

echo "    Node 1 (控制 Drone1): PID $NODE_PID_1"
echo "    Node 2 (控制 Drone2): PID $NODE_PID_2"

# ---- 6. 分别发指令 ----
echo ""
echo "============================================"
echo "  Drone 1 → fly to (10, 0, 3)"
echo "  Drone 2 → fly to (0, 10, 3)"
echo "============================================"
echo ""
echo "给 Drone 1 发指令..."
timeout 8 python3 ~/send_nl.py "UAV 1 fly to 10 0 3" /drone1/nl_input 2>&1 | head -2
echo ""
sleep 3
echo "给 Drone 2 发指令..."
timeout 8 python3 ~/send_nl.py "UAV 2 fly to 0 10 3" /drone2/nl_input 2>&1 | head -2

echo ""
echo "============================================"
echo "  观察 AirSim：两架无人机各自飞向不同目标！"
echo "============================================"
echo ""
echo "Node1 日志: /tmp/node_1.log"
echo "Node2 日志: /tmp/node_2.log"
echo "PX4日志: /tmp/px4_1.log /tmp/px4_2.log"
echo "按 Ctrl+C 停止全部"
echo ""

wait

kill $NODE_PID_1 $NODE_PID_2 $PX4_PID_1 $PX4_PID_2 2>/dev/null || true
