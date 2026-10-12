"""
量化基准矩阵测试（创新点2：延迟-精度权衡的系统性基准）

在多个量化档位（FP16/Q8_0/Q6_K/Q5_K_M/Q4_K_M）上跑同一套 16 条测试集，
测量：JSON 准确率、吞吐、延迟、显存、模型大小，输出对比表 + CSV。

用法：
    # 测单个模型
    python benchmark_matrix.py phi2-dmpc-q6_k.gguf
    # 测全部并汇总
    python benchmark_matrix.py --all
"""
import os
import sys
import csv
import json
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

# 注入 CUDA DLL 路径（必须在 import llama_cpp 之前）
for _cuda_root in [
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
]:
    _p = os.path.join(_cuda_root, "bin", "x64")
    if os.path.isdir(_p):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
        break

import pynvml
from llama_cpp import Llama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PEAK_VRAM_FILE = os.path.join(BASE_DIR, "train_peak_vram.txt")

SYSTEM_PROMPT = (
    "Parse the user natural language command into a structured JSON for UAV DMPC."
)

# 16 条测试集（与 benchmark_gguf.py 完全一致）
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

# 全部待测模型
ALL_MODELS = [
    ("FP16",   "phi2-fp16.gguf"),
    ("Q8_0",   "phi2-q8_0.gguf"),
    ("Q6_K",   "phi2-dmpc-q6_k.gguf"),
    ("Q5_K_M", "phi2-q5_k_m.gguf"),
    ("Q4_K_M", "phi2-q4_k_m.gguf"),
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


def benchmark_single(gguf_path, label):
    """对单个 GGUF 模型跑基准，返回结果 dict。"""
    full_path = os.path.join(BASE_DIR, gguf_path) if not os.path.isabs(gguf_path) else gguf_path
    if not os.path.exists(full_path):
        print(f"[{label}] ❌ 文件不存在: {full_path}")
        return None

    model_size_gb = os.path.getsize(full_path) / 1024**3
    print(f"\n{'='*60}")
    print(f"  测试: {label}  ({model_size_gb:.2f} GB)")
    print(f"{'='*60}")

    load_before = get_gpu_used_mb()

    # 尝试加载（FP16 5.2GB 在 6GB 卡上可能 OOM）
    try:
        llm = Llama(model_path=full_path, n_gpu_layers=-1, n_ctx=512, verbose=False)
    except Exception as e:
        print(f"[{label}] ❌ 加载失败（可能 OOM）: {str(e)[:80]}")
        return {
            "label": label, "file": gguf_path, "size_gb": round(model_size_gb, 2),
            "accuracy": "OOM", "tok_s": "-", "ms_tok": "-",
            "vram_mb": "-", "note": "加载失败: " + str(e)[:50],
        }

    load_after = get_gpu_used_mb()
    vram_mb = load_after
    print(f"  模型加载后 GPU: {load_after:.0f} MB")

    # 跑 16 条测试
    correct = 0
    total_tokens = 0
    total_time = 0.0
    fails = []
    for i, (user_input, expected) in enumerate(TEST_CASES, 1):
        prompt = build_prompt(user_input)
        t0 = time.time()
        output = llm(prompt, max_tokens=64, temperature=0.1,
                     stop=["<|endoftext|>", "\n###"])
        elapsed = time.time() - t0

        completion_tokens = output["usage"]["completion_tokens"]
        raw_text = output["choices"][0]["text"].strip()
        predicted = extract_json(raw_text)
        ok = json_matches(predicted, expected) if predicted else False
        if ok:
            correct += 1
        else:
            fails.append((i, user_input[:30], raw_text[:40]))
        total_tokens += completion_tokens
        total_time += elapsed

    acc = correct / len(TEST_CASES) * 100
    tok_s = total_tokens / total_time if total_time > 0 else 0
    ms_tok = (total_time / total_tokens * 1000) if total_tokens else 0

    print(f"  准确率: {correct}/{len(TEST_CASES)} ({acc:.0f}%)")
    print(f"  吞吐: {tok_s:.1f} tok/s | 延迟: {ms_tok:.1f} ms/tok")
    if fails:
        print(f"  失败案例:")
        for idx, inp, out in fails:
            print(f"    #{idx} {inp}... -> {out}...")

    # 释放模型
    del llm
    import gc
    gc.collect()
    time.sleep(2)  # 等显存释放

    return {
        "label": label, "file": gguf_path, "size_gb": round(model_size_gb, 2),
        "accuracy": f"{acc:.0f}% ({correct}/{len(TEST_CASES)})",
        "tok_s": f"{tok_s:.1f}", "ms_tok": f"{ms_tok:.1f}",
        "vram_mb": f"{vram_mb:.0f}", "note": "",
    }


def main():
    results = []

    if "--all" in sys.argv:
        for label, gguf in ALL_MODELS:
            r = benchmark_single(gguf, label)
            if r:
                results.append(r)
    else:
        # 测单个：python benchmark_matrix.py <file.gguf>
        gguf = sys.argv[1] if len(sys.argv) > 1 else ALL_MODELS[2][1]  # 默认 Q6_K
        label = os.path.basename(gguf).replace(".gguf", "")
        r = benchmark_single(gguf, label)
        if r:
            results.append(r)

    # 汇总表
    print(f"\n{'='*70}")
    print(f"  📊 量化基准矩阵（{len(results)} 档 | RTX 3060 Laptop 6GB | 16条测试集）")
    print(f"{'='*70}")
    print(f"  {'格式':<8} {'大小':<8} {'准确率':<16} {'tok/s':<8} {'ms/tok':<8} {'显存MB':<8}")
    print(f"  {'-'*60}")
    for r in results:
        print(f"  {r['label']:<8} {r['size_gb']:<8} {r['accuracy']:<16} "
              f"{r['tok_s']:<8} {r['ms_tok']:<8} {r['vram_mb']:<8}")
    print(f"{'='*70}")

    # 写 CSV
    csv_path = os.path.join(BASE_DIR, "benchmark_matrix_results.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "label", "file", "size_gb", "accuracy", "tok_s", "ms_tok", "vram_mb", "note"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  CSV 已保存: {csv_path}")


if __name__ == "__main__":
    main()
