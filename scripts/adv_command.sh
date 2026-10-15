#!/bin/bash
# adv_command.sh - 给红/蓝队发对抗指令的快捷入口
# 用法：
#   bash adv_command.sh red "Red team, pursue the enemy"
#   bash adv_command.sh blue "Blue team, evade to safety"
#   bash adv_command.sh all  # 同时给两队发默认对抗指令
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

SCRIPT="/mnt/d/2026-2027/Phi-2 QLoRA/scripts/pub_nl.py"

TEAM=$1
TEXT=$2

case "$TEAM" in
    red)
        python3 "$SCRIPT" "${TEXT:-Red team, pursue the enemy}" /red1/nl_input
        python3 "$SCRIPT" "${TEXT:-Red team, pursue the enemy}" /red2/nl_input
        ;;
    blue)
        python3 "$SCRIPT" "${TEXT:-Blue team, evade to safety}" /blue1/nl_input
        python3 "$SCRIPT" "${TEXT:-Blue team, evade to safety}" /blue2/nl_input
        ;;
    all)
        python3 "$SCRIPT" "Red team, pursue the enemy" /red1/nl_input
        python3 "$SCRIPT" "Red team, pursue the enemy" /red2/nl_input
        sleep 1
        python3 "$SCRIPT" "Blue team, evade to safety" /blue1/nl_input
        python3 "$SCRIPT" "Blue team, evade to safety" /blue2/nl_input
        ;;
    *)
        echo "用法: bash adv_command.sh {red|blue|all} [自定义指令]"
        echo "  red   → 给红队两机发追击指令"
        echo "  blue  → 给蓝队两机发规避指令"
        echo "  all   → 同时给四机发默认对抗指令"
        exit 1
        ;;
esac
