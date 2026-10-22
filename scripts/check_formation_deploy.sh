#!/bin/bash
# check_formation_deploy.sh — 验证 WSL 侧 mappo_formation 部署是否可用
set -e
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "--- 入口点 ---"
ros2 pkg executables uav_adversarial | grep mappo || true

echo "--- 模块可导入（不启动节点）---"
python3 -c "
import uav_adversarial.edge.mappo_bridge_math as bm
actor = bm.NumpyActor.from_npz('/home/chuanyu/px4_ws/models/mappo_2d_seed555_actor.npz')
import numpy as np
obs = np.zeros((4, 14), dtype=np.float32)
print('actor ok:', actor.obs_dim, actor.action_dim, actor.act(obs).shape)
"

echo "--- 节点模块语法/导入 ---"
python3 -c "
import py_compile
py_compile.compile('/home/chuanyu/px4_ws/src/uav_adversarial/uav_adversarial/edge/mappo_policy_node.py', doraise=True)
print('mappo_policy_node 语法 OK')
"

echo "--- npz 校验 ---"
sha256sum /home/chuanyu/px4_ws/models/mappo_2d_seed555_actor.npz
sha256sum "/mnt/d/2026-2027/Phi-2 QLoRA/assets/mappo_2d_seed555_actor.npz"
