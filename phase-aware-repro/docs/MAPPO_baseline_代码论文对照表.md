# MAPPO Baseline 代码-论文对照表

依据仓库：`ACHICHU666/phase-aware-llm-meta-controller`（论文 "Phase-Aware LLM-Guided Meta-Controller for Multi-UAV Formation Learning" 官方复现包）
代码基准：`src/experiment_core.py`（与 `comparison_full_task_success_n10.py` 逐字节相同，diff = 0）
撰写日期：2026-10-10　|　环境：Python 3.11.17 / numpy 1.26.4 / scipy 1.16.1 / torch 2.14.1 CPU

---

## 1. 数据流图（从一次 rollout 到一次 PPO update）

```text
环境 MovingLeaderFormationEnv (2D, 4 follower + 1 leader)
   │  reset(): follower 固定四角起点 (±100,±100)，leader (0,0)，目标 (200,200)
   ▼
obs (4×14) ──────────────► SquashedGaussianActor (共享, 64-64 tanh) ──► tanh(action) 4×2 ──► env.step()
global_state (22) ───────► CentralizedCritic (128-128 ReLU) ──► V(s) 4                      │
   ▲                                                                                          │
   │              ┌── reward r_t (4)  = -0.5·w_pos·e_pos - 0.2·w_form·e_pair + shaping 奖励 ──┘
   │              └── terminated: leader 距目标 < 5 m；truncated: t ≥ 500
   ▼
Rollout buffer（on-policy, 单 episode 为一个 update 单元, T×N 展平）
   ▼
compute_gae: δ_t = r_t + γ·V_{t+1}·(非终止) - V_t;  A_t = δ_t + γλ·(非终止)·A_{t+1}
   （terminated → bootstrap 0；truncated → V(last_state) bootstrap）
   ▼
ppo_update (2 epochs):
   actor:  L = -E[min(ratio·A, clip(ratio,0.2̄,1.2̄)·A)] - entropy_coef·H    （A 先全 batch 归一化）
   critic: L = 0.5·E[max((V-R)², (V_clip-R)²)]   （value clip ±0.5）
   两者 grad-norm 均 clip 到 1.0
   ▼
下一 episode；元控制器（仅 LLM/规则方法）在 episode 边界调整 w_position / w_formation / w_success / entropy_coef
```

## 2. 张量维度与论文定义对应

| 张量 | 维度 | 代码位置 | 组成 |
|---|---|---|---|
| observation（每 agent） | **14** | `obs()` L437-459 | pos(2) + vel(2) + 相对目标(2) + 目标绝对坐标(2) + formation_phase(1) + formation_complete(1) + 相对 leader(2) + leader_vel(2) |
| global state（CTDE 的 C） | **22** | `global_state()` L461-471 | 4×pos(8) + 4×vel(8) + leader_pos(2) + leader_vel(2) + 2 个阶段标志 |
| action（每 agent） | 2 | `step()` L580 | 加速度方向（tanh 压到 [-1,1]，×act_scale 15 m/s² × dt 积分到速度，限速 15 m/s） |
| Critic 输出 | 4（=n_agents） | `CentralizedCritic` L724-736 | 一次前向输出 4 个 per-agent value |

## 3. MAPPO 组件实现要点

| 组件 | 实现 | 代码位置 |
|---|---|---|
| CTDE | Actor 只见自身 14 维 obs；Critic 见 22 维全局 state，输出 4 个 value | L689-736 |
| 共享参数 | **单一 Actor 被 4 个 follower 共享**（非独立网络）；Critic 亦单一 | L1627-1628 |
| GAE | γ=0.99, λ=0.95；终局 bootstrap 修正（terminated→0, truncated→V(last)） | `compute_gae` L752-774 |
| PPO clip | ε=0.2（ratio），value clip 0.5，2 epochs，grad-norm 1.0，actor lr 5e-5，critic lr 1e-4 | `ppo_update` L777-861 |
| 熵正则 | 系数 entropy_coef 是**元控制器可调参数**（0.001–0.02，默认 0.005），随训练相位动态变化 | L1680 |
| tanh 高斯 | mean=MLP(obs)，log_std 为**状态无关**可学参数（初始 0）；log-prob 带 tanh 修正项 | L689-721 |
| Advantage 归一化 | T×N 展平后全 batch 归一化（非 per-agent） | L804-805 |
| Buffer | 纯 on-policy：每 episode 一条 rollout，episode 边界立即 update（无 minibatch，全量 500×4 样本 2 epochs） | `build_rollout` L1524-1579 |

## 4. Reward 与终止（论文可复述口径）

- **逐 shaped 惩罚**：`-0.5·w_position·e_pos - 0.2·w_formation·e_pairwise`（长度单位米，量级大，早期 reward 约 -600）
- **阶梯 bonus（可叠加）**：e_pos<20m→+2，<10m→+5，<5m→+10，<2m→+20（`calculate_rewards` L548-551）
- **成功事件**：编队首次达成（5 步稳定 max_error≤20m）→ +10·w_success；跟踪期 max_error<5m → 每步 +5·w_success
- **终止**：terminated = leader 到达目标（<5m）；truncated = 500 步。碰撞（<10m）只记日志不进 reward（`collision_penalty=0`）
- **full-task success**：编队达成 ∧ leader 到达 ∧ 每 follower 跟踪有效率≥80%（误差≤30m 步占比）∧ 终局 max 误差≤30m（`step` L633-649）
- **w_formation 默认 0.8 生效**（非 1.0），且处于元控制器白名单内

## 5. 相位与元控制器（Ours 侧，供理解 baseline 差异）

| 机制 | 设定 | 代码位置 |
|---|---|---|
| 相位划分 | early→mid→late，**指标驱动**（非固定边界）：early→mid 需 ep≥200 且 (acq≥5% 或 e_pos≤60m) 连续 5 次；mid→late 需 ep≥600 且 acq≥80% 且 follow_err≤30m 连续 5 次 | `_update_training_phase` L1037-1084 |
| 咨询间隔 | early 30 ep / mid 50 / late 100，mid/late 另有性能退化触发 | `should_consult_phase_aware` L1086-1106 |
| 白名单 | early 只许动 entropy_coef+w_position；mid 全部 4 参数；late 只许 w_position+w_formation | BASE_CFG L152-157 |
| 安全层 | 数量上限→白名单→乘法换算（幅度×方向查表）→min/max 边界 clip→相位平滑 α→最小有效变化 1% 过滤 | `apply_safe_adjustment_audited` L1133-1205 |
| 匹配对照 | uniform_matched / random_matched 在与 Ours **完全相同的 episode、相同数量**的参数更新事件上重放（schedule 由 Ours 生成） | `load_matched_schedule` L1582-1594 |

## 6. 需向师兄确认的架构细节（≥6 项，附代码反推的答案）

| # | 待确认问题 | 代码证据与反推答案 |
|---|---|---|
| 1 | Actor/Critic 是否参数共享？论文 Method 如何表述"shared policy"？ | 代码：4 个 follower **共享同一个 Actor**（同一组权重），Critic 亦单网络输出 4 个 value。若论文写"independent actors"则与代码不符 |
| 2 | Critic 形式：一个中心网络输出 per-agent V，还是多个 critic？ | 单个 128-128 MLP，输出层 4 维，一次前向得 4 个 value（L724-736）。等价于 MAPPO 论文的 V_tot 分解方式之一，需确认论文表述 |
| 3 | truncated（500 步截断）时的 GAE bootstrap 是否用了 V(last_state)？ | 是（L788-794：last_terminated=False 时 bootstrap V(last_state)；terminated 时为 0）。这是常被写错的点，README "correction 10" 也强调 |
| 4 | tanh-squashed Gaussian 的 log-prob 修正是精确还是近似？ | 近似：`log_prob(raw) - log(1-a²+1e-6)`，且 evaluate 时用 atanh 反推 raw（clamp ±0.999999）。与 SAC 的精确修正差一个常数项，对 PPO ratio 无影响，但论文若声称"exact"需修正 |
| 5 | 熵系数 entropy_coef 可被 LLM 在线调整，是否在论文 PPO 公式中体现为时变 β_t？ | 是：每 episode 的 ppo_update 用 `monitor.current_params["entropy_coef"]`（L1680），baseline 下恒 0.005。论文需写清 Ours 的 β 是时变的 |
| 6 | reward 中阶梯 shaping bonus（+2/+5/+10/+20）是否属于论文正式 reward 定义？ | 在代码中且影响所有方法（L548-551）。若论文 reward 公式只写了三项加权和，则漏报了 shaping 项 |
| 7 | 训练环境起点是固定的（四角 ±100m），无随机化——训练/评估同分布，如何支撑泛化声明？ | E1 主实验 `randomize_start_positions=False`、`start_position_jitter=0`（L86-87），E4 才引入 ±30m jitter。论文的 robustness 声明范围需与此对齐 |
| 8 | "full-task success" 的四条件（编队∧到达∧80% 保持∧终局≤30m）在论文中如何形式化？未达成时 right-censor 到 2501 的统计口径是否一致？ | L633-649 定义；统计脚本对 None 用 2501 代理（`analyze_paired_statistics.py` L87）。需确认论文时间-事件指标的删失处理 |
| 9 | 匹配对照（uniform/random）依赖 Ours 先跑出的 schedule——若 Ours 某 seed 干预次数异常，对照也会被带偏，论文是否讨论此设计取舍？ | L1582-1594 硬依赖 `matched_schedule.json`。这是"schedule-matched"的定义，但意味着对照方法不能独立先跑 |
| 10 | leader 行为（编队前静止、编队后 10m/s 巡航、加速度限 2m/s²）是环境设定还是方法一部分？ | `update_leader` L473-497，纯环境逻辑，所有方法共享 |

## 7. 复现实验口径备忘

- 10 个预注册 seed：`configs/seeds.txt`（21, 618, 2024, 7, 999, 31415, 456, 789, 555, 8888）
- 每 run：2500 episode × ≤500 步；报告指标取**最后 100 episode** 窗口
- LLM：Ollama deepseek-r1:14b，temperature=0，timeout 120s；**Ollama 不可用时 LLM 方法直接 abort**（不静默降级）
- 统计：Wilcoxon 配对符号秩 + seed 配对 bootstrap 95% CI + rank-biserial + paired dz + 组内 Holm 校正
- 原文每 seed 训练 wall-clock ≈ 520-560 s（CUDA）；本次复现 CPU 实测约 0.45-1.0 s/episode
