#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
OUTPUTS_ROOT="$REPO_ROOT/rangers_evaluator/outputs"
AIC_EVAL_RUNS_ROOT="$REPO_ROOT/aic_eval_runs"
OUTPUT_GLOB="act48_student_clean_497_real132_sfp5_gt_on_*"
RUN_REGEX='/act48-497-real-.*-gt-on/results/scoring.yaml$'
TOTAL_RUNS=660
WATCH_MODE=0
INTERVAL=10
OUTPUT_DIR=""

usage() {
  cat <<'EOF'
Usage: bash rangers_evaluator/bash/monitor_act48_real_sweep.sh [options]

Options:
  --output-dir PATH   Explicit sweep output directory to inspect.
  --watch             Refresh repeatedly.
  --every SECONDS     Refresh interval for --watch. Default: 10.
  --total-runs N      Expected total completed runs. Default: 660.
  --help              Show this help text.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --watch)
      WATCH_MODE=1
      shift
      ;;
    --every)
      INTERVAL="$2"
      shift 2
      ;;
    --total-runs)
      TOTAL_RUNS="$2"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

pick_latest_output_dir() {
  find "$OUTPUTS_ROOT" -maxdepth 1 -mindepth 1 -type d -name "$OUTPUT_GLOB" -printf '%T@ %p\n' \
    | sort -n \
    | tail -n 1 \
    | cut -d' ' -f2-
}

count_resume_logs() {
  local logs_dir="$1/logs"
  if [[ ! -d "$logs_dir" ]]; then
    printf '0\n'
    return
  fi
  find "$logs_dir" -maxdepth 1 -type f -name '*.log' | wc -l | tr -d ' '
}

latest_resume_log() {
  local logs_dir="$1/logs"
  if [[ ! -d "$logs_dir" ]]; then
    return
  fi
  find "$logs_dir" -maxdepth 1 -type f -name '*.log' -printf '%T@ %p\n' \
    | sort -n \
    | tail -n 1 \
    | cut -d' ' -f2-
}

count_completed_runs() {
  if [[ ! -d "$AIC_EVAL_RUNS_ROOT" ]]; then
    printf '0\n'
    return
  fi
  find "$AIC_EVAL_RUNS_ROOT" -maxdepth 3 -type f -path '*/results/scoring.yaml' \
    | rg "$RUN_REGEX" \
    | wc -l \
    | tr -d ' '
}

latest_scoring_file() {
  if [[ ! -d "$AIC_EVAL_RUNS_ROOT" ]]; then
    return
  fi
  find "$AIC_EVAL_RUNS_ROOT" -maxdepth 3 -type f -path '*/results/scoring.yaml' -printf '%T@ %p\n' \
    | rg "$RUN_REGEX" \
    | sort -n \
    | tail -n 1 \
    | cut -d' ' -f2-
}

print_section() {
  local title="$1"
  printf '\n== %s ==\n' "$title"
}

print_once() {
  local chosen_output_dir="$OUTPUT_DIR"
  if [[ -z "$chosen_output_dir" ]]; then
    chosen_output_dir=$(pick_latest_output_dir)
  fi

  if [[ -z "$chosen_output_dir" || ! -d "$chosen_output_dir" ]]; then
    printf 'No matching output directory found under %s\n' "$OUTPUTS_ROOT" >&2
    exit 1
  fi

  local resume_logs completed_runs percent latest_log latest_scoring
  resume_logs=$(count_resume_logs "$chosen_output_dir")
  completed_runs=$(count_completed_runs)
  percent=$(awk -v done="$completed_runs" -v total="$TOTAL_RUNS" 'BEGIN { if (total == 0) { printf "0.0" } else { printf "%.1f", (100.0 * done / total) } }')
  latest_log=$(latest_resume_log "$chosen_output_dir" || true)
  latest_scoring=$(latest_scoring_file || true)

  printf 'Output dir: %s\n' "$chosen_output_dir"
  printf 'Completed runs: %s / %s (%s%%)\n' "$completed_runs" "$TOTAL_RUNS" "$percent"
  printf 'Resume-session logs: %s\n' "$resume_logs"

  if [[ -n "$latest_scoring" ]]; then
    print_section "Latest Finished Scoring"
    printf 'File: %s\n' "$latest_scoring"
    sed -n '1,40p' "$latest_scoring"
  fi

  if [[ -n "$latest_log" ]]; then
    print_section "Current Session Latest Log"
    printf 'File: %s\n' "$latest_log"
    tail -n 30 "$latest_log"
  fi
}

if [[ "$WATCH_MODE" -eq 1 ]]; then
  while true; do
    clear || true
    print_once
    sleep "$INTERVAL"
  done
else
  print_once
fi
