# phi2-phase-instruction-parsing

**相位条件化的端侧轻量化 LLM 指令解析**（多无人机集群分层协同控制主线）+ **师兄 Phase-Aware LLM 元控制器仓库的完整复现**。

RTX 3060 Laptop（6GB）上完成的全链路：QLoRA 4-bit 微调 Phi-2 → 五档量化基准 → 相位条件化（5 轮迭代）→ 单机/双机 PX4 飞行闭环 → 云-边相位协同与断连降级（8 月）；论文级评测体系与因果消融（10 月 P0-2/P0-3）；MAPPO + Phase-Aware LLM 元控制器 E1/E3/诊断实验复现（10 月 P0-1）。

**已验证的完整架构**：

```
云端（态势→相位信号，10 token）→ 端侧（Phi-2 v5 Q5_K_M 1.87GB，解析→PX4）
  → 起飞→巡航→悬停→返回→降落→上锁（全程相位缓存）
  → 断连→自主降级（飞往缓存相位安全目标）→ 恢复对齐
```

## 三大板块与目录导览

| 板块 | 目录 | 内容 | 状态 |
|---|---|---|---|
| **A. 端侧指令解析基础链路**（8 月） | 根目录 `*.py` | download_model → train_phi2_qlora → merge_and_quantize → benchmark 四步训练链；phase_verify*（相位一致性验证）、context_compression*、benchmark_matrix*（五档量化基准） | ✅ 端到端跑通（分步细节见各脚本头部注释与 `docs/八月成果总览.md`） |
| | `scripts/` | 云-边-端 ROS2 链路：cloud_phase_generator（云端相位生成）、nl_command_node（端侧解析→PX4 Offboard）、双机 demo、WSL 部署/评测脚本 | ✅ 双机闭环 + 断连降级验证 |
| | `datasets/` | 训练集 9 个版本（109 条原始 → v5 726 条 → v6lc 846 条含 120 长态势），版本演化即方法迭代记录 | 归档 |
| | `phi2-dmpc-adapter/`、`phi2-v6lc-adapter/` | QLoRA adapter 权重（merged 模型与 GGUF 按 .gitignore 不入库，可由 adapter+基座重建） | 归档 |
| | `logs/`、`eval_out/` | 训练/合并历史日志、峰值显存记录、相位一致性产物 | 归档 |
| | `docs/` | 8 月工作汇报、MAPPO 原理学习文档、px4_ws 架构分析、论文草稿 v2 等 docx | 归档 |
| **B. 论文级评测体系**（10 月） | `evaluation/` | P0-2 基准（600 条冻结测试集 basic_240+phase_200+robust_160，隔离校验零泄漏，一键六指标评测）、P0-3 因果消融（G1-G7）、错误模式深度分析；testsets/ 与 results*/ 为冻结测试集与评测产物 | ✅ 完成 |
| **C. 师兄仓库复现**（10 月） | `phase-aware-repro/` | [ACHICHU666/phase-aware-llm-meta-controller](https://github.com/ACHICHU666/phase-aware-llm-meta-controller) @ `c767b88` 的完整复现：E1 四臂（baseline/uniform/random/phase_aware ×10 预注册 seed）、E3 规则臂、31415 熵边界诊断，共 40+3 run 原始产物 + 驱动/分析脚本 + 报告 | ✅ 完成（P0-1） |

> 不入库目录（.gitignore）：上游克隆 `phase-aware-llm-meta-controller/`、`llama.cpp/`、`models/`、`*.gguf`、merged 模型、训练中间产物 `phi2-*-3060/`、`.venv/`。

## 10 月任务书 P0 进度

| 任务 | 状态 | 记录文档 |
|---|---|---|
| P0-1 MAPPO baseline 独立复现 | ✅ 达标（7/10 seed 定量一致，远超 ≥3 要求） | `phase-aware-repro/docs/复现报告.md`、`MAPPO_baseline_代码论文对照表.md`（10 项待与师兄确认） |
| P0-2 指令解析 Benchmark v1 | ✅ 600 条冻结测试集，训练/测试隔离零泄漏，一键评测 | `evaluation/P0-2_实验记录.md`、`P0-2_深度分析.md`、`matrix_report_v2.md` |
| P0-3 Phase 因果消融 | ✅ G1-G7 七组对照完成 | `evaluation/P0-3_实验记录.md` |
| P0-4 SLM+MAPPO 双机闭环 | ⏳ 第 4 周任务 | — |
| P1 文献 novelty matrix / 统计方法 | 🔄 进行中 | — |

## 关键结论速览

- **P0-2 评测**：量化敏感度是能力维度依赖（basic 全档 ≥97.5%，phase 档 Q4 悬崖 43%，robust 与量化无关）；越界指令 84-100% 危险回声、歧义 100% 捏造（跨全档含 FP16）→ **确定性安全层必须外置于模型**（P0-4 依据）；随机相位 63-70% 被跟随 → phase 是真语义信号。
- **P0-3 因果链**：散文态势 0% → 同长结构化 9-12%（崩溃主因是长度/分布而非格式）→ 相位标签 55%（压缩总收益 +55pp）→ 随机标签被跟随（语义真实）→ 错误标签 100% 捏造（安全层必要）→ 长样本重训 0→57% 但 basic 100→82.9% 显著回退 → **云-边分工的定量依据**。
- **复现（P0-1）**：机制层完全复现（相位白名单拒绝率 72% 与论文精确一致、生效参数更新 188 vs 195、健康 seed 分相位咨询数逐 seed 相同）；定量 7/10 seed 一致，分歧集中于 3 个困难 seed（999/31415/789），根因 = 动作采样 RNG 后端差异（CPU MT19937 vs CUDA Philox）而非方法失效（16 组 CI 全部重叠）；phase_aware 是唯一大幅挽救困难 seed999 的方法（0→86%）；31415 诊断否定"权限不足"假说（真约束 = episode 预算）。

## 复跑指引

**两个独立环境，勿混用**：

| 环境 | 用途 | 关键依赖 |
|---|---|---|
| `.venv/`（Python 3.12） | 板块 A 训练/量化链路、板块 B 评测 | torch 2.11+cu128（必须 CUDA 版）、transformers/trl/peft/bitsandbytes |
| conda `phase-llm`（Python 3.11） | 板块 C 复现 | torch 2.14 CPU、Ollama 0.40.2 + deepseek-r1:14b（本地构建） |

```bash
# 板块 A：训练链路（分步说明见各脚本头部注释）
python download_model.py && python train_phi2_qlora.py && python merge_and_quantize.py && python benchmark.py

# 板块 B：一键评测矩阵（5 档量化 × 600 条，约 53 分钟）
python evaluation/run_matrix_v2.py

# 板块 C：复现（需先 clone 上游 c767b88 至本目录，脚本在 phase-aware-repro/scripts/）
python repro_baseline_n10.py
PYTHONUNBUFFERED=1 python repro_e1_llm_arms.py        # 需 Ollama 服务运行
python analysis/analysis_part1_perseed.py             # 逐项分析（part1-6 依次）
```

**环境坑（均已踩过并验证解法）**：

- `pip install torch` 默认装 CPU 版 → 必须用 `--index-url https://download.pytorch.org/whl/cu128`；
- HF 直连不可用 → `download_model.py` 已内置 ModelScope 源；
- GitHub 大文件限速 → gh-proxy.com + 显式 `Range` 头多路并行下载；
- Ollama 官方 registry 被校园网 DNS 污染（`auth.ollama.ai` 无解析）→ 模型从 ModelScope 下 GGUF 后 `ollama create` 本地构建。

## 记录规范

所有实验遵循 10 月任务书第五节：日期 / git commit / 模型与数据版本 / seed / 配置 / 硬件 / 命令 / 结果路径八要素齐全；失败实验保留（含现象、排查、根因、验证计划）；图表数据均可由脚本从原始 `results.json` 重新生成。复现工作的唯一配置偏差（`llm_timeout` 120→600，本机 LLM 延迟所致）声明于 `phase-aware-repro/results/e1_llm_arms_config.json`。

---

## 实验室训练机工作流（2026-10-15 接入）

实验室服务器（RTX 4090 24GB）**只负责训练，不负责仿真**。分工与流程：

- **环境**：conda env `syc_phi2`（Python 3.11，版本组合见 `requirements.txt` 钉版注释）
- **基座模型**：`models/phi-2/`（不入库）— 缺失时 `python src/training/download_model.py`（ModelScope 源；网络慢用 `scripts/pdl.py` 并行下载）
- **训练**：`python src/training/train_qlora.py`（默认 v5 主力数据集）
  - 冒烟：`PHI2_SMOKE=40 python src/training/train_qlora.py`（产物带 `_smoke` 后缀，不覆盖正式权重）
- **产物入库**：训练完成 → `git add adapters/ && git commit -m "train: <版本> <说明>" && git push`
  - 正式权重：`adapters/dmpc_v5/`（本机 2026-10-15 复训件）；`adapters/dmpc_v5_original/`（原机权威件，只读）；`adapters/dmpc_v6lc/`
  - 里程碑训练记录归档：`docs/training_runs/`
- **认证安全**：GitHub 凭据仅会话内有效，断开连接自动登出（`~/.bash_logout`）
