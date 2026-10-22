#!/bin/bash
# check_node_3d_init.sh — 验证 3D 模式节点可构造（无 PX4，仅初始化后退出）
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

timeout 6 ros2 run uav_adversarial mappo_formation --ros-args \
    -p actor_npz:=/home/chuanyu/px4_ws/models/mappo_3d_seed21_actor_best.npz \
    -p policy_dim:=3 \
    -p altitude:=10.0 \
    -p log_file:=/tmp/mappo_3d_init_test.jsonl > /tmp/mappo_3d_init_test.log 2>&1 || true

echo "--- 初始化日志 ---"
head -8 /tmp/mappo_3d_init_test.log
echo "--- 事件文件 ---"
head -2 /tmp/mappo_3d_init_test.jsonl 2>/dev/null || echo "(无)"
echo "--- 期望：node_start 且 policy_dim=3 配置无异常；INIT 等待位置 ---"
if grep -q "mappo_formation 就绪" /tmp/mappo_3d_init_test.log; then
    echo "PASS 3D 节点构造成功"
else
    echo "FAIL 节点未就绪"
    exit 1
fi
