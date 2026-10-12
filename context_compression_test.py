"""
context_compression_test.py - 创新点1假设检验：相位标签 vs 完整态势 vs 基准

导师假设："相位的引入让端侧小模型的输入上下文压缩一个量级"
本实验用三组对照验证：
  C组（基准）  ：训练时的原始 System Prompt
  A组（无相位）：完整全局态势描述（模拟云端LLM输出直传端侧）
  B组（有相位）：相位标签（模拟云端只传相位信号）

测量：prompt_tokens（tokenizer 精确计数）、JSON成功率、延迟

用法：python context_compression_test.py（本地加载模型，无需 server）
"""
import json
import time
import os
import statistics
import warnings

warnings.filterwarnings("ignore")

# 注入 CUDA DLL 路径（必须在 import llama_cpp 之前）
for _root in [
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
]:
    _p = os.path.join(_root, "bin", "x64")
    if os.path.isdir(_p):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
        break

from llama_cpp import Llama

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "phi2-q5_k_m.gguf")

# ======================================================================
# 场景与相位定义（对应导师的创新点1：集结/保持/重构/避障 + 补充侦察）
# ======================================================================
PHASES = {
    "ASSEMBLE": {
        "situation": (
            "UAV swarm control context: 4 followers currently scattered at "
            "positions (0,0,3), (5,2,3), (-3,5,3), (8,-2,3). Virtual leader "
            "at (10,10,5) heading north at 4 m/s. Formation target is wedge "
            "with 5m spacing. Team needs to gather into formation before "
            "advancing. Wind calm. All links stable. Energy levels above 70%. "
            "No threats detected. Mission timeline: assemble within 60 "
            "seconds then advance to reconnaissance area at (100, 150)."
        ),
        "phase_tag": "ASSEMBLE",
    },
    "OBSTACLE_AVOID": {
        "situation": (
            "UAV swarm control context: 4 followers in wedge formation "
            "advancing north at 5 m/s toward waypoint (100,150). Obstacle "
            "cluster detected 15m ahead: tall structures spanning 30m width. "
            "Radar from sector 4 suggests active scanning. Team must execute "
            "evasive lateral maneuver while maintaining formation cohesion. "
            "Right side blocked by no-fly zone. Recommended action: shift "
            "formation left and increase altitude. Wind from east 3 m/s "
            "adding drift. Fuel at 60%, sufficient for detour."
        ),
        "phase_tag": "OBSTACLE_AVOID",
    },
    "HOLD": {
        "situation": (
            "UAV swarm control context: 4 followers holding line formation "
            "at standoff position (80, 120, 8). Virtual leader circling "
            "overhead providing overwatch. Reconnaissance target building "
            "at (100, 150) under observation. Sensors recording. All UAVs "
            "in stable hover with formation error under 0.5m. Waiting for "
            "extraction order from ground station. Cloud cover increasing, "
            "GPS signal degrading to 80%. Battery at 45%, holding pattern "
            "sustainable for 20 more minutes. No hostile activity detected."
        ),
        "phase_tag": "HOLD",
    },
    "RECONFIGURE": {
        "situation": (
            "UAV swarm control context: mission shift from wedge formation "
            "to line formation required for canyon traversal ahead. Canyon "
            "entrance at (120, 180), width 12m, requires single-file entry. "
            "4 followers must resequence into line with 4m longitudinal "
            "spacing. Two UAVs need lateral position swap (UAV 2 and 3). "
            "Reconfiguration window 30 seconds before canyon entry. Wind "
            "gusting 5 m/s from south complicating lateral moves. All "
            "systems nominal, links stable, no threats in vicinity."
        ),
        "phase_tag": "RECONFIGURE",
    },
    "RECON": {
        "situation": (
            "UAV swarm control context: reconnaissance phase initiated. "
            "Primary target: compound at (150, 200) suspected hostile. 4 "
            "followers to sweep pattern with 10m corridor spacing. Sensor "
            "payloads: EO/IR camera on UAV 1, SIGINT on UAV 2, relay on "
            "UAV 3, spare battery UAV 4. Hostile radar emitting from grid "
            "E4, maintain 50m standoff. Exfiltration route south to LZ "
            "Bravo at (100, 100). Radio silence after crossing phase line "
            " CHARLIE. Sunrise in 40 minutes, use remaining darkness."
        ),
        "phase_tag": "RECON",
    },
}

# ======================================================================
# 测试指令（每组场景用相同指令集，控制变量）
# 指令设计成"需要上下文消歧"的模糊表述——检验上下文是否被利用
# ======================================================================
COMMANDS = [
    # (指令, 期望的行为特征描述——用于判断语义响应)
    ("UAV 1 and 2, adjust formation.", "编队调整——语义取决于场景"),
    ("UAV 3, proceed.", "前进——方向/方式取决于场景"),
    ("All units, execute.", "执行——执行什么取决于场景"),
    ("UAV 2, change position.", "位置变更——目标位置取决于场景"),
    ("UAV 1 and 4, tighten up.", "收紧——间距取决于场景"),
]

ORIG_SYSTEM = ("Parse the user natural language command into a "
               "structured JSON for UAV DMPC.")


def build_prompt(system_text, user_text):
    return (
        f"### System:\n{system_text}\n\n"
        f"### User:\n{user_text}\n\n### Response:\n"
    )


def call_phi2(llm, tok, prompt, max_tokens=80):
    """本地推理，返回 (text, prompt_tokens, completion_tokens, latency)。"""
    # 精确 token 计数（用 tokenizer 编码整个 prompt）
    prompt_tokens = len(tok(prompt)["input_ids"])

    t0 = time.time()
    output = llm(prompt, max_tokens=max_tokens, temperature=0.1,
                 stop=["<|endoftext|>", "\n###"], echo=False)
    latency = time.time() - t0

    # llama_cpp 本地返回格式
    text = output["choices"][0]["text"].strip()
    ct = output["usage"]["completion_tokens"]
    return text, prompt_tokens, ct, latency


def is_valid_json(text):
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                json.loads(text[s:e+1])
                return True
            except json.JSONDecodeError:
                return False
        return False


def main():
    print("=" * 70)
    print("  创新点1假设检验：相位标签 vs 完整态势 vs 基准")
    print("  假设：相位让上下文压缩一个量级（导师原话）")
    print("=" * 70)

    print("\n  加载 Q5_K_M 模型（本地，~3GB 显存）...")
    llm = Llama(model_path=MODEL_PATH, n_gpu_layers=-1, n_ctx=1024,
                verbose=False)
    tok = llm.tokenize.__self__ if hasattr(llm, "tokenize") else None
    # llama_cpp 的 tokenizer 访问方式
    def count_tokens(text):
        return len(llm.tokenize(text.encode("utf-8"), add_bos=False, special=True))

    # 用一个包装替代 tok
    class TokWrapper:
        def __call__(self, text):
            return {"input_ids": llm.tokenize(
                text.encode("utf-8"), add_bos=False, special=True)}
    tok = TokWrapper()

    print("  模型加载完成，开始实验（75 次推理）...\n")

    groups = {"C_baseline": [], "A_full_context": [], "B_phase_tag": []}

    for phase_name, phase_info in PHASES.items():
        for cmd, expectation in COMMANDS:
            prompts = {
                "C_baseline": ORIG_SYSTEM,
                "A_full_context": phase_info["situation"],
                "B_phase_tag": f"Phase: {phase_info['phase_tag']}. {ORIG_SYSTEM}",
            }

            for group, sys_text in prompts.items():
                prompt = build_prompt(sys_text, cmd)
                try:
                    text, pt, ct, lat = call_phi2(llm, tok, prompt)
                    valid = is_valid_json(text)
                    groups[group].append({
                        "phase": phase_name, "cmd": cmd,
                        "prompt_tokens": pt, "completion_tokens": ct,
                        "latency": lat, "json_ok": valid, "output": text,
                    })
                except Exception as e:
                    groups[group].append({
                        "phase": phase_name, "cmd": cmd,
                        "prompt_tokens": 0, "completion_tokens": 0,
                        "latency": 0, "json_ok": False,
                        "output": f"ERROR: {e}",
                    })

        print(f"  完成 {phase_name} ({len(groups['C_baseline'])} 样本/组)")

    # ================= 汇总 =================
    print("\n" + "=" * 70)
    print(f"  📊 结果汇总（每组 {len(groups['C_baseline'])} 个样本）")
    print("=" * 70)

    print(f"\n  {'组':<18} {'平均prompt_tok':<15} {'JSON成功率':<12} "
          f"{'平均延迟(s)':<12} {'压缩比'}")
    print(f"  {'-'*65}")

    base_tokens = statistics.mean(
        [s["prompt_tokens"] for s in groups["C_baseline"]])

    for group in ["C_baseline", "A_full_context", "B_phase_tag"]:
        data = groups[group]
        avg_tok = statistics.mean([s["prompt_tokens"] for s in data])
        avg_lat = statistics.mean([s["latency"] for s in data])
        json_rate = sum(1 for s in data if s["json_ok"]) / len(data) * 100
        ratio = avg_tok / base_tokens
        print(f"  {group:<18} {avg_tok:<15.1f} {json_rate:<12.0f}% "
              f"{avg_lat:<12.2f} {ratio:.2f}x")

    # A vs B 对比（核心）
    a_tok = statistics.mean([s["prompt_tokens"] for s in groups["A_full_context"]])
    b_tok = statistics.mean([s["prompt_tokens"] for s in groups["B_phase_tag"]])
    compression = a_tok / b_tok

    print(f"\n  {'='*65}")
    print(f"  核心对比：A(完整态势) {a_tok:.0f} tok → B(相位标签) {b_tok:.0f} tok")
    print(f"  压缩比：{compression:.1f}x "
          f"{'✅ 达到量级压缩（>10x）' if compression > 10 else '⚠️ 未达量级（<10x）'}")
    print(f"  {'='*65}")

    # 输出样本对比
    print("\n  === 样本输出对比（OBSTACLE_AVOID 场景, 'All units, execute.'）===")
    for group in ["C_baseline", "A_full_context", "B_phase_tag"]:
        for s in groups[group]:
            if s["phase"] == "OBSTACLE_AVOID" and s["cmd"] == "All units, execute.":
                print(f"\n  [{group}] ({s['prompt_tokens']} tok)")
                print(f"    {s['output'][:120]}")

    # JSON 成功率细分
    print("\n  === JSON 成功率按场景 ===")
    for phase_name in PHASES:
        row = []
        for group in ["C_baseline", "A_full_context", "B_phase_tag"]:
            phase_samples = [s for s in groups[group] if s["phase"] == phase_name]
            rate = sum(1 for s in phase_samples if s["json_ok"]) / len(phase_samples) * 100
            row.append(f"{group.split('_')[0]}:{rate:.0f}%")
        print(f"  {phase_name:<16} {' | '.join(row)}")

    # 保存详细结果
    out_path = "context_compression_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    print(f"\n  详细结果已保存: {out_path}")


if __name__ == "__main__":
    main()
