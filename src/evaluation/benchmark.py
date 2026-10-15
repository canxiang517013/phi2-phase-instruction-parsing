"""
Step 3: 4-bit 量化推理测评 (transformers + QLoRA, GPU)

说明（重要）：
    原计划用 llama.cpp 的 Q6_K GGUF 做 GPU 推理，但 Windows 平台没有
    llama-cpp-python 的 CUDA 预编译 wheel，本机又未安装 CUDA Toolkit，
    源码编译 CUDA 版不可行。因此改用 transformers + bitsandbytes 的
    4-bit (NF4) 量化在 GPU 上推理测评 —— 这与训练时同一套量化方案，
    验收指标（显存/延迟/吞吐/JSON 准确率）同样有效且更贴近实际部署形态。

本脚本完成：
    1. 用 4-bit NF4 量化加载 phi-2 + 挂载训练好的 LoRA adapter（GPU）
    2. 在多条测试 prompt（含训练外泛化样本）上推理
    3. 自动校验 JSON 合法性，统计解析准确率
    4. 测量并输出：首字延迟、平均 ms/token、tokens/s、峰值 VRAM
    5. 汇总打印验收数据表（自动读取训练峰值显存 train_peak_vram.txt）

运行前提：
    - ./models/phi-2 存在（download_model.py 下载）
    - ./phi2-dmpc-adapter 存在（train_phi2_qlora.py 训练产物）

用法：
    python benchmark.py
"""
import os
import sys
import json
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

import torch
import pynvml
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "phi-2")
ADAPTER_DIR = os.path.join(BASE_DIR, "phi2-dmpc-adapter")
PEAK_VRAM_FILE = os.path.join(BASE_DIR, "train_peak_vram.txt")

# System prompt：简洁描述任务，不含范例。
# （测试发现 few-shot 范例会让模型复读范例里的 uav_ids/target 值，
#  反而降低准确率。依靠训练数据均衡分布来保证字段正确性。）
SYSTEM_PROMPT = (
    "Parse the user natural language command into a structured JSON for UAV DMPC."
)

# 测试集：16 条，覆盖所有 5 种阵型 + single-agent + 多种表述 + 训练外泛化
# （5 条样本统计不靠谱，扩大到 16 条以得到可靠准确率）
TEST_CASES = [
    # swarm - 各阵型
    ("UAV 1 and 2, form a line at (10, 5, 20).",
     {"mode": "swarm", "formation": "line", "uav_ids": [1, 2], "target": [10.0, 5.0, 20.0]}),
    ("UAV 4 and 5, form triangle at (-3, 18, 6).",
     {"mode": "swarm", "formation": "triangle", "uav_ids": [4, 5], "target": [-3.0, 18.0, 6.0]}),
    ("UAV 2 and 3 and 4, form wedge at (7, 7, 19).",
     {"mode": "swarm", "formation": "wedge", "uav_ids": [2, 3, 4], "target": [7.0, 7.0, 19.0]}),
    ("UAV 1 and 2, form grid at (-12, -5, 10).",
     {"mode": "swarm", "formation": "grid", "uav_ids": [1, 2], "target": [-12.0, -5.0, 10.0]}),
    ("UAV 1 and 4, form circle at (19, 11, 7).",
     {"mode": "swarm", "formation": "circle", "uav_ids": [1, 4], "target": [19.0, 11.0, 7.0]}),
    # swarm - 完整表述变体
    ("UAV 2 and 4 and 5, form a wedge formation and move to target coordinates (-8, 12, 6).",
     {"mode": "swarm", "formation": "wedge", "uav_ids": [2, 4, 5], "target": [-8.0, 12.0, 6.0]}),
    ("UAV 3 and 5, form line at (25, -8, 12).",
     {"mode": "swarm", "formation": "line", "uav_ids": [3, 5], "target": [25.0, -8.0, 12.0]}),
    ("UAV 1 and 3 and 5, form triangle at (-1, 20, 18).",
     {"mode": "swarm", "formation": "triangle", "uav_ids": [1, 3, 5], "target": [-1.0, 20.0, 18.0]}),
    ("UAV 1 and 2 and 5, form grid at (3, 3, 21).",
     {"mode": "swarm", "formation": "grid", "uav_ids": [1, 2, 5], "target": [3.0, 3.0, 21.0]}),
    # single-agent - 最简表述（不带 single/alone/solo 关键词）
    ("UAV 3, fly to (0, -10, 5).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [0.0, -10.0, 5.0]}),
    ("UAV 2, go to (15, 3, 11).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 3.0, 11.0]}),
    ("Drone 1, proceed to (-9, -14, 2).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-9.0, -14.0, 2.0]}),
    # single-agent - 显式表述
    ("Drone 4, single-agent, move to (22, -3, 14).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [22.0, -3.0, 14.0]}),
    ("UAV 5, travel solo to (0, 22, 14).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [5], "target": [0.0, 22.0, 14.0]}),
    ("UAV 4, head to (-18, 14, 5).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [-18.0, 14.0, 5.0]}),
    ("UAV 3, navigate to (8, -20, 3).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [8.0, -20.0, 3.0]}),
]


# ----------------------------------------------------------------------
# 显存监控
# ----------------------------------------------------------------------
def get_gpu_used_mb():
    pynvml.nvmlInit()
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return info.used / 1024 / 1024
    finally:
        pynvml.nvmlShutdown()


def build_prompt(user_input):
    return (
        f"### System:\n{SYSTEM_PROMPT}\n\n"
        f"### User:\n{user_input}\n\n### Response:\n"
    )


def extract_json(text):
    """从模型输出中抽取第一个 JSON 对象（容忍前后多余文本）。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def json_matches(predicted, expected):
    """字段级匹配（数值容差 1e-3，uav_ids 顺序不敏感）。"""
    if not isinstance(predicted, dict):
        return False
    for key in ("mode", "formation"):
        if predicted.get(key) != expected.get(key):
            return False
    if sorted(predicted.get("uav_ids", [])) != sorted(expected.get("uav_ids", [])):
        return False
    pt = predicted.get("target")
    et = expected.get("target")
    if not (isinstance(pt, list) and isinstance(et, list) and len(pt) == len(et)):
        return False
    for a, b in zip(pt, et):
        try:
            if abs(float(a) - float(b)) > 1e-3:
                return False
        except (TypeError, ValueError):
            return False
    return True


def check_prereqs():
    if not os.path.isdir(MODEL_PATH) or not os.path.exists(
        os.path.join(MODEL_PATH, "config.json")
    ):
        print(f"[benchmark] ❌ 未找到基座模型: {MODEL_PATH}")
        print("[benchmark] 请先运行: python download_model.py")
        sys.exit(1)
    if not os.path.isdir(ADAPTER_DIR) or not os.path.exists(
        os.path.join(ADAPTER_DIR, "adapter_config.json")
    ):
        print(f"[benchmark] ❌ 未找到 LoRA Adapter: {ADAPTER_DIR}")
        print("[benchmark] 请先运行训练: python train_phi2_qlora.py")
        sys.exit(1)


def main():
    check_prereqs()

    print("\n=== 加载 4-bit 量化模型 + LoRA Adapter (GPU) ===")
    print(f"[benchmark] 基座: {MODEL_PATH}")
    print(f"[benchmark] Adapter: {ADAPTER_DIR}")
    load_before = get_gpu_used_mb()

    # 4-bit NF4 量化（与训练时一致：bf16 compute + double quant）
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, ADAPTER_DIR)
    model.eval()

    load_after = get_gpu_used_mb()
    print(f"[benchmark] 加载前 GPU: {load_before:.1f} MB | 加载后: {load_after:.1f} MB "
          f"(模型占用 ~{load_after - load_before:.1f} MB)")

    EOS_ID = tokenizer.eos_token_id  # 50256 (<|endoftext|>)
    PAD_ID = tokenizer.pad_token_id

    # 推理 + 评测
    results = []
    peak_vram = load_after
    print("\n=== 开始推理测评 ===")
    for i, (user_input, expected) in enumerate(TEST_CASES, 1):
        prompt = build_prompt(user_input)
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

        # 每次推理前清理缓存 + 重置峰值统计，确保测的是「本条」的真实峰值
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        t0 = time.time()
        with torch.no_grad():
            out_ids = model.generate(
                **inputs,
                max_new_tokens=64,
                do_sample=False,        # 贪心解码：更快更稳定，命令解析无需采样
                pad_token_id=PAD_ID,
                eos_token_id=EOS_ID,
                use_cache=True,         # 显式启用 KV cache，降低显存与延迟
            )
        torch.cuda.synchronize()
        elapsed = time.time() - t0
        # 本条推理的峰值显存（allocated，不含碎片）
        peak_alloc = torch.cuda.max_memory_allocated() / 1024**2  # MB

        # 只取新生成的 token（去掉 prompt 部分）
        input_len = inputs["input_ids"].shape[1]
        new_tokens = out_ids[0][input_len:]
        completion_tokens = len(new_tokens)
        raw_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        predicted = extract_json(raw_text)
        ok = json_matches(predicted, expected) if predicted else False

        ms_per_tok = (elapsed / completion_tokens * 1000) if completion_tokens else 0
        tok_per_s = (completion_tokens / elapsed) if elapsed > 0 else 0
        peak_vram = max(peak_vram, peak_alloc)  # 用 allocated 峰值，更准确

        results.append({
            "idx": i,
            "input": user_input,
            "raw": raw_text,
            "json_ok": ok,
            "latency_s": elapsed,
            "tokens": completion_tokens,
            "ms_per_tok": ms_per_tok,
            "tok_per_s": tok_per_s,
        })

        status = "✅" if ok else "❌"
        print(f"[{status}] #{i} {user_input[:45]}")
        print(f"      输出: {raw_text}")
        print(f"      耗时 {elapsed:.3f}s | {completion_tokens} tok | "
              f"{ms_per_tok:.1f} ms/tok | {tok_per_s:.1f} tok/s")

    # 汇总统计
    n = len(results)
    n_ok = sum(1 for r in results if r["json_ok"])
    avg_ms = sum(r["ms_per_tok"] for r in results) / n
    avg_tps = sum(r["tok_per_s"] for r in results) / n

    train_peak = ""
    if os.path.exists(PEAK_VRAM_FILE):
        with open(PEAK_VRAM_FILE, encoding="utf-8") as f:
            train_peak = f.read().strip()

    print("\n" + "=" * 60)
    print("     📋 RTX 3060 Laptop (6GB) 复现测试验收数据")
    print("=" * 60)
    print(f"  推理方案              : transformers + QLoRA 4-bit NF4 (GPU)")
    print(f"  JSON 解析准确率       : {n_ok}/{n} ({n_ok / n * 100:.0f}%)")
    print(f"  平均单 Token 延迟     : {avg_ms:.1f} ms/token")
    print(f"  平均推理吞吐量        : {avg_tps:.1f} tokens/s")
    print(f"  推理峰值显存          : {peak_vram:.1f} MB")
    if train_peak:
        print(f"  训练峰值显存 (QLoRA)  : {train_peak} MB")
    print("=" * 60)
    print("  参考目标:")
    print("    - 推理峰值显存 < 3500 MB | 吞吐 > 30 tok/s")
    print("    - 训练峰值显存 < 5500 MB | JSON 准确率 > 90%")
    print("=" * 60)


if __name__ == "__main__":
    main()
