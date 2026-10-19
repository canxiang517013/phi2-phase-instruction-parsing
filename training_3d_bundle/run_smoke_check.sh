#!/usr/bin/env bash
# 冒烟检查：环境自检 + 2 episode baseline 训练（CPU，约 1 分钟）
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
RESULTS_DIR="${RESULTS_DIR:-results_3d_smoke}"

echo "[1/2] 环境自检"
"$PYTHON" check_environment.py

echo
echo "[2/2] 2 episode baseline 冒烟训练"
"$PYTHON" experiment_core_3d.py \
  --results-dir "$RESULTS_DIR" \
  --methods baseline \
  --seeds 7 \
  --episodes 2 \
  --episode-len 50 \
  --device cpu

echo
echo "冒烟检查完成。结果目录: $RESULTS_DIR"
