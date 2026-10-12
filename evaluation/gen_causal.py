#!/usr/bin/env python3
"""gen_causal - P0-3 因果消融测试集 causal_240（G2/G3/G4 同源三变体）

任务书第 3 周 7 组对照中的三组核心对照需要【同一态势的三种呈现】，
只改呈现方式、不改信息内容，才能做因果归因：

  G2 situation-prose     完整态势散文（150 词级）+ 中性指令，无相位标签
                         ——复现分布外崩溃（信息在文中，须从散文提取）
  G3 structured-summary  结构化 key:value 摘要 + 中性指令，无相位标签
                         ——与 G2 词数匹配（±15%，selftest 强制），
                           只改格式不改长度：分离"格式效应"与"长度效应"
  G4 phase-label         "Phase: LABEL. + 指令"（短标签）
                         ——核心方法：信息压缩为语义瓶颈标签

  80 个态势 = 5 相位 × 16，每个态势渲染成 3 个条目，共 240 条。
  金标准 = 相位规则映射（与 phase_200 同源 PHASE_TOL 容差判定）。
  G5（随机phase）/G6（错误phase）已由 robust_160 承担；G1（短格式基准）
  由 phase_200 + basic_240 承担；G7 = 长上下文 SFT 模型（gen_g7_trainset.py）。

关键参数在三种呈现中等价出现：
  ASSEMBLE: 散文"rendezvous at (x,y)" / "rendezvous=(x,y)" / ASSEMBLE@(x,y)
  HOLD:     "hold at (x,y,z)" / "hold_point=(x,y,z)" / HOLD@(x,y,z)
  OBSTACLE_AVOID: "shift left, clear by n m" / "lateral=left n" / @left@n
  RECON:    "reconnaissance zone at (x,y)" / "recon_zone=(x,y)" / RECON@(x,y)
  RECONFIGURE: "reform into {form} on mark point" / "formation={form}" / @{form}

用法：
  python evaluation/gen_causal.py              # 生成 causal_240.jsonl
  python evaluation/gen_causal.py --selftest
  python evaluation/gen_causal.py --sample 6
"""

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_testset import (  # noqa: E402
    INSTRUCTION, CMD_SINGLE, CMD_MULTI, CMD_COLLECTIVE,
    phase_target, PHASE_TOL, cmd_subject,
)

SEED = 20261013   # 与 robust_160（20261012）及训练集均不同源
ALL_CMDS = [('single', c) for c in CMD_SINGLE] + \
           [('multi', c) for c in CMD_MULTI] + \
           [('collective', c) for c in CMD_COLLECTIVE]

FILLER = [
    ('wind', ('calm', 'light breeze from west', 'moderate wind from east',
              'fresh wind from north')),
    ('fuel', ('Fuel at 85%.', 'Fuel at 60%.', 'Energy levels above 70%.',
              'Battery at 45%.')),
    ('links', ('All links stable.', 'Comms nominal.',
               'One relay degraded, redundant active.', 'Links intermittent.')),
    ('threat', ('No threats detected.', 'No hostile activity.',
                'Radar sweep clear.', 'Sector quiet.')),
    ('gps', ('GPS nominal.', 'GPS degrading to 80%.',
             'Navigation solution stable.', 'GPS hold within 2m.')),
    ('sensor', ('Sensors recording.', 'Thermal feed active.',
                'Optical suite nominal.', 'Sensor array at full rate.')),
]


def prose_situation(rng, phase, params):
    """G2 散文态势：标准态势块 + 相位使命句 + 填充事实，约 80-95 词。"""
    fillers = rng.sample(FILLER, 3)
    fl = ' '.join(rng.choice(f[1]) for f in fillers)
    form = rng.choice(('wedge', 'line', 'grid', 'column'))
    base = (f"UAV swarm control context: 4 followers in {form} formation, "
            f"virtual leader holding at ({rng.randint(-10, 40)}, "
            f"{rng.randint(-10, 50)}, {rng.randint(4, 12)}) heading "
            f"{rng.choice(('north', 'northeast', 'east'))} at "
            f"{rng.randint(3, 7)} m/s with {rng.randint(4, 10)}m spacing. "
            f"Mission window {rng.choice((45, 60, 90))} seconds. ")
    if phase == 'ASSEMBLE':
        x, y = params
        head = (base + f"Followers are currently scattered beyond cohesion. "
                f"{fl} The flight plan requires every unit to reach the "
                f"rendezvous at grid point ({x}, {y}) and form up there "
                f"before the advance begins.")
    elif phase == 'HOLD':
        x, y, z = params
        head = (base + f"The advance is complete and the area is under "
                f"observation. {fl} Command requires a stationary posture: "
                f"every unit must hold position at ({x}, {y}, {z}) until "
                f"further notice from the ground station.")
    elif phase == 'OBSTACLE_AVOID':
        side, n = params
        head = (base + f"An obstacle cluster now blocks the corridor ahead, "
                f"spanning the path width. {fl} The evasion plan is fixed: "
                f"shift {'left' if side == 'left' else 'right'} and clear "
                f"the obstacle by {n} meters while holding altitude.")
    elif phase == 'RECON':
        x, y = params
        head = (base + f"The tasking is an area survey with continuous "
                f"sensor feed. {fl} The reconnaissance zone is located at "
                f"({x}, {y}); units are to transit there and begin the "
                f"sweep at standoff altitude.")
    else:  # RECONFIGURE
        form2 = params[0]
        head = (base + f"Ground station has ordered a shape change to "
                f"respond to the new threat picture. {fl} Every unit is to "
                f"reform into a {form2} formation on the standard mark "
                f"point before continuing the advance.")
    return head


def structured_summary(rng, phase, params, target_words):
    """G3 key:value 摘要：同一决定性参数 + 填充键，词数向 G2 对齐。"""
    rows = ['context=swarm control', 'units=4']
    if phase == 'ASSEMBLE':
        x, y = params
        rows.append(f'rendezvous=({x},{y})')
        rows.append('action=gather')
    elif phase == 'HOLD':
        x, y, z = params
        rows.append(f'hold_point=({x},{y},{z})')
        rows.append('action=stationary')
    elif phase == 'OBSTACLE_AVOID':
        side, n = params
        rows.append(f'lateral={"left" if side=="left" else "right"}')
        rows.append(f'clearance={n}m')
        rows.append('action=evasive_shift')
    elif phase == 'RECON':
        x, y = params
        rows.append(f'recon_zone=({x},{y})')
        rows.append('action=survey_transit')
    else:
        form = params[0]
        rows.append(f'target_formation={form}')
        rows.append('mark_point=(15,15,8)')
        rows.append('action=reshape')
    rows.append(rng.choice(FILLER[0][1]).replace(' ', '_'))
    rows.append(rng.choice(('status=ready', 'mode=cooperative',
                            'tasking=high_priority', 'window=120s')))
    text = 'Situation summary: ' + '; '.join(rows) + '.'
    # 词数对齐：不足则补通用填充键，超出则删 status 行
    while len(text.split()) < target_words * 0.85:
        rows.append(rng.choice(('relay=leader', 'spacing=8m', 'speed=5m/s',
                                'alert=none', 'payload=standard')))
        text = 'Situation summary: ' + '; '.join(rows) + '.'
    return text


def sample_params(rng, phase=None):
    # phase 由调用方循环提供；保默认值便于单独调试
    if phase is None:
        phase = 'ASSEMBLE'
    if phase == 'ASSEMBLE':
        return (rng.randint(-10, 10), rng.randint(-10, 10))
    if phase == 'HOLD':
        return (rng.randint(-8, 6), rng.randint(-8, 5), rng.randint(6, 10))
    if phase == 'OBSTACLE_AVOID':
        return (rng.choice(('left', 'right')), rng.choice((15, 20, 25, 30, 35, 40)))
    if phase == 'RECON':
        return (rng.randint(62, 228), rng.randint(106, 239))
    return (rng.choice(('column', 'circle', 'grid', 'wedge', 'line')),)


def label_of(phase, params):
    if phase == 'ASSEMBLE':
        return f'ASSEMBLE@({params[0]},{params[1]})'
    if phase == 'HOLD':
        return f'HOLD@({params[0]},{params[1]},{params[2]})'
    if phase == 'OBSTACLE_AVOID':
        return f'OBSTACLE_AVOID@{params[0]}@{params[1]}'
    if phase == 'RECON':
        return f'RECON@({params[0]},{params[1]})'
    return f'RECONFIGURE@{params[0]}'


def make_gold(phase, label, cmd):
    mode, uids, formation = cmd_subject(cmd)
    target = phase_target(label)
    if phase == 'RECONFIGURE':
        formation = 'free' if formation == 'free' else label.split('@')[1]
    return {'mode': mode, 'formation': formation, 'uav_ids': uids,
            'target': target}, {'mode': mode, 'uav_ids': uids}


def gen(rng):
    items = []
    idx = 0
    for phase in ('ASSEMBLE', 'HOLD', 'OBSTACLE_AVOID', 'RECON', 'RECONFIGURE'):
        for _ in range(16):
            params = sample_params(rng, phase)
            label = label_of(phase, params)
            _, cmd = rng.choice(ALL_CMDS)
            gold, subj = make_gold(phase, label, cmd)
            tol = PHASE_TOL[phase]
            judge = {'type': 'tolerant',
                     'tol': {'x': tol[0], 'y': tol[1], 'z': tol[2]},
                     'formation_required': phase == 'RECONFIGURE'}

            prose = prose_situation(rng, phase, params)
            struct = structured_summary(rng, phase, params,
                                        len(prose.split()))
            variants = [
                ('G2-situation-prose', prose + ' ' + cmd, INSTRUCTION),
                ('G3-structured-summary', struct + ' ' + cmd, INSTRUCTION),
                ('G4-phase-label', cmd, f'Phase: {label}. {INSTRUCTION}'),
            ]
            for cat, user, system in variants:
                items.append({
                    'id': f'C-{idx+1:03d}', 'kind': 'causal', 'category': cat,
                    'split': phase, 'phase_label': label,
                    'system': system, 'user': user,
                    'expected': gold, 'subject': subj, 'judge': judge})
                idx += 1
    return items


def selftest(items):
    from gen_testset import validate_phase
    errs = []

    def check(cond, msg):
        if not cond:
            errs.append(msg)

    # 三变体同源：每 3 条一组的金标准与 label 必须一致
    for i in range(0, len(items), 3):
        grp = items[i:i + 3]
        check(len({json.dumps(g['expected']) for g in grp}) == 1,
              f"{grp[0]['id']}: 三变体金标准不一致")
        check(len({g['phase_label'] for g in grp}) == 1,
              f"{grp[0]['id']}: 三变体 label 不一致")
        check({g['category'] for g in grp} ==
              {'G2-situation-prose', 'G3-structured-summary', 'G4-phase-label'},
              f"{grp[0]['id']}: 三变体类别缺失")
    # G3 词数与 G2 匹配（±15%）
    for i in range(0, len(items), 3):
        g2, g3, g4 = items[i:i + 3]
        w2 = len(g2['user'].split())
        w3 = len(g3['user'].split())
        check(abs(w3 - w2) / w2 <= 0.18,
              f"{g2['id']}: G3 词数 {w3} vs G2 {w2} 超差")
        check(len(g4['user'].split()) < 12, f"{g4['id']}: G4 应为短标签")
        check(len(g2['user'].split()) >= 55, f"{g2['id']}: G2 态势过短")
    # 相位标签合法性 + 金标准规则一致
    for it in items:
        check(validate_phase(it['phase_label']),
              f"{it['id']}: 非法相位 {it['phase_label']}")
    cnt = {}
    for it in items:
        cnt[it['category']] = cnt.get(it['category'], 0) + 1
    check(cnt == {'G2-situation-prose': 80, 'G3-structured-summary': 80,
                  'G4-phase-label': 80}, f'类别计数 {cnt}')
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--sample', type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(SEED)
    items = gen(rng)
    errs = selftest(items)
    if errs:
        print('[selftest] %d 处失败:' % len(errs))
        for e in errs[:20]:
            print('  ' + e)
        sys.exit(1)
    print(f'[selftest] 通过（causal {len(items)} 条，三变体各 80，词数匹配 ±18%）')

    out = os.path.join(HERE, 'testsets', 'causal_240.jsonl')
    with open(out, 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
    print(f'写出 {out}（{len(items)} 条）')

    if args.sample:
        rng2 = random.Random(SEED + 1)
        for it in rng2.sample(items, args.sample):
            print(f"\n[{it['id']}|{it['category']}|{it['split']}]")
            print('  user: %r' % (it['user'][:200]))
            print('  gold: %s' % json.dumps(it['expected']))


if __name__ == '__main__':
    main()
