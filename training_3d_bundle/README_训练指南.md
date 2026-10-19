# 3D 多无人机编队 MAPPO 训练包（Linux 服务器版）

本目录是 `src/training/experiment_core_3d.py` 的**自包含快照**，只依赖 Python 包，不依赖仓库其他文件，拷到 Linux 服务器即可运行。

## 0. 先说明：这里没有外部训练数据集

训练数据不是预先准备的文件，而是由环境**在线生成**的：

- 4 架跟随者 + 1 架虚拟 leader，固定起点、固定航路、正四面体编队；
- 每个 episode 从 `env.reset()` 重新采样（本配置关闭了起点随机化，随机性来自动作采样与网络初始化）；
- `--seeds` 控制随机流，同一 seed 下不同方法看到相同环境序列，便于配对比较；
- 每次运行会自动把完整配置写入 `results/<method>_seed<seed>/config_snapshot.json`。

因此“整理训练数据”实际是固定三件事：**代码版本、种子列表、配置快照**。本包把三者都固化了。

## 1. 目录内容

| 文件 | 用途 |
|---|---|
| `experiment_core_3d.py` | 训练主程序（环境 + MAPPO + PPO + 相位控制器 + 报告） |
| `requirements.txt` | Python 依赖 |
| `check_environment.py` | 环境自检：依赖、CUDA、磁盘、环境维度 |
| `run_smoke_check.sh` | 冒烟检查：2 episode baseline，约 1 分钟 |
| `run_baseline_3seeds.sh` | Baseline MAPPO × 3 seeds |
| `run_phase_aware_3seeds.sh` | Phase-aware LLM × 3 seeds（需 Ollama） |
| `run_all_5methods_10seeds.sh` | 论文完整协议：5 方法 × 10 seeds |
| `config_reference_3d.json` | 默认配置快照（由 `BASE_CFG` 导出） |

默认种子：`21 618 2024`（前三个预注册种子）。论文完整协议使用：`21 618 2024 7 999 31415 456 789 555 8888`。

## 2. 服务器环境准备

```bash
# 1) 建环境（Python 3.10 或 3.11）
conda create -n mappo3d python=3.11 -y
conda activate mappo3d

# 2) 安装 CUDA 版 PyTorch（按服务器驱动选择，下面是 CUDA 12.1 示例）
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 3) 安装其余依赖
pip install -r requirements.txt

# 4) 自检
python check_environment.py
```

`check_environment.py` 会明确打印 CUDA 是否可用、GPU 型号、观测/状态维度。若显示 CUDA 不可用，训练仍能跑，但会退回 CPU。

> 不需要 `git clone`，也不需要仓库其他目录。`experiment_core_3d.py` 是单文件程序。

## 3. Ollama 准备（只有 LLM 方法需要）

`baseline`、`rule_based`、`random_matched` 不需要 Ollama；`phase_aware` 和 `uniform_matched` 需要。

```bash
# 安装（若无 ollama）
curl -fsSL https://ollama.com/install.sh | sh

# 启动服务（默认 11434）
ollama serve &

# 拉取默认模型
ollama pull deepseek-r1:14b

# 验证
curl -s http://127.0.0.1:11434/api/tags
```

如果服务器不能直连 Ollama 模型库，可先在有网的机器上下载 GGUF，再在服务器上用 Modelfile 导入：

```bash
cat > Modelfile <<'EOF'
FROM /data/models/deepseek-r1-14b.Q4_K_M.gguf
EOF
ollama create deepseek-r1:14b -f Modelfile
```

用其他模型时，训练命令加 `--llm-model <name>` 即可，脚本不绑定具体模型。

## 4. 拷贝到服务器

任选一种：

```bash
# 方式 A：scp 整个目录
scp -r training_3d_bundle user@server:/data/

# 方式 B：先在本机打包再传
# Windows PowerShell: Compress-Archive -Path training_3d_bundle -DestinationPath training_3d_bundle.zip
scp training_3d_bundle.zip user@server:/data/
ssh user@server 'cd /data && unzip training_3d_bundle.zip'
```

U 盘拷贝也可以。Linux 上首次运行前加执行权限：

```bash
cd /data/training_3d_bundle
chmod +x *.sh
```

## 5. 先做冒烟检查（必须）

```bash
bash run_smoke_check.sh
```

它会先跑 `check_environment.py`，再跑 2 个 episode 的 baseline（CPU，约 1 分钟）。看到 `Total wall-clock time` 和 `Results written to` 即成功。

建议再跑一次短程 GPU 训练，确认显存与速度：

```bash
DEVICE=cuda python experiment_core_3d.py \
  --results-dir results_3d_pilot \
  --methods baseline \
  --seeds 21 \
  --episodes 20 \
  --episode-len 500
```

观察日志里的 `error=` 是否随 episode 下降、`elapsed_seconds` 估算单 episode 耗时。

## 6. 正式训练命令

### 6.1 Baseline × 3 seeds（不需要 Ollama，可先跑）

```bash
nohup bash run_baseline_3seeds.sh > logs/baseline_nohup.log 2>&1 &
# 或 tmux 中直接: bash run_baseline_3seeds.sh
```

等价的原始命令：

```bash
python experiment_core_3d.py \
  --results-dir results_3d \
  --methods baseline \
  --seeds 21 618 2024 \
  --episodes 2500 \
  --episode-len 500
```

### 6.2 Phase-aware LLM × 3 seeds（需要 Ollama）

```bash
bash run_phase_aware_3seeds.sh
```

等价命令：

```bash
python experiment_core_3d.py \
  --results-dir results_3d \
  --methods phase_aware \
  --seeds 21 618 2024 \
  --episodes 2500 \
  --episode-len 500 \
  --ollama-url http://127.0.0.1:11434 \
  --llm-model deepseek-r1:14b
```

### 6.3 合并两套结果、生成对比报告

两种方法跑完后，用**同一个 results-dir** 再执行一次，`--resume` 会跳过已完成的运行，只重新汇总：

```bash
python experiment_core_3d.py \
  --results-dir results_3d \
  --methods phase_aware baseline \
  --seeds 21 618 2024 \
  --episodes 2500 \
  --episode-len 500 \
  --resume
```

注意：报告文件（`summary_metrics.csv`、`fig_*.png`）写在 results-dir 根目录。**最后一次汇总命令包含哪些方法，报告就只含哪些方法**。

### 6.4 消融/对照方法

```bash
# rule_based：不需要 Ollama
python experiment_core_3d.py --results-dir results_3d \
  --methods rule_based --seeds 21 618 2024

# uniform_matched：需要 Ollama，且必须先有 phase_aware 的 matched_schedule
# random_matched：不需要 Ollama，但也必须先有 phase_aware 的 matched_schedule
python experiment_core_3d.py --results-dir results_3d \
  --methods uniform_matched random_matched --seeds 21 618 2024
```

如果对应的 `phase_aware_seed*/matched_schedule.json` 不存在，程序会立刻报错并列出缺失文件，不会静默跳过。

### 6.5 论文完整协议（5 方法 × 10 seeds）

```bash
tmux new -s mappo3d
bash run_all_5methods_10seeds.sh
# Ctrl+b d 脱离；tmux attach -t mappo3d 回来
```

执行顺序固定为 `phase_aware → baseline → uniform_matched → random_matched → rule_based`，因为两个 matched 基线要读取 phase_aware 生成的调度。

## 7. 输出文件说明

每个 `results_3d/<method>_seed<seed>/` 下：

| 文件 | 含义 |
|---|---|
| `results.json` | 该次运行的全部指标（最终误差、成功率、首次成功 episode 等） |
| `config_snapshot.json` | 本次运行的完整配置，论文附录可直接引用 |
| `matched_schedule.json` | 仅 phase_aware 生成，供 matched 基线复用 |
| `llm_calls.jsonl` / `random_calls.jsonl` / `rule_calls.jsonl` | 每次干预的输入、输出、延迟、是否接受 |
| `tensorboard/` | TensorBoard 事件 |
| `actor_final.pth` / `critic_final.pth` | 最终策略与价值网络 |
| `actor_ep500.pth` 等 | 每 500 episode 的检查点 |

结果根目录：

| 文件 | 含义 |
|---|---|
| `experiment_config.json` | 本次汇总运行的配置 |
| `per_seed_metrics.csv` | 每个方法 × 种子一行 |
| `summary_metrics.csv` / `.json` | 均值 ± 样本标准差（ddof=1） |
| `fig_training_position_error.png` | 训练收敛曲线 |
| `fig_first_success.png` / `fig_stable_breakthrough.png` | 首次成功 / 稳定突破 |
| `fig_final_*.png` | 最终成功率、跟随误差、编队误差、干预次数 |

TensorBoard：

```bash
tensorboard --logdir results_3d --port 6006 --bind_all
```

## 8. 耗时与资源

- 网络很小（Actor 64×64，Critic 128×128），显存占用通常在 1 GB 以内；瓶颈是 CPU-GPU 同步与 LLM 调用。
- 单 episode 500 步。先在 pilot 日志里看 `elapsed_seconds / episodes`，再乘 2500 估算。
- `phase_aware` 的主要额外开销是 Ollama 调用：early 每 30 episode、mid 每 50、late 每 100 次咨询一次；实际调用次数和延迟会在 `results.json` 的 `llm_consultation_count`、`llm_latency_*` 中记录。
- 3 个种子建议预留：baseline 数小时量级，phase_aware 一到两天量级（取决于模型推理速度和是否使用 GPU 推理）。

## 9. 中断与续跑

- `--resume` 只跳过**已经写出 `results.json`** 的运行；
- 如果某个 run 在 2500 episode 中途被中断，不会从第 N 个 episode 续训，会从头重跑该 run；
- 因此长任务请放 tmux/nohup，并保留 `logs/`；
- 失败实验不要删除，换 `--results-dir` 重跑，旧目录留作审计。

## 10. 3D 相对 2D 的关键配置

| 项 | 2D 原版 | 3D 版 |
|---|---|---|
| 观测维度 | 14 | 20 |
| 全局状态维度 | 22 | 32 |
| 动作维度 | 2 | 3 |
| 编队 | 圆周（半径 60） | 正四面体（外接球半径 60，边长 ≈ 98 m） |
| leader 起点 → 终点 | `[0,0]` → `[200,200]` | `[0,0,20]` → `[200,200,25]` |
| 跟随者起点 | 平面四角 | `z=10` 的四角 |
| 速度限制 | 统一 `max_speed=15` | 水平 15 + 垂直 8（分轴） |
| 高度范围 | 无 | 2–80 m |
| 编队完成阈值 | 15 m | 25 m |

奖励尺度、PPO 超参、相位检测阈值与 2D 版保持一致，目的是让 2D→3D 的差异只来自环境和策略维度，便于论文做受控对比。

## 11. 论文记录清单（每次训练都记）

- 日期、服务器主机名、GPU 型号与驱动/CUDA 版本；
- 代码提交号（本包对应仓库 commit，见仓库根目录）；
- 命令全文（脚本已自动写入 `logs/*.log` 开头）；
- 种子列表、`episodes`、`episode_len`；
- Ollama 模型名与量化版本（若跑 LLM 方法）；
- 结果目录路径；
- 异常与失败原因（不要删除失败 run）。

## 12. 常见问题

**Q: 报 `--device requests CUDA, but torch.cuda.is_available() is False`**
A: 装的是 CPU 版 torch，或驱动不可见。按第 2 节重装 CUDA 版，或去掉 `--device cuda`。

**Q: phase_aware 报 `Ollama is unavailable`**
A: `ollama serve` 没启动、端口不对，或模型名不存在。先用 `curl http://127.0.0.1:11434/api/tags` 验证。程序故意 fail-fast，不会把 LLM 方法偷偷跑成 baseline。

**Q: 只跑了 1 个种子会怎样？**
A: 可以跑，程序会打印警告。论文主实验要求至少 10 个种子；3 个种子只用于趋势验证和调参。

**Q: 图里的中文/负号显示异常？**
A: 图内文字是英文；服务器缺 Arial 时会自动回退到 DejaVu Sans，不影响结果。

**Q: 可以改无人机数量吗？**
A: 环境支持 N≠4（自动使用 Fibonacci 球面编队），但本训练包和论文协议固定 N=4。改 N 会同时改变 obs/state 维度和编队几何，需要单独做消融并记录。
