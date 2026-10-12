#!/bin/bash
# wsl_llm_live_test.sh - 云端节点 DeepSeek 模式实测（含心跳不阻塞验证）
#
# 用法（Windows 侧，Git Bash）：
#   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash \
#     "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_llm_live_test.sh"
#
# 验证点：
#   1. 节点以 provider=deepseek 启动，API key 被识别
#   2. 显式态势 → LLM 推断正确相位（engine=deepseek）
#   3. 隐式态势 → LLM 语义推断（规则引擎会回落的那些）
#   4. LLM 推断期间 /cloud/heartbeat 保持 1Hz（后台线程设计的关键验证）
#   5. ~/cloud_llm_stats.jsonl 落盘记录

set -e

# 从 ~/.bashrc 提取 API key（非交互 shell 不会加载 .bashrc，见 wsl_eval_llm.sh 注释）
for var in DEEPSEEK_API_KEY GLM_API_KEY CLOUD_LLM_API_KEY; do
  line=$(grep "^export ${var}=" ~/.bashrc 2>/dev/null | tail -1)
  if [ -n "$line" ] && [ -z "${!var}" ]; then
    eval "$line"
  fi
done
if [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$CLOUD_LLM_API_KEY" ]; then
  echo "[错误] ~/.bashrc 中未找到 DEEPSEEK_API_KEY"; exit 1
fi

source /opt/ros/humble/setup.bash
source /home/chuanyu/px4_ws/install/setup.bash

CLOUD_LOG=/tmp/cloud_llm_live.log
HZ_LOG=/tmp/hb_hz.log

# 心跳频率监测（后台，全程运行）
ros2 topic hz /cloud/heartbeat > "$HZ_LOG" 2>&1 &
HZ_PID=$!

# 云端节点（DeepSeek 模式）
CLOUD_LLM_PROVIDER=deepseek ros2 run nl_command cloud_phase_generator \
  > "$CLOUD_LOG" 2>&1 &
NODE_PID=$!
sleep 4

# 显式关键词态势
ros2 topic pub --once /cloud/situation std_msgs/msg/String \
  "{data: 'Obstacle cluster 30m ahead on right side, evasive maneuver needed'}" > /dev/null 2>&1 || true
sleep 3

# 隐式语义态势（规则引擎会回落 HOLD，LLM 应给出 OBSTACLE_AVOID）
ros2 topic pub --once /cloud/situation std_msgs/msg/String \
  "{data: 'Weather radar shows a strong downdraft zone 25m ahead; lateral detour to the left is advised'}" > /dev/null 2>&1 || true
sleep 4

kill $NODE_PID 2>/dev/null || true
sleep 1
kill -9 $HZ_PID 2>/dev/null || true

echo "===== 云端节点日志 ====="
cat "$CLOUD_LOG"
echo ""
echo "===== /cloud/heartbeat 频率（推断期间应保持 ~1Hz） ====="
tail -5 "$HZ_LOG"
echo ""
echo "===== 统计落盘（~/cloud_llm_stats.jsonl 最后 2 条） ====="
tail -2 ~/cloud_llm_stats.jsonl 2>/dev/null || echo "（无记录）"
