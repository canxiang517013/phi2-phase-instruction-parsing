#!/bin/bash
# check_p04_deploy.sh — 验证 P0-4 闭环组件在 WSL 侧的部署
set -e
source /opt/ros/humble/setup.bash
source ~/px4_ws/install/setup.bash

echo "--- 入口点 ---"
ros2 pkg executables uav_adversarial | grep -E "mappo|mission" || true

echo "--- 模块导入 + 链路自检 ---"
python3 - <<'PYEOF'
import sys
from uav_adversarial.edge import p04_link
from uav_adversarial.edge import mission_commander_node
from uav_adversarial.edge import mappo_policy_node
from uav_adversarial.common.phase_rules import validate_phase

print('p04_link/mapper/commander import OK')

link = p04_link.P04Link(lambda s: None)
now = 100.0
assert link.on_phase('ASSEMBLE@(0,0)', now, now) == 'accepted'
assert link.state == 'FRESH'
assert link.tick(now + 3.5) == 'DEGRADED'
assert link.on_phase('HOLD@(0,0,5)', now + 3.5, now + 3.5) == 'accepted'
assert link.state == 'FRESH'
print('link 状态机: 接受/退化/恢复 OK')

# mappo 支持的编队几何
from uav_adversarial.edge import mappo_bridge_math as bm
for f in bm.SUPPORTED_FORMATIONS:
    off = bm.offsets_for(f, 60.0, 4)
    assert off.shape == (4, 2), f
    print('formation %-8s offsets ok %s' % (f, off.round(1).tolist()[0]))
PYEOF

echo "--- 安全层自检 ---"
python3 /home/chuanyu/px4_ws/src/uav_adversarial/uav_adversarial/common/safety_layer.py --selftest | tail -2
