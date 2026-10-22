#!/bin/bash
# check_deployed_node.sh — 核查 WSL 侧部署的 mappo_policy_node 是否含原语订阅
set -x
grep -n "mission_primitive_topic\|create_subscription" \
    /home/chuanyu/px4_ws/src/uav_adversarial/uav_adversarial/edge/mappo_policy_node.py | head -8
grep -c "_on_primitive" \
    /home/chuanyu/px4_ws/install/uav_adversarial/lib/python3.10/site-packages/uav_adversarial/edge/mappo_policy_node.py
grep -n "TRANSIENT_LOCAL" \
    /home/chuanyu/px4_ws/src/uav_adversarial/uav_adversarial/edge/mission_commander_node.py
