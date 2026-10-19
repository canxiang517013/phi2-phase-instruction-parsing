#!/usr/bin/env bash
# 论文完整协议：5 种方法 × 10 个预注册种子 × 2500 episodes
# 预计耗时以天计，建议在 tmux/screen 中运行：
#   tmux new -s mappo3d
#   bash run_all_5methods_10seeds.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
RESULTS_DIR="${RESULTS_DIR:-results_3d_paper}"
SEEDS="${SEEDS:-21 618 2024 7 999 31415 456 789 555 8888}"
EPISODES="${EPISODES:-2500}"
EPISODE_LEN="${EPISODE_LEN:-500}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
LLM_MODEL="${LLM_MODEL:-deepseek-r1:14b}"

read -r -a SEED_ARR <<< "$SEEDS"

if ! curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" >/dev/null; then
  echo "错误: Ollama 不可达 ($OLLAMA_URL)。uniform_matched 与 phase_aware 都需要它。" >&2
  exit 1
fi
if ! curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" | grep -q "\"$LLM_MODEL\""; then
  echo "错误: Ollama 中找不到模型 $LLM_MODEL。先执行: ollama pull $LLM_MODEL" >&2
  exit 1
fi

mkdir -p logs
LOG="logs/all_5methods_$(date +%Y%m%d_%H%M%S).log"

ARGS=(
  --results-dir "$RESULTS_DIR"
  --methods phase_aware baseline uniform_matched random_matched rule_based
  --seeds "${SEED_ARR[@]}"
  --episodes "$EPISODES"
  --episode-len "$EPISODE_LEN"
  --ollama-url "$OLLAMA_URL"
  --llm-model "$LLM_MODEL"
  --resume
)
if [[ -n "${DEVICE:-}" ]]; then
  ARGS+=(--device "$DEVICE")
fi

echo "命令: $PYTHON experiment_core_3d.py ${ARGS[*]}"
echo "日志: $LOG"
"$PYTHON" experiment_core_3d.py "${ARGS[@]}" 2>&1 | tee "$LOG"
