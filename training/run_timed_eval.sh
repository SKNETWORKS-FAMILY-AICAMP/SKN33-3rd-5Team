#!/usr/bin/env bash
# extractor_eval을 실행하며 로딩·추론 구간을 분리한 실행 시간과
# 1초 간격 GPU 메모리를 함께 기록한다. CUDA GPU가 있는 환경(RunPod 등)에서
# 프로젝트 루트에서 실행한다.
#
#   bash training/run_timed_eval.sh baseline data/finetuning/holdout.jsonl
#   bash training/run_timed_eval.sh lora data/finetuning/holdout.jsonl \
#     /workspace/models/picare-qwen3-4b-qlora
#
# 초기 버전은 nvidia-smi -l 루프가 개행 없이 타임스탬프를 이어붙이는 버그가
# 있어, 모델 로딩이 빨리 끝나면 로딩·추론 경계가 뭉개졌다(2026-09-01,
# Holdout 20건 LoRA 재현 시 발견). 여기서는 각 측정을 독립된 한 줄로 강제하고,
# 로그에서 "Loading checkpoint shards: 100%"를 찾아 로딩 완료 시각을 따로 남긴다.
set -euo pipefail

MODE=${1:?"사용법: run_timed_eval.sh <baseline|lora> <data.jsonl> [adapter_path]"}
DATA=${2:?"평가 데이터 경로가 필요합니다"}
ADAPTER_PATH=${3:-}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

STEM="$(basename "${DATA%.jsonl}")"
OUT_DIR="artifacts/evaluation"
mkdir -p "$OUT_DIR"
OUT="${OUT_DIR}/${MODE}-${STEM}"

ADAPTER_ARGS=()
if [ -n "$ADAPTER_PATH" ]; then
  ADAPTER_ARGS=(--adapter-path "$ADAPTER_PATH")
fi

: > "${OUT}.gpu.csv"
(
  while true; do
    ts=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
    nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits \
      | awk -v ts="$ts" '{print ts "," $1}' >> "${OUT}.gpu.csv"
    sleep 0.5
  done
) &
MONITOR_PID=$!
trap 'kill $MONITOR_PID 2>/dev/null || true' EXIT

START=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
LOAD_MARK_FILE="${OUT}.load_done"
rm -f "$LOAD_MARK_FILE"

python3 -u -m src.evaluation.extractor_eval \
  --mode "$MODE" \
  --data "$DATA" \
  --catalog data/products/catalog.json \
  "${ADAPTER_ARGS[@]}" \
  --output "${OUT}.json" \
  2>&1 | while IFS= read -r line; do
    echo "$line"
    if [[ "$line" == *'Loading checkpoint shards: 100%'* ]] && [ ! -f "$LOAD_MARK_FILE" ]; then
      date -u +%Y-%m-%dT%H:%M:%S.%3NZ > "$LOAD_MARK_FILE"
    fi
  done > "${OUT}.log"

END=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
kill $MONITOR_PID 2>/dev/null || true
trap - EXIT

{
  echo "start_utc=$START"
  echo "load_done_utc=$(cat "$LOAD_MARK_FILE" 2>/dev/null || echo unknown)"
  echo "end_utc=$END"
} > "${OUT}.runtime.txt"
echo "done: ${OUT}"
