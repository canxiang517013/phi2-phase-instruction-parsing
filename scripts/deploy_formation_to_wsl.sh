#!/bin/bash
# deploy_formation_to_wsl.sh — 部署 MAPPO 桥接节点到 WSL2 的 uav_adversarial 包
# 用法（Windows 侧）：
#   wsl.exe -d Ubuntu-22.04 -- bash "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/deploy_formation_to_wsl.sh"
set -e

REPO="/mnt/d/2026-2027/Phi-2 QLoRA"
EDGE_DIR=/home/chuanyu/px4_ws/src/uav_adversarial/uav_adversarial/edge
SETUP_PY=/home/chuanyu/px4_ws/src/uav_adversarial/setup.py
MODEL_DIR=/home/chuanyu/px4_ws/models

echo "[1/4] 复制桥接模块..."
cp "$REPO/src/nodes/edge/mappo_bridge_math.py" "$EDGE_DIR/"
cp "$REPO/src/nodes/edge/mappo_policy_node.py" "$EDGE_DIR/"
cp "$REPO/src/nodes/edge/p04_link.py" "$EDGE_DIR/"
cp "$REPO/src/nodes/edge/mission_commander_node.py" "$EDGE_DIR/"

echo "[2/4] 复制 npz 权重..."
mkdir -p "$MODEL_DIR"
cp "$REPO/assets/mappo_2d_seed555_actor.npz" "$MODEL_DIR/"
cp "$REPO/assets/mappo_3d_seed21_actor_best.npz" "$MODEL_DIR/"
cp "$REPO/assets/mappo_3d_pa_seed21_actor_best.npz" "$MODEL_DIR/"

echo "[3/4] 注册入口点（幂等）..."
python3 - <<'PYEOF'
from pathlib import Path

path = Path('/home/chuanyu/px4_ws/src/uav_adversarial/setup.py')
text = path.read_text(encoding='utf-8')
entries = {
    "'mappo_formation = uav_adversarial.edge.mappo_policy_node:main',":
        "'edge_node = uav_adversarial.edge.nl_command_node:main',",
    "'mission_commander = uav_adversarial.edge.mission_commander_node:main',":
        "'mappo_formation = uav_adversarial.edge.mappo_policy_node:main',",
}
anchor0 = "'edge_node = uav_adversarial.edge.nl_command_node:main',"
changed = False
for entry, anchor in entries.items():
    if entry not in text:
        if anchor not in text:
            raise SystemExit('未找到锚点，setup.py 结构可能已变化: %s' % anchor)
        text = text.replace(anchor, anchor + '\n            ' + entry)
        changed = True
        print('已添加入口点: %s' % entry.split()[0][1:])
if changed:
    path.write_text(text, encoding='utf-8')
else:
    print('入口点均已存在，跳过')
PYEOF

echo "[4/4] colcon build..."
source /opt/ros/humble/setup.bash
cd /home/chuanyu/px4_ws
colcon build --packages-select uav_adversarial 2>&1 | tail -3

echo
echo "部署完成。下一步："
echo "  1. Windows 侧打开 AirSim 并 Play"
echo "  2. WSL 侧运行: bash \"$REPO/launch/launch_4uav_formation.sh\""
