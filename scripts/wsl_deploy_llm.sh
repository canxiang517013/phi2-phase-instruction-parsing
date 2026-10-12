#!/bin/bash
# wsl_deploy_llm.sh - 把云端 LLM 化的文件部署到 WSL2 px4_ws 的 nl_command 包
#
# 用法（Windows 侧）：
#   wsl.exe -d Ubuntu-22.04 -- bash "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_deploy_llm.sh"
# 或（WSL2 内）：
#   bash /mnt/d/2026-2027/Phi-2\ QLoRA/scripts/wsl_deploy_llm.sh
#
# 做三件事：
#   1. 备份 WSL 侧旧的 cloud_phase_generator.py（带日期后缀）
#   2. 复制 cloud_phase_generator.py + phase_rules.py 到包源码目录
#   3. colcon build --packages-select nl_command

set -e

PKG=/home/chuanyu/px4_ws/src/nl_command/nl_command
SRC="/mnt/d/2026-2027/Phi-2 QLoRA/scripts"
STAMP=$(date +%Y%m%d)

echo "[1/3] 备份旧文件..."
if [ -f "$PKG/cloud_phase_generator.py" ] && [ ! -f "$PKG/cloud_phase_generator.py.bak_$STAMP" ]; then
  cp "$PKG/cloud_phase_generator.py" "$PKG/cloud_phase_generator.py.bak_$STAMP"
  echo "    已备份: cloud_phase_generator.py.bak_$STAMP"
else
  echo "    今日已备份过，跳过"
fi

echo "[2/3] 复制新文件..."
cp "$SRC/cloud_phase_generator.py" "$SRC/phase_rules.py" "$PKG/"
echo "    cloud_phase_generator.py + phase_rules.py -> $PKG"

echo "[3/3] colcon build..."
source /opt/ros/humble/setup.bash
cd /home/chuanyu/px4_ws
colcon build --packages-select nl_command 2>&1 | tail -3

echo ""
echo "部署完成。回归验证（规则模式，应输出 'provider=rule'）："
echo "  source /opt/ros/humble/setup.bash && source ~/px4_ws/install/setup.bash"
echo "  timeout 5 ros2 run nl_command cloud_phase_generator 2>&1 | head -5"
echo "DeepSeek 模式："
echo "  CLOUD_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-xxx ros2 run nl_command cloud_phase_generator"
