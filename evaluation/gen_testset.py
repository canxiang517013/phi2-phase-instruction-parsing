#!/usr/bin/env python3
"""gen_testset - 程序化生成大规模分层评测集（固定随机种子，金标准与训练规则同源）

背景（方向5：评估体系升级）：现有全部准确率结论建立在 16 条硬编码测试上，
两条样本的摆动就是 12 个百分点。本脚本生成统计可信的大评测集：

  basic_240.jsonl  基础指令解析（无相位），240 条 = 训练内 160 / 训练外 80
                   分层：single-agent 90 + swarm 150（5 阵型各 30）
                   金标准 = 生成时构造的 ground truth，判定 = 精确匹配

  phase_200.jsonl  相位条件化，200 条 = 每相位 40（seen 14 / in-range-unseen 10 / ood 16）
                   金标准 = 确定性规则映射（与训练数据生成规则 100% 同源，已验证）
                   判定 = 容差匹配（沿用 phase_verify_v4 的 λ 容差）

训练分布（dataset_phased_v5.jsonl，磁盘模型实际训练集，2026-09-06 实测统计）：
  基础 target：|x|<=30.5, |y|<=30, 0<=z<=25
  ASSEMBLE：16 个坐标，x,y ∈ [-10,10] 整数
  HOLD：12 个坐标 (x,y,z)，x∈[-8,6], y∈[-8,5], z∈[6,10]
  OBSTACLE_AVOID：{left,right} × N∈{15,20,25,30,35,40}
  RECON：14 个坐标，x∈[62,228], y∈[106,239]
  RECONFIGURE：5 队形，target 恒 (15,15,8)
  中性指令池：33 条（single/multi-explicit/collective 三类，
  mode+uav_ids 确定性映射；collective 的 formation 训练本身一对多，判定不约束）

用法：
  python evaluation/gen_testset.py                # 生成两个评测集
  python evaluation/gen_testset.py --selftest     # 金标准 schema 全量校验
  python evaluation/gen_testset.py --sample 20    # 抽样展示供人工核验
"""

import argparse
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from phase_rules import validate_phase  # noqa: E402

SEED = 20260906
INSTRUCTION = ('Parse the user natural language command into a '
               'structured JSON for UAV DMPC.')

# ---- 训练分布常量（split 设计依据，见模块 docstring） ----
TRAIN_BASIC_BBOX = (30.5, 30.0, 25.0)      # |x|,|y|,z 上界
ASM_SEEN = {(x, y) for x in range(-10, 11) for y in range(-10, 11)} & {
    (5, 5), (-5, 5), (5, -5), (-5, -5), (-2, 9), (-4, 1), (-6, -1), (10, 10),
    (-10, -10), (0, 8), (8, 0), (3, 3), (-7, 2), (2, -7), (9, -4), (-1, -9)}
HOLD_SEEN = {(-2, -6, 9), (-3, 3, 7), (-4, -5, 8), (-5, -5, 7), (1, -2, 6),
             (1, -4, 8), (0, 0, 5), (2, 2, 7), (6, 5, 10), (-8, 3, 6),
             (4, -8, 9), (-6, -7, 10)}
OBST_SEEN = {(d, n) for d in ('left', 'right') for n in (15, 20, 25, 30, 35, 40)}
RECON_SEEN = {(103, 117), (121, 235), (135, 196), (136, 206), (156, 167),
              (168, 195), (180, 120), (200, 150), (225, 110), (62, 140),
              (95, 200), (240, 228), (110, 106), (228, 239)}
RECONF_FORMS = ('column', 'circle', 'grid', 'wedge', 'line')

# 训练用过的 33 条中性指令（相位样本的 input），按主体类型分组
CMD_SINGLE = ['UAV 1, change position.', 'UAV 1, continue.', 'UAV 1, proceed.',
              'UAV 2, change position.', 'UAV 2, continue.', 'UAV 2, proceed.',
              'UAV 3, change position.', 'UAV 3, proceed.', 'UAV 4, continue.',
              'UAV 4, proceed.']
CMD_MULTI = ['UAV 1 and 2, adjust formation.', 'UAV 1 and 2, follow through.',
             'UAV 1 and 2, tighten up.', 'UAV 1 and 4, adjust formation.',
             'UAV 1 and 4, move.', 'UAV 2 and 3, adjust formation.',
             'UAV 2 and 3, move.', 'UAV 3 and 4, adjust formation.',
             'UAV 3 and 4, tighten up.']
CMD_COLLECTIVE = ['All units, advance.', 'All units, change formation.',
                  'All units, evade.', 'All units, execute.',
                  'All units, form up.', 'Everyone, hold.',
                  'Everyone, scout ahead.', 'Squad, respond to the situation.',
                  'Squad, stand by.', 'Squad, take cover.', 'Team, gather.',
                  'Team, get clear.', 'Team, push forward.', 'Team, reshuffle.']


def cmd_subject(cmd):
    """中性指令 → 确定性的 (mode, uav_ids)。collective 的 formation 训练本身
    一对多（line/wedge/grid 混杂），判定不约束（gold 存 None）。"""
    if cmd.startswith('All units') or cmd.startswith('Everyone') \
            or cmd.startswith('Squad') or cmd.startswith('Team'):
        return 'swarm', [1, 2, 3, 4], None
    lower = cmd.lower()
    ids = [int(t) for t in ''.join(c if c.isdigit() else ' ' for c in lower).split()]
    if len(ids) == 1:
        return 'single-agent', ids, 'free'
    return 'swarm', ids, None


# ---- 相位 → target 的规则映射（与训练数据 100% 同源） ----
def phase_target(label):
    head = label.split('@')[0]
    if head == 'ASSEMBLE':
        x, y = eval(label[len('ASSEMBLE@('):-1])
        return [float(x), float(y), 5.0]
    if head == 'HOLD':
        x, y, z = eval(label[len('HOLD@('):-1])
        return [float(x), float(y), float(z)]
    if head == 'OBSTACLE_AVOID':
        _, side, n = label.split('@')
        n = float(n)
        return [-n if side == 'left' else n, 0.0, 15.0]
    if head == 'RECON':
        x, y = eval(label[len('RECON@('):-1])
        return [float(x), float(y), 15.0]
    if head == 'RECONFIGURE':
        return [15.0, 15.0, 8.0]
    raise ValueError(label)


PHASE_TOL = {  # (x, y, z) 容差，沿用 phase_verify_v4
    'ASSEMBLE': (1, 1, 1), 'HOLD': (1, 1, 1),
    'OBSTACLE_AVOID': (2, 2, 1), 'RECON': (5, 5, 1), 'RECONFIGURE': (2, 2, 1),
}

# ---- 基础集表述模板（模仿训练 109 条的句式风格） ----
SA_VERBS = ['fly to', 'go to', 'proceed to', 'move to', 'head to',
            'navigate to', 'travel to']
SA_CALLS = ['UAV', 'Drone', 'Unit']
SWARM_TEMPLATES = [
    'UAV {ids}, form a {form} formation and move to target coordinates ({x}, {y}, {z}).',
    'Drones {ids}, create a {form} formation going to ({x}, {y}, {z}).',
    'UAV {ids}, assemble into a {form} and head to ({x}, {y}, {z}).',
    'Have UAV {ids} form up in a {form} and proceed to ({x}, {y}, {z}).',
    'UAV {ids}, {form} formation, target ({x}, {y}, {z}).',
]
FORMATION_ADJ = {'triangle': 'triangle', 'line': 'line', 'grid': 'grid',
                 'wedge': 'wedge', 'circle': 'circle'}


def fmt_ids(ids):
    parts = [str(i) for i in ids]
    if len(parts) == 2:
        return ' and '.join(parts)
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


def fmt_num(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def gen_basic(rng):
    items = []

    def coord_in():
        x = round(rng.uniform(-30, 30), 1)
        y = round(rng.uniform(-30, 30), 1)
        z = round(rng.uniform(1, 25), 1)
        if rng.random() < 0.3:   # 三成整数坐标
            x, y, z = int(x), int(y), int(z)
        return x, y, z

    def coord_out():
        # 系统性外推：至少一轴越过训练包围盒（|x|>30.5 / |y|>30 / z>25）
        for _ in range(50):
            x, y, z = coord_in()
            axis = rng.choice(('x', 'y', 'z'))
            if axis == 'x':
                x = round(rng.uniform(31, 60), 1) * rng.choice((1, -1))
            elif axis == 'y':
                y = round(rng.uniform(31, 60), 1) * rng.choice((1, -1))
            else:
                z = round(rng.uniform(26, 40), 1)
            if abs(x) > 30.5 or abs(y) > 30.0 or z > 25.0:
                return x, y, z
        return 45.0, -35.0, 10.0

    # single-agent 90 = in 60 / out 30
    for i in range(90):
        split = 'in' if i < 60 else 'out'
        x, y, z = coord_in() if split == 'in' else coord_out()
        n = rng.randint(1, 5)
        call = rng.choice(SA_CALLS) if n != 3 else 'UAV'   # "Drone 3" 训练少，保守
        verb = rng.choice(SA_VERBS)
        user = f'{call} {n}, {verb} ({fmt_num(x)}, {fmt_num(y)}, {fmt_num(z)}).'
        gold = {'mode': 'single-agent', 'formation': 'free',
                'uav_ids': [n], 'target': [float(x), float(y), float(z)]}
        items.append({'id': f'B-{i+1:03d}', 'kind': 'basic',
                      'category': 'single-agent', 'split': split,
                      'system': INSTRUCTION, 'user': user,
                      'expected': gold, 'subject': None,
                      'judge': {'type': 'exact'}})

    # swarm 150 = 5 阵型 × (in 20 / out 10)
    idx = 90
    for form in ('line', 'triangle', 'grid', 'wedge', 'circle'):
        for j in range(30):
            split = 'in' if j < 20 else 'out'
            x, y, z = coord_in() if split == 'in' else coord_out()
            n_uav = rng.choice((2, 2, 3))
            ids = sorted(rng.sample(range(1, 6), n_uav))
            tpl = rng.choice(SWARM_TEMPLATES)
            user = tpl.format(ids=fmt_ids(ids), form=FORMATION_ADJ[form],
                              x=fmt_num(x), y=fmt_num(y), z=fmt_num(z))
            gold = {'mode': 'swarm', 'formation': form, 'uav_ids': ids,
                    'target': [float(x), float(y), float(z)]}
            items.append({'id': f'B-{idx+1:03d}', 'kind': 'basic',
                          'category': f'swarm-{form}', 'split': split,
                          'system': INSTRUCTION, 'user': user,
                          'expected': gold, 'subject': None,
                          'judge': {'type': 'exact'}})
            idx += 1
    return items


def gen_phase(rng):
    items = []
    idx = 0
    all_cmds = [('single', c) for c in CMD_SINGLE] + \
               [('multi', c) for c in CMD_MULTI] + \
               [('collective', c) for c in CMD_COLLECTIVE]

    def asm_label(kind):
        if kind == 'seen':
            return 'ASSEMBLE@(%d,%d)' % rng.choice(sorted(ASM_SEEN))
        if kind == 'in-range-unseen':
            while True:
                p = (rng.randint(-10, 10), rng.randint(-10, 10))
                if p not in ASM_SEEN:
                    return 'ASSEMBLE@(%d,%d)' % p
        return 'ASSEMBLE@(%d,%d)' % rng.choice(
            [(12, -9), (-12, 15), (18, 0), (0, -20), (25, 25), (-30, 8)])

    def hold_label(kind):
        if kind == 'seen':
            return 'HOLD@(%d,%d,%d)' % rng.choice(sorted(HOLD_SEEN))
        if kind == 'in-range-unseen':
            while True:
                p = (rng.randint(-8, 6), rng.randint(-8, 5), rng.randint(6, 10))
                if p not in HOLD_SEEN:
                    return 'HOLD@(%d,%d,%d)' % p
        return 'HOLD@(%d,%d,%d)' % rng.choice(
            [(3, 2, 12), (-5, 5, 3), (15, 0, 8), (0, -15, 15), (20, 20, 2)])

    def obst_label(kind):
        if kind == 'seen':
            return 'OBSTACLE_AVOID@%s@%d' % rng.choice(sorted(OBST_SEEN))
        if kind == 'in-range-unseen':
            return 'OBSTACLE_AVOID@%s@%d' % (
                rng.choice(('left', 'right')), rng.choice((17, 22, 28, 33, 38)))
        return 'OBSTACLE_AVOID@%s@%d' % (
            rng.choice(('left', 'right')), rng.choice((10, 12, 45, 50, 60)))

    def recon_label(kind):
        if kind == 'seen':
            return 'RECON@(%d,%d)' % rng.choice(sorted(RECON_SEEN))
        if kind == 'in-range-unseen':
            while True:
                p = (rng.randint(62, 228), rng.randint(106, 239))
                if p not in RECON_SEEN:
                    return 'RECON@(%d,%d)' % p
        return 'RECON@(%d,%d)' % rng.choice(
            [(50, 300), (280, 90), (30, 60), (250, 260), (300, 150), (60, 80)])

    makers = {'ASSEMBLE': asm_label, 'HOLD': hold_label,
              'OBSTACLE_AVOID': obst_label, 'RECON': recon_label,
              'RECONFIGURE': lambda kind: 'RECONFIGURE@%s' % rng.choice(RECONF_FORMS)}

    for phase in ('ASSEMBLE', 'HOLD', 'OBSTACLE_AVOID', 'RECON', 'RECONFIGURE'):
        # RECONFIGURE 无数值参数，seen/ood 之分只在队形稀有度上无意义：
        # 统一按 in 处理（40 条 = 5 队形均衡），split 记 'in'
        plan = ([( 'in', 40)] if phase == 'RECONFIGURE'
                else [('seen', 14), ('in-range-unseen', 10), ('ood', 16)])
        for split, n in plan:
            for _ in range(n):
                label = makers[phase](split)
                _, cmd = rng.choice(all_cmds)
                mode, uids, formation = cmd_subject(cmd)
                target = phase_target(label)
                # 训练约定（v5 实测 48 条）：RECONFIGURE@X 的 output formation
                # 在 multi/collective 命令下 = X；single 命令下 = free
                if phase == 'RECONFIGURE':
                    exp_formation = 'free' if formation == 'free' \
                        else label.split('@')[1]
                else:
                    exp_formation = formation
                gold = {'mode': mode, 'formation': exp_formation,
                        'uav_ids': uids, 'target': target}
                tol = PHASE_TOL[phase]
                items.append({
                    'id': f'P-{idx+1:03d}', 'kind': 'phase', 'category': phase,
                    'split': split, 'phase_label': label,
                    'system': f'Phase: {label}. {INSTRUCTION}', 'user': cmd,
                    'expected': gold,
                    'subject': {'mode': mode, 'uav_ids': uids},
                    'judge': {'type': 'tolerant', 'tol': {'x': tol[0], 'y': tol[1],
                                                          'z': tol[2]},
                              'formation_required': phase == 'RECONFIGURE'}})
                idx += 1
    rng.shuffle(items)
    for i, it in enumerate(items, 1):
        it['id'] = f'P-{i:03d}'
    return items


def selftest(items_basic, items_phase):
    errs = []

    def check(cond, msg):
        if not cond:
            errs.append(msg)

    for it in items_basic + items_phase:
        exp = it['expected']
        check(isinstance(exp['uav_ids'], list) and all(isinstance(v, int) for v in exp['uav_ids']),
              f"{it['id']}: uav_ids 类型错")
        check(len(exp['target']) == 3 and all(isinstance(v, float) for v in exp['target']),
              f"{it['id']}: target 类型错")
        check(exp['formation'] is None or exp['formation'] in
              ('free', 'triangle') + RECONF_FORMS, f"{it['id']}: 非法 formation")
        if it['kind'] == 'phase':
            check(validate_phase(it['phase_label']),
                  f"{it['id']}: 相位标签非法 {it['phase_label']}")
            want = phase_target(it['phase_label'])
            check(all(abs(a - b) < 1e-9 for a, b in zip(want, exp['target'])),
                  f"{it['id']}: 金标准 target 与规则不符 {exp['target']} != {want}")
            mode, uids, _ = cmd_subject(it['user'])
            check(exp['mode'] == mode and exp['uav_ids'] == uids,
                  f"{it['id']}: subject 映射错")
            # RECONFIGURE 金标准遵循训练约定：single→free，multi/collective→相位队形
            if it['category'] == 'RECONFIGURE':
                want_form = 'free' if mode == 'single-agent' \
                    else it['phase_label'].split('@')[1]
                check(exp['formation'] == want_form,
                      f"{it['id']}: RECONFIGURE 金标准 formation 应为 {want_form}")

    # split 计数核对
    b_in = sum(1 for i in items_basic if i['split'] == 'in')
    p_seen = sum(1 for i in items_phase if i['split'] == 'seen')
    p_ood = sum(1 for i in items_phase if i['split'] == 'ood')
    p_reconf = sum(1 for i in items_phase if i['category'] == 'RECONFIGURE')
    check(b_in == 160, f'basic in={b_in} != 160')
    # RECONFIGURE 无数值参数，40 条全记 'in'，不参与 seen/ood 计数
    check(p_seen == 56, f'phase seen={p_seen} != 56（4 相位 × 14）')
    check(p_ood == 64, f'phase ood={p_ood} != 64（4 相位 × 16）')
    check(p_reconf == 40, f'RECONFIGURE={p_reconf} != 40')
    # 训练内坐标确实在训练包围盒内
    for it in items_basic:
        if it['split'] == 'in':
            x, y, z = it['expected']['target']
            check(abs(x) <= 30.5 and abs(y) <= 30.0 and z <= 25.0,
                  f"{it['id']}: in 样本越界 {it['expected']['target']}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--sample', type=int, default=0)
    ap.add_argument('--out-dir', default=os.path.join(HERE, 'testsets'))
    args = ap.parse_args()

    rng = random.Random(SEED)
    basic = gen_basic(rng)
    phase = gen_phase(rng)
    errs = selftest(basic, phase)
    if errs:
        print('[selftest] %d 处失败:' % len(errs))
        for e in errs[:20]:
            print('  ' + e)
        sys.exit(1)
    print('[selftest] 全部通过（basic %d + phase %d）' % (len(basic), len(phase)))

    os.makedirs(args.out_dir, exist_ok=True)
    for name, items in (('basic_240.jsonl', basic), ('phase_200.jsonl', phase)):
        path = os.path.join(args.out_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + '\n')
        print('写出 %s（%d 条）' % (path, len(items)))

    if args.sample:
        rng2 = random.Random(SEED + 1)
        for it in rng2.sample(basic, args.sample // 2) + \
                rng2.sample(phase, args.sample - args.sample // 2):
            print('\n[%s|%s|%s] system=%r' % (it['id'], it['category'], it['split'],
                                              it['system'][:60]))
            print('  user: %r' % it['user'])
            print('  gold: %s' % json.dumps(it['expected']))


if __name__ == '__main__':
    main()
