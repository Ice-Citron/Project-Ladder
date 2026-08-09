"""Reporting helpers for the AIC evaluation runner."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from errors import EvalRunnerError


def load_scoring(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvalRunnerError(f"Expected scoring file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise EvalRunnerError(f"Expected scoring.yaml to contain a mapping: {path}")
    return data


def format_score(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.3f}"
    return str(value)


def colorize_blue(text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[94m{text}\033[0m"


def print_summary(
    *,
    policy: str,
    scenario_path: Path,
    run_dir: Path,
    scoring_path: Path,
    compose_log_path: Path,
    eval_log_path: Path | None,
    policy_log_path: Path | None,
    scoring: dict[str, Any],
) -> None:
    summary_lines = [
        "",
        "Evaluation summary",
        f"Policy: {policy}",
        f"Scenario: {scenario_path}",
        f"Run dir: {run_dir}",
        f"Scoring: {scoring_path}",
        f"Compose log: {compose_log_path}",
    ]
    if eval_log_path is not None:
        summary_lines.append(f"Eval log: {eval_log_path}")
    if policy_log_path is not None:
        summary_lines.append(f"Policy log: {policy_log_path}")

    summary_lines.append(f"Total score: {format_score(scoring.get('total'))}")

    for trial_name, trial_data in scoring.items():
        if trial_name == "total":
            continue
        if not isinstance(trial_data, dict):
            summary_lines.append(f"{trial_name}: unexpected score payload")
            continue
        tier_1 = trial_data.get("tier_1", {})
        tier_2 = trial_data.get("tier_2", {})
        tier_3 = trial_data.get("tier_3", {})
        tier_1_score = (
            float(tier_1.get("score", 0.0)) if isinstance(tier_1, dict) else 0.0
        )
        tier_2_score = (
            float(tier_2.get("score", 0.0)) if isinstance(tier_2, dict) else 0.0
        )
        tier_3_score = (
            float(tier_3.get("score", 0.0)) if isinstance(tier_3, dict) else 0.0
        )
        trial_total = tier_1_score + tier_2_score + tier_3_score
        summary_lines.append(
            f"{trial_name}: total={trial_total:.3f} "
            f"(tier_1={tier_1_score:.3f}, tier_2={tier_2_score:.3f}, "
            f"tier_3={tier_3_score:.3f})"
        )

    print(colorize_blue("\n".join(summary_lines)))


def print_failure_summary(
    *,
    policy: str,
    scenario_path: Path,
    run_dir: Path,
    scoring_path: Path,
    compose_log_path: Path,
    eval_log_path: Path | None,
    policy_log_path: Path | None,
    error: str,
) -> None:
    summary_lines = [
        "",
        "Evaluation summary",
        f"Policy: {policy}",
        f"Scenario: {scenario_path}",
        f"Run dir: {run_dir}",
        f"Scoring: {scoring_path}",
        f"Compose log: {compose_log_path}",
    ]
    if eval_log_path is not None:
        summary_lines.append(f"Eval log: {eval_log_path}")
    if policy_log_path is not None:
        summary_lines.append(f"Policy log: {policy_log_path}")
    summary_lines.append("Status: failed")
    summary_lines.append(f"Error: {error}")
    print(colorize_blue("\n".join(summary_lines)))
