#!/usr/bin/env bash
# Baseline MAPPO ×3 seeds（不需要 Ollama）
# 默认: seeds 21 618 2024，每个 2500 episodes
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
RESULTS_DIR="${RESULTS_DIR:-results_3d}"
SEEDS="${SEEDS:-21 618 2024}"
EPISODES="${EPISODES:-2500}"
EPISODE_LEN="${EPISODE_LEN:-500}"

read -r -a SEED_ARR <<< "$SEEDS"
mkdir -p logs
LOG="logs/baseline_$(date +%Y%m%d_%H%M%S).log"

ARGS=(
  --results-dir "$RESULTS_DIR"
  --methods baseline
  --seeds "${SEED_ARR[@]}"
  --episodes "$EPISODES"
  --episode-len "$EPISODE_LEN"
)
if [[ -n "${DEVICE:-}" ]]; then
  ARGS+=(--device "$DEVICE")
fi

echo "命令: $PYTHON experiment_core_3d.py ${ARGS[*]}"
echo "日志: $LOG"
"$PYTHON" experiment_core_3d.py "${ARGS[@]}" 2>&1 | tee "$LOG"
