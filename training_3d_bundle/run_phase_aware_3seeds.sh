#!/usr/bin/env bash
# Phase-aware LLM ×3 seeds（需要 Ollama 与指定模型）
# 建议先跑完 run_baseline_3seeds.sh，再用同一 RESULTS_DIR 跑本脚本；
# 最后用 README 中的 --resume 命令生成合并报告。
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
RESULTS_DIR="${RESULTS_DIR:-results_3d}"
SEEDS="${SEEDS:-21 618 2024}"
EPISODES="${EPISODES:-2500}"
EPISODE_LEN="${EPISODE_LEN:-500}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
LLM_MODEL="${LLM_MODEL:-deepseek-r1:14b}"

read -r -a SEED_ARR <<< "$SEEDS"

if ! curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null; then
  echo "错误: Ollama 不可达 ($OLLAMA_URL)。先启动: ollama serve" >&2
  exit 1
fi
if ! curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" | grep -q "\"$LLM_MODEL\""; then
  echo "错误: Ollama 中找不到模型 $LLM_MODEL。先执行: ollama pull $LLM_MODEL" >&2
  exit 1
fi

mkdir -p logs
LOG="logs/phase_aware_$(date +%Y%m%d_%H%M%S).log"

ARGS=(
  --results-dir "$RESULTS_DIR"
  --methods phase_aware
  --seeds "${SEED_ARR[@]}"
  --episodes "$EPISODES"
  --episode-len "$EPISODE_LEN"
  --ollama-url "$OLLAMA_URL"
  --llm-model "$LLM_MODEL"
)
if [[ -n "${DEVICE:-}" ]]; then
  ARGS+=(--device "$DEVICE")
fi

echo "命令: $PYTHON experiment_core_3d.py ${ARGS[*]}"
echo "日志: $LOG"
"$PYTHON" experiment_core_3d.py "${ARGS[@]}" 2>&1 | tee "$LOG"

cat <<EOF

Phase-aware 训练完成。若 baseline 已在同一 RESULTS_DIR 中完成，
执行以下命令把两种方法合并成一套报告（已完成的运行会被跳过）：

  $PYTHON experiment_core_3d.py \\
    --results-dir $RESULTS_DIR \\
    --methods phase_aware baseline \\
    --seeds ${SEED_ARR[*]} \\
    --episodes $EPISODES --episode-len $EPISODE_LEN \\
    --resume

EOF
