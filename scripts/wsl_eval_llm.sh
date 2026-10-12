#!/bin/bash
# wsl_eval_llm.sh - 在 WSL2 里跑 phase_consistency_eval（key 从 ~/.bashrc 提取）
#
# 用法（Windows 侧，Git Bash）：
#   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash \
#     "/mnt/d/2026-2027/Phi-2 QLoRA/scripts/wsl_eval_llm.sh" --provider deepseek --n 5
#
# 为什么需要这个脚本：WSL 的 ~/.bashrc 开头有交互检测守卫，wsl.exe 非交互
# 调用时不会加载其中内容，所以这里用 grep 精确提取 key 那一行再 source。
# 其余参数原样传给 phase_consistency_eval.py。

# 从 ~/.bashrc 提取 API key（支持 DEEPSEEK / GLM / CLOUD_LLM 三个变量名）
for var in DEEPSEEK_API_KEY GLM_API_KEY CLOUD_LLM_API_KEY; do
  line=$(grep "^export ${var}=" ~/.bashrc 2>/dev/null | tail -1)
  if [ -n "$line" ] && [ -z "${!var}" ]; then
    eval "$line"
  fi
done

if [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$CLOUD_LLM_API_KEY" ]; then
  echo "[警告] ~/.bashrc 中未找到 DEEPSEEK_API_KEY"
fi

PROJ="/mnt/d/2026-2027/Phi-2 QLoRA"
exec python3 "$PROJ/scripts/phase_consistency_eval.py" \
  --out-dir "$PROJ/eval_out" "$@"
