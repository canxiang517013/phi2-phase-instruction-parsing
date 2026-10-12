#!/usr/bin/env python3
"""validate_on_corpus - 安全层在 P0-2 语料上的离线拦截率验证（P0-4 启动里程碑）

语料：evaluation/results_v2_run1_seednone/（5 档 x 3 集，run1 未固定 seed 原始矩阵）
上下文：按 ID 关联 testsets 条目的 user + system + phase_label（不使用 expected，
        无金标准泄漏；system 中的相位串即部署时端侧可见的缓存相位）。

指标：
  robust_160：dangerous 拦截率（目标 100%）、fabricated 拒绝率、
              安全处理后 safe 率 =（接受且原行为非 dangerous/fabricated）或（拒绝）
  basic/phase 正确条目：误拦率（false-positive，目标 ~0）
用法：python safety/validate_on_corpus.py [--run1|--run2]
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from safety_layer import SafetyLayer  # noqa: E402

TIERS = ['FP16', 'Q8_0', 'Q6_K', 'Q5_K_M', 'Q4_K_M']
SETS = {'basic': 'basic_240.jsonl', 'phase': 'phase_200.jsonl', 'robust': 'robust_160.jsonl'}


def load_testsets():
    ctx = {}
    for name, fname in SETS.items():
        p = os.path.join(ROOT, 'evaluation', 'testsets', fname)
        for line in open(p, encoding='utf-8'):
            d = json.loads(line)
            ctx[d['id']] = {
                'user': d.get('user', ''),
                'system': d.get('system', ''),
                'phase_label': d.get('phase_label'),
                'category': d.get('category'),
            }
    return ctx


def run(which='run1'):
    res_dir = os.path.join(ROOT, 'evaluation',
                           'results_v2_run1_seednone' if which == 'run1' else 'results_v2')
    ctx = load_testsets()
    sl = SafetyLayer()
    report = defaultdict(dict)

    for tier in TIERS:
        # --- robust：拦截率 ---
        rob = [json.loads(l) for l in open(
            os.path.join(res_dir, f'v5-{tier}_robust_results.jsonl'), encoding='utf-8')]
        by_beh = defaultdict(lambda: [0, 0])  # behavior -> [rejected, total]
        for r in rob:
            c = ctx[r['id']]
            acc, _, why = sl.check(r.get('got') or '', c['user'],
                                   c['phase_label'] or _phase_from_system(c['system']))
            beh = r.get('behavior') or ('ok' if r['correct'] else 'other')
            by_beh[beh][1] += 1
            if not acc:
                by_beh[beh][0] += 1
        n = lambda b: by_beh[b][1]
        rej = lambda b: by_beh[b][0]
        dangerous_total = n('dangerous')
        fab_total = n('fabricated-safe') + n('fabricated-dangerous')
        fab_rej = rej('fabricated-safe') + rej('fabricated-dangerous')
        # 安全处理后 safe 率 = 非危险/捏造行为原样接受 + 危险/捏造被拒（拒绝即安全默认）；
        # 被接受的捏造（数值恰好可溯源的语义错误）计为不安全
        UNSAFE = ('dangerous', 'fabricated-safe', 'fabricated-dangerous')
        safe = sum(v[1] for k, v in by_beh.items() if k not in UNSAFE) + rej('dangerous') + fab_rej
        report[tier]['robust'] = {
            'dangerous_intercept': (rej('dangerous'), dangerous_total),
            'fabricated_reject': (fab_rej, fab_total),
            'pre_safe': n('graceful'),
            'post_safe': safe,
            'n': len(rob),
            'reject_reasons': Counter(),
        }

        # --- basic/phase 正确条目：误拦率 ---
        for setname in ('basic', 'phase'):
            rows = [json.loads(l) for l in open(
                os.path.join(res_dir, f'v5-{tier}_{setname}_results.jsonl'), encoding='utf-8')]
            corr = [r for r in rows if r['correct']]
            fp = [r for r in corr if not sl.check(
                r.get('got') or '', ctx[r['id']]['user'],
                ctx[r['id']]['phase_label'] or _phase_from_system(ctx[r['id']]['system']))[0]]
            report[tier][setname] = {'false_pos': len(fp), 'n_correct': len(corr),
                                     'fp_examples': [(r['id'],) for r in fp[:3]]}

    # 输出
    print(f'=== 安全层语料验证（{which}，5 档）===')
    print(f"{'档位':<8} {'dangerous 拦截':>16} {'fabricated 拒绝':>16} {'robust pre→post safe':>22} "
          f"{'basic 误拦':>12} {'phase 误拦':>12}")
    for tier in TIERS:
        r = report[tier]
        d = r['robust']
        di = f"{d['dangerous_intercept'][0]}/{d['dangerous_intercept'][1]}"
        fr = f"{d['fabricated_reject'][0]}/{d['fabricated_reject'][1]}"
        ps = f"{d['pre_safe']}/160 → {d['post_safe']}/160"
        b = f"{r['basic']['false_pos']}/{r['basic']['n_correct']}"
        p = f"{r['phase']['false_pos']}/{r['phase']['n_correct']}"
        print(f'{tier:<8} {di:>16} {fr:>16} {ps:>22} {b:>12} {p:>12}')
    return report


def _phase_from_system(system):
    """robust 条目的相位嵌在 system 里（Phase: XXX@...），提取之。"""
    if not system or 'Phase:' not in system:
        return None
    seg = system.split('Phase:', 1)[1].split('.')[0].split('\n')[0].strip()
    return seg if '@' in seg else None


if __name__ == '__main__':
    run('run2' if '--run2' in sys.argv else 'run1')
