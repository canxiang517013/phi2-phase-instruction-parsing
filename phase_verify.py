"""
phase_verify.py - 验证相位条件化微调效果

核心检验：同一模糊指令在不同相位标签下，输出是否真正分化
（训练前的模型输出合法 JSON 但不响应相位语义）

用法：python phase_verify.py
"""
import os
import json
import warnings

warnings.filterwarnings("ignore")

for _root in [
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.3",
    r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8",
]:
    _p = os.path.join(_root, "bin", "x64")
    if os.path.isdir(_p):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
        break

from llama_cpp import Llama

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "phi2-phased-v2-q5_k_m.gguf")
INSTRUCTION = ("Parse the user natural language command into a "
               "structured JSON for UAV DMPC.")

PHASES = ["ASSEMBLE", "HOLD", "RECONFIGURE", "OBSTACLE_AVOID", "RECON"]

# 验证指令（训练用过的 + 训练外的泛化指令）
TEST_CMDS = [
    "UAV 1 and 2, adjust formation.",   # 训练内
    "All units, execute.",               # 训练内
    "UAV 1, proceed.",                   # 训练内
    "UAV 2 and 3, move out.",            # 训练外（泛化测试）
]


def build_prompt(phase, cmd):
    sys_text = f"Phase: {phase}. {INSTRUCTION}" if phase else INSTRUCTION
    return f"### System:\n{sys_text}\n\n### User:\n{cmd}\n\n### Response:\n"


def try_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e+1])
            except json.JSONDecodeError:
                return None
        return None


def main():
    print("加载相位微调模型:", MODEL)
    llm = Llama(model_path=MODEL, n_gpu_layers=-1, n_ctx=512, verbose=False)

    print("\n" + "=" * 70)
    print("  相位条件化验证：同一指令 × 5 相位 → 输出是否分化")
    print("=" * 70)

    for cmd in TEST_CMDS:
        print(f"\n{'─'*60}")
        print(f"指令: {cmd}")
        print(f"{'─'*60}")
        targets_by_phase = {}
        for phase in PHASES:
            prompt = build_prompt(phase, cmd)
            out = llm(prompt, max_tokens=60, temperature=0.1,
                      stop=["<|endoftext|>", "\n###"])
            text = out["choices"][0]["text"].strip()
            d = try_json(text)
            if d and "target" in d:
                t = d["target"]
                targets_by_phase[phase] = t
                form = d.get("formation", "?")
                print(f"  {phase:<16} → target={t} formation={form}")
            else:
                print(f"  {phase:<16} → 解析失败: {text[:50]}")

        # 分化分析
        if len(targets_by_phase) >= 2:
            zs = [t[2] if len(t) > 2 else 0 for t in targets_by_phase.values()]
            xs = [t[0] for t in targets_by_phase.values()]
            z_spread = max(zs) - min(zs)
            x_spread = max(xs) - min(xs)
            print(f"  → 分化度: z范围={z_spread:.1f}m, x范围={x_spread:.1f}m "
                  f"{'✅ 分化' if (z_spread > 5 or x_spread > 10) else '⚠️ 未分化'}")

            # 相位特征检查：RECON 应该远，ASSEMBLE 应该近
            if "RECON" in targets_by_phase and "ASSEMBLE" in targets_by_phase:
                recon_d = abs(targets_by_phase["RECON"][0]) + abs(targets_by_phase["RECON"][1])
                assem_d = abs(targets_by_phase["ASSEMBLE"][0]) + abs(targets_by_phase["ASSEMBLE"][1])
                if recon_d > assem_d * 3:
                    print(f"  → 相位语义 ✅: RECON({recon_d:.0f}m) 远于 ASSEMBLE({assem_d:.0f}m)")

    # 无相位基准（确认基础能力保持）
    print(f"\n{'='*70}")
    print("  基础能力抽查（无相位，训练原格式）")
    print(f"{'='*70}")
    base_cmds = [
        ("UAV 1 and 2, form a line at (10, 5, 20).", "swarm/line/[1,2]/(10,5,20)"),
        ("UAV 3, fly to (0, -10, 5).", "single-agent/free/[3]/(0,-10,5)"),
        ("UAV 1, 2, 3, form grid at (5, -18, 9).", "swarm/grid/[1,2,3]/(5,-18,9)"),
    ]
    ok = 0
    for cmd, expect in base_cmds:
        prompt = build_prompt(None, cmd)
        out = llm(prompt, max_tokens=60, temperature=0.1,
                  stop=["<|endoftext|>", "\n###"])
        text = out["choices"][0]["text"].strip()
        d = try_json(text)
        valid = d is not None and "target" in d
        if valid:
            ok += 1
        print(f"  {'✅' if valid else '❌'} {cmd[:35]:38s} → "
              f"{text[:60] if valid else 'FAIL: ' + text[:40]}")
    print(f"\n  基础能力: {ok}/{len(base_cmds)}")


if __name__ == "__main__":
    main()
