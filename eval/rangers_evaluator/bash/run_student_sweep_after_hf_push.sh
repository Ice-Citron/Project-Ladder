#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SWEEP_SCRIPT="${REPO_ROOT}/tools/act48_eval/sweep_checkpoints.py"
CHECKPOINT_ROOT="/home/starforge-sf95/Black-Projects/Project-Automaton/aic-rangers-isaac-training/rangers_training/outputs/sfp_student_clean_497_48ep/2026-04-21_15-28-25/checkpoints"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR_DEFAULT="${REPO_ROOT}/rangers_evaluator/outputs/act48_student_clean_497_sweep_after_hf_${TIMESTAMP}"

UPLOAD_PID=""
OUTPUT_DIR="${OUTPUT_DIR_DEFAULT}"

usage() {
  cat <<'EOF'
Usage:
  bash rangers_evaluator/bash/run_student_sweep_after_hf_push.sh --upload-pid PID [--output-dir PATH]

Options:
  --upload-pid PID   PID of the active publish_act_run.py process to wait for.
  --output-dir PATH  Sweep artifact directory. Defaults under rangers_evaluator/outputs/.
  -h, --help         Show this help text.

Behavior:
  - waits until the given HF upload PID exits
  - launches the full 132-checkpoint ACT48 GT-on sweep
  - writes the sweep stdout/stderr to OUTPUT_DIR/launcher.log
EOF
}

while (($# > 0)); do
  case "$1" in
    --upload-pid)
      UPLOAD_PID="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${UPLOAD_PID}" ]]; then
  echo "--upload-pid is required." >&2
  exit 2
fi

if [[ ! -f "${SWEEP_SCRIPT}" ]]; then
  echo "Sweep script not found: ${SWEEP_SCRIPT}" >&2
  exit 1
fi

if [[ ! -d "${CHECKPOINT_ROOT}" ]]; then
  echo "Checkpoint root not found: ${CHECKPOINT_ROOT}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
LAUNCHER_LOG="${OUTPUT_DIR}/launcher.log"

{
  echo "[$(date -Is)] watcher started"
  echo "[$(date -Is)] waiting for upload PID ${UPLOAD_PID}"
  echo "[$(date -Is)] output_dir=${OUTPUT_DIR}"

  while kill -0 "${UPLOAD_PID}" 2>/dev/null; do
    echo "[$(date -Is)] upload still running"
    sleep 60
  done

  echo "[$(date -Is)] upload PID ${UPLOAD_PID} exited"
  echo "[$(date -Is)] starting ACT48 student sweep"

  cd "${REPO_ROOT}"
  exec pixi run --frozen python "${SWEEP_SCRIPT}" \
    --ground-truth \
    --no-export-mp4 \
    --policy-class aic_example_policies.ros.RunACT \
    --root-497 "${CHECKPOINT_ROOT}" \
    --output-dir "${OUTPUT_DIR}"
} >>"${LAUNCHER_LOG}" 2>&1
