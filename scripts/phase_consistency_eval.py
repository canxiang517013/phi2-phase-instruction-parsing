#!/usr/bin/env python3
"""phase_consistency_eval - 规则引擎 vs 云端 LLM 相位推断一致性评测（离线，无 ROS）

用途（论文三产出的数据来源）：
  1. 延迟/成本实测   —— 每次 LLM 调用的延迟分布、token 用量、成本估算
  2. 解析可靠性      —— 首次成功率 / 重试后成功率 / 失败率的漏斗
  3. 一致性对比      —— 规则引擎 vs LLM 逐条对照 + 分歧案例明细
                        + 隐式语义类金标准准确率（"LLM 必要性"证据）

用法（Windows，项目 .venv 或任意 Python 3.10+，纯 stdlib）：
  # 冒烟（5 条，验证 key 与通路）
  python scripts/phase_consistency_eval.py --provider deepseek --n 5
  # 全量 + 两家横向对比 + 确定性检查（temp=0 每条重复 3 次）
  export DEEPSEEK_API_KEY=sk-xxx GLM_API_KEY=xxx
  python scripts/phase_consistency_eval.py --provider all --repeat 3
  # 不调 API，只验证 harness 与规则引擎基线
  python scripts/phase_consistency_eval.py --dry-run

输出（--out-dir，默认 ./eval_out）：
  phase_consistency_results.csv   逐条明细（长表，方便 pandas 分析）
  phase_consistency_report.md     汇总报告（一致性/准确率/延迟/成本/分歧表）
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phase_rules import (DEFAULT_PHASE, llm_infer_phase, phase_type,  # noqa: E402
                         rule_infer, validate_phase)

# 与 cloud_phase_generator.PROVIDERS 保持一致（改预设时两处同步）
PROVIDERS = {
    'deepseek': {
        'base_url': 'https://api.deepseek.com/v1',
        'model': 'deepseek-chat',
        'key_env': 'DEEPSEEK_API_KEY',
    },
    'glm': {
        'base_url': 'https://open.bigmodel.cn/api/paas/v4',
        'model': 'glm-4-flash',
        'key_env': 'GLM_API_KEY',
    },
    'local': {
        'base_url': 'http://127.0.0.1:8080/v1',
        'model': 'phi2-phased-v5-q5_k_m.gguf',
        'key_env': None,
    },
}

# 价格常量（人民币元/百万 token；官网调价后更新此处，报告中标注为估算）
PRICES = {
    'deepseek': {'in': 2.0, 'out': 3.0},
    'glm': {'in': 0.0, 'out': 0.0},   # glm-4-flash 免费档
    'local': {'in': 0.0, 'out': 0.0},
}


def percentile(vals, q):
    s = sorted(vals)
    if not s:
        return 0.0
    return s[int(round(q * (len(s) - 1)))]


def load_testset(path, n_limit, categories):
    with open(path, encoding='utf-8') as f:
        items = json.load(f)
    if categories:
        items = [it for it in items if it['category'] in categories]
    if n_limit:
        items = items[:n_limit]
    return items


def resolve_providers(names):
    if names == 'all':
        names = 'deepseek,glm'
    out = []
    for name in names.split(','):
        name = name.strip().lower()
        if not name:
            continue
        if name not in PROVIDERS:
            sys.exit('未知 provider: %s（可选 %s/all）' % (name, '/'.join(PROVIDERS)))
        cfg = dict(PROVIDERS[name])
        cfg['name'] = name
        key_env = cfg.get('key_env')
        cfg['api_key'] = os.environ.get('CLOUD_LLM_API_KEY', '') or \
            (os.environ.get(key_env, '') if key_env else '')
        out.append(cfg)
    return out


def eval_one_llm(cfg, item, args):
    """单条态势 × 单个 LLM provider：重复 repeat 次，返回逐次结果列表。"""
    runs = []
    for _ in range(args.repeat):
        phase, info = llm_infer_phase(
            cfg['base_url'], cfg['model'], cfg['api_key'], item['text'],
            timeout=args.timeout, max_tokens=args.max_tokens,
            temperature=args.temperature)
        runs.append({'phase': phase, 'info': info})
        if args.repeat > 1:
            time.sleep(0.2)   # 温和限速
    return runs


def gold_match(phase, expected):
    """金标准匹配两级：精确串匹配 / 相位类型匹配（参数容差）。"""
    if not expected:
        return None, None
    exact = (phase == expected)
    ptype = (phase_type(phase) == phase_type(expected)) if phase else False
    return exact, ptype


def build_rows(items, providers, args):
    """长表行：规则引擎 1 行 + 每个 provider 的每次运行 1 行。"""
    rows = []
    for i, item in enumerate(items, 1):
        rule_phase = rule_infer(item['text'])
        rows.append({
            'id': item['id'], 'category': item['category'],
            'situation': item['text'][:80],
            'expected_phase': item.get('expected_phase', ''),
            'engine': 'rule', 'phase': rule_phase,
            'latency_ms': '', 'attempts': '', 'parse_stage': '',
            'prompt_tokens': '', 'completion_tokens': '', 'error': '',
        })
        if args.dry_run:
            print('[%2d/%d] %s rule=%s（dry-run 跳过 LLM）'
                  % (i, len(items), item['id'], rule_phase))
            continue

        for cfg in providers:
            runs = eval_one_llm(cfg, item, args)
            for run in runs:
                info = run['info']
                rows.append({
                    'id': item['id'], 'category': item['category'],
                    'situation': item['text'][:80],
                    'expected_phase': item.get('expected_phase', ''),
                    'engine': cfg['name'], 'phase': run['phase'] or '',
                    'latency_ms': sum(info.get('latencies_ms', [])),
                    'attempts': info.get('attempts', 0),
                    'parse_stage': info.get('parse_stage', ''),
                    'prompt_tokens': info.get('prompt_tokens', 0),
                    'completion_tokens': info.get('completion_tokens', 0),
                    'error': '; '.join(info.get('errors', []))[:120],
                })
            print('[%2d/%d] %s %-8s llm=%s (%.0fms)'
                  % (i, len(items), item['id'], cfg['name'],
                     runs[-1]['phase'] or 'FAILED',
                     sum(runs[-1]['info'].get('latencies_ms', []))))
    return rows


def write_csv(rows, path):
    cols = ['id', 'category', 'situation', 'expected_phase', 'engine', 'phase',
            'latency_ms', 'attempts', 'parse_stage', 'prompt_tokens',
            'completion_tokens', 'error']
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def engine_stats(rows, items, engine):
    """单个 engine 的汇总统计 dict。"""
    eng_rows = [r for r in rows if r['engine'] == engine]
    rule_rows = [r for r in rows if r['engine'] == 'rule']
    rule_by_id = {r['id']: r['phase'] for r in rule_rows}

    lats = [r['latency_ms'] for r in eng_rows if r['latency_ms'] != '']
    stages = [r['parse_stage'] for r in eng_rows]
    tok_in = sum(r['prompt_tokens'] for r in eng_rows if r['prompt_tokens'] != '')
    tok_out = sum(r['completion_tokens'] for r in eng_rows
                  if r['completion_tokens'] != '')

    # 一致性 / 金标准（有金标准的子集上）
    agree, gold_n, gold_exact, gold_type = 0, 0, 0, 0
    per_cat_agree, per_cat_n = {}, {}
    for r in eng_rows:
        rule_phase = rule_by_id.get(r['id'])
        if rule_phase is not None and r['phase']:
            if r['phase'] == rule_phase:
                agree += 1
            per_cat_n[r['category']] = per_cat_n.get(r['category'], 0) + 1
            if r['phase'] == rule_phase:
                per_cat_agree[r['category']] = per_cat_agree.get(r['category'], 0) + 1
        if r['expected_phase'] and r['phase']:
            gold_n += 1
            exact, ptype = gold_match(r['phase'], r['expected_phase'])
            gold_exact += bool(exact)
            gold_type += bool(ptype)

    n_cmp = sum(1 for r in eng_rows if r['phase'] and r['id'] in rule_by_id)
    price = PRICES.get(engine, PRICES['local'])
    return {
        'engine': engine,
        'n_rows': len(eng_rows),
        'parse_first': stages.count('first'),
        'parse_retry': stages.count('after_retry'),
        'parse_failed': stages.count('failed'),
        'lat_mean': sum(lats) / len(lats) if lats else 0.0,
        'lat_p50': percentile(lats, 0.5),
        'lat_p95': percentile(lats, 0.95),
        'lat_max': max(lats) if lats else 0.0,
        'tok_in': tok_in, 'tok_out': tok_out,
        'cost_cny': tok_in / 1e6 * price['in'] + tok_out / 1e6 * price['out'],
        'agree': agree, 'n_cmp': n_cmp,
        'per_cat_agree': per_cat_agree, 'per_cat_n': per_cat_n,
        'gold_n': gold_n, 'gold_exact': gold_exact, 'gold_type': gold_type,
    }


def rule_gold_stats(rows, items):
    """规则引擎在有金标准子集上的准确率。"""
    rule_rows = {r['id']: r for r in rows if r['engine'] == 'rule'}
    n = exact = ptype = 0
    for it in items:
        expected = it.get('expected_phase')
        if not expected:
            continue
        phase = rule_rows[it['id']]['phase']
        n += 1
        e, p = gold_match(phase, expected)
        exact += bool(e)
        ptype += bool(p)
    return {'n': n, 'exact': exact, 'type': ptype}


def determinism_stats(rows, engine):
    """同一条态势多次运行的一致率（--repeat > 1 时有意义）。"""
    eng = [r for r in rows if r['engine'] == engine and r['phase']]
    by_id = {}
    for r in eng:
        by_id.setdefault(r['id'], []).append(r['phase'])
    if not by_id:
        return None
    total = 0
    for phases in by_id.values():
        if len(phases) < 2:
            continue
        best = max(phases.count(p) for p in set(phases))
        total += best / len(phases)
    n_multi = sum(1 for v in by_id.values() if len(v) >= 2)
    return {'rate': total / n_multi if n_multi else 1.0, 'n': n_multi}


def disagreement_rows(rows, engine):
    """rule != llm 的分歧案例（研究素材核心）。"""
    rule_by_id = {r['id']: r['phase'] for r in rows if r['engine'] == 'rule'}
    seen = set()
    out = []
    for r in rows:
        if r['engine'] != engine or not r['phase']:
            continue
        if r['id'] in seen:
            continue
        rule_phase = rule_by_id.get(r['id'])
        if rule_phase and r['phase'] != rule_phase:
            seen.add(r['id'])
            out.append({'id': r['id'], 'category': r['category'],
                        'situation': r['situation'], 'rule': rule_phase,
                        'llm': r['phase'],
                        'expected': r['expected_phase'] or '-'})
    return out


def write_report(path, items, rows, providers, args):
    lines = []
    a = lines.append
    a('# 规则引擎 vs 云端 LLM 相位推断一致性报告')
    a('')
    a('- 生成时间：%s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    a('- 态势数：%d（%s）' % (
        len(items),
        ', '.join('%s=%d' % (c, sum(1 for i in items if i['category'] == c))
                  for c in ('explicit', 'implicit', 'ambiguous', 'bilingual')
                  if any(i['category'] == c for i in items))))
    a('- 对比引擎：%s | temperature=%s | repeat=%d | timeout=%ss'
      % ('/'.join(p['name'] for p in providers), args.temperature,
         args.repeat, args.timeout))
    a('')

    # 规则引擎金标准基线
    rg = rule_gold_stats(rows, items)
    a('## 规则引擎基线（金标准子集）')
    a('')
    a('| 有金标准的态势 | 精确匹配 | 类型匹配 |')
    a('|---|---|---|')
    a('| %d | %d (%.0f%%) | %d (%.0f%%) |' % (
        rg['n'], rg['exact'], 100 * rg['exact'] / max(rg['n'], 1),
        rg['type'], 100 * rg['type'] / max(rg['n'], 1)))
    a('')

    for cfg in providers:
        s = engine_stats(rows, items, cfg['name'])
        a('## %s（%s）' % (cfg['name'], cfg['model']))
        a('')
        a('| 指标 | 值 |')
        a('|---|---|')
        a('| 解析漏斗 | 首次成功 %d / 重试后成功 %d / 失败 %d |' % (
            s['parse_first'], s['parse_retry'], s['parse_failed']))
        a('| 延迟 ms | mean=%.0f p50=%.0f p95=%.0f max=%.0f |' % (
            s['lat_mean'], s['lat_p50'], s['lat_p95'], s['lat_max']))
        a('| token | 输入 %d / 输出 %d（成本估算 ¥%.4f） |' % (
            s['tok_in'], s['tok_out'], s['cost_cny']))
        if s['n_cmp']:
            a('| 与规则引擎一致 | %d/%d (%.0f%%) |' % (
                s['agree'], s['n_cmp'], 100 * s['agree'] / s['n_cmp']))
            for cat in ('explicit', 'implicit', 'ambiguous', 'bilingual'):
                n = s['per_cat_n'].get(cat)
                if n:
                    a('| · %s 一致 | %d/%d (%.0f%%) |' % (
                        cat, s['per_cat_agree'].get(cat, 0), n,
                        100 * s['per_cat_agree'].get(cat, 0) / n))
        if s['gold_n']:
            a('| 金标准（n=%d） | 精确 %d (%.0f%%) / 类型 %d (%.0f%%) |' % (
                s['gold_n'], s['gold_exact'], 100 * s['gold_exact'] / s['gold_n'],
                s['gold_type'], 100 * s['gold_type'] / s['gold_n']))
        det = determinism_stats(rows, cfg['name'])
        if det and det['n']:
            a('| 确定性（重复运行） | %.0f%%（%d 条 × %d 次） |' % (
                det['rate'] * 100, det['n'], args.repeat))
        a('')

        dis = disagreement_rows(rows, cfg['name'])
        if dis:
            a('### 与规则引擎的分歧案例（%d 条）' % len(dis))
            a('')
            a('| id | 类别 | 态势 | 规则引擎 | %s | 金标准 |' % cfg['name'])
            a('|---|---|---|---|---|---|')
            for d in dis:
                a('| %s | %s | %s | `%s` | `%s` | `%s` |' % (
                    d['id'], d['category'], d['situation'].replace('|', '/'),
                    d['rule'], d['llm'], d['expected']))
            a('')

    a('## 说明')
    a('')
    a('- 一致性 = LLM 与规则引擎输出完全相同的比例；分歧本身是研究素材'
      '（隐式语义类规则引擎回落 `%s`，LLM 若给出正确相位即"LLM 必要性"证据）。'
      % DEFAULT_PHASE)
    a('- 类型匹配 = 相位名+方向/队形一致、参数容差（如距离 25 vs 30）。')
    a('- 成本为估算（PRICES 常量快照），以官网当前价格为准。')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--provider', default='all',
                    help='deepseek/glm/local/all（all=deepseek+glm），逗号分隔可组合')
    ap.add_argument('--n', type=int, default=0, help='只跑前 N 条（冒烟）')
    ap.add_argument('--categories', default='',
                    help='只跑指定类别（逗号分隔：explicit,implicit,ambiguous,bilingual）')
    ap.add_argument('--repeat', type=int, default=1,
                    help='每条重复次数（>1 时输出确定性一致率，temp=0）')
    ap.add_argument('--timeout', type=float, default=30.0)
    ap.add_argument('--max-tokens', type=int, default=64)
    ap.add_argument('--temperature', type=float, default=0.0)
    ap.add_argument('--dry-run', action='store_true', help='不调 API，只跑规则引擎')
    ap.add_argument('--out-dir', default='eval_out')
    args = ap.parse_args()

    testset = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'situations_testset.json')
    items = load_testset(testset, args.n,
                         set(filter(None, args.categories.split(','))))

    providers = [] if args.dry_run else resolve_providers(args.provider)
    for cfg in providers:
        if not cfg['api_key'] and cfg.get('key_env'):
            print('[警告] %s 缺少 API key（%s），该 provider 跳过'
                  % (cfg['name'], cfg['key_env']))
    providers = [c for c in providers
                 if c['api_key'] or not c.get('key_env')]
    if not args.dry_run and not providers:
        sys.exit('无可用 provider：请设置 DEEPSEEK_API_KEY / GLM_API_KEY，或用 --dry-run')

    print('态势 %d 条 | provider: %s'
          % (len(items), ','.join(c['name'] for c in providers) or 'dry-run'))
    t0 = time.time()
    rows = build_rows(items, providers, args)

    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, 'phase_consistency_results.csv')
    rpt_path = os.path.join(args.out_dir, 'phase_consistency_report.md')
    write_csv(rows, csv_path)
    write_report(rpt_path, items, rows, providers, args)
    print('完成，耗时 %.1fs\n  %s\n  %s'
          % (time.time() - t0, csv_path, rpt_path))


if __name__ == '__main__':
    main()
