"""Command-line parsing for the AIC evaluation runner."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_scenario = repo_root / "aic_engine" / "config" / "sample_config.yaml"
    default_compose = repo_root / "docker" / "docker-compose.yaml"
    default_results_root = repo_root / "aic_eval_runs"

    parser = argparse.ArgumentParser(
        description=(
            "Launch the AIC Gazebo evaluator, run a policy for N trials, "
            "and summarize scoring.yaml."
        )
    )
    parser.add_argument(
        "--policy",
        default="aic_example_policies.ros.WaveArm",
        help=(
            "Policy class path loaded by the local aic_model process "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--policy-cmd",
        help=(
            "Full shell command used to launch the policy locally. If omitted, "
            "the runner executes 'pixi run --as-is ros2 run aic_model aic_model ...'."
        ),
    )
    parser.add_argument(
        "--policy-cwd",
        help="Working directory for --policy-cmd. Defaults to the repo root.",
    )
    parser.add_argument(
        "--scenario",
        default=str(default_scenario),
        help="Path to an AIC engine YAML scenario file.",
    )
    parser.add_argument(
        "--config",
        dest="scenario",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        help="Run only the first N configured trials.",
    )
    parser.add_argument(
        "--results-dir",
        help=(
            "Host directory to store the generated config, compose override, "
            "logs, and scoring.yaml. Defaults to a timestamped directory under "
            f"{default_results_root}."
        ),
    )
    parser.add_argument(
        "--docker-compose-file",
        default=str(default_compose),
        help="Path to docker-compose.yaml.",
    )
    parser.add_argument(
        "--project-name",
        help="Docker Compose project name. Defaults to a generated unique name.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=900,
        help="Hard timeout for the docker compose run (default: %(default)s).",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "Force a rebuild of the relevant service image before running. In "
            "the default dockerized-model mode the runner already auto-builds "
            "the fingerprinted 'model' image when its local cache is missing."
        ),
    )
    parser.add_argument(
        "--ground-truth",
        action="store_true",
        help="Run the evaluator with ground_truth:=true.",
    )
    parser.add_argument(
        "--gazebo-gui",
        action="store_true",
        help="Show the Gazebo GUI instead of running headless.",
    )
    parser.add_argument(
        "--launch-rviz",
        action="store_true",
        help="Launch RViz alongside Gazebo.",
    )
    parser.add_argument(
        "--keep-containers",
        action="store_true",
        help="Do not tear down docker compose services after the run.",
    )
    parser.add_argument(
        "--dockerized-model",
        action="store_true",
        help=(
            "Use the docker compose 'model' service. This is the default "
            "behavior unless --local-model is supplied."
        ),
    )
    parser.add_argument(
        "--local-model",
        action="store_true",
        help=(
            "Launch the policy locally with pixi instead of using the docker "
            "compose 'model' service."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the effective config and compose override, then stop.",
    )
    return parser.parse_args()
