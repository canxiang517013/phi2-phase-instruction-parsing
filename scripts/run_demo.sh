#!/bin/bash
# run_demo.sh - 端侧指令解析 Demo 一键启动脚本
# 用法：在 WSL2 终端里运行 bash ~/run_demo.sh
# 前提：Windows 上 AirSim 已 Play（TCP 4560 监听）、Phi-2 server 在跑（:8080）

echo "============================================"
echo "  端侧指令解析 Demo"
echo "============================================"

# ---- 0. 清理旧进程 ----
echo "[0] 清理旧进程..."
pkill -f "bin/px4" 2>/dev/null || true
pkill -f MicroXRCEAgent 2>/dev/null || true
pkill -f nl_command 2>/dev/null || true
sleep 2

# ---- 1. 启动 DDS Agent（输出重定向到文件，不刷屏）----
echo "[1] 启动 DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds_agent.log 2>&1 &
AGENT_PID=$!
sleep 2

# ---- 2. 启动 PX4 SITL 连 AirSim（输出重定向到文件，不刷屏）----
echo "[2] 启动 PX4 SITL 连接 AirSim (25秒)..."
cd ~/PX4-Autopilot
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SIM_LOCKSTEP=0 \
  make px4_sitl_default none_iris > /tmp/px4_run.log 2>&1 &
PX4_PID=$!
sleep 25

# ---- 3. 验证连通 ----
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash
FMU=$(ros2 topic list 2>/dev/null | grep -c fmu)
echo "[3] FMU 话题数: $FMU"
if [ "$FMU" -eq 0 ]; then
    echo "    ❌ PX4 没连上！检查 AirSim 是否已 Play"
    echo "    PX4 日志: tail -50 /tmp/px4_run.log"
    kill $PX4_PID $AGENT_PID 2>/dev/null
    exit 1
fi
echo "    ✅ PX4 + AirSim + DDS 连通"

# 检查 PX4 是否 ready for takeoff
grep -q "Ready for takeoff" /tmp/px4_run.log 2>/dev/null && echo "    ✅ PX4 Ready for takeoff" || echo "    ⚠️ PX4 还没 Ready（EKF 可能未收敛）"

# ---- 4. 启动 nl_command_node ----
echo "[4] 启动 nl_command_node..."
ros2 run nl_command nl_command_node &
NODE_PID=$!
sleep 5

# 验证节点在线
if ros2 node list 2>/dev/null | grep -q nl_command; then
    echo "    ✅ nl_command_node 在线"
else
    echo "    ❌ nl_command_node 未上线，检查错误"
    kill $PX4_PID $AGENT_PID 2>/dev/null
    exit 1
fi

# ---- 5. 验证订阅并发送指令 ----
echo ""
echo "=== 0. 自检：消息类型是否可用 ==="
timeout 5 ros2 interface show std_msgs/msg/String > /dev/null 2>&1 \
  && echo "    ✅ std_msgs/msg/String 类型可用" \
  || echo "    ❌ std_msgs/msg/String 类型不可用（环境问题！）"

echo "=== 订阅检查 ==="
ros2 topic info /nl_input -v 2>&1 | grep -E "Publisher count|Subscription count" | head -4
echo ""
echo "============================================"
echo "  发送指令: UAV 1 fly to (10, 20, 5)"
echo "============================================"
# 用 Python 发布（ros2 topic pub CLI 在本机有类型解析 bug，Python 直接发布可靠）
timeout 15 python3 ~/send_nl.py "UAV 1 fly to 10 20 5"
PUB_EXIT=$?
echo ""
echo "pub 退出码: $PUB_EXIT  (0=成功)"

echo ""
echo "节点持续运行中，等待 ARM + 起飞..."
echo "（节点每 5 秒打印一次状态；PX4 日志在 /tmp/px4_run.log）"
echo "按 Ctrl+C 停止全部"
echo ""

# 等待 node 结束
wait $NODE_PID

# ---- 清理 ----
echo "清理进程..."
kill $PX4_PID $AGENT_PID 2>/dev/null
echo "Done."
