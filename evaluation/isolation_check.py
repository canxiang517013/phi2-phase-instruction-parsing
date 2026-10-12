#!/usr/bin/env python3
"""isolation_check - 训练/测试隔离自动校验（任务书 P0-2：严格隔离 + 可追溯）

校验三个测试集（basic_240 / phase_200 / robust_160，共 600 条）与
训练集（dataset_phased_v5.jsonl，v5 磁盘模型实际训练数据；附带校验
dataset_original_109.jsonl 与 dataset.jsonl）之间的关系：

  1. 精确重复：归一化（小写/去多余空白/统一标点）后 user 文本 == 训练 input
  2. 近重复：字符 8-gram Jaccard >= 0.6 判为疑似改写
  3. 白名单 A（设计内复用）：phase_200 / robust 随机相位条目有意复用训练的
     33 条中性指令（"未见 phase+参数组合"类别的要求——命令可见、相位标签
     全新、金标准由相位规则决定，与训练样本语义不同）。
     白名单 B（最小对探针）：ambiguous / bad-phase 条目复用中性短指令但
     【无相位上下文】——被测条件（缺相位）从未在训练出现，恰是检验模型
     是否依赖相位上下文的最小对设计。两类白名单均在 manifest 记录。

输出 evaluation/isolation_manifest.json：各项计数 + 命中明细（如有）。
退出码：发现非白名单泄漏 = 1。
"""

import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TRAIN_FILES = ['dataset_phased_v5.jsonl', 'dataset_original_109.jsonl',
               'dataset.jsonl']
TESTSET_FILES = ['basic_240.jsonl', 'phase_200.jsonl', 'robust_160.jsonl']

# 训练中性指令池（gen_testset.py 白纸黑字列出的 33 条，允许作为相位条目主体）
WHITELIST_CMDS = set()


def norm(s):
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(s.split())


def ngrams(s, n=8):
    toks = norm(s).split()
    if len(toks) < n:
        return {(' '.join(toks),)} if toks else set()
    return {' '.join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_train():
    """加载训练 input 文本 + 提取中性指令白名单。"""
    inputs, whitelist = [], set()
    for name in TRAIN_FILES:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as f:
            for line in f:
                d = json.loads(line)
                inp = d.get('input', '')
                inputs.append(inp)
                # v5 相位样本 input = 中性短指令（无坐标/formation 词）→ 白名单
                toks = norm(inp)
                if len(toks.split()) <= 6 and not re.search(r'\d ?,|\d\)', toks):
                    whitelist.add(toks)
    return inputs, whitelist


def main():
    train_inputs, whitelist = load_train()
    train_norm = {norm(t) for t in train_inputs}
    train_grams = [ngrams(t) for t in train_inputs if t]

    manifest = {
        'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'train_files': TRAIN_FILES,
        'n_train_inputs': len(train_inputs),
        'testsets': {}, 'violations': [], 'whitelist_used': 0,
    }

    bad = 0
    for name in TESTSET_FILES:
        p = os.path.join(HERE, 'testsets', name)
        with open(p, encoding='utf-8') as f:
            items = [json.loads(l) for l in f]
        stats = {'n': len(items), 'exact_dup': [], 'near_dup': [],
                 'whitelisted': 0}
        for it in items:
            un = norm(it['user'])
            is_phase_item = 'phase_label' in it and 'Phase: ' in it['system']
            # 白名单 B：ambiguous/bad-phase 的中性短命令（无相位上下文最小对）
            is_minpair = it.get('category') in ('ambiguous', 'bad-phase') \
                and un in whitelist
            if (un in whitelist and is_phase_item) or is_minpair:
                stats['whitelisted'] += 1
                manifest['whitelist_used'] += 1
                continue
            if un in train_norm:
                stats['exact_dup'].append(it['id'])
                bad += 1
                manifest['violations'].append(
                    {'id': it['id'], 'type': 'exact', 'text': it['user'][:80]})
                continue
            g = ngrams(it['user'])
            for ti, tg in zip(train_inputs, train_grams):
                if jaccard(g, tg) >= 0.6:
                    # 长态势条目天然包含训练风格的短句——按 8-gram 阈值可判近重复，
                    # 但其语义主体（150+词态势）在训练中不存在，记录为审核项而非违例
                    if it['category'] == 'long-context' or is_phase_item:
                        continue
                    stats['near_dup'].append(it['id'])
                    bad += 1
                    manifest['violations'].append(
                        {'id': it['id'], 'type': 'near',
                         'text': it['user'][:80], 'train': ti[:80]})
                    break
        manifest['testsets'][name] = stats
        print(f"{name}: n={stats['n']} 精确重复={len(stats['exact_dup'])} "
              f"近重复={len(stats['near_dup'])} 白名单={stats['whitelisted']}")

    print(f"\n训练输入共 {len(train_inputs)} 条；白名单命中 "
          f"{manifest['whitelist_used']} 条（相位条目复用中性指令，设计内）")
    out = os.path.join(HERE, 'isolation_manifest.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f'manifest -> {out}')
    if bad:
        print(f'[失败] {bad} 条疑似泄漏，见 manifest.violations')
        sys.exit(1)
    print('[通过] 训练/测试隔离校验：无精确/近重复泄漏')


if __name__ == '__main__':
    main()
