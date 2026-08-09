#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TRAINING_ROOT="${REPO_ROOT}/../aic-rangers-isaac-training/rangers_training"
PYTHON_BIN="${TRAINING_ROOT}/.pixi/envs/default/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Training Python env not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [[ -f "${TRAINING_ROOT}/.secrets.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${TRAINING_ROOT}/.secrets.env"
  set +a
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "HF_TOKEN not set; cannot publish evaluator artifacts." >&2
  exit 1
fi

DEFAULT_OUTPUT_DIR="${REPO_ROOT}/rangers_evaluator/outputs/act97_gt_on_sweep_20260421"

cd "${REPO_ROOT}"

"${PYTHON_BIN}" rangers_evaluator/scripts/publish_eval_output.py \
  --output-dir "${AIC_EVAL_OUTPUT_DIR:-${DEFAULT_OUTPUT_DIR}}" \
  --repo-id "${AIC_EVAL_HF_REPO_ID:-rangers-intrinsic/aic-evaluator-artifacts}" \
  --branch-prefix "${AIC_EVAL_HF_BRANCH_PREFIX:-act97-gt-on-sweep}" \
  --private \
  "$@"
