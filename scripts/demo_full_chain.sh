#!/bin/bash
# demo_full_chain.sh - 完整链条端到端演示（创新点1+3串联）
#
# 演示流程：
#   1. 启动 PX4 + AirSim（飞行环境）
#   2. 启动云端相位规划器（LLM 读态势→生成相位信号）
#   3. 启动端侧 nl_command_node（v4 模型，相位条件化解析）
#   4. [正常] 端侧接收云端相位 + NL指令 → 飞行
#   5. [态势变化] 发送新态势 → 云端 LLM 推断新相位 → 端侧收到新相位
#   6. [断连] 杀掉云端 → 端侧用缓存相位自主飞往安全目标
#   7. [恢复] 重启云端 → 端侧重新对齐
#
# 前提：AirSim 已 Play、Phi-2 server 已启动

echo "============================================"
echo "  完整链条演示（云端相位→端侧执行→断连降级→恢复）"
echo "  创新点1（云-边协同）+ 创新点3（断连降级）"
echo "============================================"

# ---- 0. 清理 ----
echo "[0] 清理旧进程..."
pkill -9 -f "bin/px4" 2>/dev/null
pkill -9 -f MicroXRCEAgent 2>/dev/null
pkill -9 -f nl_command 2>/dev/null
pkill -9 -f cloud_phase 2>/dev/null
sleep 2

source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

# ---- 1. DDS Agent ----
echo "[1] DDS Agent..."
MicroXRCEAgent udp4 -p 8888 > /tmp/dds_fc.log 2>&1 &
sleep 2

# ---- 2. PX4 ----
echo "[2] PX4 SITL 连 AirSim..."
cd ~/PX4-Autopilot
PX4_SIM_HOST_ADDR=172.21.112.1 PX4_SYS_AUTOSTART=10016 \
  make px4_sitl_default none_iris > /tmp/px4_fc.log 2>&1 &
sleep 20
grep -q "Simulator connected" /tmp/px4_fc.log && echo "    ✅ PX4 连上 AirSim" || echo "    ⚠️ PX4 待确认"

# ---- 3. 云端相位规划器 ----
# 相位推断引擎由 CLOUD_LLM_PROVIDER 选择（默认 rule）：
#   rule      规则引擎（关键词匹配，无需网络）
#   deepseek  DeepSeek API（真云端 LLM，需 export DEEPSEEK_API_KEY=sk-xxx）
#   glm       智谱 GLM API（需 export GLM_API_KEY=xxx）
#   local     本地 llama.cpp server（Windows 宿主机 :8080，需先起 Phi-2 server）
PROVIDER="${CLOUD_LLM_PROVIDER:-rule}"
echo "[3] 云端相位规划器（provider=$PROVIDER）..."
# ⚠️ 直接执行节点可执行文件（单进程）。若用 ros2 run，kill 包装进程时真正的
# 节点子进程会存活并继续发心跳，[断连] 永不触发（2026-09 两轮排障确认的根因）
python3 ~/px4_ws/install/nl_command/lib/nl_command/cloud_phase_generator \
  > /tmp/cloud_fc.log 2>&1 &
CLOUD_PID=$!
sleep 3
echo "    初始相位: HOLD@(0,0,5)"
echo "    心跳: 1Hz | 相位重发: 0.2Hz"
if [ "$PROVIDER" != "rule" ]; then
  echo "    （LLM 模式：推断在后台线程执行，心跳不受阻；延迟/成功率落盘 ~/cloud_llm_stats.jsonl）"
fi

# ---- 4. 端侧节点 ----
echo "[4] 端侧 nl_command_node（v4 相位条件化）..."
# 预检：端侧依赖 Windows 宿主机的 Phi-2 server（:8080），没起会在飞行中才报错
if curl -s -m 3 http://172.21.112.1:8080/v1/models | grep -q gguf 2>/dev/null; then
  echo "    ✅ Phi-2 server 在线（172.21.112.1:8080）"
else
  echo "    ⚠️ Phi-2 server 未启动！端侧解析 NL 指令会 Connection refused。"
  echo "       在 Windows 新开 PowerShell 执行："
  echo "       cd D:\2026-2027\Phi-2\ QLoRA && .venv\Scripts\python.exe -m llama_cpp.server --model phi2-phased-v5-q5_k_m.gguf --n_gpu_layers -1 --host 0.0.0.0 --port 8080"
  echo "       起好后再继续（Ctrl+C 退出本脚本重跑，或直接继续——相位链路不依赖它）"
fi
ros2 run nl_command nl_command_node > /tmp/nl_fc.log 2>&1 &
NODE_PID=$!
sleep 4

echo ""
echo "============================================"
echo "  演示操作（按顺序在另一个终端执行）："
echo ""
echo "  A. [正常飞行] 发送 NL 指令："
echo "     ros2 topic pub --once /nl_input std_msgs/msg/String \"{data: 'UAV 1 fly to 5 5 3'}\""
echo "     （观察无人机起飞，此时 link=CONNECTED）"
echo ""
echo "  B. [态势变化→新相位] 发送态势："
echo "     ros2 topic pub --once /cloud/situation std_msgs/msg/String \"{data: 'Obstacle cluster 30m ahead on right side, evasive maneuver needed'}\""
echo "     （显式关键词：规则引擎/LLM 均应推断 OBSTACLE_AVOID@right@30）"
echo ""
echo "  B2. [隐式语义态势] 规则引擎 vs 真 LLM 的分水岭："
echo "     ros2 topic pub --once /cloud/situation std_msgs/msg/String \"{data: 'Weather radar shows a strong downdraft zone 25m ahead; lateral detour to the left is advised'}\""
echo "     （无任何关键词：rule 模式回落 HOLD；deepseek/glm 模式应推断 OBSTACLE_AVOID@left@25）"
echo "     ros2 topic pub --once /cloud/situation std_msgs/msg/String \"{data: 'Command requests all units consolidate at checkpoint Bravo (12,-8) for the night'}\""
echo "     （应推断 ASSEMBLE@(12,-8)）"
echo ""
echo "  C. [断连降级] 杀掉云端（⚠️ 在 phase=cruising 且 offboard=True 时执行）："
echo "     kill -9 $CLOUD_PID"
echo "     # 该 PID 就是节点进程本身（本脚本直接执行，无 ros2 run 包装）"
echo "     # 验证已死、清理残留：pgrep -af cloud_phase_generator 应无输出"
echo "     （观察 [断连] 3.0秒无心跳 → 降级 → 用缓存相位自主飞往安全目标）"
echo ""
echo "  D. [恢复] 重启云端（⚠️ 新终端先 source；直接执行节点文件，与脚本启动方式一致）："
echo "     source /opt/ros/humble/setup.bash && source ~/px4_ws/install/setup.bash"
echo "     CLOUD_LLM_PROVIDER=$PROVIDER python3 ~/px4_ws/install/nl_command/lib/nl_command/cloud_phase_generator &"
echo "     （观察 [恢复] 重新对齐）"
echo ""
echo "  按 Ctrl+C 退出演示"
echo "============================================"
echo ""

# 持续显示端侧和云端日志
tail -f /tmp/nl_fc.log /tmp/cloud_fc.log 2>/dev/null | \
  grep --line-buffered -E "云端|相位|断连|降级|恢复|NL input|Phi-2|Target|OFFBOARD|ARM|状态|态势"

# 清理（Ctrl+C 后执行）
kill $NODE_PID $CLOUD_PID 2>/dev/null
