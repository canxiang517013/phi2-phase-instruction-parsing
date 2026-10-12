#!/bin/bash
# demo_degradation.sh - 断连降级机制演示（创新点3）
#
# 演示流程：
#   1. 启动云端心跳节点（模拟云端相位规划器）
#   2. 启动 nl_command_node（端侧，含降级状态机）
#   3. 观察正常连接状态
#   4. Ctrl+C 杀掉心跳 → 端侧3秒后进入 DEGRADED 模式（自主悬停维持）
#   5. 重新启动心跳 → 端侧恢复 CONNECTED
#
# 用法：开 3 个终端，按提示操作
#   终端1: bash ~/demo_degradation.sh
#   终端2: 手动杀心跳（Ctrl+C），观察终端1的降级日志
#   终端3: 手动重启心跳，观察恢复日志

echo "============================================"
echo "  断连降级机制演示（创新点3）"
echo "============================================"

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo ""
echo "[1] 启动云端心跳节点（模拟云端）"
echo "    心跳频率 1Hz，相位信号低频 0.1Hz"
echo ""
python3 ~/px4_ws/install/nl_command/lib/nl_command/cloud_heartbeat_node &
HB_PID=$!
echo "    心跳节点 PID: $HB_PID"
sleep 2

echo ""
echo "[2] 启动端侧 nl_command_node"
echo ""
python3 ~/px4_ws/install/nl_command/lib/nl_command/nl_command_node &
NL_PID=$!
echo "    端侧节点 PID: $NL_PID"
echo ""

echo "============================================"
echo "  操作指引："
echo ""
echo "  观察[云端]链路已连接 → 正常状态"
echo ""
echo "  ▶ 模拟断连：在另一个终端执行："
echo "     kill -9 $HB_PID"
echo "  然后回到这里看端侧日志："
echo "  应出现 [断连] xx秒无心跳，进入降级模式"
echo "  之后每5秒打印 [降级维持中]"
echo ""
echo "  ▶ 模拟恢复：在另一个终端执行："
echo "     python3 ~/px4_ws/install/nl_command/lib/nl_command/cloud_heartbeat_node &"
echo "  端侧应打印 [恢复] 云端链路恢复，重新对齐相位"
echo ""
echo "  按 Ctrl+C 退出演示"
echo "============================================"
echo ""

wait

# 清理
kill $NL_PID $HB_PID 2>/dev/null
