#!/usr/bin/env python3
"""gen_g7_trainset - G7 长上下文 SFT 训练集（P0-3）

假设：v5 在完整态势（G2）上的 0/80 崩溃源于训练分布不匹配（短输入），
而非 2.7B 模型的长文本能力不足。G7 = 在 v5 数据上追加长态势样本重训，
若 G2 恢复 → 分布不匹配（可训练修复）；若仍崩溃 → 能力上限。

设计要点（单因素）：
  - 仅追加【散文态势】样本（G2 同分布），不混入结构化摘要——G3 的恢复
    情况作为迁移测试而非训练目标
  - 参数与 causal_240 评测集【显式不相交】（从 causal 文件反读参数集，
    采样时剔除，保证 G2 评测仍是分布外的新态势）
  - 样本格式与 dataset_phased_v5.jsonl 完全一致（instruction/input/output），
    input = 态势散文 + ' ' + 中性指令（与 G2 评测同构）

输出：
  g7_long_120.jsonl     追加的 120 条（审计用）
  dataset_v6lc.jsonl    = v5 全量 726 条 + 120 条长样本（训练入口）
"""

import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from gen_causal import (  # noqa: E402  同构生成器，保证分布一致
    sample_params, label_of, prose_situation, make_gold,
)
from gen_testset import INSTRUCTION, CMD_SINGLE, CMD_MULTI, CMD_COLLECTIVE  # noqa: E402

SEED = 20261014
N_LONG = 120


def causal_params_used():
    """从 causal_240.jsonl 反读已用参数（按相位标签），保证不相交。"""
    used = set()
    p = os.path.join(HERE, 'testsets', 'causal_240.jsonl')
    with open(p, encoding='utf-8') as f:
        for line in f:
            it = json.loads(line)
            if it['category'] == 'G4-phase-label':
                used.add(it['phase_label'])
    return used


def wide_params(rng, phase):
    """G7 训练参数：比 causal 评测更宽的盒内空间（评测参数仍不可见）。
    RECONFIGURE 为 5 类别变量，无法数值不相交，按类别豁免（金标准 target
    恒 (15,15,8)，formation 集合本就是全空间）。"""
    if phase == 'ASSEMBLE':
        return (rng.randint(-12, 12), rng.randint(-12, 12))
    if phase == 'HOLD':
        return (rng.randint(-9, 7), rng.randint(-9, 6), rng.randint(5, 11))
    if phase == 'OBSTACLE_AVOID':
        return (rng.choice(('left', 'right')),
                rng.choice((16, 17, 18, 22, 23, 24, 26, 27, 28,
                            32, 33, 34, 36, 37, 38)))
    if phase == 'RECON':
        return (rng.randint(55, 235), rng.randint(100, 245))
    return (rng.choice(('column', 'circle', 'grid', 'wedge', 'line')),)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=N_LONG)
    args = ap.parse_args()

    used = causal_params_used()
    rng = random.Random(SEED)
    all_cmds = CMD_SINGLE + CMD_MULTI + CMD_COLLECTIVE
    samples = []
    tries = 0
    while len(samples) < args.n:
        tries += 1
        phase = ['ASSEMBLE', 'HOLD', 'OBSTACLE_AVOID', 'RECON',
                 'RECONFIGURE'][len(samples) % 5]   # 均衡相位
        params = wide_params(rng, phase)
        label = label_of(phase, params)
        # 数值相位：与评测参数不相交；RECONFIGURE 类别变量豁免（5 类全空间）
        if phase != 'RECONFIGURE' and label in used:
            if tries > 20000:
                sys.exit('参数空间不足，无法与评测集不相交')
            continue
        used.add(label)
        cmd = rng.choice(all_cmds)
        gold, _ = make_gold(phase, label, cmd)
        output = json.dumps(gold, ensure_ascii=False)
        samples.append({'instruction': INSTRUCTION,
                        'input': prose_situation(rng, phase, params) + ' ' + cmd,
                        'output': output})

    out_long = os.path.join(ROOT, 'datasets', 'g7_long_120.jsonl')
    with open(out_long, 'w', encoding='utf-8') as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    v5 = os.path.join(ROOT, 'datasets', 'dataset_phased_v5.jsonl')
    with open(v5, encoding='utf-8') as f:
        v5_lines = f.readlines()
    out_train = os.path.join(ROOT, 'datasets', 'dataset_v6lc.jsonl')
    with open(out_train, 'w', encoding='utf-8') as f:
        f.writelines(v5_lines)
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    words = sum(len(s['input'].split()) for s in samples) / len(samples)
    print(f'长样本 {len(samples)} 条（平均 {words:.0f} 词），相位均衡，'
          f'与 causal_240 参数零交集（剔除 {tries - len(samples)} 次冲突）')
    print(f'训练集 {out_train} = v5 {len(v5_lines)} + long {len(samples)}')
    print(f'审计副本 {out_long}')


if __name__ == '__main__':
    main()
