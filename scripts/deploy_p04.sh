#!/bin/bash
# deploy_p04.sh - 部署 P0-4 节点与依赖模块到 WSL2 px4_ws 的 nl_command 包
#
# 用法（Windows 侧）：
#   wsl.exe -d Ubuntu-22.04 -- bash "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/deploy_p04.sh"
set -e

PKG=/home/chuanyu/px4_ws/src/nl_command/nl_command
SRC="/mnt/d/2026-2027/Phi-2 QLoRA/scripts"
SAFE="/mnt/d/2026-2027/Phi-2 QLoRA/safety"
STAMP=$(date +%Y%m%d)

echo "[1/3] 备份旧文件（当日首份）..."
for f in nl_command_node_p04.py phase_link.py safety_layer.py phase_fault_proxy.py; do
  if [ -f "$PKG/$f" ] && [ ! -f "$PKG/$f.bak_$STAMP" ]; then
    cp "$PKG/$f" "$PKG/$f.bak_$STAMP"
  fi
done

echo "[2/3] 复制 P0-4 文件..."
cp "$SRC/nl_command_node_p04.py" "$SRC/phase_link.py" "$SRC/phase_fault_proxy.py" "$PKG/"
cp "$SAFE/safety_layer.py" "$PKG/"
ls -la "$PKG" | grep -E "p04|link|safety" || true

echo "[3/3] colcon build..."
source /opt/ros/humble/setup.bash
cd /home/chuanyu/px4_ws
colcon build --packages-select nl_command 2>&1 | tail -3
echo "部署完成。"
