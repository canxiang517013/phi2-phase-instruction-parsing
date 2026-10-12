#!/usr/bin/env python3
"""Part 2: E7 机制审计逐 seed 对比（mine llm_calls.jsonl vs reference llm_audit_per_run.csv）"""
import csv, json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent
SEEDS = [21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888]

REF = {}
with (ROOT / "results/E7_audit/llm_audit_per_run.csv").open(encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        REF[int(row["seed"])] = row

def mine_audit(seed):
    path = ROOT / f"results_repro/phase_aware_seed{seed}/llm_calls.jsonl"
    d = dict(consultations=0, parsed=0, unauthorized=0, over_budget=0, updates=0,
             events=0, early_c=0, mid_c=0, late_c=0, lat=[], params={}, dirs={})
    seen_episodes = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            d["consultations"] += 1
            d["parsed"] += len(j["parsed_suggestions_raw"])
            d["unauthorized"] += len(j["unauthorized_suggestions"])
            d["over_budget"] += len(j["over_budget_suggestions"])
            d["updates"] += len(j["applied_updates"])
            ph = j["rule_phase"]
            d[f"{ph}_c"] = d.get(f"{ph}_c", 0) + 1
            m = (j["llm_meta"] or {}).get("latency_seconds")
            if m: d["lat"].append(m)
            for s in j["selected_suggestions"]:
                d["params"][s["param_name"]] = d["params"].get(s["param_name"], 0) + 1
                key = (s["param_name"], s["adjustment_type"])
                d["dirs"][key] = d["dirs"].get(key, 0) + 1
    with (ROOT / f"results_repro/phase_aware_seed{seed}/results.json").open(encoding="utf-8") as f:
        d["events"] = json.load(f)["intervention_event_count"]
    return d

print("=" * 110)
print("PART 2A  逐 seed 机制审计（phase_aware：本机 / 论文E7参考）")
print("=" * 110)
print(f"{'seed':>7} | {'咨询':>11} | {'解析建议':>11} | {'未授权':>11} | {'超预算':>9} | {'生效更新':>11} | {'干预事件':>11} | {'E/M/L 咨询':>17}")
for s in SEEDS:
    m = mine_audit(s); r = REF[s]
    fmt = lambda mk, rk, cast=int: f"{cast(m[mk]):>5}/{cast(float(r[rk])):>5}"
    print(f"{s:>7} | {fmt('consultations','consultations')} | {fmt('parsed','parsed_suggestions')} | "
          f"{fmt('unauthorized','phase_unauthorized_suggestions')} | {fmt('over_budget','over_budget_suggestions')} | "
          f"{fmt('updates','accepted_parameter_updates')} | {fmt('events','intervention_events')} | "
          f"{m['early_c']:>5}/{m['mid_c']:>2}/{m['late_c']:>2} vs {int(float(r['early_consultations'])):>4}/{int(float(r['mid_consultations'])):>2}/{int(float(r['late_consultations'])):>3}")

print()
print("=" * 110)
print("PART 2B  聚合：机制漏斗 + 分相位活动（本机 vs 论文E7）")
print("=" * 110)
tot_m = dict(consultations=0, parsed=0, unauthorized=0, over_budget=0, updates=0, events=0, early=0, mid=0, late=0, lat=[])
tot_r = dict(consultations=0, parsed=0, unauthorized=0, over_budget=0, updates=0, events=0, early=0, mid=0, late=0, lat=[])
for s in SEEDS:
    m = mine_audit(s); r = REF[s]
    for k in ["consultations","parsed","unauthorized","over_budget","updates","events"]:
        tot_m[k] += m[k]; tot_r[k] += int(float(r[{"consultations":"consultations","parsed":"parsed_suggestions","unauthorized":"phase_unauthorized_suggestions","over_budget":"over_budget_suggestions","updates":"accepted_parameter_updates","events":"intervention_events"}[k]]))
    tot_m["early"]+=m["early_c"]; tot_m["mid"]+=m["mid_c"]; tot_m["late"]+=m["late_c"]
    tot_r["early"]+=int(float(r["early_consultations"])); tot_r["mid"]+=int(float(r["mid_consultations"])); tot_r["late"]+=int(float(r["late_consultations"]))
    tot_m["lat"] += m["lat"]; tot_r["lat"] += [float(r["latency_mean_s"])]*int(float(r["consultations"]))
rows = [
    ("LLM 咨询总次数", tot_m["consultations"], tot_r["consultations"]),
    ("解析建议总数", tot_m["parsed"], tot_r["parsed"]),
    ("相位未授权拒绝数（率）", f'{tot_m["unauthorized"]} ({tot_m["unauthorized"]/tot_m["parsed"]*100:.0f}%)', f'{tot_r["unauthorized"]} ({tot_r["unauthorized"]/tot_r["parsed"]*100:.0f}%)'),
    ("超预算拒绝数", tot_m["over_budget"], tot_r["over_budget"]),
    ("生效参数更新数", tot_m["updates"], tot_r["updates"]),
    ("干预事件数", tot_m["events"], tot_r["events"]),
    ("early 相位咨询数（均值/seed）", f'{tot_m["early"]} ({tot_m["early"]/10:.1f})', f'{tot_r["early"]} ({tot_r["early"]/10:.1f})'),
    ("mid 相位咨询数（均值/seed）", f'{tot_m["mid"]} ({tot_m["mid"]/10:.1f})', f'{tot_r["mid"]} ({tot_r["mid"]/10:.1f})'),
    ("late 相位咨询数（均值/seed）", f'{tot_m["late"]} ({tot_m["late"]/10:.1f})', f'{tot_r["late"]} ({tot_r["late"]/10:.1f})'),
    ("单次延迟 mean s", f'{np.mean(tot_m["lat"]):.1f}', f'{np.mean(tot_r["lat"]):.1f}'),
]
for name, a, b in rows:
    print(f"{name:<28} 本机 {a!s:>18}    参考 {b!s:>18}")

print()
print("=" * 110)
print("PART 2C  LLM 实际推荐内容分布（本机 10 seed 合计，selected 建议）")
print("=" * 110)
all_params, all_dirs = {}, {}
for s in SEEDS:
    m = mine_audit(s)
    for k, v in m["params"].items(): all_params[k] = all_params.get(k, 0) + v
    for k, v in m["dirs"].items(): all_dirs[k] = all_dirs.get(k, 0) + v
print("按参数:", dict(sorted(all_params.items(), key=lambda x: -x[1])))
print("按参数×方向:", {f"{k[0]}·{k[1]}": v for k, v in sorted(all_dirs.items(), key=lambda x: -x[1])})
