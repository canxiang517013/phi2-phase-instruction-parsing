#!/usr/bin/env python3
"""p0_deep_dive - P0-2 结果深度解剖：从指标反查代码与设计根因

逐项回答：
  Q1  target-z 主导失败（79-104/200）到底错在哪？→ 按相位分解期望 z vs 实际 z
  Q2  Q5_K_M basic 的 mode=4 翻转是什么模式混淆？
  Q3  盒内未见 < 盒外(ood) 的反直觉从哪来？→ 内插失败 vs 极端直传
  Q4  越界指令的输出是精确回声还是变形？缺字段捏造的坐标从哪来？
  Q5  长态势 0/30：模型输出什么？坐标是否抄自态势文本中的数字？
  Q6  随机相位跨域参数是否被钳制回训练盒？（记忆盒 vs 规则映射之辨）
  Q7  FP16 vs Q8 的 17 条分歧是什么条目？
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, 'results_v2')
sys.path.insert(0, HERE)
from eval_run import try_json  # noqa: E402


def load(label, ts):
    with open(os.path.join(RES, f'{label}_{ts}_results.jsonl'), encoding='utf-8') as f:
        return [json.loads(l) for l in f]


def got_target(r):
    g = try_json(r['got'])
    if isinstance(g, dict) and isinstance(g.get('target'), list) and len(g['target']) == 3:
        try:
            return [float(v) for v in g['target']]
        except (TypeError, ValueError):
            return None
    return None


def got_field(r, key):
    g = try_json(r['got'])
    return g.get(key) if isinstance(g, dict) else None


def nums_in_text(text):
    return [int(v) for v in re.findall(r'-?\d+', text)]


print('=' * 72)
print('Q1  phase 失败的 z 轴解剖（v5-Q8_0，按相位：期望z -> 实际z 分布）')
print('=' * 72)
rows = load('v5-Q8_0', 'phase')
zmap = defaultdict(Counter)
for r in rows:
    t = got_target(r)
    if t is None:
        zmap[r['split']]['<unparseable>'] += 1
        continue
    ez, gz = r['expected']['target'][2], t[2]
    ok = r['correct']
    zmap[r['split']][f'z:{ez}->{gz}' + ('' if ok else ' ✗')] += 1
for ph in ('ASSEMBLE', 'HOLD', 'OBSTACLE_AVOID', 'RECON', 'RECONFIGURE'):
    print(f'--- {ph} ---')
    for k, v in sorted(zmap[ph].items(), key=lambda x: -x[1])[:6]:
        print(f'  {k:<28} {v}')

print()
print('=' * 72)
print('Q2  Q5_K_M basic 的失败明细（mode 翻转成什么）')
print('=' * 72)
for r in load('v5-Q5_K_M', 'basic'):
    if not r['correct']:
        print(f"  {r['id']} [{r['category']}/{r['split']}] {r['reason']}: "
              f"got mode={got_field(r,'mode')!r} ids={got_field(r,'uav_ids')!r} "
              f"tgt={got_target(r)} | 期望 mode={r['expected']['mode']} "
              f"ids={r['expected']['uav_ids']} | {r['user'][:60]}")

print()
print('=' * 72)
print('Q3  盒内未见 vs 盒外（v5-Q8_0 phase，误差方向：直传 or 收缩到训练值）')
print('=' * 72)
for split in ('seen', 'in-range-unseen', 'ood'):
    sub = [r for r in rows if r['split'] == split]
    k = sum(1 for r in sub if r['correct'])
    echo = clamp = 0
    for r in sub:
        if r['split'] == 'seen':
            continue
        t = got_target(r)
        e = r['expected']['target']
        if t is None:
            continue
        # 直传：首轴误差<=容差；收缩：输出显著更接近训练盒中心
        if abs(t[0] - e[0]) <= 5 and abs(t[1] - e[1]) <= 5:
            echo += 1
        elif abs(t[0]) <= 12 and abs(e[0]) > 12:
            clamp += 1
    print(f'  {split:<16} acc={k}/{len(sub)} ({k/len(sub)*100:.0f}%)  '
          f'数值直传≈{echo}  收缩回训练盒≈{clamp}')

print()
print('=' * 72)
print('Q4a 越界指令输出解剖（v5-Q6_K robust out-of-envelope）')
print('=' * 72)
for r in load('v5-Q6_K', 'robust'):
    if r['category'] == 'out-of-envelope' and r['behavior'] == 'dangerous':
        t = got_target(r)
        instr_nums = nums_in_text(r['user'])
        exact = t == [float(v) for v in instr_nums[1:4]] if t and len(instr_nums) >= 4 else False
        print(f"  {r['id']} [{r['split']}] 指令{instr_nums[1:4]} -> 输出{t} "
              f"{'精确回声' if exact else '变形'}")

print()
print('=' * 72)
print('Q4b 缺字段捏造解剖（v5-Q6_K missing-field：捏造值来源猜测）')
print('=' * 72)
for r in load('v5-Q6_K', 'robust'):
    if r['category'] == 'missing-field':
        t = got_target(r)
        mode = got_field(r, 'mode')
        ids = got_field(r, 'uav_ids')
        print(f"  {r['id']} [{r['split']}] {r['user'][:45]!r} -> "
              f"mode={mode} ids={ids} tgt={t}")

print()
print('=' * 72)
print('Q5  长态势失败解剖（v5-Q6_K：输出坐标 vs 态势文本中的数字）')
print('=' * 72)
lc = [r for r in load('v5-Q6_K', 'robust') if r['category'] == 'long-context']
for r in lc[:8]:
    t = got_target(r)
    cands = nums_in_text(r['user'])
    exp = r['expected']['target']
    hit = ''
    if t:
        for c in set(cands):
            if abs(t[0] - c) < 1 or abs(t[1] - c) < 1:
                hit = f' 命中态势数字{c}'
                break
    print(f"  {r['id']} 期望{[int(v) for v in exp]} 输出{t}{hit} "
          f"| schema_ok={r['schema_ok']}")

print()
print('=' * 72)
print('Q6  随机相位跨域参数解剖（v5-Q6_K：是否钳制回训练盒）')
print('=' * 72)
rp = [r for r in load('v5-Q6_K', 'robust') if r['category'] == 'random-phase']
clamp_cnt = follow = other = 0
examples = []
for r in rp:
    t = got_target(r)
    e = r['expected']['target']
    if t is None:
        continue
    if abs(t[0] - e[0]) <= 5 and abs(t[1] - e[1]) <= 5:
        follow += 1
    elif abs(t[0]) <= 12 and abs(t[1]) <= 12:
        clamp_cnt += 1
        if len(examples) < 5:
            examples.append(f"  {r['id']} {r['phase_label']}: 期望{[int(v) for v in e]} "
                            f"输出{[int(v) for v in t]}（钳回±12盒内）")
    else:
        other += 1
print(f'  30 条中：规则跟随(±5容差)={follow}  钳回训练盒={clamp_cnt}  其他={other}')
for e in examples:
    print(e)

print()
print('=' * 72)
print('Q7  FP16 vs Q8_0 的 phase 分歧条目（FP16 错 Q8 对的 17 条）')
print('=' * 72)
q8 = {r['id']: r for r in load('v5-Q8_0', 'phase')}
fp = {r['id']: r for r in load('v5-FP16', 'phase')}
by_phase = Counter()
by_reason = Counter()
for i, r in fp.items():
    if not r['correct'] and q8[i]['correct']:
        by_phase[r['split']] += 1
        by_reason[r['reason']] += 1
        t = got_target(r)
print(f'  按相位: {dict(by_phase)}')
print(f'  按原因: {dict(by_reason)}')
for i, r in list(fp.items()):
    if not r['correct'] and q8[i]['correct'] and by_reason.get('target-z', 0) > 0:
        t = got_target(r)
        ez = r['expected']['target'][2]
        print(f"  例 {i} [{r['split']}] 期望z={ez} 输出z={t[2] if t else '?'}")
        by_reason['target-z'] -= 1
        if by_reason.get('target-z', 0) <= 0:
            break
