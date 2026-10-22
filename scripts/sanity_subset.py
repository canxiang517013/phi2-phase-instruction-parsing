#!/usr/bin/env python3
"""sanity_subset.py — v6.3 门禁评测（四任务方案 D4）

判定标准：
  ① phase_200 前 100 条：输出非空率必须 100%（针对 v6.2 的 EOS 退化）
  ② basic_240 前 100 条：主指标（judge_basic exact）≥ 90%

加载方式：transformers 4-bit + LoRA adapter（本机无 llama.cpp；
判分逻辑复用 src/evaluation/eval_run.py，与正式评测同口径）。
生成：贪心（等效其 temperature=0.1 固定种子的近贪心设定），max_new_tokens=70，
stop 处理 '<|endoftext|>' 与 '\\n###'。

用法：
  python scripts/sanity_subset.py dmpc_v6_3 [dmpc_v5 ...]
"""
import json
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# 本机未装 llama-cpp-python；评测判分函数不依赖它，stub 掉模块导入
sys.modules.setdefault("llama_cpp", types.SimpleNamespace(Llama=object))

from evaluation.eval_run import build_prompt, try_json, judge_basic, judge_phase  # noqa: E402

import torch  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: E402
from peft import PeftModel  # noqa: E402

MAX_NEW = 70
LIMIT = 100


def load_model(adapter_dir: str):
    tok = AutoTokenizer.from_pretrained(str(ROOT / "models" / "phi-2"), trust_remote_code=True)
    tok.pad_token = tok.eos_token
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    base = AutoModelForCausalLM.from_pretrained(
        str(ROOT / "models" / "phi-2"), quantization_config=bnb,
        device_map="auto", trust_remote_code=True)
    model = PeftModel.from_pretrained(base, str(ROOT / "adapters" / adapter_dir))
    model.eval()
    return tok, model


def generate(tok, model, prompt: str) -> str:
    ids = tok(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=MAX_NEW, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    text = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    return text.split("\n###")[0].strip()


def evaluate(tok, model, testset: str):
    items = [json.loads(l) for l in
             open(ROOT / "evaluation" / "testsets" / f"{testset}.jsonl", encoding="utf-8")][:LIMIT]
    n = nonempty = acc = schema_ok_n = 0
    failures = []
    t0 = time.time()
    for item in items:
        raw = generate(tok, model, build_prompt(item))
        got = try_json(raw)
        n += 1
        if raw:
            nonempty += 1
        if isinstance(got, dict):
            schema_ok_n += 1
        if item["kind"] == "basic":
            ok, _ = judge_basic(got, item["expected"])
        else:
            ok, _, _ = judge_phase(got, item)
        if ok:
            acc += 1
        elif len(failures) < 5:
            failures.append((item["id"], raw[:90]))
    dt = time.time() - t0
    return {"testset": testset, "n": n,
            "nonempty": nonempty / n, "schema": schema_ok_n / n,
            "acc": acc / n, "sec": dt, "failures": failures}


def main():
    print(f"torch {torch.__version__} | cuda {torch.cuda.is_available()}")
    for adapter in sys.argv[1:]:
        print(f"\n===== {adapter} =====")
        tok, model = load_model(adapter)
        for ts in ("basic_240", "phase_200"):
            r = evaluate(tok, model, ts)
            print(f"[{adapter}/{ts}] n={r['n']} 非空率={r['nonempty']:.1%} "
                  f"schema={r['schema']:.1%} 主指标={r['acc']:.1%} ({r['sec']:.0f}s)")
            for fid, raw in r["failures"]:
                print(f"    失败示例 {fid}: {raw!r}")
        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
