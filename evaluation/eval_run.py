#!/usr/bin/env python3
"""eval_run - 统一评测执行器（方向5：评估体系 v2）

取代三个 benchmark 脚本里硬编码的 16 条小测试：加载任意 GGUF 模型，
在 440 条分层评测集上运行，输出带 Wilson 95% 置信区间与分层矩阵的统计报告。

判定口径（与旧基准纵向可比）：
  basic（精确匹配，沿 benchmark_matrix.json_matches）：
    mode/formation 字符串相等、uav_ids 排序相等、target 逐元素 |diff|<=1e-3
  phase（容差匹配，沿 phase_verify_v4）：
    JSON 可解析 + target 各轴 |diff| <= λ（OBST/RECONF ±2/±2/±1，RECON ±5/±5/±1，
    ASM/HOLD ±1）；RECONFIGURE 另要求 formation 与相位参数一致。
    次级指标 subject_ok：mode+uav_ids 与指令主体一致（collective 的 formation
    训练本身一对多，不约束）。

用法：
  python evaluation/eval_run.py --model phi2-phased-v5-q5_k_m.gguf \
      --label v5-Q5_K_M --testset both
  python evaluation/eval_run.py --model xxx.gguf --label smoke --testset basic --limit 20
  python evaluation/eval_run.py --compare results/A_basic.jsonl results/B_basic.jsonl

输出（evaluation/results/）：
  {label}_{testset}_results.jsonl   逐条：id/category/split/got/correct/subject_ok/latency
  {label}_{testset}_summary.md      汇总：总体+分层准确率（Wilson CI）+ 失败样例
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime

# llama.dll 依赖 CUDA runtime DLL（与 benchmark_matrix 同款注入）
for _cuda_root in (
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
):
    _p = os.path.join(_cuda_root, 'bin', 'x64')
    if os.path.isdir(_p):
        os.environ['PATH'] = _p + os.pathsep + os.environ.get('PATH', '')
        break

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RESULTS_DIR = os.path.join(HERE, 'results')
TESTSET_DIR = os.path.join(HERE, 'testsets')
TESTSET_FILES = {'basic': 'basic_240.jsonl', 'phase': 'phase_200.jsonl'}

MAX_TOKENS = 70          # 覆盖最长相位 JSON，与 phase_verify_v4 一致
TEMPERATURE = 0.1        # 与旧基准一致，保证纵向可比


# ---------------------------------------------------------------------------
# 统计工具
# ---------------------------------------------------------------------------

def wilson(k, n, z=1.96):
    """Wilson score 区间：小 n 下比正态近似稳健。返回 (p̂, lo, hi)。"""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return p, max(0.0, (c - h) / d), min(1.0, (c + h) / d)


def mcnemar_exact(b, c):
    """配对 McNemar 精确二项检验（双侧）。b/c 为两模型判断不一致的两个方向计数。"""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n) * 2
    return min(1.0, p)


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------

def try_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find('{'), text.rfind('}')
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                return None
        return None


def judge_basic(got, expected):
    if not isinstance(got, dict):
        return False, 'unparseable'
    if got.get('mode') != expected['mode']:
        return False, 'mode'
    if got.get('formation') != expected['formation']:
        return False, 'formation'
    if sorted(got.get('uav_ids') or []) != sorted(expected['uav_ids']):
        return False, 'uav_ids'
    tgt = got.get('target')
    if not isinstance(tgt, list) or len(tgt) != 3:
        return False, 'target'
    for a, b in zip(tgt, expected['target']):
        try:
            if abs(float(a) - float(b)) > 1e-3:
                return False, 'target'
        except (TypeError, ValueError):
            return False, 'target'
    return True, ''


def judge_phase(got, item):
    """主判定（相位规则）+ 次级判定（指令主体）。"""
    expected, spec = item['expected'], item['judge']
    subj = item.get('subject') or {}
    if not isinstance(got, dict):
        return False, 'unparseable', False
    subject_ok = (got.get('mode') == subj.get('mode')
                  and sorted(got.get('uav_ids') or []) == sorted(subj.get('uav_ids', [])))
    tgt = got.get('target')
    if not isinstance(tgt, list) or len(tgt) != 3:
        return False, 'target', subject_ok
    tol = spec['tol']
    for i, axis in enumerate(('x', 'y', 'z')):
        try:
            if abs(float(tgt[i]) - float(expected['target'][i])) > tol[axis]:
                return False, f'target-{axis}', subject_ok
        except (TypeError, ValueError):
            return False, 'target-type', subject_ok
    if spec.get('formation_required') and got.get('formation') != expected['formation']:
        return False, 'formation', subject_ok
    return True, '', subject_ok


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def build_prompt(item):
    return (f"### System:\n{item['system']}\n\n"
            f"### User:\n{item['user']}\n\n### Response:\n")


def run_model(label, model_path, testset_name, limit, note=''):
    from llama_cpp import Llama
    import pynvml

    path = os.path.join(TESTSET_DIR, TESTSET_FILES[testset_name])
    with open(path, encoding='utf-8') as f:
        items = [json.loads(l) for l in f]
    if limit:
        items = items[:limit]

    print(f'[{label}] 加载 {model_path} ...')
    try:
        llm = Llama(model_path=model_path, n_gpu_layers=-1, n_ctx=512, verbose=False)
    except Exception as e:
        print(f'[{label}] 模型加载失败: {e}')
        return None
    pynvml.nvmlInit()
    vram_mb = pynvml.nvmlDeviceGetMemoryInfo(
        pynvml.nvmlDeviceGetHandleByIndex(0)).used // (1024 * 1024)
    pynvml.nvmlShutdown()

    results = []
    t_start = time.time()
    for i, item in enumerate(items, 1):
        prompt = build_prompt(item)
        t0 = time.perf_counter()
        out = llm(prompt, max_tokens=MAX_TOKENS, temperature=TEMPERATURE,
                  stop=['<|endoftext|>', '\n###'])
        latency = (time.perf_counter() - t0) * 1000
        raw = out['choices'][0]['text'].strip()
        got = try_json(raw)
        if item['judge']['type'] == 'exact':
            ok, why = judge_basic(got, item['expected'])
            subject_ok = None
        else:
            ok, why, subject_ok = judge_phase(got, item)
        results.append({'id': item['id'], 'category': item['category'],
                        'split': item['split'], 'correct': ok, 'reason': why,
                        'subject_ok': subject_ok, 'latency_ms': round(latency, 1),
                        'user': item['user'][:90],
                        'expected': item['expected'],
                        'got': raw[:200] if raw else ''})
        if i % 20 == 0 or i == len(items):
            acc = sum(1 for r in results if r['correct']) / len(results)
            print(f'  {i}/{len(items)} acc={acc:.3f}', flush=True)

    wall = time.time() - t_start
    os.makedirs(RESULTS_DIR, exist_ok=True)
    res_path = os.path.join(RESULTS_DIR, f'{label}_{testset_name}_results.jsonl')
    meta = {'label': label, 'model': os.path.basename(model_path),
            'testset': testset_name, 'n': len(items), 'vram_mb': vram_mb,
            'wall_s': round(wall, 1), 'note': note,
            'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    with open(res_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with open(res_path.replace('_results.jsonl', '_meta.json'), 'w',
              encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    summ_path = write_summary(meta, results, testset_name)
    print(f'[{label}] 完成: {res_path}\n        汇总: {summ_path}')
    return res_path


def fmt_ci(k, n):
    p, lo, hi = wilson(k, n)
    return f'{k}/{n} ({p*100:.1f}%, CI [{lo*100:.1f}, {hi*100:.1f}])'


def write_summary(meta, results, testset_name):
    lines = []
    a = lines.append
    a(f"# {meta['label']} · {testset_name} 评测汇总")
    a('')
    a(f"- 模型: `{meta['model']}` | n={meta['n']} | {meta['ts']}")
    a(f"- 显存(加载后总量): {meta['vram_mb']}MB | 耗时 {meta['wall_s']}s"
      + (f" | {meta['note']}" if meta['note'] else ''))
    a('')

    ok = [r for r in results if r['correct']]
    a('## 总体')
    a('')
    a(f"- 主指标（basic=精确匹配 / phase=规则容差）：**{fmt_ci(len(ok), len(results))}**")
    subj = [r for r in results if r.get('subject_ok') is not None]
    if subj:
        sok = sum(1 for r in subj if r['subject_ok'])
        a(f"- 次级（指令主体 mode+uav_ids）：{fmt_ci(sok, len(subj))}")
    unp = sum(1 for r in results if r['reason'] == 'unparseable')
    a(f"- JSON 解析失败: {unp}/{len(results)}")
    lats = [r['latency_ms'] for r in results]
    a(f"- 延迟 ms: mean={statistics.mean(lats):.0f} "
      f"p50={statistics.median(lats):.0f} max={max(lats):.0f}")
    a('')

    a('## 按 split')
    a('')
    a('| split | n | 主指标 |')
    a('|---|---|---|')
    order = (['in', 'out'] if testset_name.startswith('basic')
             else ['seen', 'in-range-unseen', 'ood', 'in'])
    for s in order:
        sub = [r for r in results if r['split'] == s]
        if sub:
            k = sum(1 for r in sub if r['correct'])
            a(f'| {s} | {len(sub)} | {fmt_ci(k, len(sub))} |')
    a('')

    a('## 按类别')
    a('')
    a('| category | n | 主指标 | subject_ok |')
    a('|---|---|---|---|')
    cats = sorted({r['category'] for r in results})
    for c in cats:
        sub = [r for r in results if r['category'] == c]
        k = sum(1 for r in sub if r['correct'])
        ssub = [r for r in sub if r.get('subject_ok') is not None]
        s = (f"{sum(1 for r in ssub if r['subject_ok'])}/{len(ssub)}"
             if ssub else '-')
        a(f'| {c} | {len(sub)} | {fmt_ci(k, len(sub))} | {s} |')
    a('')

    fails = [r for r in results if not r['correct']]
    if fails:
        a(f'## 失败样例（前 10 / 共 {len(fails)}）')
        a('')
        for r in fails[:10]:
            exp_t = r['expected'].get('target')
            a(f"- **{r['id']}** [{r['category']}/{r['split']}] {r['reason']}: "
              f"`{r['user']}`")
            a(f"  - 期望 target={exp_t}；输出 `{r['got'][:120]}`")
        a('')

    path = os.path.join(RESULTS_DIR, f"{meta['label']}_{testset_name}_summary.md")
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path


def compare(file_a, file_b):
    def load(p):
        with open(p, encoding='utf-8') as f:
            return {json.loads(l)['id']: json.loads(l)['correct'] for l in f}

    ra, rb = load(file_a), load(file_b)
    common = sorted(set(ra) & set(rb))
    if not common:
        sys.exit('两文件无共同条目')
    b = sum(1 for i in common if ra[i] and not rb[i])   # A 对 B 错
    c = sum(1 for i in common if not ra[i] and rb[i])   # A 错 B 对
    a_ = sum(1 for i in common if ra[i] and rb[i])
    d_ = sum(1 for i in common if not ra[i] and not rb[i])
    ka = sum(1 for i in common if ra[i])
    kb = sum(1 for i in common if rb[i])
    p = mcnemar_exact(b, c)
    print(f'共同条目 n={len(common)}')
    print(f'A ({os.path.basename(file_a)}): {fmt_ci(ka, len(common))}')
    print(f'B ({os.path.basename(file_b)}): {fmt_ci(kb, len(common))}')
    print(f'配对表: 两者都对 {a_} | 仅A对 {b} | 仅B对 {c} | 都错 {d_}')
    print(f'McNemar 精确检验 p = {p:.4f}'
          + ('（不显著）' if p >= 0.05 else '（显著）'))
    if b or c:
        print('不一致条目：')
        for i in common:
            if ra[i] != rb[i]:
                print(f'  {i}: A={"✓" if ra[i] else "✗"} B={"✓" if rb[i] else "✗"}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', help='GGUF 路径')
    ap.add_argument('--label', default='model')
    ap.add_argument('--testset', default='both',
                    choices=('basic', 'phase', 'both'))
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--note', default='')
    ap.add_argument('--compare', nargs=2, metavar=('RESULTS_A', 'RESULTS_B'))
    args = ap.parse_args()

    if args.compare:
        compare(*args.compare)
        return
    if not args.model:
        sys.exit('需要 --model 或 --compare')

    testsets = ('basic', 'phase') if args.testset == 'both' else (args.testset,)
    for ts in testsets:
        run_model(args.label, args.model, ts, args.limit, args.note)


if __name__ == '__main__':
    main()
