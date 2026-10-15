"""G7: merge v6lc adapter -> merged dir (CPU)."""
import os, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

import os as _o; BASE_DIR = _o.path.dirname(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))  # 仓库根
base = AutoModelForCausalLM.from_pretrained(
    os.path.join(BASE_DIR, "models", "phi-2"), torch_dtype=torch.float16,
    device_map="cpu", trust_remote_code=True)
merged = PeftModel.from_pretrained(base, os.path.join(BASE_DIR, "adapters", "dmpc_v6lc"))
merged = merged.merge_and_unload()
out = os.path.join(BASE_DIR, "phi2-v6lc-merged")
os.makedirs(out, exist_ok=True)
merged.save_pretrained(out, safe_serialization=True)
AutoTokenizer.from_pretrained(os.path.join(BASE_DIR, "adapters", "dmpc_v6lc"),
                              trust_remote_code=True).save_pretrained(out)
print("MERGED ->", out)
