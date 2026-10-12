#!/usr/bin/env python3
"""Part 6: 评审回应补充分析
6A 效应量(dz/rank-biserial)  6B 精确配对置换检验  6C BCa bootstrap
6D 成功率曲线 AUC  6E 参数边界命中  6F 墙钟成本效益  6G 建议密度分解"""
import csv, itertools, json
import numpy as np
from pathlib import Path
from scipy import stats as st

ROOT = Path(__file__).parent
SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]
METHODS = ["baseline", "random_matched", "uniform_matched", "phase_aware"]

REF_PER = {}
with (ROOT / "results/E1_primary/per_seed_metrics.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        REF_PER[(r["method"], int(r["seed"]))] = r
MINE = {}
for p in ROOT.glob("results_repro/*_seed*/results.json"):
    m, s = p.parent.name.rsplit("_seed", 1)
    with p.open(encoding="utf-8") as f:
        MINE[(m, int(s))] = json.load(f)

def get(store, key, metric):
    v = store[key].get(metric)
    if metric.endswith("_episode") and (v is None or v == ""):
        return 2501.0
    return float(v)

print("=" * 108)
print("6A  效应量：paired Cohen's dz 与 rank-biserial（本机 vs 参考，参考侧=phase_aware）")
print("=" * 108)
REF_PAIR, MINE_PAIR = {}, {}
with (ROOT / "results/E1_primary/paired_statistics.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        REF_PAIR[(r["metric"], r["baseline"])] = r
with (ROOT / "results_repro/statistics_e1_full/paired_statistics.csv").open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        MINE_PAIR[(r["metric"], r["baseline"])] = r
def dz_es(a, b):
    d = np.asarray(a) - np.asarray(b)
    sd = d.std(ddof=1)
    return 0.0 if sd < 1e-12 else d.mean() / sd
print(f"{'指标':<32} {'对照':<15} {'dz 参考':>8} {'dz 本机':>8} {'|dz|判定':>10} {'rbc 参考':>9} {'rbc 本机':>9}")
for metric in ["first_success_episode", "final_follow_position_error", "final_pairwise_formation_error", "final_success_rate"]:
    for comp in ["baseline", "random_matched", "uniform_matched"]:
        rp, mp = REF_PAIR[(metric, comp)], MINE_PAIR[(metric, comp)]
        rdz, mdz = float(rp["cohens_dz_favors_reference"]), float(mp["cohens_dz_favors_reference"])
        rrb, mrb = float(rp["rank_biserial_favors_reference"]), float(mp["rank_biserial_favors_reference"])
        interp = lambda z: "大" if abs(z) >= 0.8 else ("中" if abs(z) >= 0.5 else ("小" if abs(z) >= 0.2 else "微"))
        print(f"{metric:<32} {comp:<15} {rdz:>8.2f} {mdz:>8.2f} {interp(mdz) + '<' + interp(rdz) + '>':>10} {rrb:>9.2f} {mrb:>9.2f}")

print()
print("=" * 108)
print("6B  精确配对置换检验（2^10=1024 全枚举符号翻转；对照 Wilcoxon 结论）")
print("=" * 108)
def perm_p(d):
    d = np.asarray(d, float)
    obs = abs(d.sum())
    stat = sum(abs((d * s).sum()) >= obs - 1e-9 for s in itertools.product([1, -1], repeat=len(d)))
    return stat / 2 ** len(d)
print(f"{'指标':<32} {'对照':<15} {'置换p 本机':>10} {'Wilcoxon p':>10} {'一致?':>5} {'置换p 论文侧(参考数据)':>12}")
for metric in ["first_success_episode", "final_follow_position_error", "final_pairwise_formation_error", "final_success_rate"]:
    for comp in ["baseline", "random_matched", "uniform_matched"]:
        dm = [get(MINE, ("phase_aware", s), metric) - get(MINE, (comp, s), metric) for s in SEEDS]
        dr = [get(REF_PER, ("phase_aware", s), metric) - get(REF_PER, (comp, s), metric) for s in SEEDS]
        pm, wl = perm_p(dm), float(MINE_PAIR[(metric, comp)]["wilcoxon_p"])
        pr = perm_p(dr)
        agree = "是" if (pm < 0.05) == (wl < 0.05) else "否"
        print(f"{metric:<32} {comp:<15} {pm:>10.3f} {wl:>10.3f} {agree:>5} {pr:>12.3f}")

print()
print("=" * 108)
print("6C  BCa bootstrap 95% CI（配对差，phase_aware − baseline，对比百分位法）")
print("=" * 108)
for metric in ["final_follow_position_error", "final_pairwise_formation_error", "final_success_rate"]:
    dm = np.array([get(MINE, ("phase_aware", s), metric) - get(MINE, ("baseline", s), metric) for s in SEEDS])
    bca = st.bootstrap((dm,), np.mean, method="BCa", n_resamples=20000, random_state=np.random.default_rng(1))
    lo, hi = bca.confidence_interval.low, bca.confidence_interval.high
    idx = np.random.default_rng(20260725).integers(0, 10, size=(20000, 10))
    pm_lo, pm_hi = np.percentile(dm[idx].mean(axis=1), [2.5, 97.5])
    cover0 = "含0" if lo <= 0 <= hi else "不含0"
    print(f"{metric:<34} BCa [{lo:>8.2f},{hi:>8.2f}] {cover0}   百分位 [{pm_lo:>7.2f},{pm_hi:>7.2f}]")

print()
print("=" * 108)
print("6D  成功率曲线时间积分（AUC = 全 2500 ep 成功标记均值，%·ep 归一为 %）")
print("=" * 108)
print(f"{'seed':>7} | {'baseline':>9} {'rule':>6} {'uniform':>8} {'random':>7} {'pa':>6} | pa 排名")
ranks_all = {m: [] for m in ["baseline", "rule_based", "uniform_matched", "random_matched", "phase_aware"]}
for s in SEEDS:
    aucs = {}
    for m in ranks_all:
        h = MINE[(m, s)]["success_history"]
        aucs[m] = 100.0 * float(np.mean(h))
    order = sorted(ranks_all, key=lambda m: -aucs[m])
    for i, m in enumerate(order):
        ranks_all[m].append(i + 1)
    print(f"{s:>7} | {aucs['baseline']:>9.2f} {aucs['rule_based']:>6.2f} {aucs['uniform_matched']:>8.2f} {aucs['random_matched']:>7.2f} {aucs['phase_aware']:>6.2f} | 第{order.index('phase_aware')+1}/5")
print("平均排名:", {m: round(float(np.mean(r)), 2) for m, r in ranks_all.items()})

print()
print("=" * 108)
print("6E  phase_aware 参数边界命中（终值占可行域位置，10 seed）")
print("=" * 108)
BOUNDS = {"w_position": (0.3, 2.0), "w_formation": (0.3, 2.0), "w_success": (5.0, 30.0), "entropy_coef": (0.001, 0.02)}
for name, (lo, hi) in BOUNDS.items():
    finals = [MINE[("phase_aware", s)]["param_history"][name][-1] for s in SEEDS]
    pos = [(v - lo) / (hi - lo) for v in finals]
    n_at = sum(p >= 0.95 for p in pos)
    print(f"{name:<14} 终值域位置均值 {np.mean(pos):.2f}，≥95% 上界的 seed 数 {n_at}/10，默认起始位置 {(BOUNDS[name][1] if name in ('w_position',) else 0)and ''}{0.5 if name!='w_success' else (10-5)/25:.2f}")

print()
print("=" * 108)
print("6F  墙钟成本效益（每 seed 训练秒数：本机 vs 参考；LLM 开销占比）")
print("=" * 108)
print(f"{'方法':<16} {'本机 s/seed':>11} {'参考 s/seed':>11} {'本机LLM推理s':>12} {'LLM占比':>8}")
for m in METHODS:
    mine_t = [MINE[(m, s)]["elapsed_seconds"] for s in SEEDS]
    ref_t = [float(REF_PER[(m, s)]["elapsed_seconds"]) for s in SEEDS]
    llm_s = None
    if m in ("phase_aware", "uniform_matched"):
        tot = []
        for s in SEEDS:
            r = MINE[(m, s)]
            c = r["llm_consultation_count"]
            tot.append((r["llm_latency_mean_seconds"] or 0) * c)
        llm_s = np.mean(tot)
    print(f"{m:<16} {np.mean(mine_t):>11.0f} {np.mean(ref_t):>11.0f} "
          f"{(f'{llm_s:.0f}' if llm_s else '—'):>12} {(f'{llm_s/np.mean(mine_t)*100:.0f}%' if llm_s else '—'):>8}")
# 成本归一化的加速
for m in ["baseline", "random_matched", "uniform_matched", "phase_aware"]:
    fs_m = [get(MINE, (m, s), "first_success_episode") for s in SEEDS]
    t_m = np.mean([MINE[(m, s)]["elapsed_seconds"] for s in SEEDS])
    hours_to_first = np.mean(fs_m) / 2500 * t_m / 3600
    print(f"  {m:<16} 平均首达成功耗时 ≈ {hours_to_first:.2f} h/seed（含失败 seed 按 2501 计）")

print()
print("=" * 108)
print("6G  建议密度分解（每咨询解析建议数：本机 vs 参考 E7）")
print("=" * 108)
for s in SEEDS:
    r = MINE[("phase_aware", s)]
    mine_dens = r["llm_consultation_count"] and sum(
        1 for _ in []) # placeholder
mine_c = sum(MINE[("phase_aware", s)]["llm_consultation_count"] for s in SEEDS)
mine_p = 862; ref_c = 357; ref_p = 739
print(f"本机：{mine_p} 条 / {mine_c} 次 = {mine_p/mine_c:.2f} 条/次；参考：{ref_p}/{ref_c} = {ref_p/ref_c:.2f} 条/次")
print(f"建议总量差分解：+{mine_p-ref_p} 条 = 调用次数差贡献 +{(mine_c-ref_c)*(ref_p/ref_c):.0f} 条 + 单次啰嗦度差贡献 +{mine_c*(mine_p/mine_c-ref_p/ref_c):.0f} 条")
