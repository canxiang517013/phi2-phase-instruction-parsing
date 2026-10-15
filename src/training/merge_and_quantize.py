"""
Step 2: 合并 LoRA 权重到基座模型，并输出 llama.cpp 量化命令

本脚本完成:
    1. 在 CPU 上把 phi2-dmpc-adapter 合并进基座模型（避免 GPU OOM）
    2. 保存合并后的完整模型到 ./phi2-dmpc-merged/
    3. 打印 llama.cpp 转 GGUF + Q6_K 量化的精确命令（由你手动执行）

运行前提:
    - 已完成训练，./phi2-dmpc-adapter/ 存在
    - ./models/phi-2 存在

用法:
    python merge_and_quantize.py

说明:
    合并步骤在 CPU 进行（device_map="cpu"），约需 5-10GB 内存、几分钟时间，
    不会占用宝贵的 GPU 显存。GGUF 转换与量化需要 llama.cpp 工具链，
    请按下方打印的命令手动执行（编译 llama.cpp 较耗时，不自动跑）。
"""
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "models", "phi-2")
ADAPTER_DIR = os.path.join(BASE_DIR, "phi2-dmpc-adapter")
MERGED_DIR = os.path.join(BASE_DIR, "phi2-dmpc-merged")
FP16_GGUF = os.path.join(BASE_DIR, "phi2-fp16.gguf")
Q6_GGUF = os.path.join(BASE_DIR, "phi2-dmpc-q6_k.gguf")


def check_prereqs():
    if not os.path.isdir(MODEL_PATH) or not os.path.exists(
        os.path.join(MODEL_PATH, "config.json")
    ):
        print(f"[merge] ❌ 未找到基座模型: {MODEL_PATH}")
        print("[merge] 请先运行: python download_model.py")
        sys.exit(1)
    if not os.path.isdir(ADAPTER_DIR) or not os.path.exists(
        os.path.join(ADAPTER_DIR, "adapter_config.json")
    ):
        print(f"[merge] ❌ 未找到 LoRA Adapter: {ADAPTER_DIR}")
        print("[merge] 请先运行训练: python train_phi2_qlora.py")
        sys.exit(1)


def merge():
    print("\n=== [1/2] 合并 LoRA 权重到基座模型 (CPU) ===")
    print("[merge] 在 CPU 上加载基座模型，避免 GPU OOM ...")

    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )

    print("[merge] 挂载 LoRA Adapter ...")
    merged = PeftModel.from_pretrained(base_model, ADAPTER_DIR)

    print("[merge] 执行 merge_and_unload() ...")
    merged = merged.merge_and_unload()

    print(f"[merge] 保存合并模型到 {MERGED_DIR} ...")
    os.makedirs(MERGED_DIR, exist_ok=True)
    merged.save_pretrained(MERGED_DIR, safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_DIR, trust_remote_code=True)
    tokenizer.save_pretrained(MERGED_DIR)
    print(f"[merge] ✅ 合并完成: {MERGED_DIR}")
    return merged


def print_quantize_instructions():
    print("\n=== [2/2] llama.cpp 量化命令（请手动执行）===")
    print("[merge] 合并后的模型是 HuggingFace 格式 (safetensors)，")
    print("[merge] 需用 llama.cpp 转 GGUF 并执行 Q6_K (6-bit) 量化。")
    print()
    print("-" * 70)
    print("# 1) 一次性准备 llama.cpp（首次执行）")
    print("git clone https://github.com/ggerganov/llama.cpp")
    print("cd llama.cpp")
    print("pip install -r requirements.txt")
    print("# Windows 下编译 llama-quantize.exe（需 CMake）")
    print("cmake -B build -DGGML_CUDA=ON")  # 3060 可启用 CUDA 加速量化
    print("cmake --build build --config Release")
    print()
    print("# 2) 转换为 FP16 GGUF")
    print(
        f'python convert_hf_to_gguf.py "{MERGED_DIR}" '
        f'--outtype f16 --outfile "{FP16_GGUF}"'
    )
    print()
    print("# 3) 执行 Q6_K (6-bit) 量化")
    print(
        f'build/bin/Release/llama-quantize.exe "{FP16_GGUF}" "{Q6_GGUF}" Q6_K'
    )
    print("-" * 70)
    print()
    print(f"[merge] 量化完成后会生成: {Q6_GGUF}")
    print("[merge] 之后运行测评: python benchmark.py")


def main():
    check_prereqs()
    merge()
    print_quantize_instructions()


if __name__ == "__main__":
    main()
