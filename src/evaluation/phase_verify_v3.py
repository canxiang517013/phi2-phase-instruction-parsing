"""
phase_verify_v3.py - 第三轮验证：确定性相位模板的规则学习与泛化

关键测试：
  1. 参数化相位的规则应用（训练内坐标）
  2. 训练外坐标泛化（ASSEMBLE@ 未见过的参数）
  3. 方向规则（OBSTACLE_AVOID@left/right → ∓20）
  4. 队形参数跟随（RECONFIGURE@column → formation=column）
  5. 基础能力保持
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
                     "phi2-phased-v3-q5_k_m.gguf")
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
    text = out["choices"][0]["text"].strip()
    return try_json(text), text


def check_rule(d, rule_name, expected_fn):
    """检查输出是否符合相位规则。"""
    if d is None:
        return f"❌ {rule_name}: JSON 解析失败"
    ok = expected_fn(d)
    t = d.get("target", [None]*3)
    return f"{'✅' if ok else '❌'} {rule_name}: target={t} form={d.get('formation')}"


def main():
    print("加载 v3 模型:", MODEL)
    llm = Llama(model_path=MODEL, n_gpu_layers=-1, n_ctx=512, verbose=False)
    cmd = "UAV 1 and 2, adjust formation."

    print("\n" + "=" * 70)
    print("  第三轮验证：确定性相位规则学习")
    print("=" * 70)

    # ===== 1. ASSEMBLE 规则：target = @(参数x, 参数y, 5) =====
    print("\n[1] ASSEMBLE@ 规则（target 应等于参数 + z=5）")
    for gx, gy, note in [(5, 5, "训练内"), (-7, 3, "训练内"), (12, -9, "训练外泛化")]:
        d, raw = run(llm, f"ASSEMBLE@({gx},{gy})", cmd)
        result = check_rule(d, f"ASSEMBLE@({gx},{gy}) [{note}]",
                            lambda dd, x=gx, y=gy: (
                                abs(dd["target"][0]-x) < 1 and
                                abs(dd["target"][1]-y) < 1 and
                                abs(dd["target"][2]-5) < 1))
        print(f"  {result}")

    # ===== 2. HOLD 规则：target = 参数原样 =====
    print("\n[2] HOLD@ 规则（target 应等于参数原样）")
    for px, py, pz, note in [(3, -2, 7, "训练内"), (-5, 6, 9, "训练外泛化")]:
        d, raw = run(llm, f"HOLD@({px},{py},{pz})", cmd)
        result = check_rule(d, f"HOLD@({px},{py},{pz}) [{note}]",
                            lambda dd, x=px, y=py, z=pz: (
                                abs(dd["target"][0]-x) < 1 and
                                abs(dd["target"][1]-y) < 1 and
                                abs(dd["target"][2]-z) < 1))
        print(f"  {result}")

    # ===== 3. OBSTACLE_AVOID 规则：left→(-20,0,15), right→(20,0,15) =====
    print("\n[3] OBSTACLE_AVOID@ 方向规则")
    for direction, exp_x in [("left", -20), ("right", 20)]:
        d, raw = run(llm, f"OBSTACLE_AVOID@{direction}", cmd)
        result = check_rule(d, f"OBSTACLE_AVOID@{direction}",
                            lambda dd, x=exp_x: (
                                abs(dd["target"][0]-x) < 1 and
                                abs(dd["target"][1]) < 1 and
                                abs(dd["target"][2]-15) < 1))
        print(f"  {result}")

    # ===== 4. RECONFIGURE 规则：formation 跟参数，target=(15,15,8) =====
    print("\n[4] RECONFIGURE@ 队形跟随规则")
    for form in ["column", "circle", "wedge"]:
        d, raw = run(llm, f"RECONFIGURE@{form}", cmd)
        result = check_rule(d, f"RECONFIGURE@{form}",
                            lambda dd, f=form: dd.get("formation") == f)
        print(f"  {result}")

    # ===== 5. RECON 规则：target = @(参数, 15) =====
    print("\n[5] RECON@ 规则（target 应等于参数 + z=15）")
    for tx, ty, note in [(120, 90, "训练内"), (200, 150, "训练外泛化")]:
        d, raw = run(llm, f"RECON@({tx},{ty})", cmd)
        result = check_rule(d, f"RECON@({tx},{ty}) [{note}]",
                            lambda dd, x=tx, y=ty: (
                                abs(dd["target"][0]-x) < 2 and
                                abs(dd["target"][1]-y) < 2 and
                                abs(dd["target"][2]-15) < 1))
        print(f"  {result}")

    # ===== 6. 相位间分化（同指令不同相位） =====
    print("\n[6] 相位分化（同指令 'All units, execute.'）")
    for label in ["ASSEMBLE@(5,5)", "HOLD@(3,3,7)", "OBSTACLE_AVOID@left",
                  "RECON@(100,100)"]:
        d, raw = run(llm, label, "All units, execute.")
        if d:
            print(f"  {label:<22} → target={d.get('target')}")
        else:
            print(f"  {label:<22} → FAIL: {raw[:40]}")

    # ===== 7. 基础能力 =====
    print("\n[7] 基础能力（无相位）")
    base_cmds = [
        "UAV 1 and 2, form a line at (10, 5, 20).",
        "UAV 3, fly to (0, -10, 5).",
        "UAV 1, 2, 3, form grid at (5, -18, 9).",
    ]
    ok = 0
    for bc in base_cmds:
        d, raw = run(llm, None, bc)
        valid = d is not None and "target" in d
        if valid:
            ok += 1
        print(f"  {'✅' if valid else '❌'} {bc[:38]:40s}")
    print(f"\n  基础能力: {ok}/{len(base_cmds)}")


if __name__ == "__main__":
    main()
