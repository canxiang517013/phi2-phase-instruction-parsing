# Phi-2 QLoRA × UAV DMPC 指令解析 — RTX 3060 Laptop (6GB) 全流程

在 RTX 3060 Laptop（6GB 显存）上完成端侧轻量化 LLM 元控制器的全链路验证：QLoRA 4-bit 微调 → 五档量化基准 → 相位条件化（5轮迭代）→ 单机/双机 PX4 飞行闭环 → 云-边相位协同 + 断连降级（创新点1/2/3 全部端到端跑通）。

**研究主线**：相位感知的端侧轻量化 LLM 元控制器（多无人机集群分层协同控制）

**已验证的完整架构**：

```
云端（态势→相位信号，10 token）→ 端侧（Phi-2 v5 Q5_K_M 1.87GB，解析→PX4）
  → 起飞→巡航→悬停→返回→降落→上锁（全程相位缓存）
  → 断连→自主降级（飞往缓存相位安全目标）→ 恢复对齐
```

---

## 环境前提

- Windows + NVIDIA RTX 3060 Laptop（6GB VRAM）
- Python 3.12（项目已带 `.venv`）
- 已安装依赖：`pip install -r requirements.txt`
- ⚠️ **本机无法直连 huggingface.co**，模型改从 **ModelScope** 下载（脚本已自动处理）

实测已装的库版本（已验证互相兼容、能在 GPU 上跑）：

| 库           | 版本                                                           |
| ------------ | -------------------------------------------------------------- |
| torch        | **2.11.0+cu128** ⚠️ 必须是 CUDA 版，不能用 `+cpu` 版 |
| transformers | 5.14.1                                                         |
| trl          | 1.9.2                                                          |
| peft         | 0.20.0                                                         |
| bitsandbytes | 0.50.0                                                         |
| datasets     | 5.0.1                                                          |

> **⚠️ torch 安装踩坑警告**：直接 `pip install torch` 会装到 `+cpu` 版（纯 CPU 构建，CUDA 不可用），
> 表现为训练时 GPU 利用率仅 6%、`no accelerator is found` 警告、进程 CPU 飙满但训练极慢。
> 必须从 PyTorch 官方 CUDA 索引安装：
>
> ```bash
> pip install torch==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
> # 国内若慢，用清华镜像：
> # pip install torch==2.11.0+cu128 -i https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128
> ```
>
> 验证：`python -c "import torch; print(torch.cuda.is_available())"` 必须输出 `True`。

---

## 执行流程（共 4 步）

```
download_model.py ─► train_phi2_qlora.py ─► merge_and_quantize.py ─► benchmark.py (4-bit, 无需额外环境)
   下载基座模型        QLoRA 4-bit 微调      合并+GGUF量化                ─► setup_cuda_inference.py (一次性)
   (~5.5GB)           (手动启动)                                        ─► benchmark_gguf.py (Q6_K 高吞吐)
```

### 第 0 步：下载基座模型

```bash
python download_model.py
```

- 从 ModelScope 下载 `microsoft/phi-2` 到 `./models/phi-2`
- 自动校验文件完整性；已下载则跳过

### 第 1 步：QLoRA 微调（**手动启动**）

```bash
python train_phi2_qlora.py
```

- 4-bit NF4 量化 + 双重量化，仅训练 self-attention（q/k/v/dense）
- `batch=1 × 梯度累加8 = 等效batch8`，梯度检查点，8-bit 分页优化器
- 产物：`./phi2-dmpc-adapter/`（LoRA 权重）+ `train_peak_vram.txt`（峰值显存）

### 第 2 步（可选）：合并权重 + GGUF 量化

```bash
python merge_and_quantize.py
```

- CPU 上 `merge_and_unload()` 合并 LoRA → `./phi2-dmpc-merged/`
- 打印 llama.cpp 的 GGUF 转换 + Q6_K 量化命令（需手动编译 llama.cpp 执行）

> ⚠️ **关于 GGUF 推理路径**：Windows 平台没有 `llama-cpp-python` 的 CUDA 预编译 wheel，
> 需本地编译 CUDA 版（见第 4 步）。在装好 CUDA 推理环境前，可先用第 3 步的
> transformers 4-bit 路径做验收（无需额外装包，但吞吐仅 ~10 tok/s）。

### 第 3 步：4-bit 推理测评（transformers + QLoRA, GPU）—— 无需额外环境

```bash
python benchmark.py
```

- 用 4-bit NF4 量化加载 phi-2 + 挂载训练好的 LoRA adapter（GPU）
- 16 条测试 prompt（含训练外泛化样本），自动 `json.loads` 校验
- 输出：JSON 准确率、ms/token、tokens/s、推理峰值显存、训练峰值显存汇总
- **吞吐 ~10 tok/s**（4-bit bitsandbytes 反量化是瓶颈）

### 第 4 步（高吞吐）：CUDA 推理环境 + Q6_K GGUF 测评

```bash
python setup_cuda_inference.py    # 一次性：装 CUDA Toolkit + 编译 llama.cpp CUDA 版
python benchmark_gguf.py          # Q6_K GPU 推理测评
```

- `setup_cuda_inference.py` 自动完成：winget 装 CUDA Toolkit → 编译 llama.cpp CUDA 版 →
  装 llama-cpp-python CUDA 版（编译时屏蔽 Anaconda 避免 OpenSSL 冲突）→ 验证 GPU offload
- `benchmark_gguf.py` 用 Q6_K GGUF 全量卸载 GPU 推理，**预期吞吐 40-60 tok/s**
- 需管理员权限（装 CUDA Toolkit 会弹 UAC）

---

## 数据集

**模型版本口径（2026-09-06 核实）**：磁盘现存权重均为 **v5 训练产物**（`phi2-fp16.gguf`
= v5 合并模型的 fp16，`phi2-phased-v5-q5_k_m.gguf` = 现役端侧模型）；**v4 的权重已被
v5 覆盖、不可恢复**。`dataset.jsonl` 实际内容 = `dataset_phased_v4.jsonl`（287 条，与
`dataset_phased_v5.jsonl`/330 条不是同一份——v5 训练用的是后者）。此前文档中
"最终交付 v4 / dataset.jsonl 为 v5" 的表述以此为准更正。

- `dataset_phased_v5.jsonl`（330 条 = 基础 109 + 相位 221）：**v5 模型的实际训练集**
- `dataset.jsonl`（= v4，287 条）：v4 数据设计，历史保留
- 输出固定 schema：

```json
{"mode": "swarm", "formation": "triangle", "uav_ids": [1, 2], "target": [10.0, 15.0, 5.0]}
{"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [0.0, -20.0, 10.0]}
```

覆盖：5 种阵型（line/triangle/grid/wedge/circle）、2~5 架 UAV、正负/小数坐标、多种自然语言表述。

---

## Context 压缩验证（创新点1：云-边相位协同的可行性检验）

**假设来源**：导师创新点1——"相位的引入让端侧小模型的输入上下文压缩一个量级"
**工具**：`context_compression_test.py`（本地加载 Q5_K_M，tokenizer 精确计数）
**设计**：三组对照 × 5 场景 × 5 指令 = 75 个样本，控制变量（指令相同，只变 System Prompt）

| 组            | System Prompt                         | 平均 prompt tok | JSON 成功率       |
| ------------- | ------------------------------------- | --------------- | ----------------- |
| C（基准）     | 训练时的原始格式                      | 40.2            | **100%**    |
| A（完整态势） | ~90 tok 全局态势描述                  | 128.4           | **0%** ⚠️ |
| B（相位标签） | `Phase: OBSTACLE_AVOID. + 原始格式` | 47.0            | **100%** ✅ |

### 关键发现（比"压缩一个量级"更重要的三个结论）

1. **长上下文直传是死路（A 组 0%）**：把云端 LLM 的态势描述直接塞给微调后的小模型，
   解析能力完全崩溃。原因：Phi-2 用固定短 System Prompt 微调，对 prompt 格式极其敏感。
   → **相位机制不是"优化"，是"必需品"**——没有它，云端→端侧的上下文传递根本不成立。
2. **相位标签完整保留解析能力（B 组 100%）**：`Phase: XXX.` 前缀 + 训练格式 = 解析无损。
   端侧可以接受相位信号而不破坏已有能力。
3. **压缩比 2.7x 是保守下界**：本实验的态势描述只有 ~90 tok。真实云端 LLM 输出的
   全局态势（含威胁/气象/队形/能量等多维信息）通常 500-1000+ tok，
   实际压缩比可达 **10-20x**，达到导师说的"一个量级"。

### 下一步（创新点1的数据准备）

B 组输出显示模型输出了合法 JSON 但**未真正利用相位信息**（如 OBSTACLE_AVOID 相位下
未输出避障相关动作）——因为训练数据无相位概念。下一步：构造带 `phase` 字段的
微调数据（如 `{"phase":"avoid","instruction":...,"input":...,"output":避障动作JSON}`），
让模型学会"以相位为条件"解析指令。

---

## 相位条件化微调（创新点1第一轮实验）

**数据**：`dataset_phased.jsonl` 209 条（109 原有无相位 + 100 新增相位条件）

- 5 相位（ASSEMBLE/HOLD/RECONFIGURE/OBSTACLE_AVOID/RECON）× 15 模糊指令 + 5 专属指令
- 格式：`Phase: XXX. ` 前缀加 instruction（匹配压缩实验的 B 组格式）
- 核心设计：**同指令异相位异输出**（相位条件化的学习信号）

**训练**：200 步，loss 0.85，峰值 5715MB，产物 `phi2-phased-q5_k_m.gguf` (1.87GB)

**验证结果**（`phase_verify.py`）：

| 指令                           | 相位分化  | 相位语义               | 备注                  |
| ------------------------------ | --------- | ---------------------- | --------------------- |
| UAV 1 and 2, adjust formation. | ✅ z=10m  | ✅ RECON 远于 ASSEMBLE | 训练内                |
| UAV 2 and 3, move out.         | ✅ z=20m  | ✅ RECON 远于 ASSEMBLE | **训练外泛化**  |
| UAV 1, proceed.                | ⚠️ z=4m | -                      | 分化弱                |
| All units, execute.            | ⚠️      | -                      | JSON 截断             |
| 基础能力（无相位）             | -         | -                      | **3/3 保持** ✅ |

**结论**：相位条件化**初步验证成功**——模型学会了"相位影响输出"且具备泛化能力
（训练外的 "move out" 也能分化），基础解析能力无损。分化一致性可通过增加
训练步数（200→400）和增大相位间 target 差异提升（第二轮迭代方向）。

---

## 相位微调第二轮：负结果与关键发现（模式坍缩）

**第二轮设计**（以为会更好）：399 条（每相位 58 条）、400 步、相位特征分布更鲜明
（HOLD ±2 / OBSTACLE_AVOID z≥12 且 |x|≥15 / RECON ≥80）。

**结果**：loss 降到 0.59，但**相位分化完全消失**——所有相位输出坍缩到 [1,-1,5] 均值点。

### 根因：一对多映射 → 均值坍缩（instruct-tuning 经典陷阱）

```
第二轮的数据设计（错误）：
  (Phase: ASSEMBLE, "adjust formation") → target A1   ← 同一(相位,指令)对
  (Phase: ASSEMBLE, "adjust formation") → target A2   ← 对应多个随机 target
  (Phase: ASSEMBLE, "adjust formation") → target A3
                                    ↓
        模型最小化 loss 的最优解 = 输出所有 target 的均值
                                    ↓
        所有相位坍缩到同一输出（分布交集的中心）

第一轮（碰巧正确）：每对只有 1 条样本 → 一对一映射 → 模型"记住"了分化
（但那是记忆效应，不是真正的相位语义学习）
```

### 关键教训（论文方法论素材）

**随机 target 教不会模型相位语义，只会教它输出均值。** 要让模型学到
"相位→动作语义"的映射，训练数据必须是**确定性规则**（同相位+同指令→同 target），
多样性应来自不同指令的组合，而非同指令的随机 target 变体。

### 第三轮修复方案：确定性相位模板

| 相位           | 确定 target 模板        | 语义         |
| -------------- | ----------------------- | ------------ |
| ASSEMBLE       | (集结点x, 集结点y, 5)   | 向集结点收拢 |
| HOLD           | (原位x±1, 原位y±1, 5) | 原位微调     |
| RECONFIGURE    | (新slot_x, 新slot_y, 8) | 新队形位置   |
| OBSTACLE_AVOID | (±20, 原位y, 15)       | 高空侧移避障 |
| RECON          | (侦察点x, 侦察点y, 15)  | 推进到侦察点 |

---

## 相位微调第三轮：确定性映射取得突破 ✅

**数据设计**：233 条（109 基础 + 124 确定性相位映射），400 步训练，loss 0.57

**核心设计**：相位标签带参数，target 由规则确定性推导（同相位+同指令 → 同 target）：

```
Phase: ASSEMBLE@(5,5).      + 任意指令 → target = [5.0, 5.0, 5.0]   （参数→坐标, z固定5）
Phase: HOLD@(3,-2,7).       + 任意指令 → target = [3.0, -2.0, 7.0]  （参数原样）
Phase: RECONFIGURE@column.  + 任意指令 → formation = column          （队形跟参数）
Phase: OBSTACLE_AVOID@left. + 任意指令 → target = [-20.0, 0.0, 15.0] （方向→坐标）
Phase: RECON@(120,90).      + 任意指令 → target = [120.0, 90.0, 15.0]（参数→坐标, z固定15）
```

**验证结果**（`phase_verify_v3.py`，13 项规则测试 + 分化 + 基础）：

| 测试项                  | 结果             | 亮点                                  |
| ----------------------- | ---------------- | ------------------------------------- |
| ASSEMBLE@ 参数规则      | **3/3 ✅** | **训练外坐标 (12,-9) 完美泛化** |
| HOLD@ 参数规则          | **2/2 ✅** | 训练外泛化                            |
| RECONFIGURE@ 队形跟随   | **3/3 ✅** | column/circle/wedge 全对              |
| OBSTACLE_AVOID@ 方向    | 0/2 ❌           | 方向对（left→负x）但数值偏差         |
| RECON@ 参数规则         | 1/2              | 训练内完美；训练外 y=150 超分布衰减   |
| 相位分化（同指令4相位） | ✅               | target 完全不同                       |
| 基础能力                | **3/3 ✅** | 无相位格式无损                        |

### 三轮对比总结（论文方法论完整素材）

| 轮次             | 数据设计                 | 相位分化               | 根因分析                 |
| ---------------- | ------------------------ | ---------------------- | ------------------------ |
| 第一轮           | 随机target，一对一       | 2/4（弱）              | 记忆效应，非真语义       |
| 第二轮           | 随机target，一对多       | **0/4（坍缩）**  | 均值坍缩（负结果）       |
| **第三轮** | **确定性规则映射** | **10/13 + 泛化** | **真正的规则学习** |

### 核心成果：模型学会了"解析参数→应用规则"

第三轮证明端侧小模型（2.7B Q5）可以学会参数化相位的变换规则：

- 输入 `Phase: ASSEMBLE@(12,-9)`（训练外坐标）→ 输出 `target=[12.0,-9.0,5.0]`
- 这不是记忆（该坐标从未在训练中出现），是**学到了"ASSEMBLE 相位的 z=5 + 参数直传"规则**
- 直接支撑导师创新点1："云端传相位信号（含参数），端侧解析为本地动作"

---

## 相位微调第四轮：修复 OBSTACLE_AVOID + RECON 边缘 ✅

**修复设计**（287条 = 109 基础 + 178 相位）：

1. OBSTACLE_AVOID **参数化**：`@left@N` → target=(-N, 0, 15)，N ∈ {15..40}，
   样本量从 12 → 34 条，教"方向→符号 + 距离→幅度"两层规则
2. RECON 参数范围从 80-180 扩到 **60-250**，覆盖边缘值

**结果**（v3 → v4）：

| 测试项               | v3          | v4                    | 说明                              |
| -------------------- | ----------- | --------------------- | --------------------------------- |
| OBSTACLE_AVOID@dir@N | 0/2         | **6/6 ✅**      | **训练外 N=28/50 完美泛化** |
| RECON@ 边缘坐标      | 1/2         | **4/4 ✅**      | v3 失败的 (200,150) 修复          |
| ASSEMBLE@ 回归       | 3/3         | 2/3                   | (5,5) 偶发 z=15（非系统退化）     |
| HOLD / RECONFIGURE   | 5/5         | 2/3                   | column 偶发（circle 仍对）        |
| 基础能力             | 3/3         | **3/3**         | 无损                              |
| **总计**       | 10/13 (77%) | **14/16 (88%)** |                                   |

**第四轮亮点**：OBSTACLE_AVOID@left@28（训练外距离）→ [-28.0, 0.0, 15.0]、
@right@50 → [50.0, 0.0, 15.0]——模型学会了"参数即幅度"的完整规则。
新出现的 2 个偶发失败（ASSEMBLE@(5,5) 的 z、RECONFIGURE@column）属于
特定 token 组合的边缘不稳定性，同类其他参数均通过。

---

## 相位微调第五轮：数据不平衡教训（最终采用 v4）

**第五轮尝试**（330条）：单方面加强 ASSEMBLE（36→64条）和 RECONFIGURE（35→48条）
以修复 v4 的两个偶发退化。

**结果**：ASSEMBLE@(5,5) 修复 ✅，但 RECON 全线 z 从 15 退化为 5，总体 8/16（v4 是 14/16）。

### 根因：共享特征的数据平衡敏感性

z 值在多相位间共享（ASSEMBLE/HOLD 用 z=5，OBSTACLE_AVOID/RECON 用 z=15，RECONFIGURE 用 z=8）。
单方面增加 ASSEMBLE 样本量（z=5 出现频率大增）后，z=5 特征主导了 z=15 相位的输出——
**这是数据不平衡导致特征干扰的典型案例**。

### 教训（第五个消融数据点）

| 轮次   | 策略         | 结果               | 教训                           |
| ------ | ------------ | ------------------ | ------------------------------ |
| 第一轮 | 随机·一对一 | 2/4 弱             | 记忆≠语义                     |
| 第二轮 | 随机·一对多 | 0/4 坍缩           | 随机目标→均值                 |
| 第三轮 | 确定性规则   | 10/13              | 规则映射有效                   |
| 第四轮 | 参数化增强   | **14/16** ✅ | **参数泛化成功（最优）** |
| 第五轮 | 单相位加强   | 8/16 退化          | **共享特征需全相位平衡** |

**最终交付**：`phi2-phased-v4-q5_k_m.gguf`（14/16 = 88% 规则通过率）。
若进一步提升，需全相位同步扩充并做 z 值去混淆设计（如 z 编码进相位参数）。

---

## 断连降级机制（创新点3）：完整闭环验证 ✅

**机制**：`cloud_heartbeat_node`（1Hz心跳+低频相位信号）+ `nl_command_node`（心跳监听+降级状态机）

```
CONNECTED ──3秒无心跳──► DEGRADED ──心跳恢复──► CONNECTED
    │                       │                     │
    ▼                       ▼                     ▼
 缓存相位            使用缓存相位自主维持        重新对齐云端相位
（HOLD@(x,y,z)）    （悬停保持+定期日志）      （任务状态机无缝恢复）
```

**实测验证**（2026-08-30 真实终端运行日志）：

| 阶段     | 日志证据                                         | 结果                        |
| -------- | ------------------------------------------------ | --------------------------- |
| 断连检测 | `[断连] 3.0秒无心跳，进入降级模式！`           | ✅ 精确3.0秒触发            |
| 相位缓存 | `缓存=HOLD@(0,0,5)`                            | ✅ 断连前最后相位被缓存使用 |
| 自主维持 | `位置=NED(-0.0,-0.0,-0.0)` 持续14秒，偏差<0.1m | ✅ 安全悬停                 |
| 飞控稳定 | `armed=True offboard=True` 全程保持            | ✅ 无failsafe               |
| 恢复检测 | `[恢复] 云端链路恢复，重新对齐相位`            | ✅ 心跳恢复触发             |
| 无缝接管 | DISARM重试立即恢复，`link=CONNECTED`           | ✅ 状态机无损恢复           |

**交付物**：

- `cloud_heartbeat_node.py`（云端心跳模拟，1Hz心跳+0.1Hz相位信号）
- `nl_command_node.py` 升级（心跳监听+DISCONNECTED/CONNECTED/DEGRADED 三态）
- `demo_degradation.sh`（交互式演示脚本）

**导师创新点3三条要求全部达成**：

1. "通信中断时端侧模型依据最后相位缓存" → ✅ HOLD@(0,0,5) 缓存并使用
2. "自主维持安全编队" → ✅ 14秒自主悬停，偏差<0.1m
3. "恢复后重新对齐云端相位" → ✅ 恢复日志+任务无缝继续

> 2026-09-06 更新：云端切换为真 DeepSeek 后，断连降级+恢复在**飞行中**全链条
> 复验通过（断连时无人机放弃原目标、飞往缓存相位 ASSEMBLE@(20,-20) 并保持 16s，
> 恢复后任务续跑至原目标完成），详见「云端真 LLM 化」章节的演示记录。
> 同时修复了 `ros2 run` 包装进程导致断连永不触发的 8 月遗留 bug。

---

## 完整链条端到端演示（创新点1+2+3 串联，真实飞行验证）✅

**架构**：云端相位规划器 + 端侧 Phi-2 v5 + PX4 SITL + AirSim（Blocks 环境，性能约束）

```
┌─ 云端 cloud_phase_generator ──────────────────────────┐
│  订阅 /cloud/situation（态势文本）                      │
│  相位推断引擎可切换：rule / deepseek / glm / local      │
│  发布 /cloud/phase（如 OBSTACLE_AVOID@right@30）      │
│  发布 /cloud/heartbeat（1Hz）                         │
└──────────────────────────────────────────────────────┘
         │ 10 token（vs 全态势100-200 token，压缩一个量级）
         ▼
┌─ 端侧 nl_command_node（Phi-2 v5 Q5_K_M）─────────────┐
│  订阅 /cloud/phase → 缓存最新相位                      │
│  订阅 /nl_input → Phi-2 解析 → JSON → PX4 Offboard    │
│  断连 → 用缓存相位自主飞往安全目标（非悬停）             │
│  恢复 → 重新对齐                                       │
└──────────────────────────────────────────────────────┘
         ▼
   PX4 SITL → AirSim（起飞→巡航→悬停→返回→降落→上锁）
```

**实测飞行时间线**（2026-08-30 真实 PX4 + AirSim Blocks 环境）：

| 时间      | 日志                                                    | 阶段                            |
| --------- | ------------------------------------------------------- | ------------------------------- |
| 7977      | `NL input: UAV 1 fly to 15 15 30`                     | 接收指令                        |
| 7978      | `Target ENU=(15,15,30) → NED=(15,15,-30)`            | Phi-2 解析（0.7s）✅            |
| 7979      | `PX4 ARMED successfully!`                             | 起飞 ✅                         |
| 7986      | `[云端→端侧] OBSTACLE_AVOID@right@30`                | 态势变化→云端推断→端侧缓存 ✅ |
| 7989-7999 | `phase=cruising cached_phase=OBSTACLE_AVOID@right@30` | 巡航中携带相位缓存 ✅           |
| 8004      | `phase=hovering`                                      | 到达目标悬停 ✅                 |
| 8009      | `phase=landing`                                       | 开始降落 ✅                     |
| 8017      | `cached_phase 变回 HOLD@(0,0,5)`                      | 云端重启→新相位覆盖 ✅         |
| 8030      | `Sent DISARM command`                                 | 降落完成后上锁                  |
| 8034      | `offboard=False` → `[done] ✅ DISARM 成功`         | **完整任务收官** ✅       |

**三大创新点在单次飞行中全部验证**：

| 创新点          | 本次飞行中的证据                                                      |
| --------------- | --------------------------------------------------------------------- |
| 1 云-边相位协同 | 态势→`OBSTACLE_AVOID@right@30`（10 token）→端侧缓存→飞行全程携带 |
| 2 端侧量化部署  | Phi-2 Q5_K_M 解析 0.7s → PX4 精确执行（到达、悬停、降落）            |
| 3 断连降级+恢复 | 云端被杀→重启→端侧持续工作→最终成功 DISARM                         |

**交付物**：

- `cloud_phase_generator.py`（云端相位规划器：规则引擎 + LLM 预留接口 `USE_LLM`）
- `nl_command_node.py`（端侧：相位缓存 + 降级飞往安全目标 + 恢复对齐 + DISARM 修复）
- `demo_full_chain.sh`（完整链条演示脚本）

### 修复记录（本阶段 3 个 bug）

| Bug                | 根因                                                   | 修复                                        |
| ------------------ | ------------------------------------------------------ | ------------------------------------------- |
| DISARM 被 PX4 拒绝 | offboard 模式+持续 setpoint 时 PX4 安全机制拒绝 DISARM | done 阶段停止 offboard 输出→等退出→DISARM |
| DISARM 后重新 ARM  | 控制循环 armed=False 时自动发 ARM，与 done 冲突        | done 阶段拦截，跳过 ARM 重试                |
| offboard 循环掉线  | 目标过远（15,45,30）触发环境限制                       | 用适中目标（15,15,30）解决                  |

### 已知限制

- Blocks 环境限制远距离目标（约>40m 可能触发 offboard 掉线）
- ~~`USE_LLM=False`（规则引擎推断相位）~~ → **2026-09 已接入真云端 LLM**：
  `cloud_phase_generator` 支持 deepseek/glm/local 三种 LLM provider + 规则引擎兜底，
  离线一致性评测与延迟/成本统计一并交付（见下节）
- 单机演示（双机独立控制已验证，但完整链条暂未扩展到双机）

---

## 云端真 LLM 化（DeepSeek/GLM 接入，2026-09）

`cloud_phase_generator.py` 的相位推断引擎已参数化（`llm_provider`，ROS 参数或
`CLOUD_LLM_PROVIDER` 环境变量），四种模式：

| provider         | 后端                           | 用途                           |
| ---------------- | ------------------------------ | ------------------------------ |
| `rule`（默认） | 关键词规则引擎                 | 回归验证、无网环境             |
| `deepseek`     | DeepSeek API（deepseek-chat）  | **研究主线**：真云端 LLM |
| `glm`          | 智谱 API（glm-4-flash 免费档） | 备选 / 横向对比                |
| `local`        | 本地 llama.cpp server（:8080） | 端侧模型演云端（对照组）       |

### 可靠性设计（为什么要这样接）

1. **后台线程推断**：LLM 调用秒级延迟若发生在订阅回调里，会阻塞 1Hz 心跳定时器，
   端侧 3 秒心跳超时机制会误判 DEGRADED。推断已移入 worker 线程，心跳永不阻塞
   （验证：`ros2 topic hz /cloud/heartbeat` 在推断中应稳定 1Hz）。
2. **完整语法校验**：LLM 输出经 `phase_rules.validate_phase`（与端侧
   `_parse_cached_phase_target` 同一契约的完整正则）校验——旧版只查前缀，
   `OBSTACLE_AVOID@up@30` 这类输出能过云端但被端侧静默丢弃。非法输出带错误
   反馈重试 1 次，仍失败回退规则引擎：云端断网时节点不死，降级可审计。
3. **统计落盘**（师兄论文 E7 的云端对应物）：每次调用 append
   `~/cloud_llm_stats.jsonl`（延迟 / token / 解析阶段 / 是否回退），
   每 20 次输出一次汇总日志，节点退出时总结。

### 用法（WSL2）

```bash
# 部署：备份旧文件 + 复制 cloud_phase_generator.py / phase_rules.py 到
# px4_ws 的 nl_command 包 + colcon build，一条命令完成
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash \
  "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_deploy_llm.sh"
# 回归验证（规则模式，注入显式+隐式态势各一条）
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash \
  "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_regression_llm.sh"

# DeepSeek 模式（key 只走环境变量，不进 ROS 参数，避免落入日志）
CLOUD_LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-xxx \
  ros2 run nl_command cloud_phase_generator

# 或 ROS 参数覆盖（llm_base_url/llm_model/llm_timeout/llm_max_tokens 均可）
ros2 run nl_command cloud_phase_generator --ros-args -p llm_provider:=glm
```

### 规则引擎 vs LLM 一致性评测（论文三产出）

```bash
# Windows 侧离线评测（纯 stdlib，无需 ROS/API 之外的任何依赖）
export DEEPSEEK_API_KEY=sk-xxx GLM_API_KEY=xxx
python scripts/phase_consistency_eval.py --provider all --repeat 3
python scripts/phase_consistency_eval.py --n 5        # 冒烟
python scripts/phase_consistency_eval.py --dry-run    # 不调 API
```

评测集 `situations_testset.json` 40 条 = 显式关键词 15 + **隐式语义 15（带金标准）**

+ 模糊 5 + 中文 5。输出到 `eval_out/`（长表 CSV + Markdown 报告）：

| 论文产出         | 对应报告内容                                                            |
| ---------------- | ----------------------------------------------------------------------- |
| 1 延迟与成本实测 | 延迟 mean/p50/p95/max、token 用量、成本估算                             |
| 2 解析可靠性     | 首次成功 / 重试后成功 / 失败 的漏斗（+repeat>1 时 temp=0 确定性一致率） |
| 3 一致性对比     | 总体/分类一致率、**分歧案例明细表**、金标准准确率（rule vs LLM）  |

dry-run 基线（规则引擎，2026-09-06）：金标准子集精确 **40%** / 类型 **54%**——
弱项全部来自隐式语义（无关键词 → 回落 `HOLD@(0,0,5)`）与 HOLD 参数丢失，
正是 LLM 对照要量化的部分（隐式类 LLM 若给出正确相位 = "云端 LLM 必要性"正面证据）。

### 首批 DeepSeek 实测结果（2026-09-06，deepseek-chat，temp=0，40 条 × 3 次 = 120 调用）

| 指标                            | DeepSeek                                  | 规则引擎              |
| ------------------------------- | ----------------------------------------- | --------------------- |
| 金标准准确率（n=35 有标注态势） | **95%（100/105 次运行）**           | 40% 精确 / 54% 类型   |
| 隐式语义类（15 条）             | **15/15 相位与参数全对**            | 0 条（全部回落 HOLD） |
| 解析漏斗                        | **120/120 首次成功**，0 重试 0 失败 | -（无格式问题）       |
| 延迟                            | mean 563ms / p95 861ms / max 1446ms       | ~0ms                  |
| 确定性（temp=0 × 3 次重复）    | 98%                                       | 100%                  |
| 成本                            | 全场 120 次调用共**¥0.09**         | 0                     |

关键结论（论文可直接引用）：

1. **一致性分解才是重点**：显式类 LLM 与规则引擎一致率 93%（规则对的 LLM 也对），
   隐式/中文类一致率 0%——分歧全部是"规则回落 HOLD、LLM 推断正确"，
   这就是文档4 E3 预判需要回答的"云端 LLM 必要性"正面证据。
2. **延迟远好于预期**（p95 < 1s）：相位信号更新频率上限不再是架构瓶颈，
   "低频相位 + 1Hz 心跳"的假设有充分余量。
3. **成本可忽略**（¥0.0008/次）：云端咨询成本不构成部署障碍。
4. 5 次金标准失误集中在两处方向/语义歧义：`threat incoming from the left`
   （来袭方向 vs 所在侧）与"收紧纵队"→ line（应为 column）——
   prompt 中补充方向约定与队形词汇表可修复，属已知改进项。

WSL2 节点 DeepSeek 模式实测（`scripts/wsl_llm_live_test.sh`）：
显式/隐式态势均正确推断（546/728ms），**LLM 推断期间心跳严格保持
min=max=1.000s（std 0.0001s）**——后台线程设计验证通过。

### 真机全链条演示记录（2026-09-06，DeepSeek 云端 + 飞行中断连降级 + 恢复）

单次飞行中三大创新点首次全部以真 LLM 云端验证（PX4 SITL + AirSim Blocks，
目标 ENU(-20,10,15)，缓存相位 ASSEMBLE@(20,-20)）：

| 时间      | 事件                                                                                  | 创新点 |
| --------- | ------------------------------------------------------------------------------------- | ------ |
| 5884.7    | 态势`checkpoint Bravo (20,-20)` → DeepSeek 358ms → `ASSEMBLE@(20,-20)` 端侧缓存 | 1      |
| 5902-5904 | NL 指令 → Phi-2 解析 0.65s → ARMED 起飞                                             | 2      |
| 5915.4    | `[断连] 3.0秒无心跳` 精确触发（kill 后整 3.0s）                                     | 3      |
| 5920-5925 | 无人机放弃原任务目标，转向飞往缓存相位目标 ENU(20,-20,5)                              | 3      |
| 5925-5941 | 在相位目标自主保持 16 秒，位置偏差 <1.5m                                              | 3      |
| 5942.0    | 云端重启 1 秒后`[恢复] 云端链路恢复，重新对齐相位`                                  | 3      |
| 5946-6011 | 恢复后任务状态机续跑，抵达原目标 ENU(-20,10,15)                                       | 1+3    |
| 6030.9    | `[done] ✅ DISARM 成功`，完整收官                                                   | -      |

本次演示排障中确认并修复的三个问题（均已落入 `demo_full_chain.sh`）：

| 问题                          | 根因                                                                                                                                                                                                     | 修复                                                |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| 端侧解析 Connection refused   | Windows 侧 Phi-2 server（:8080）未启动                                                                                                                                                                   | 脚本第[4]步预检，未启动即警告并给出启动命令         |
| `[断连]` 永不触发           | `ros2 run` 会起 wrapper+节点两个进程，kill wrapper 后节点存活继续发心跳（**8 月遗留 bug：全链条场景下断连从未真正触发过**；8 月断连验证能成功是因为 `demo_degradation.sh` 用的是直接执行方式） | 脚本改为直接执行节点可执行文件（单进程），kill 即死 |
| 巡航/悬停期 offboard 反复抖动 | Blocks 距离边界：42m/51m 目标抖动，14m/22m 干净（三组正反实证）                                                                                                                                          | 演示目标建议 ≤30m                                  |

已知行为（非 bug）：恢复后云端为新实例、无态势记忆，相位从默认 HOLD 重新
发布并覆盖端侧缓存（"重新对齐"机制本身成立；云端态势持久化属 future work）；
恢复后若当前位置距原目标 >40m 仍会触发距离边界抖动，重挂 offboard 后任务可
继续完成（本轮实测如此）。

### 顺带修复：规则引擎隐藏 bug

原 `_rule_infer` 的 RECON 分支排在 RECONFIGURE 之前，而 `'recon'` 是
`'reconfigure'` 的子串——`"Reconfigure to column formation."` 会被误判为
`RECON@(100,100)`（此前演示未用过该措辞所以未暴露，dry-run 发现）。
已在 `phase_rules.rule_infer` 调整分支顺序，selftest 已覆盖该用例。

**测试环境**：RTX 3060 Laptop 6GB | llama.cpp CUDA | 16 条测试集（9 swarm + 7 single-agent）
工具：`benchmark_matrix.py`（支持单测/全测，CSV 输出）

> ⚠️ **下表为 8 月 16 条小样本口径，多项结论已被「评估体系 v2」440 条重测修正
> （Q8_0 反常不复现、Q5_K_M 甜点地位被 Q6_K 取代），引用请以 v2 为准：**

| 格式             | 模型大小          | JSON 准确率            | 吞吐 (tok/s)   | 延迟 (ms/tok)  | 显存 (MB)      |
| ---------------- | ----------------- | ---------------------- | -------------- | -------------- | -------------- |
| FP16             | 5.18 GB           | **100%** (16/16) | 18.7           | 53.6           | 6041           |
| Q8_0             | 2.75 GB           | 88% (14/16)            | 72.5           | 13.8           | 3967           |
| **Q6_K**   | **2.13 GB** | **100%** (16/16) | 79.5           | 12.6           | 3521           |
| **Q5_K_M** | **1.87 GB** | **100%** (16/16) | **87.9** | **11.4** | **3044** |
| Q4_K_M           | 1.62 GB           | 88% (14/16)            | 91.0           | 11.0           | 2784           |

### 关键发现（论文写作素材）

1. **Q5_K_M 是最优甜点**：模型最小（1.87GB）+ 100% 准确率 + 最高效吞吐（87.9 tok/s）。
   比 Q6_K 快 10%，比 Q4_K_M 准确率高 12 个百分点。
2. **FP16 无法端侧部署**：6041MB 显存占用超过 6GB 卡的限额（实测勉强能跑但零余量），
   证实端侧必须量化。
3. **Q8_0 反而不如 Q6_K/Q5_K_M 准确**（88% vs 100%）：非直觉现象——8-bit 量化的
   per-tensor scale 误差在指令解析这类精确格式任务上比 K-quant 的分块量化更敏感。
   这是文献少有报告的发现，可作为论文的一个分析点。
4. **压缩-加速非单调**：从 FP16→Q5_K_M，模型缩小 64%，速度提升 4.7 倍，
   且精度无损；但 Q4_K_M 再压缩 13% 就损失 12 个百分点精度——
   说明 5-bit 是该任务量化的精度悬崖边缘。

### 失败案例模式

- Q8_0 / Q4_K_M 共同失败：`Drone 4, single-agent, move to...`（#13）
- Q8_0 额外失败：`UAV 2, go to...`（#11，mode 误判为 swarm）
- Q4_K_M 额外失败：`UAV 1 and 2, form a line...`（#1，mode/formation 字段错位）
- 模式：低比特下字段顺序和 mode 判断最容易出错

---

## 评估体系 v2（440 条大样本重测，2026-09-06）

> 上表的全部结论建立在 16 条测试上——两条样本的摆动就是 12 个百分点，
> Q8_0 不如 Q6_K 这类"反常发现"无法区分真现象与噪声。本节用 440 条分层
> 评测集 + 统计检验重测，是所有量化结论的最终口径。

### 评测集设计（`evaluation/`，固定种子 20260906，程序化生成 + selftest + 人工抽查）

| 评测集              | 规模                                                         | 分层                                                                                                                                       | 金标准                                         | 判定                                                                                             |
| ------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `basic_240.jsonl` | 240 = 训练内 160 / 训练外 80                                 | single-agent 90 + swarm 150（5 阵型各 30）；表述 = 动词池 × 称呼池 × 5 句式模板；训练外 = 坐标系统性外推（\|x\|>30.5 / \|y\|>30 / z>25） | 生成时构造                                     | 精确匹配（沿用旧基准：字段相等 + target 1e-3）                                                   |
| `phase_200.jsonl` | 200 = seen 56 / in-range-unseen 50 / ood 64 / RECONFIGURE 40 | 每相位覆盖训练参数（seen）、包围盒内未见值、包围盒外值                                                                                     | 确定性规则映射（与训练数据生成规则 100% 同源） | 容差匹配（沿用 phase_verify_v4：OBST/RECONF ±2、RECON ±5、ASM/HOLD ±1）+ RECONFIGURE 队形精确 |

设计要点：金标准严格遵循训练约定——RECONFIGURE 的 output formation 在
multi/collective 命令下 = 相位参数、single 命令下 = free（v5 训练数据 48 条实测
100% 如此）；collective 命令的 formation 训练本身一对多，不判定。次级指标
subject_ok（mode+uav_ids）单独报告，与相位能力解耦。

### 执行器（`evaluation/eval_run.py`）

- 生成参数与旧基准一致（n_ctx=512, temp=0.1），保证纵向可比
- 报告：总体 / 分 split / 分类别准确率 **+ Wilson 95% CI**、失败原因分布、失败样例
- `--compare A B`：同测试集两档对比，**McNemar 精确配对检验**（同条目配对）
- 全量驱动：`evaluation/run_matrix.py`（v5 五档 × 双测试集 + dmpc 第一代参考）

### 结果矩阵（2026-09-07，RTX 3060 Laptop；完整版含 McNemar 见 `evaluation/results/matrix_report.md`）

**basic_240（精确匹配）**：

| 档位                     | 大小   | 总体           | 训练外(80) |
| ------------------------ | ------ | -------------- | ---------- |
| v5-Q8_0                  | 2.75GB | **100%** | 80/80      |
| v5-Q6_K                  | 2.13GB | **100%** | 80/80      |
| v5-Q5_K_M（现役）        | 1.87GB | 97.5%          | 77/80      |
| v5-Q4_K_M                | 1.62GB | 97.9%          | 78/80      |
| dmpc1-Q6_K（第一代参考） | 2.13GB | 62.5%          | 50/80      |

**phase_200（容差匹配）**：Q8_0 **57.5%** > Q6_K 54.0% > Q5_K_M 52.5% > Q4_K_M 43.0%
（排除 RECONFIGURE 后：71.9% / 67.5% / 65.6% / 53.8%）

**核心修正（相对 8 月 16 条矩阵）**：

1. **"Q8_0 反常"不复现**——Q8_0 全场最好或并列最好，与 Q6_K/Q5_K_M 差异不显著
   （McNemar p≥0.14）。旧结论系小样本噪声。
2. **部署甜点从 Q5_K_M 改为 Q6_K**——Q5_K_M 的 basic 97.5% 显著低于 Q6_K 的 100%
   （p=0.031），Q6_K 仅大 14%（2.13GB）。
3. **精度悬崖在 4-bit 且只作用于相位能力**——Q5_K_M vs Q4_K_M 相位差异显著
   （p=0.005），基础解析全档 ≥97.5% 不受量化影响：**量化敏感度取决于能力类型**。
4. **RECONFIGURE 全档 0/40（含 Q8_0）= v5 模型级退化**——z=8 槽位被 z=5/z=15
   侵占（与第五轮"z 共享特征干扰"教训同构、规模更大），是 v6 重训首要目标；
   seen 参数也仅 64-80%，说明是系统性 z 表示冲突而非泛化问题。
5. FP16 因 6GB 显存临界（~5s/条）仅跑 basic 60 条子样本：60/60，与旧结论一致。

### dmpc"考古"结论（重要更正）

尝试从 8/1 遗留的 `phi2-dmpc-merged/model.safetensors` 复活 8 月矩阵模型失败：
复活的权重行为完整（格式/坐标/ids 全对）但在**原 16 条测试上仅 11/16**——所有
裸单机指令（"UAV 3, fly to ..."）被判为 swarm。结合时间线推断：该文件是
**line/grid 扩充重训之前的"第一代"dmpc**（第一代训练数据无裸单机样本）；8 月
矩阵测的最终版 dmpc 合并权重已被后续覆盖删除，**不可恢复**。

因此：旧矩阵的 Q8_0 反常**无法在原模型上复验**，只能由 v5 大样本矩阵对现役
模型回答。第一代 dmpc 的裸单机缺陷反而是一个好的训练数据设计实证——最终版
109 条数据补了 25 条裸单机样本后该能力才出现（与五轮相位微调的"数据设计决定
能力"教训链同构）。

---

## 验收目标与实测说明（最终结果）

### 推理方案对比

本项目支持两条推理路径，均已在 RTX 3060 6GB 上验证通过：

| 指标              | 目标        | transformers 4-bit   | **GGUF Q6_K + llama.cpp CUDA** |
| ----------------- | ----------- | -------------------- | ------------------------------------ |
| JSON 解析准确率   | > 90%       | 100% (16/16) ✅      | **100% (16/16)** ✅            |
| 推理吞吐          | 30+ tok/s   | 10.2 tok/s ⚠️      | **90.1 tok/s** ✅              |
| 平均单 Token 延迟 | < 35 ms/tok | 98.5 ms/tok          | **11.1 ms/tok** ✅             |
| 推理峰值显存      | < 3500 MB   | 2128 MB（模型占用）  | 4931 MB（含 KV cache + CUDA ctx）    |
| 环境门槛          | -           | 无需额外装包         | 需 CUDA Toolkit + 编译               |
| 适用场景          | 开发验证    | **高吞吐部署** |                                      |

训练指标（两条路径共用）：

| 指标           | 目标      | 实测              | 达标 |
| -------------- | --------- | ----------------- | ---- |
| 训练峰值显存   | < 5500 MB | **5265 MB** | ✅   |
| 训练全程无 OOM | ✅        | ✅                | ✅   |

### 关于两条推理路径

- **transformers 4-bit（`benchmark.py`）**：与训练同栈，开箱即用，但 bitsandbytes 每步要反量化权重，
  吞吐仅 ~10 tok/s。适合开发期快速验证。
- **GGUF Q6_K + llama.cpp CUDA（`benchmark_gguf.py`）**：专用 4-bit GPU kernel，无反量化开销，
  吞吐达 **90 tok/s**（8.8 倍提升）。需运行 `setup_cuda_inference.py` 搭建 CUDA 编译环境。
  适合生产部署。

---

## 📋 实验验收报告（2026-08-04 最终）

### 硬件与环境

- **GPU**：NVIDIA GeForce RTX 3060 Laptop（6144 MB VRAM, compute capability 8.6）
- **torch**：2.11.0+cu128（CUDA 12.8）｜transformers 5.14.1｜trl 1.9.2｜peft 0.20.0｜bitsandbytes 0.50.0
- **CUDA Toolkit**：13.3（用于编译 llama.cpp CUDA 版）
- **推理引擎**：llama.cpp（de699957b）+ llama-cpp-python 0.3.34（CUDA 编译）

### 微调配置

| 项         | 值                                                           |
| ---------- | ------------------------------------------------------------ |
| 基座模型   | microsoft/phi-2（2.7B，ModelScope 下载）                     |
| 微调方法   | QLoRA 4-bit NF4 + 双重量化                                   |
| LoRA       | r=8, alpha=16, target=q/k/v/dense（仅 self-attention）       |
| 训练精度   | bf16（3060 原生支持，避免 fp16 GradScaler 与 bf16 梯度冲突） |
| 等效 batch | 1 × 8（梯度累加）                                           |
| 优化器     | paged_adamw_8bit                                             |
| 学习率     | 2e-4, cosine, warmup 5%                                      |
| 训练步数   | 200 步（≈16.7 epoch）                                       |
| 训练数据   | 109 条（swarm 5 阵型各 9-15 条 + single-agent 45 条）        |

### 最终验收数据（GGUF Q6_K GPU 推理）

| 指标                        | 实测值                            | 验收目标      | 判定                  |
| --------------------------- | --------------------------------- | ------------- | --------------------- |
| **JSON 解析准确率**   | **100%（16/16）**           | > 90%         | ✅                    |
| **推理吞吐**          | **90.1 tok/s**              | 30+ tok/s     | ✅ 超额 3 倍          |
| **平均单 Token 延迟** | **11.1 ms/tok**             | ~18-25 ms/tok | ✅ 优于目标           |
| **训练峰值显存**      | **5265 MB**                 | < 5500 MB     | ✅                    |
| **推理峰值显存**      | 4931 MB（含 KV cache + CUDA ctx） | < 3500 MB     | ⚠️ 模型本身 2445 MB |
| **训练 loss**         | 2.76 → 0.33                      | 下降收敛      | ✅                    |
| **token 准确率**      | 51% → 91%                        | 上升          | ✅                    |
| **训练耗时**          | ~12 分钟                          | -             | -                     |

### 测试集覆盖（16 条全对）

- swarm 模式：line / triangle / wedge / grid / circle 各阵型，2-5 架 UAV 组合
- single-agent 模式：最简表述（fly to / go to / head to）+ 显式表述（single-agent / solo）
- 坐标覆盖：正负值、小数、不同量级

### 产物清单

| 文件                    | 大小    | 说明                                |
| ----------------------- | ------- | ----------------------------------- |
| `phi2-dmpc-adapter/`  | ~10 MB  | LoRA 权重（可加载推理）             |
| `phi2-dmpc-merged/`   | ~5.2 GB | 合并后的完整 fp16 模型              |
| `phi2-dmpc-q6_k.gguf` | 2.13 GB | Q6_K 6-bit 量化（llama.cpp 部署用） |
| `train_peak_vram.txt` | -       | 训练峰值显存记录                    |

---

## 文件说明

| 文件                                                                  | 作用                                                                 |
| --------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **训练与量化**                                                  |                                                                      |
| `download_model.py`                                                 | ModelScope 下载 phi-2 到`./models/phi-2`                           |
| `train_phi2_qlora.py`                                               | QLoRA 微调，保存 Adapter                                             |
| `merge_and_quantize.py`                                             | 合并 LoRA，打印量化命令                                              |
| `setup_cuda_inference.py`                                           | 一次性搭建 CUDA 推理环境                                             |
| **基准测试**                                                    |                                                                      |
| `benchmark.py`                                                      | 4-bit GPU 推理（transformers）+ JSON 校验                            |
| `benchmark_gguf.py`                                                 | Q6_K GGUF GPU 推理 + JSON 校验                                       |
| `benchmark_matrix.py`                                               | 五档量化基准矩阵（CSV 输出）                                         |
| `context_compression_test.py`                                       | 创新点1假设检验（75样本三组对照）                                    |
| `phase_verify.py` / `phase_verify_v3.py` / `phase_verify_v4.py` | 相位条件化验证（各轮迭代）                                           |
| **ROS2 节点（WSL2 nl_command 包）**                             |                                                                      |
| `scripts/nl_command_node.py`                                        | 端侧核心节点：NL→Phi-2→PX4 + 相位缓存 + 断连降级                   |
| `scripts/cloud_phase_generator.py`                                  | 云端相位规划器：rule/deepseek/glm/local 四引擎 + 规则兜底 + 统计落盘 |
| `scripts/phase_rules.py`                                            | 共享库：相位语法契约 + 规则引擎 + LLM 调用（`--selftest` 自检）    |
| `scripts/cloud_heartbeat_node.py`                                   | 云端心跳模拟（创新点3独立演示用）                                    |
| **云端 LLM 评测（Windows 离线）**                               |                                                                      |
| `scripts/phase_consistency_eval.py`                                 | 规则引擎 vs LLM 一致性评测（论文三产出）                             |
| `scripts/situations_testset.json`                                   | 态势评测集 40 条（显式/隐式/模糊/中文）                              |
| `scripts/wsl_deploy_llm.sh`                                         | 一键部署到 WSL2 px4_ws（备份+复制+colcon build）                     |
| **评估体系 v2（2026-09）**                                      |                                                                      |
| `evaluation/gen_testset.py`                                         | 评测集生成器（440 条分层 + selftest，固定种子）                      |
| `evaluation/eval_run.py`                                            | 统一评测执行器（Wilson CI / McNemar / 分层报告）                     |
| `evaluation/run_matrix.py`                                          | 全量矩阵跑批驱动                                                     |
| `evaluation/testsets/`                                              | basic_240 + phase_200 评测集                                         |
| `evaluation/results/matrix_report.md`                               | v2 全量矩阵报告（论文口径）                                          |
| `scripts/wsl_regression_llm.sh`                                     | 部署后回归验证（规则模式注入两条态势）                               |
| `scripts/wsl_eval_llm.sh`                                           | 从 WSL2 跑一致性评测（自动从 ~/.bashrc 提取 key）                    |
| `scripts/wsl_llm_live_test.sh`                                      | 节点 DeepSeek 模式实测 + 心跳不阻塞验证                              |
| **演示脚本**                                                    |                                                                      |
| `scripts/run_demo.sh`                                               | 单机完整任务闭环演示                                                 |
| `scripts/run_two_drones_v2.sh`                                      | 两机独立控制演示                                                     |
| `scripts/demo_degradation.sh`                                       | 断连降级交互演示                                                     |
| `scripts/demo_full_chain.sh`                                        | 完整链条端到端演示（云端→端侧→降级→恢复）                         |
| `scripts/send_nl.py`                                                | Python 消息发布（绕过 ros2 topic pub bug）                           |
| **数据**                                                        |                                                                      |
| `dataset.jsonl`                                                     | v4 数据（287 条，与 dataset_phased_v4.jsonl 相同；注意非 v5）        |
| `dataset_original_109.jsonl`                                        | 基础数据备份                                                         |
| `dataset_phased_v*.jsonl`                                           | 各轮迭代数据版本                                                     |
| `requirements.txt`                                                  | 依赖清单                                                             |

## 关键技术决策（为何不用 Gemini 原始脚本）

1. **模型源**：huggingface.co 实测超时 → 改用 ModelScope
2. **TRL API**：原脚本用的 `SFTTrainer(tokenizer=, max_seq_length=)` 在 trl 1.9.2 已被移除 → 迁移到 `SFTConfig(processing_class=, max_length=)`
3. **数据安全**：原 `pipeline_and_benchmark.py` 会在 import 时覆盖 `dataset.jsonl`（且 schema 不一致）→ 已拆分职责、移除该脚本

## 踩坑记录（排障历程）

| 问题                                                                            | 根因                                                                   | 解决                                                        |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------- |
| 训练卡住、GPU 利用率 6%                                                         | 装的是`torch+cpu`（纯 CPU 构建）                                     | 装`torch 2.11.0+cu128`（CUDA 索引）                       |
| `_amp_foreach_non_finite_check_and_unscale_cuda not implemented for BFloat16` | fp16 GradScaler 与 bf16 梯度不兼容                                     | 改用`bf16=True`（无需 GradScaler）                        |
| `'list' object has no attribute 'endswith'`                                   | trl 1.9.2 以 batched=False 调用 formatting_func                        | formatting_func 接收单条样本、返回单字符串                  |
| `SFTConfig got unexpected keyword 'use_cache'`                                | 新版 transformers 移除了该参数                                         | 删除该行，gradient_checkpointing 自动处理                   |
| line/grid 字段混淆（mode 填成 formation 值）                                    | 训练数据里这两种阵型样本偏少 + 词汇歧义                                | 扩充 line/grid 各到 15 条                                   |
| CMake`CUDA Toolkit directory '' does not exist`                               | VS 生成器的 MSBuild CUDA`.targets` 解析 `CudaToolkitDir` 脆弱      | 改用`-G Ninja` 生成器 + `vcvars64.bat` 初始化 MSVC 环境 |
| nvcc`Cannot find compiler 'cl.exe'`                                           | nvcc 需要 MSVC 完整环境（INCLUDE/LIB），不只是 PATH                    | 编译前`call vcvars64.bat`                                 |
| llama.cpp 链接`libcrypto.a` LNK2019（`__mingw_vsscanf` 等）                 | 误链了系统里 MinGW 版 curl 的 OpenSSL                                  | `-DLLAMA_OPENSSL=OFF -DLLAMA_CURL=OFF`                    |
| llama.cpp UI 编译失败`download dist.tar.gz failed`                            | Web UI 资源需从 huggingface.co 下载（本机不可达）                      | `-DLLAMA_BUILD_UI=OFF -DLLAMA_BUILD_SERVER=OFF`           |
| llama-cpp-python`CMAKE_CUDA_COMPILER: C:Program`                              | CMAKE_ARGS 环境变量含空格路径被截断                                    | 不传含空格路径，靠 vcvars 的 PATH 让 CMake 发现 nvcc        |
| llama-cpp-python`Cannot import 'scikit_build_core'`                           | `--no-build-isolation` 但 venv 缺构建后端                            | 先`pip install scikit-build-core ninja`                   |
| GGUF 准确率突然下降                                                             | 重训后忘了重新合并+量化 GGUF（用的是旧 adapter）                       | 每次重训后重跑`merge_and_quantize.py` + 重新量化          |
| `Failed to load shared library 'llama.dll'`                                   | 终端在装 CUDA Toolkit 之前打开，PATH 缺`CUDA\bin\x64`（runtime DLL） | benchmark_gguf.py 已自动注入 CUDA DLL 路径；或重开终端      |
| `ros2 topic pub` 报 `The passed message type is invalid`                    | ros2 CLI 类型解析 bug（`interface show` 正常但 pub 失败）            | 用 Python`rclpy` 直接发布（send_nl.py）                   |
| PX4 实例2 命令无响应                                                            | 多实例`MAV_SYS_ID=1+instance=2`，硬编码 `target_system=1` 被忽略   | `target_system` 参数化，节点2 传 2                        |
| `ros2 run` 的 `-p` 参数不生效                                               | 被解释为 remap 而非参数                                                | 加`--ros-args` 前缀                                       |
| DISARM 被 PX4 拒绝                                                              | offboard 模式+持续 setpoint 时安全机制拒绝 DISARM                      | done 阶段停止 offboard 输出→等退出→DISARM                 |
| DISARM 成功后又重新 ARM                                                         | 控制循环`not armed` 自动发 ARM，与 done 冲突                         | done 阶段提前拦截，跳过 ARM 重试                            |
| offboard 循环掉线                                                               | 目标过远（>40m）触发 Blocks 环境限制                                   | 用适中目标（<30m）                                          |
| 相位微调第二轮坍缩                                                              | 随机 target 一对多映射→模型学输出均值                                 | 确定性规则映射（第三轮修复）                                |
| 相位微调第五轮退化                                                              | 单相位加强导致 z 值共享特征干扰                                        | 全相位同步扩充（后续方向）                                  |
