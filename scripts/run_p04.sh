#!/bin/bash
# run_p04.sh - P0-4 双机闭环实验编排（在 WSL2 内运行）
#
# 前提：
#   1. Windows AirSim 已 Play（双机版 settings.json 已在 Documents/AirSim/）
#   2. Windows Phi-2 server 已跑（:8080，phi2-phased-v5-q5_k_m.gguf）
#   3. deploy_p04.sh 已部署并 colcon build
#
# 用法（WSL2 内）：
#   DRONES=1 bash run_p04.sh           # 单机冒烟
#   DRONES=2 bash run_p04.sh           # 双机
#   SCENARIO=disconnect bash run_p04.sh  # 断连注入（相位+心跳代理）
#   SCENARIO=replay bash run_p04.sh      # 旧相位重放注入
set -e
DRONES=${DRONES:-1}
SCENARIO=${SCENARIO:-none}

echo "============================================"
echo "  P0-4 双机闭环 | DRONES=$DRONES SCENARIO=$SCENARIO"
echo "============================================"

echo "[0] 清理旧进程..."
pkill -9 -f "bin/px4" 2>/dev/null || true
pkill -9 -f MicroXRCEAgent 2>/dev/null || true
pkill -9 -f nl_command 2>/dev/null || true
pkill -9 -f phase_fault_proxy 2>/dev/null || true
sleep 2
echo "    清理完成"

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "[1] 启动 DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds.log 2>&1 &
sleep 2

echo "[2] PX4 实例 1（/fmu）..."
cd ~/PX4-Autopilot
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  make px4_sitl_default none_iris > /tmp/px4_1.log 2>&1 &
sleep 15

if [ "$DRONES" = "2" ]; then
  echo "[3] PX4 实例 2（/px4_1/fmu）..."
  PX4_BUILD=~/PX4-Autopilot/build/px4_sitl_default
  cd $PX4_BUILD
  PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
    bin/px4 -i 1 > /tmp/px4_2.log 2>&1 &
  sleep 15
fi

echo "[4] 验证话题..."
FMU1=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^/fmu/" || true)
FMU2=$(timeout 8 ros2 topic list 2>/dev/null | grep -c "^/px4_1/fmu/" || true)
echo "    /fmu/ 话题: $FMU1 | /px4_1/fmu/ 话题: $FMU2"

if [ "$SCENARIO" = "disconnect" ]; then
  echo "[5a] 故障注入代理（断连窗口 30-45s）..."
  python3 /home/chuanyu/px4_ws/src/nl_command/nl_command/phase_fault_proxy.py \
    --profile /tmp/fi_disconnect.json --in /cloud/phase --out /cloud/phase_fi \
    > /tmp/proxy_phase.log 2>&1 &
  python3 /home/chuanyu/px4_ws/src/nl_command/nl_command/phase_fault_proxy.py \
    --profile /tmp/fi_disconnect.json --in /cloud/heartbeat --out /cloud/hb_fi \
    > /tmp/proxy_hb.log 2>&1 &
  sleep 2
  PHASE_TOPIC=/cloud/phase_fi
  HB_TOPIC=/cloud/hb_fi
else
  PHASE_TOPIC=/cloud/phase
  HB_TOPIC=/cloud/heartbeat
  if [ "$SCENARIO" = "replay" ]; then
    echo "[5a] 故障注入代理（旧相位重放）..."
    python3 /home/chuanyu/px4_ws/src/nl_command/nl_command/phase_fault_proxy.py \
      --profile /tmp/fi_replay.json --in /cloud/phase --out /cloud/phase_fi \
      > /tmp/proxy_phase.log 2>&1 &
    sleep 2
    PHASE_TOPIC=/cloud/phase_fi
  fi
fi

echo "[6] 启动云端相位生成器..."
ros2 run nl_command cloud_phase_generator > /tmp/cloud.log 2>&1 &
sleep 3

echo "[7] 启动端侧 P04 节点 ×$DRONES..."
NODE1_ARGS="--ros-args -p nl_topic:=/drone1/nl_input -p fmu_prefix:=/fmu -p target_system:=1 -p log_file:=/tmp/p04_drone1_episode.jsonl"
if [ -n "$PHASE_TOPIC" ]; then
  NODE1_ARGS="$NODE1_ARGS -p phase_topic:=$PHASE_TOPIC"
fi
if [ -n "$HB_TOPIC" ]; then
  NODE1_ARGS="$NODE1_ARGS -p heartbeat_topic:=$HB_TOPIC"
fi
ros2 run nl_command nl_command_node_p04 $NODE1_ARGS \
  > /tmp/p04_node1.log 2>&1 &
NODE_PID_1=$!
sleep 2

if [ "$DRONES" = "2" ]; then
  NODE2_ARGS="--ros-args -r __node:=p04_drone2 -p nl_topic:=/drone2/nl_input -p fmu_prefix:=/px4_1/fmu -p target_system:=2 -p log_file:=/tmp/p04_drone2_episode.jsonl"
  if [ -n "$PHASE_TOPIC" ]; then
    NODE2_ARGS="$NODE2_ARGS -p phase_topic:=$PHASE_TOPIC"
  fi
  if [ -n "$HB_TOPIC" ]; then
    NODE2_ARGS="$NODE2_ARGS -p heartbeat_topic:=$HB_TOPIC"
  fi
  ros2 run nl_command nl_command_node_p04 $NODE2_ARGS \
    > /tmp/p04_node2.log 2>&1 &
  NODE_PID_2=$!
  sleep 3
fi

echo ""
echo "============================================"
echo "  全链路已启动。手动操作步骤："
echo "  1. 发态势 → ros2 topic pub /cloud/situation ..."
echo "  2. 发指令 → python3 ~/send_nl.py <text> /drone1/nl_input"
echo "  3. 观察日志 → tail -f /tmp/p04_node1.log"
echo "============================================"
echo "节点 PID: Node1=$NODE_PID_1${NODE_PID_2:+ Node2=$NODE_PID_2}"
echo "按 Ctrl+C 停止"
echo ""

wait
