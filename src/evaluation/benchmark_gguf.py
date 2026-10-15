"""
Q6_K GGUF GPU 推理测评（llama.cpp CUDA 加速）

用 llama-cpp-python 加载 phi2-dmpc-q6_k.gguf，全量卸载到 GPU，
在 16 条测试集上测准确率 + 显存 + 延迟 + 吞吐。

运行前提：
    - 已运行 setup_cuda_inference.py（装好 CUDA 版 llama-cpp-python）
    - phi2-dmpc-q6_k.gguf 存在

用法：
    python benchmark_gguf.py

预期：吞吐 40-60 tok/s（vs transformers 4-bit 的 10 tok/s）
"""
import os
import sys
import json
import time
import warnings

warnings.filterwarnings("ignore")

# ----- 自动把 CUDA runtime DLL 目录加入 PATH（必须在 import llama_cpp 之前）-----
# ggml-cuda.dll 依赖 cudart64_13.dll / cublas64_13.dll 等，
# 它们在 CUDA Toolkit 的 bin\x64\ 下。如果终端是在装 Toolkit 之前打开的，
# PATH 里没有这个目录，会导致 llama.dll 加载失败。
# 这里主动探测并添加，保证脚本在任何终端都能跑。
for _cuda_root in [
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
]:
    _cuda_bin_x64 = os.path.join(_cuda_root, "bin", "x64")
    if os.path.isdir(_cuda_bin_x64):
        os.environ["PATH"] = _cuda_bin_x64 + os.pathsep + os.environ.get("PATH", "")
        break

import pynvml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GGUF_PATH = os.path.join(BASE_DIR, "phi2-dmpc-q6_k.gguf")
PEAK_VRAM_FILE = os.path.join(BASE_DIR, "train_peak_vram.txt")

SYSTEM_PROMPT = (
    "Parse the user natural language command into a structured JSON for UAV DMPC."
)

# 与 benchmark.py 完全一致的 16 条测试集
TEST_CASES = [
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
    ("UAV 2 and 4 and 5, form a wedge formation and move to target coordinates (-8, 12, 6).",
     {"mode": "swarm", "formation": "wedge", "uav_ids": [2, 4, 5], "target": [-8.0, 12.0, 6.0]}),
    ("UAV 3 and 5, form line at (25, -8, 12).",
     {"mode": "swarm", "formation": "line", "uav_ids": [3, 5], "target": [25.0, -8.0, 12.0]}),
    ("UAV 1 and 3 and 5, form triangle at (-1, 20, 18).",
     {"mode": "swarm", "formation": "triangle", "uav_ids": [1, 3, 5], "target": [-1.0, 20.0, 18.0]}),
    ("UAV 1 and 2 and 5, form grid at (3, 3, 21).",
     {"mode": "swarm", "formation": "grid", "uav_ids": [1, 2, 5], "target": [3.0, 3.0, 21.0]}),
    ("UAV 3, fly to (0, -10, 5).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [0.0, -10.0, 5.0]}),
    ("UAV 2, go to (15, 3, 11).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [2], "target": [15.0, 3.0, 11.0]}),
    ("Drone 1, proceed to (-9, -14, 2).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [1], "target": [-9.0, -14.0, 2.0]}),
    ("Drone 4, single-agent, move to (22, -3, 14).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [22.0, -3.0, 14.0]}),
    ("UAV 5, travel solo to (0, 22, 14).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [5], "target": [0.0, 22.0, 14.0]}),
    ("UAV 4, head to (-18, 14, 5).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [4], "target": [-18.0, 14.0, 5.0]}),
    ("UAV 3, navigate to (8, -20, 3).",
     {"mode": "single-agent", "formation": "free", "uav_ids": [3], "target": [8.0, -20.0, 3.0]}),
]


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


def main():
    if not os.path.exists(GGUF_PATH):
        print(f"[benchmark_gguf] ❌ 未找到 {GGUF_PATH}")
        print("[benchmark_gguf] 请先运行 merge_and_quantize.py 生成 GGUF。")
        sys.exit(1)

    # 检查 llama-cpp-python 是否支持 GPU
    try:
        from llama_cpp import llama_supports_gpu_offload
        if not llama_supports_gpu_offload():
            print("[benchmark_gguf] ❌ llama-cpp-python 不支持 GPU offload。")
            print("[benchmark_gguf] 请先运行: python setup_cuda_inference.py")
            sys.exit(1)
    except ImportError:
        print("[benchmark_gguf] ❌ 未安装 llama-cpp-python。")
        print("[benchmark_gguf] 请先运行: python setup_cuda_inference.py")
        sys.exit(1)

    from llama_cpp import Llama

    print("\n=== 加载 Q6_K GGUF 模型（全量卸载到 GPU）===")
    print(f"[benchmark_gguf] 模型: {GGUF_PATH}")
    load_before = get_gpu_used_mb()

    llm = Llama(
        model_path=GGUF_PATH,
        n_gpu_layers=-1,   # 全量卸载 GPU
        n_ctx=512,
        verbose=False,
    )

    load_after = get_gpu_used_mb()
    print(f"[benchmark_gguf] 加载前 GPU: {load_before:.1f} MB | 加载后: {load_after:.1f} MB "
          f"(模型占用 ~{load_after - load_before:.1f} MB)")

    # 推理 + 评测
    results = []
    peak_vram = load_after
    print("\n=== 开始推理测评 ===")
    for i, (user_input, expected) in enumerate(TEST_CASES, 1):
        prompt = build_prompt(user_input)
        t0 = time.time()
        output = llm(
            prompt,
            max_tokens=64,
            temperature=0.1,
            stop=["<|endoftext|>", "\n###"],
        )
        elapsed = time.time() - t0

        completion_tokens = output["usage"]["completion_tokens"]
        raw_text = output["choices"][0]["text"].strip()
        predicted = extract_json(raw_text)
        ok = json_matches(predicted, expected) if predicted else False

        ms_per_tok = (elapsed / completion_tokens * 1000) if completion_tokens else 0
        tok_per_s = (completion_tokens / elapsed) if elapsed > 0 else 0
        used_now = get_gpu_used_mb()
        peak_vram = max(peak_vram, used_now)

        results.append({
            "idx": i, "raw": raw_text, "json_ok": ok,
            "latency_s": elapsed, "tokens": completion_tokens,
            "ms_per_tok": ms_per_tok, "tok_per_s": tok_per_s,
        })

        status = "✅" if ok else "❌"
        print(f"[{status}] #{i} {user_input[:42]}")
        print(f"      输出: {raw_text}")
        print(f"      耗时 {elapsed:.3f}s | {completion_tokens} tok | "
              f"{ms_per_tok:.1f} ms/tok | {tok_per_s:.1f} tok/s")

    # 汇总
    n = len(results)
    n_ok = sum(1 for r in results if r["json_ok"])
    avg_ms = sum(r["ms_per_tok"] for r in results) / n
    avg_tps = sum(r["tok_per_s"] for r in results) / n

    train_peak = ""
    if os.path.exists(PEAK_VRAM_FILE):
        with open(PEAK_VRAM_FILE, encoding="utf-8") as f:
            train_peak = f.read().strip()

    print("\n" + "=" * 60)
    print("     📋 Q6_K GGUF GPU 推理验收数据")
    print("=" * 60)
    print(f"  推理方案              : llama.cpp Q6_K GGUF (CUDA GPU)")
    print(f"  JSON 解析准确率       : {n_ok}/{n} ({n_ok / n * 100:.0f}%)")
    print(f"  平均单 Token 延迟     : {avg_ms:.1f} ms/token")
    print(f"  平均推理吞吐量        : {avg_tps:.1f} tokens/s")
    print(f"  推理峰值显存          : {peak_vram:.1f} MB")
    if train_peak:
        print(f"  训练峰值显存 (QLoRA)  : {train_peak} MB")
    print("=" * 60)
    print("  参考目标:")
    print("    - 推理峰值显存 < 3500 MB | 吞吐 > 30 tok/s")
    print("    - JSON 准确率 > 90%")
    print("=" * 60)
    if avg_tps > 30:
        print(f"\n  🎉 吞吐 {avg_tps:.1f} tok/s 达标！（transformers 4-bit 仅 ~10 tok/s）")


if __name__ == "__main__":
    main()
