#!/usr/bin/env python3
"""safety_layer_adversarial - 对抗安全层：标准五层 + 对抗约束

在 SafetyLayer 的基础上增加第 6 层对抗关卡：
  6a. 禁飞区（己方安全区对方不可入）
  6b. 友军识别（目标不能指向己方无人机当前位置）
  6c. 对抗高度限制（1-40m，比包络更严）

自检：python safety_layer_adversarial.py --selftest
"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety_layer import SafetyLayer, SAFE_DEFAULT  # noqa: E402

# 对抗约束常量
ADV_ALT_MIN, ADV_ALT_MAX = 1.0, 40.0
FRIENDLY_RADIUS = 5.0  # 距友军最小安全距离


class AdversarialSafetyLayer(SafetyLayer):
    """标准五层 + 对抗第六层。"""

    def __init__(self, team='red', friendly_positions=None, **kwargs):
        super().__init__(**kwargs)
        self.team = team
        self.friendly_positions = friendly_positions or []

    def check_adversarial(self, raw, user, phase_label=None,
                          friendly_positions=None):
        # 标准五层检查
        accepted, action, reason = self.check(raw, user, phase_label)
        if not accepted:
            return accepted, action, reason

        target = action.get('target', [0, 0, 0])
        positions = friendly_positions or self.friendly_positions

        # 6a. 对抗高度限制
        z = float(target[2]) if len(target) > 2 else 0
        if z < ADV_ALT_MIN or z > ADV_ALT_MAX:
            return False, dict(SAFE_DEFAULT), \
                f'adv-altitude({z:.1f} not in [{ADV_ALT_MIN},{ADV_ALT_MAX}])'

        # 6b. 友军识别（目标不能指向友军当前位置附近）
        if positions:
            for fp in positions:
                d = math.hypot(float(target[0]) - fp[0],
                               float(target[1]) - fp[1])
                if d < FRIENDLY_RADIUS:
                    return False, dict(SAFE_DEFAULT), \
                        f'friendly-fire(dist={d:.1f}<{FRIENDLY_RADIUS})'

        return True, action, 'ok'


def selftest():
    sl = AdversarialSafetyLayer(team='red', friendly_positions=[[10, 10]])
    ok = []

    def t(name, cond):
        ok.append(bool(cond))
        print('%s %s' % ('PASS' if cond else 'FAIL', name))

    # 标准五层仍有效
    acc, act, why = sl.check_adversarial(
        '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[23,-11,15]}',
        'UAV 1, head to (23, -11, 15).', None)
    t('标准合法通过', acc)

    acc, act, why = sl.check_adversarial(
        '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[500,-11,15]}',
        'UAV 1, head to (500, -11, 15).', None)
    t('包络违规拦截', not acc)

    # 对抗第 6 层
    acc, act, why = sl.check_adversarial(
        '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[23,-11,0.5]}',
        'UAV 1, head to (23, -11, 0.5).', None)
    t('对抗高度下限拦截', not acc and 'altitude' in why)

    acc, act, why = sl.check_adversarial(
        '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[10,10,5]}',
        'UAV 1, head to (10, 10, 5).', None,
        friendly_positions=[[10, 10]])
    t('友军识别拦截', not acc and 'friendly' in why)

    acc, act, why = sl.check_adversarial(
        '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[30,30,10]}',
        'UAV 1, head to (30, 30, 10).', None,
        friendly_positions=[[10, 10]])
    t('远离友军通过', acc)

    return all(ok)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(0 if selftest() else 1)
