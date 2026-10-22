# 精读 | SkyAgent: A lightweight LLM-driven reinforcement learning framework for adaptive cooperative path planning of two UAVs

> 精读日期：2026-10-20 ｜ 来源：Journal of King Saud University – Computer and Information Sciences（Springer, OA），Vol. 38, Art. 732，2026-08-21 出版
> 作者：Yuting Cao, Zheng Zhao, Jiekai Wu, Chia Hau Lee, Qi Wei Oung, Hoi Leong Lee（四个机构）
> 对我们的意义：**与我们端侧栈最近的系统近邻**（本地 Q4 量化小模型 + RL 低层控制 + 分层架构），Novelty Matrix b/c 行的又一数据点；其"Oracle 代理训练"工程技巧值得吸收。

---

## 1. 一句话总结

全本地运行的轻量 LLM（Qwen2.5-1.5B Q4_K_M，~1GB 显存，Ollama，无外部 API）作高层语义规划器，每 K=20 步输出 JSON 子目标坐标，PPO 作双机集中式低层控制器，在 2D 障碍场景中实现双 UAV 位置交换任务，96.7% 任务成功率、较纯 PPO 碰撞少 83%、样本效率 3.3 倍。

## 2. 架构

**两层分层，LLM 完全在端侧（实为笔记本 GPU 级）**：

- **高层**：LLM 语义规划器，每 K=20 步生成 JSON 子目标坐标；失败/超时/格式错时回退 Greedy——一个简易版"确定性降级层"；
- **低层**：PPO（Stable-Baselines3 MlpPolicy，52 维观测 → 4 维加速度指令），作为两机的集中式联合控制器；
- **训练技巧（全文最值得注意的工程点）**：LLM 太慢进不了训练循环 → 训练时用快速确定性势场"Oracle"规划器代理，评估时才换真 LLM。

## 3. 任务与基线

- 任务：100×100 m² 二维场地，两 UAV 位置互换，8 静态 + 3 动态障碍，需避障+互避；
- 基线 7 个：Random / Greedy / APF / A* / PPO / SAC / OraclePID；
- 30 seeds。

## 4. 关键数字

- 任务成功率 **96.7%**（vanilla PPO 80.0%、OraclePID 90.0%）；
- 碰撞比 PPO **少 83%**；路径最短（131.5 m）；
- 样本效率 **3.3×**（到 80% 阈值 55k vs 180k 步）；
- 30 障碍重动态场景 90.9% 成功率；
- **延迟**：模型前向 ~1.9 s/次，端到端（Ollama 往返+解析）~6.5 s；每 episode ~16 次调用（~100 s 开销，异步化不阻塞控制）；
- 消融：去传感器观测 **−32pp**、去子目标引导 **−28pp**、去 LLM **−18pp**。

## 5. 局限（作者自述）

理想化 2D 仿真；部署假设 GPU 级加速器而非 MCU 级微型无人机平台。

## 6. 与我们工作的关系（Novelty Matrix 影响）

| 维度 | 判定 |
|---|---|
| 撞车程度 | **中**。它占了"本地小模型 Q4 量化 + LLM 高层/RL 低层 + UAV 协同"的组合（Novelty b+部分 c），但与我们核心主张不冲突：无相位概念、无云-边链路（纯本地）、无量化档位×能力维度扫描（单档 Q4_K_M）、无通信约束/TTL/断连、无实机（2D 仿真 vs 我们双机 PX4）、无指令解析任务（输出的是子目标坐标而非控制原语/相位语法）。 |
| 定位差异句（建议） | "SkyAgent runs a single quantization tier of a local LLM as a high-level planner on a laptop-class GPU in 2D simulation; we characterize the quantization-tier × capability-dimension deployment boundary of edge instruction parsing and validate the phase protocol on real dual-drone PX4 closed loops under link constraints." |
| Novelty b 行更新 | 该行原判定"LMUCS 高度重叠（端侧 LoRA 小模型解析+Jetson+Tello）"。SkyAgent 是第二个数据点（端侧 1.5B Q4 规划+GPU 本地），趋势确认：**端侧小 LLM 上机这件事正在快速扩散，我们的护城河必须在"相位条件化 + 档位×维度边界 + 通信受限协议"上**——与既有结论一致但紧迫性上升。 |
| 可吸收的工程技巧 | **Oracle 代理训练**：云端 LLM/相位引擎太慢进不了 MARL 训练循环 → 训练期用确定性代理（规则相位切换器），评估期换真实 LLM 输出。这直接适用于我们 v7 训练（若尚未做）。学它的报告方式：明确声明训练/评估用不同规划器及理由。 |
| 延迟数字的引用价值 | 其 1.5B Q4 前向 1.9s / 端到端 6.5s（RTX 5060 笔记本）可与我们的 Jetson 延迟矩阵（Phi-2 Q4-Q8）并列引用，说明"延迟是端侧 LLM 系统的一等约束"——我们 Jetson 数据更嵌入式、更苛刻，占优。 |
| 期刊层级 | JKSU-CIS（Springer OA，中等偏上）。作为系统近邻引用合适，不构成投稿威胁。 |

## 7. 可借鉴的写法/实验设计

- **失败回退作为一等机制报告**（Greedy fallback on failure/timeout/malformed）+ 消融量化（−18pp）：我们的 TTL 降级/安全悬停同族，可按"回退触发率 × 回退后任务保全率"两个指标报告，比只报成功率信息量大；
- **异步化声明**：明说 LLM 开销 ~100s/episode 但异步不阻塞控制——我们端侧解析周期与控制周期的解耦（时间尺度分离）可用同样句式；
- **干净的消融排序**（−32/−28/−18pp 一目了然）：学其把消融做成单变量递减条形叙事。

> 依据：Springer 文章页（redirect 后抓取）；数字来自 abstract 与正文实验节。
