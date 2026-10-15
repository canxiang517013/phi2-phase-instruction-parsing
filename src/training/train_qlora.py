"""
Step 1: QLoRA 4-bit 微调 Phi-2 (UAV DMPC 指令解析)

针对 RTX 3060 Laptop (6GB VRAM) 优化：
    - 4-bit NF4 量化 + 双重量化
    - 仅训练 self-attention 的 q/k/v/dense（避开 MLP，省显存）
    - 梯度检查点 + 8-bit 分页优化器
    - batch_size=1，梯度累加 8 步（等效 batch=8）

运行前提:
    1. 先运行 download_model.py 把 microsoft/phi-2 下到 ./models/phi-2
    2. pip install pynvml（用于显存监控，脚本会自动尝试安装）

用法:
    python train_phi2_qlora.py

训练产物:
    ./phi2-dmpc-adapter/        LoRA 权重 + tokenizer
    ./train_peak_vram.txt       训练峰值显存（MB），供验收卡 / benchmark 读取
"""
import os
import sys
import subprocess
import warnings

# pynvml 13.x 会抛 FutureWarning，静默它以免污染训练日志
warnings.filterwarnings("ignore", category=FutureWarning)

# ----------------------------------------------------------------------
# 路径配置
# ----------------------------------------------------------------------
import os as _os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根（src/training 上两级）
MODEL_PATH = os.path.join(BASE_DIR, "models", "phi-2")     # 本地基座模型
DATA_PATH = os.path.join(BASE_DIR, "datasets", "dataset_phased_v5.jsonl")  # v5 主力（版本对照 datasets/README.md）
OUTPUT_DIR = os.path.join(BASE_DIR, "runs", "train_v5")    # 训练日志/checkpoint（gitignore）
ADAPTER_DIR = os.path.join(BASE_DIR, "adapters", "dmpc_v5")  # 最终 LoRA 权重（入库）
PEAK_VRAM_FILE = os.path.join(OUTPUT_DIR, "train_peak_vram.txt")

# 冒烟模式：PHI2_SMOKE=40 python src/training/train_qlora.py
# 步数受限、产物带 _smoke 后缀，绝不覆盖正式权重
SMOKE_STEPS = int(_os.environ.get("PHI2_SMOKE", "0"))
if SMOKE_STEPS:
    OUTPUT_DIR = os.path.join(BASE_DIR, "runs", "smoke")
    ADAPTER_DIR = os.path.join(BASE_DIR, "adapters", "dmpc_v5_smoke")
    PEAK_VRAM_FILE = os.path.join(OUTPUT_DIR, "train_peak_vram.txt")


# ----------------------------------------------------------------------
# 自动安装 pynvml（显存监控依赖）
# ----------------------------------------------------------------------
def ensure_pynvml():
    try:
        import pynvml  # noqa: F401
        return
    except ImportError:
        print("[train] 未检测到 pynvml，自动安装 ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pynvml"])


ensure_pynvml()

import torch  # noqa: E402
import pynvml  # noqa: E402
from datasets import load_dataset  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402
from peft import LoraConfig, prepare_model_for_kbit_training  # noqa: E402
from trl import SFTConfig, SFTTrainer  # noqa: E402
from transformers import TrainerCallback  # noqa: E402


# ----------------------------------------------------------------------
# 显存监控辅助函数 (PyNVML)
# ----------------------------------------------------------------------
def get_gpu_used_mb():
    """返回当前 GPU 已用显存（MB）。"""
    pynvml.nvmlInit()
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / 1024 / 1024
    finally:
        pynvml.nvmlShutdown()


def get_gpu_total_mb():
    """返回 GPU 总显存（MB）。"""
    pynvml.nvmlInit()
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.total / 1024 / 1024
    finally:
        pynvml.nvmlShutdown()


def print_gpu_memory(stage_name=""):
    used_mb = get_gpu_used_mb()
    total_mb = get_gpu_total_mb()
    print(f"[{stage_name}] GPU 显存占用: {used_mb:.1f} MB / {total_mb:.0f} MB "
          f"({used_mb / total_mb * 100:.1f}%)")
    return used_mb


# ----------------------------------------------------------------------
# 显存峰值记录回调：在每个训练 step 后采样，记录真实峰值 VRAM
# ----------------------------------------------------------------------
class PeakVramCallback(TrainerCallback):
    def __init__(self):
        self.peak_mb = 0.0

    def on_step_end(self, args, state, control, **kwargs):
        try:
            used = get_gpu_used_mb()
            if used > self.peak_mb:
                self.peak_mb = used
        except Exception:
            pass
        return control


# ----------------------------------------------------------------------
# 前置检查
# ----------------------------------------------------------------------
if not os.path.isdir(MODEL_PATH) or not os.path.exists(os.path.join(MODEL_PATH, "config.json")):
    print(f"[train] ❌ 未找到本地基座模型: {MODEL_PATH}")
    print("[train] 请先运行: python download_model.py")
    sys.exit(1)
if not os.path.exists(DATA_PATH):
    print(f"[train] ❌ 未找到训练数据: {DATA_PATH}")
    sys.exit(1)


# ----------------------------------------------------------------------
# 1. 加载 Tokenizer
# ----------------------------------------------------------------------
print("\n=== [1/4] 加载 Tokenizer 与基座模型 ===")
print_gpu_memory("加载前")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
# Phi-2 没有官方 pad_token，复用 eos_token
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"


# ----------------------------------------------------------------------
# 2. 4-bit 量化加载基座模型 (QLoRA)
#    compute dtype 用 bf16：3060 (Ampere, cc 8.6) 原生支持，
#    且与下方 bf16 训练精度统一，避免 fp16 GradScaler 与 bf16 梯度混用报错。
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,  # 双重量化，进一步省 ~0.4GB
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
print_gpu_memory("模型加载后")

# 为 k-bit 训练做准备（冻结权重、启用梯度、转换 dtype 等）
model = prepare_model_for_kbit_training(model)
print("[train] prepare_model_for_kbit_training 完成")


# ----------------------------------------------------------------------
# 3. LoRA 配置（仅 self-attention，省显存）
#    Phi-2 结构：model.layers.N.self_attn.{q_proj,k_proj,v_proj,dense}
#    bare 名 "dense" 只命中 self_attn.dense，不会误伤 mlp.fc1/fc2
# ----------------------------------------------------------------------
peft_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "k_proj", "v_proj", "dense"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)


# ----------------------------------------------------------------------
# 4. 数据格式化：三段式 Prompt
#    重要：trl 1.9.2 的 SFTTrainer 以 batched=False 方式调用 formatting_func，
#    即传入「单条样本」(值为标量的 dict)，必须返回单个字符串。
#    （不要手动追加 <|endoftext|> —— SFTTrainer 的 add_eos 步骤会自动补 EOS。）
# ----------------------------------------------------------------------
def formatting_prompts_func(example):
    """接收单条样本 dict，返回格式化后的字符串。"""
    return (
        f"### System:\n{example['instruction']}\n\n"
        f"### User:\n{example['input']}\n\n"
        f"### Response:\n{example['output']}"
    )


dataset = load_dataset("json", data_files={"train": DATA_PATH})
print(f"[train] 训练集样本数: {len(dataset['train'])}")


# ----------------------------------------------------------------------
# 5. 训练超参（trl 1.9.2 的 SFTConfig）
# ----------------------------------------------------------------------
sft_config = SFTConfig(
    output_dir=OUTPUT_DIR,
    # —— batch & 梯度累加 —— 等效 batch_size = 1 * 8 = 8
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    # —— 优化器：8-bit 分页，超显存时自动 offload 到 CPU ——
    optim="paged_adamw_8bit",
    # —— 学习率 & 调度 ——
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.05,
    max_grad_norm=0.3,
    # —— 训练步数（演示 200 步；实际可调至 500+）——
    max_steps=SMOKE_STEPS or 400,
    # —— 精度 & 检查点 ——
    # 用 bf16 而非 fp16：bf16 无需 GradScaler，避免
    # "_amp_foreach_non_finite_check_and_unscale_cuda not implemented for BFloat16" 报错
    bf16=True,
    save_steps=50,
    save_total_limit=2,
    logging_steps=5,
    # —— 梯度检查点（核心省显存）。SFTConfig 默认 gradient_checkpointing=True ——
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    # 注：新版 transformers 已移除 TrainingArguments.use_cache；
    # 梯度检查点开启时会自动禁用 KV cache（框架自动处理，无需手动设）。
    # —— 数据相关 ——
    max_length=256,            # 命令解析任务 256 token 足够
    packing=False,             # 不打包，保持单条边界清晰
    dataset_text_field="text",
    # —— Windows 多进程会报错，必须设 0 ——
    dataloader_num_workers=0,
    report_to="none",
)


# ----------------------------------------------------------------------
# 6. 构造 Trainer 并启动训练
#    注意：trl 1.9.2 已移除 tokenizer= / max_seq_length= 参数，
#         它们分别改用 SFTConfig.processing_class 与 SFTConfig.max_length。
# ----------------------------------------------------------------------
trainer = SFTTrainer(
    model=model,
    args=sft_config,
    train_dataset=dataset["train"],
    peft_config=peft_config,
    processing_class=tokenizer,
    formatting_func=formatting_prompts_func,
)

peak_cb = PeakVramCallback()
trainer.add_callback(peak_cb)


print("\n=== [2/4] 开始 QLoRA 4-bit 微调 ===")
print("[train] 等效 batch_size = 1 x 8 = 8 | max_steps = 200 | max_length = 256")
print_gpu_memory("训练前")

trainer.train()

print("\n=== [3/4] 训练完成，保存 Adapter 权重 ===")
trainer.model.save_pretrained(ADAPTER_DIR)
tokenizer.save_pretrained(ADAPTER_DIR)
print(f"[train] Adapter 已保存至: {ADAPTER_DIR}")


# ----------------------------------------------------------------------
# 7. 记录训练峰值显存（供 benchmark.py / 验收卡使用）
# ----------------------------------------------------------------------
print("\n=== [4/4] 训练资源统计 ===")
peak_train = peak_cb.peak_mb
end_used = print_gpu_memory("训练结束后")
with open(PEAK_VRAM_FILE, "w", encoding="utf-8") as f:
    f.write(f"{peak_train:.1f}\n")
print(f"[train] 训练过程中 GPU 峰值显存: {peak_train:.1f} MB")
print(f"[train] 已写入 {PEAK_VRAM_FILE}")
print("\n[train] ✅ 训练阶段全部完成。下一步运行: python merge_and_quantize.py")
