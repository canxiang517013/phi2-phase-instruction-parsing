"""
phase_verify_v4.py - 第四轮验证：修复项 + 全规则回归

重点验证：
  1. OBSTACLE_AVOID@dir@N 参数化规则（含训练外距离 N=28, 50）
  2. RECON 边缘坐标（200,150 / 250,60 / 60,250）
  3. 全相位回归（ASSEMBLE/HOLD/RECONFIGURE 不退化）
  4. 基础能力
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
                     "phi2-phased-v5-q5_k_m.gguf")
INSTRUCTION = ("Parse the user natural language command into a "
               "structured JSON for UAV DMPC.")


def build_prompt(phase_label, cmd):
    sys_text = f"Phase: {phase_label}. {INSTRUCTION}" if phase_label else INSTRUCTION
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


def run(llm, phase_label, cmd):
    prompt = build_prompt(phase_label, cmd)
    out = llm(prompt, max_tokens=70, temperature=0.1,
              stop=["<|endoftext|>", "\n###"])
    return try_json(out["choices"][0]["text"].strip())


def main():
    print("加载 v4 模型:", MODEL)
    llm = Llama(model_path=MODEL, n_gpu_layers=-1, n_ctx=512, verbose=False)
    cmd = "UAV 1 and 2, adjust formation."
    passed = 0
    total = 0

    def check(desc, d, fn):
        nonlocal passed, total
        total += 1
        if d is None:
            print(f"  ❌ {desc}: JSON 解析失败")
            return
        ok = fn(d)
        if ok:
            passed += 1
        t = d.get("target", [None]*3)
        print(f"  {'✅' if ok else '❌'} {desc}: target={t} form={d.get('formation')}")

    # ===== 1. OBSTACLE_AVOID 参数化（重点修复项） =====
    print("\n[1] OBSTACLE_AVOID@dir@N 参数化规则")
    for direction, n, note in [
        ("left", 20, "训练内"), ("right", 20, "训练内"),
        ("left", 30, "训练内"), ("right", 15, "训练内"),
        ("left", 28, "训练外泛化"), ("right", 50, "训练外泛化"),
    ]:
        d = run(llm, f"OBSTACLE_AVOID@{direction}@{n}", cmd)
        exp_x = -n if direction == "left" else n
        check(f"@{direction}@{n} [{note}]", d,
              lambda dd, x=exp_x, nn=n: (
                  abs(dd["target"][0]-x) <= 2 and
                  abs(dd["target"][1]) <= 2 and
                  abs(dd["target"][2]-15) <= 1))

    # ===== 2. RECON 边缘坐标（重点修复项） =====
    print("\n[2] RECON@ 边缘坐标")
    for tx, ty, note in [
        (120, 90, "训练内"), (200, 150, "v3失败项"),
        (250, 60, "上边缘"), (60, 250, "下边缘"),
    ]:
        d = run(llm, f"RECON@({tx},{ty})", cmd)
        check(f"@({tx},{ty}) [{note}]", d,
              lambda dd, x=tx, y=ty: (
                  abs(dd["target"][0]-x) <= 5 and
                  abs(dd["target"][1]-y) <= 5 and
                  abs(dd["target"][2]-15) <= 1))

    # ===== 3. 全相位回归 =====
    print("\n[3] 全相位回归（v3 已通过的规则不退化）")
    # ASSEMBLE
    for gx, gy, note in [(5, 5, "训练内"), (12, -9, "v3泛化项"), (-10, 10, "边缘")]:
        d = run(llm, f"ASSEMBLE@({gx},{gy})", cmd)
        check(f"ASSEMBLE@({gx},{gy}) [{note}]", d,
              lambda dd, x=gx, y=gy: (
                  abs(dd["target"][0]-x) <= 1 and
                  abs(dd["target"][1]-y) <= 1 and
                  abs(dd["target"][2]-5) <= 1))
    # HOLD
    d = run(llm, "HOLD@(-5,6,9)", cmd)
    check("HOLD@(-5,6,9)", d,
          lambda dd: (abs(dd["target"][0]+5) <= 1 and
                      abs(dd["target"][1]-6) <= 1 and
                      abs(dd["target"][2]-9) <= 1))
    # RECONFIGURE
    for form in ["column", "circle"]:
        d = run(llm, f"RECONFIGURE@{form}", cmd)
        check(f"RECONFIGURE@{form}", d, lambda dd, f=form: dd.get("formation") == f)

    # ===== 4. 基础能力 =====
    print("\n[4] 基础能力（无相位）")
    base_ok = 0
    for bc in ["UAV 1 and 2, form a line at (10, 5, 20).",
               "UAV 3, fly to (0, -10, 5).",
               "UAV 1, 2, 3, form grid at (5, -18, 9)."]:
        d = run(llm, None, bc)
        valid = d is not None and "target" in d
        if valid:
            base_ok += 1
        print(f"  {'✅' if valid else '❌'} {bc[:40]}")
    print(f"  基础: {base_ok}/3")

    # ===== 汇总 =====
    print(f"\n{'='*60}")
    print(f"  规则测试: {passed}/{total}  |  基础: {base_ok}/3")
    print(f"  v3 对比: 10/13 → v4: {passed}/{total}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
