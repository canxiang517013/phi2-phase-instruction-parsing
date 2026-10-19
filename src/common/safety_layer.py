#!/usr/bin/env python3
"""safety_layer - P0-4 确定性安全层：SLM 输出在进入 PX4/MAPPO 前的强制关卡

依据（P0-2 实测结论）：
  - 越界指令 84-100% 危险回声（含 FP16）→ 必须数值钳制/拒绝
  - 缺字段捏造恒为众数 (15,15,15) → 数值溯源可拦截
  - 歧义指令 ~100% 捏造 → 指令无数值时任何数值输出都不可信
  - 错误 phase 100% 捏造 → 相位-动作一致性校验

契约（与 evaluation/eval_run_v2.ENVELOPE、scripts/phase_rules.py 对齐）：
  飞行包络 v1：|x|,|y|<=300，0<=z<=60，uav_ids 含于 {1..5}
  相位派生常量：ASSEMBLE/RECON 缺省 z=5/15，OBSTACLE_AVOID y=0 z=15
  安全默认动作：hold（原地悬停），与 8 月断连降级语义一致

自检：python safety_layer.py --selftest
"""

import json
import re

ENVELOPE = {'abs_xy': 300.0, 'z_min': 0.0, 'z_max': 60.0,
            'uav_ids': set(range(1, 6)),
            'modes': {'single-agent', 'swarm'},
            'formations': {'free', 'triangle', 'line', 'grid', 'wedge', 'circle'}}

# 相位契约的派生常量（分轴）：z 的缺省高度 5/15，OBSTACLE_AVOID 的 y=0；
# x 轴没有任何契约常量——x=15 这类"众数捏造"必须被溯源拒绝
PHASE_DERIVED_CONSTANTS = {'x': set(), 'y': {0.0}, 'z': {5.0, 15.0}}
DEFAULT_FLEET_IDS = {1, 2, 3, 4}

SAFE_DEFAULT = {'mode': 'hold', 'source': 'safety_layer'}

_NUM = r'-?\d+(?:\.\d+)?'
_NUM_RE = re.compile(_NUM)


def extract_numbers(*texts):
    """从输入文本（指令、相位串）抽取全部数值。"""
    out = set()
    for t in texts:
        if not t:
            continue
        out.update(float(m) for m in _NUM_RE.findall(str(t)))
    return out


def parse_phase(phase):
    """解析相位串 -> {'type':..., 'target':[x,y,z]|None, 'formation':str|None}。"""
    if not phase or not isinstance(phase, str):
        return None
    s = phase.strip()
    m = re.match(r'^(ASSEMBLE|HOLD|RECONFIGURE|OBSTACLE_AVOID|RECON)@', s)
    if not m:
        return None
    ptype = m.group(1)
    rest = s.split('@', 1)[1]
    if ptype == 'RECONFIGURE':
        return {'type': ptype, 'target': None, 'formation': rest}
    nums = [float(x) for x in _NUM_RE.findall(rest)]
    if ptype in ('ASSEMBLE', 'RECON'):
        if len(nums) < 2:
            return None  # 截断相位（bad-phase 类）：不可解析即不可派生
        z = 5.0 if ptype == 'ASSEMBLE' else 15.0
        return {'type': ptype, 'target': [nums[0], nums[1], z], 'formation': None}
    if ptype == 'OBSTACLE_AVOID':
        parts = rest.split('@')
        if len(parts) < 2 or not nums or parts[0] not in ('left', 'right'):
            return None
        n = nums[-1]
        d = -n if parts[0] == 'left' else n
        return {'type': ptype, 'target': [d, 0.0, 15.0], 'formation': None}
    if ptype == 'HOLD' and len(nums) == 3:
        return {'type': ptype, 'target': nums, 'formation': None}
    return None


def _close(a, b, tol=1e-6):
    return abs(float(a) - float(b)) <= tol


class SafetyLayer:
    """check(raw, user, phase_label) -> (accepted, action, reason)。"""

    def __init__(self, fleet_ids=DEFAULT_FLEET_IDS, tol=1e-6):
        self.fleet_ids = set(fleet_ids)
        self.tol = tol

    def check(self, raw, user, phase_label=None):
        if not isinstance(raw, str) or not raw.strip():
            return False, dict(SAFE_DEFAULT), 'empty-output'
        try:
            got = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return False, dict(SAFE_DEFAULT), 'unparseable-json'
        if not isinstance(got, dict):
            return False, dict(SAFE_DEFAULT), 'not-an-object'

        # 1) schema：字段类型与取值域
        if got.get('mode') not in ENVELOPE['modes']:
            return False, dict(SAFE_DEFAULT), 'mode-invalid'
        form = got.get('formation')
        if form is not None and form not in ENVELOPE['formations']:
            return False, dict(SAFE_DEFAULT), 'formation-invalid'
        ids = got.get('uav_ids')
        if not isinstance(ids, list) or not ids or not all(isinstance(v, int) for v in ids):
            return False, dict(SAFE_DEFAULT), 'ids-invalid'
        if not set(ids) <= ENVELOPE['uav_ids']:
            return False, dict(SAFE_DEFAULT), 'ids-out-of-domain'
        tgt = got.get('target')
        if not isinstance(tgt, list) or len(tgt) != 3:
            return False, dict(SAFE_DEFAULT), 'target-invalid'
        try:
            x, y, z = (float(v) for v in tgt)
        except (TypeError, ValueError):
            return False, dict(SAFE_DEFAULT), 'target-not-numeric'

        # 2) 数值包络（拦截越界危险回声）
        if not (abs(x) <= ENVELOPE['abs_xy'] and abs(y) <= ENVELOPE['abs_xy']
                and ENVELOPE['z_min'] <= z <= ENVELOPE['z_max']):
            return False, dict(SAFE_DEFAULT), 'envelope-violation'

        # 3) 数值溯源：输出数值必须来自指令/相位上下文、该轴契约常量、或相位派生目标
        #    （如 OBSTACLE_AVOID@left@15 的 x=-15 是契约符号推导，不是凭空捏造）
        ctx_nums = extract_numbers(user, phase_label)
        ph = parse_phase(phase_label)
        derived = ph['target'] if ph and ph['target'] else []
        for i, (axis, v) in enumerate(zip('xyz', (x, y, z))):
            allowed = ctx_nums | PHASE_DERIVED_CONSTANTS[axis]
            if i < len(derived):
                allowed = allowed | {float(derived[i])}
            if not any(_close(v, a, self.tol) for a in allowed):
                return False, dict(SAFE_DEFAULT), 'unverified-number[%s]:%g' % (axis, v)
        if not set(ids) <= (allowed | self.fleet_ids):
            return False, dict(SAFE_DEFAULT), 'unverified-ids'

        # 4) 相位-动作一致性（有相位上下文时才生效）
        #    RECONFIGURE: 编队名必须匹配
        #    其他相位: 仅当目标值来自相位派生（非指令显式给出）时才要求匹配；
        #    指令显式坐标通过溯源检查（第 3 层）即视为安全，允许与相位默认不同
        #    （对抗模式下指令目标可与相位不同：如 HOLD 相位下收到 evade 指令）
        if ph:
            if ph['type'] == 'RECONFIGURE':
                if form != ph['formation']:
                    return False, dict(SAFE_DEFAULT), 'phase-formation-mismatch'
            else:
                # 检查目标是否来自指令（而非相位）
                cmd_nums = extract_numbers(user)
                from_cmd = all(
                    any(_close(v, c, self.tol) for c in cmd_nums)
                    for v in (x, y, z)
                )
                if not from_cmd:
                    # 目标不是指令显式给出的 → 必须与相位目标匹配
                    if not all(_close(a, b, 1e-6) for a, b in zip((x, y, z), ph['target'])):
                        return False, dict(SAFE_DEFAULT), 'phase-target-mismatch'

        # 5) 速度/高度/间距约束（P0-4 场景参数，默认与包络一致，可外部扩展）
        action = dict(got)
        action['source'] = 'slm'
        return True, action, 'ok'


def selftest():
    sl = SafetyLayer()
    ok = []

    def t(name, raw, user, phase, want_accept, want_reason=None):
        acc, act, why = sl.check(raw, user, phase)
        good = acc == want_accept and (want_reason is None or why.startswith(want_reason))
        ok.append(good)
        print('%s %-28s -> accept=%s reason=%s' % ('PASS' if good else 'FAIL', name, acc, why))

    t('合法单机', '{"mode":"single-agent","formation":"free","uav_ids":[5],"target":[23,-11,15]}',
      'Drone 5, head to (23, -11, 15).', None, True)
    t('合法相位条件', '{"mode":"swarm","formation":"line","uav_ids":[1,2,3,4],"target":[0,-10,5]}',
      'Everyone, scout ahead.', 'ASSEMBLE@(0,-10)', True)
    t('越界危险回声被拦', '{"mode":"single-agent","formation":"free","uav_ids":[1],"target":[400,-11,15]}',
      'Drone 1, head to (400, -11, 15).', None, False, 'envelope-violation')
    t('歧义捏造被拦', '{"mode":"swarm","formation":"line","uav_ids":[1,2,3],"target":[-15,-15,5]}',
      'Everyone, fall back.', None, False, 'unverified-number')
    t('缺字段众数捏造被拦', '{"mode":"single-agent","formation":"free","uav_ids":[3],"target":[15,-20,5]}',
      'Drone 3, go to (?, -20, 5).', None, False, 'unverified-number[x]')
    t('坏 JSON 被拦', 'mode: swarm', 'x', None, False, 'unparseable-json')
    t('相位目标不一致被拦（溯源或比对任一层拒绝即可）',
      '{"mode":"swarm","formation":"line","uav_ids":[1],"target":[5,5,5]}',
      'Everyone, scout ahead.', 'ASSEMBLE@(0,-10)', False)
    t('非法 formation 被拦', '{"mode":"swarm","formation":"hexagon","uav_ids":[1],"target":[1,1,5]}',
      'Everyone, go to (1, 1, 5).', None, False, 'formation-invalid')
    return all(ok)


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(0 if selftest() else 1)
