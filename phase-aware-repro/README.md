# Phase-Aware LLM Meta-Controller 复现（师兄仓库官方复现包）

复现对象：[ACHICHU666/phase-aware-llm-meta-controller](https://github.com/ACHICHU666/phase-aware-llm-meta-controller) @ commit `c767b88`
（论文 Phase-Aware LLM-Guided Meta-Controller for Multi-UAV Formation Learning）
执行时间：2026-10-10 ~ 2026-10-12　|　对应 10 月任务书 P0-1 及其超额部分

上游代码零改动；本目录只包含**我方自产的驱动脚本、分析脚本、文档与实验结果**。
上游克隆本体位于 `../phase-aware-llm-meta-controller/`（.gitignore 排除，不入本仓库）。

## 目录结构

```
phase-aware-repro/
├── README.md                 本文件
├── scripts/                  驱动脚本（7 个，均可在上游克隆根目录直接运行）
│   ├── smoke_test.py             冒烟测试（40 ep）
│   ├── repro_baseline_n10.py     E1 baseline 臂 ×10 预注册 seed
│   ├── repro_rule_based_n10.py   E3 规则控制器臂 ×10
│   ├── repro_e1_llm_arms.py      E1 LLM 臂链：phase_aware→uniform→random（×10 each）
│   ├── repro_diag_31415_entropy.py        31415 熵上界扩界诊断（A）
│   ├── repro_diag_31415_baseline_entropy.py  固定熵对照（B=0.02 / C=0.05）
│   └── repro_compare.py          复现 vs 论文对比表生成
├── analysis/                 逐项分析脚本（5 个，见 docs/参考结果vs复现_逐项分析.md）
├── docs/                     复现报告、MAPPO 代码-论文对照表、逐项分析（Part 1-7）
└── results/                  原始实验产物
    ├── <method>_seed<N>/         40+3 个 run：results.json（逐 episode 历史）、
    │                             llm_calls.jsonl（prompt 原文+安全层裁决）、
    │                             matched_schedule.json、config_snapshot.json
    ├── statistics_e1_full/       官方配对统计（Wilcoxon/bootstrap CI/Holm）
    ├── *.csv / fig_*.png         四臂汇总与 9 张对比图
    ├── results_diag/             31415 三组诊断
    └── smoke_results/            冒烟测试
```

checkpoint（.pth）与 tensorboard 按 .gitignore 不入库，保留在本地磁盘。

## 环境

- Python 3.11.17（conda env `phase-llm`）、numpy 1.26.4、scipy 1.16.1、torch 2.14.1 CPU
- LLM：Ollama 0.40.2 + deepseek-r1:14b（unsloth DeepSeek-R1-Distill-Qwen-14B Q4_K_M GGUF 本地构建，同论文模型与量化）
- 硬件：RTX 3060 Laptop 6GB / 16 逻辑核 / 63.2GB RAM / Windows
- **唯一配置偏差**：`llm_timeout` 120→600 s（本机单次咨询 67-202 s，论文平台 4.9 s；已写入 `results/e1_llm_arms_config.json`）

## 一句话结论

机制层完全复现（相位白名单拒绝率 72% 与论文精确一致、生效更新 188 vs 195、健康 seed 分相位咨询数逐 seed 相同）；
定量层 7/10 seed 一致，分歧集中于 3 个困难 seed（999/31415/789）——根因是动作采样 RNG 后端差异（CPU MT19937 vs CUDA Philox），
而非方法失效（16 组 CI 全部重叠）。phase_aware 是唯一大幅挽救 seed999 的方法（0%→86%）。详见 `docs/`。

## 复跑

```bash
# 在上游克隆（c767b88）根目录、conda env phase-llm 下：
python scripts/repro_baseline_n10.py
python scripts/repro_rule_based_n10.py
PYTHONUNBUFFERED=1 python scripts/repro_e1_llm_arms.py     # 需 Ollama 服务在跑
python scripts/repro_compare.py                             # 对比表
python analysis/analysis_part1_perseed.py                   # 逐项分析（1-6 依次）
```
