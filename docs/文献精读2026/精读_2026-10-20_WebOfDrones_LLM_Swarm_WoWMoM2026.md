# 精读 | Say the Mission, Execute the Swarm: Agent-Enhanced LLM Reasoning in the Web-of-Drones

> 精读日期：2026-10-20 ｜ 来源：arXiv 2605.03788（2026-05-05）｜ **WoWMoM 2026**（27th IEEE WoWMoM, pp. 139–148, DOI: 10.1109/WoWMoM69805.2026.00027），CC BY 4.0
> 作者：Andrea Iannoli, Lorenzo Gigli, Luca Sciullo, Angelo Trotta, Marco Di Felice（博洛尼亚大学组）
> 对我们的意义：**LLM→集群控制接口层的最新直接竞品/必引**；其实验发现（裸 LLM 不可靠、token 与质量不相关、小模型长时程失败）是我们安全层与相位压缩论点的现成外部证据。

---

## 1. 一句话总结

把无人机、传感器、服务全部暴露为 W3C Web of Things 标准物（WoT Things），LLM 智能体经 MCP 网关以语义级工具调用（而非代码生成）闭环控制 10 机 ArduPilot 仿真集群；六个 SOTA LLM 的系统评测表明：通用 LLM 无 grounding 与运行时护栏时连简单集群任务都不可靠完成，且 token 消耗与执行质量无相关性。

## 2. 架构（三层）

1. **W3C WoT 生态**：所有资源（无人机/传感器/任务状态/服务）以机器可读 Thing Description（affordances: properties/actions/events）暴露；Thing Directory（Zion 实现）支持运行时发现与**晚绑定**；三类 Thing（Physical/Virtual/Service）；UAV Servient 将 WoT affordance 翻译为 MAVLink→ArduPilot SITL；
2. **MCP WoT 网关**（NestJS）：LLM 与 WoT 生态的**唯一桥**，提供资源发现与中介式交互，Zod 校验输入输出 schema，异步 action/completion 分离；
3. **智能体**：LLM + Agent Core（持久 core prompt 设定角色/交互模型/不变量："mandatory state verification, safe termination conditions, exclusive use of MCP-mediated interactions"）+ **运行时护栏**（从重复失败模式中经验性提炼的动态注入 prompt 片段）+ 辅助工具（send_drones_to_positions、wait_until_armed 等高频模式封装）。

**规划工具**：plan_area_coverage（网格划分+按 FOV 反解高度 a = r_cell/tan(FOV/2)）、plan_drone_formation（line/star/circle 槽位）。

**三条声称的新颖性**：N1 硬件无关互操作；N2 实时状态检索；N3 无代码生成的闭环推理（"closed-loop reasoning with feedback incorporated into subsequent steps"）。

## 3. 实验设置

10 台 ArduPilot SITL 多旋翼、四个配置（三类任务）、每配置 10 次、非确定性仅来自 LLM 推断：
1. 带规划器的区域覆盖（400×300 m，严格判据：全部槽位到达+ disarm + 零碰撞）；
2. 无规划器覆盖消融（弱判据）；
3. 星型编队（对抗性槽位分配最大化位移，5 m 间距，考避碰）；
4. 智能灌溉（3 湿度+1 温度传感器读数，均值湿度 ≤57% 或均温 ≥30°C 才触发；含安全终止）。

模型：GPT 5.2、DeepSeek V3.2、GLM 4.7、Grok 4.1 Fast、Claude Haiku 4.5、Qwen3 8B。评分函数不暴露给 LLM。

## 4. 关键结果

| 任务 | 排名与成功率 |
|---|---|
| 覆盖（有规划器） | GLM **100%** > Grok 70% > DS 60% > GPT 20%（GPT 反复不满足降落/disarm 要求） |
| 覆盖（无规划器） | GPT 100%、GLM 70%、DS 60%、Grok/Qwen 0%；去工具使 GLM −30pp；有工具更快（GLM ≈250s vs ≈351s） |
| 编队 | GPT 60% > GLM 50% > DS/Qwen 20%、Grok/Claude 0%；GPT 3 次碰撞 vs GLM 2 次 |
| 灌溉 | GLM 90% > Grok 50% > GPT 40% > DS 30%、Claude/Qwen 0%；GPT 过度触发、DS 触发不足 |

**三条核心发现**：
1. 通用 LLM 无显式 grounding/执行支持时**连简单集群任务都不能可靠执行**；
2. 任务特定规划工具+运行时护栏**显著**提升鲁棒性（但跨模型不一致——GPT 带规划器反而更差）；
3. **token 用量与执行质量/可靠性无相关性**（"no clear correlation ... between mission success rate and token consumption"）。

**失败模式与护栏**：未验证状态就宣称完成 / 停滞（重复无进展工具调用）/ 有无人机仍在空中或 armed 就尝试终止 → 护栏动态注入"重新评估状态并补齐步骤"指令修复；辅助工具降低小模型的调用冗长与记账错误。

## 5. Related Work 定位

把自己放在"带宽优化 / 位置提取（DDaS、Swarm-GPT、FlockGPT）/ 代码生成"三类之外：反对代码生成路线（"generated code remains static and does not incorporate real-time feedback"），主打标准化 WoT/MCP grounding + 闭环。**未涉及**：端侧部署、量化、通信受限/陈旧消息、学习型集群控制（编队是规划器槽位而非 RL 策略）、实机。

## 6. 局限（作者自述+精读者补充）

仿真 only（ArduPilot SITL）；灌溉决策规则简化；规划工具收益跨模型不一致且未解释；护栏是经验性 prompt 补丁（无形式化保证）；无通信约束建模（LLM-网关假设可靠本地链路）；无实机。

## 7. 与我们工作的关系（Novelty Matrix 影响）

| 维度 | 判定 |
|---|---|
| 撞车程度 | **低-中**。它做的是"云端/地面 LLM 经标准化接口直接驱动仿真集群"——不碰我们的核心主张（相位语义瓶颈、云-边协议、量化部署边界、TTL）。但其 N3"无代码生成、语义级闭环"与我们"LLM 输出结构化相位指令而非代码"在修辞上同族 → 必引并划界。 |
| 现成外部证据 | **三条发现都是我们的论据**：(1) 裸 LLM 不可靠 → 支持确定性安全层必要性（与 PKEG 四层校验同引，组成"prompt 级护栏（WoD）vs 结构化校验（PKEG）vs 确定性协议（我们）"的谱系）；(2) token 与质量无关 → 直接支持"压缩到相位语法不必损失能力"的压缩收益论证（G4 +55pp 的外部佐证）；(3) 8B 级小模型无脚手架长时程全败（Qwen3 8B 两个任务 0%）→ 支持云-边分工：端侧小模型需要结构化相位输入而非 raw prompting。 |
| 差异化句（建议写入 Related Work） | "Web-of-Drones evaluates cloud-side LLMs driving simulated swarms through standardized tool interfaces under an ideal link; our work addresses the constrained cloud–edge regime, where the semantic payload itself must be compressed into a verifiable phase protocol, executed by quantized edge models under staleness and disconnection." |
| 行动项 | ① 加入必引必比清单（LLM-swarm 接口族）；② Intro/讨论引其 token 无关性发现为 G4 佐证；③ 安全层相关工作按"护栏谱系"重组（WoD→PKEG→ours）。 |

## 8. 可借鉴的写法/实验设计

- **失败模式驱动的护栏叙述**：先列三类观察到的失败模式、再给机制——比直接描述机制可信；我们的安全层可按此重组（先展示无保护时的危险输出实例，再给分轴数值溯源）；
- **多 LLM 横评作为证据生成器**：六个模型同台暴露"能力≠token≠安全"，为接口层主张提供系统性外部证据——我们不需要横评六个模型，但可引它替代；
- **严格判据 vs 弱判据分离**（覆盖任务两档判据）：我们 P0-4 验收也可分"严格成功"（全约束+零危险动作）与"弱完成"两档报告，学 Li et al. 的诚实与 WoD 的判据分级；
- **评分函数不暴露给 LLM** 的评测卫生声明，一句就值得抄。

> 依据：arXiv abs + HTML 全文（2605.03788v1）抓取；数字来自原文实验节四个任务表与 token 分析。
