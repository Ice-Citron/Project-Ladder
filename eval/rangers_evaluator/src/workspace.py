"""Filesystem and config helpers for the AIC evaluation runner."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from errors import EvalRunnerError


def ensure_file_exists(path: Path, label: str) -> None:
    if not path.is_file():
        raise EvalRunnerError(f"{label} not found: {path}")


def sanitize_project_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    return cleaned or "aic-eval"


def make_run_directory(results_dir_arg: str | None, repo_root: Path) -> Path:
    if results_dir_arg:
        run_dir = Path(results_dir_arg).expanduser().resolve()
    else:
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = (repo_root / "aic_eval_runs" / timestamp).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def compute_tree_fingerprint(repo_root: Path, relative_paths: list[str]) -> str:
    hasher = hashlib.sha256()

    for relative_path in sorted(relative_paths):
        path = (repo_root / relative_path).resolve()
        if path.is_dir():
            children = sorted(
                candidate for candidate in path.rglob("*") if candidate.is_file()
            )
            for child in children:
                _hash_file(hasher, child, repo_root)
            continue
        if path.is_file():
            _hash_file(hasher, path, repo_root)
            continue
        raise EvalRunnerError(f"Cannot fingerprint missing path: {path}")

    return hasher.hexdigest()[:12]


def _hash_file(hasher: Any, path: Path, repo_root: Path) -> None:
    hasher.update(path.relative_to(repo_root).as_posix().encode("utf-8"))
    hasher.update(b"\0")
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    hasher.update(b"\0")


def trim_config(
    config_path: Path, num_trials: int | None, output_path: Path
) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise EvalRunnerError(f"Expected a mapping at the top of {config_path}")
    if "trials" not in config or not isinstance(config["trials"], dict):
        raise EvalRunnerError(f"Config is missing a 'trials' mapping: {config_path}")

    trials = list(config["trials"].items())
    if num_trials is not None:
        if num_trials < 1:
            raise EvalRunnerError("--num-trials must be at least 1")
        if num_trials > len(trials):
            raise EvalRunnerError(
                f"--num-trials={num_trials} exceeds available trials ({len(trials)})"
            )
        config["trials"] = dict(trials[:num_trials])

    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)

    return config


def prepare_docker_xauthority(host_run_dir: Path, display: str) -> Path:
    xauthority_path = host_run_dir / ".docker.xauth"
    xauthority_path.unlink(missing_ok=True)

    env = os.environ.copy()
    nlist_result = subprocess.run(
        ["xauth", "nlist", display],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if nlist_result.returncode != 0:
        raise EvalRunnerError(
            "Failed to query X11 authorization cookies with 'xauth nlist'. "
            f"stderr: {nlist_result.stderr.strip()}"
        )

    entries = [line for line in nlist_result.stdout.splitlines() if line.strip()]
    if not entries:
        raise EvalRunnerError(
            "No X11 authorization cookies were found for the current DISPLAY. "
            "Log into an active X11 session or set XAUTHORITY explicitly before "
            "requesting --gazebo-gui/--launch-rviz."
        )

    normalized_entries = []
    for entry in entries:
        if len(entry) >= 4:
            normalized_entries.append("ffff" + entry[4:])
        else:
            normalized_entries.append(entry)

    xauthority_path.touch(mode=0o600)
    nmerge_result = subprocess.run(
        ["xauth", "-f", str(xauthority_path), "nmerge", "-"],
        input="\n".join(normalized_entries) + "\n",
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if nmerge_result.returncode != 0:
        raise EvalRunnerError(
            "Failed to prepare the Docker X11 authorization cookie file. "
            f"stderr: {nmerge_result.stderr.strip()}"
        )

    xauthority_path.chmod(0o600)
    return xauthority_path


def build_override_config(
    host_run_dir: Path,
    *,
    ground_truth: bool,
    gazebo_gui: bool,
    launch_rviz: bool,
    dockerized_model: bool,
    model_image: str | None,
    policy: str,
) -> dict[str, Any]:
    container_runner_dir = "/runner"
    container_results_dir = f"{container_runner_dir}/results"
    container_config_path = f"{container_runner_dir}/config.yaml"
    needs_gui = gazebo_gui or launch_rviz

    services: dict[str, Any] = {
        "eval": {
            "environment": {
                "AIC_RESULTS_DIR": container_results_dir,
            },
            "volumes": [f"{host_run_dir}:{container_runner_dir}"],
            "command": [
                f"gazebo_gui:={'true' if gazebo_gui else 'false'}",
                f"launch_rviz:={'true' if launch_rviz else 'false'}",
                f"ground_truth:={'true' if ground_truth else 'false'}",
                "start_aic_engine:=true",
                "shutdown_on_aic_engine_exit:=true",
                f"aic_engine_config_file:={container_config_path}",
            ],
        }
    }

    if needs_gui:
        display = os.environ.get("DISPLAY")
        if not display:
            raise EvalRunnerError(
                "--gazebo-gui/--launch-rviz requested, but DISPLAY is not set"
            )
        x11_socket = Path("/tmp/.X11-unix")
        if not x11_socket.exists():
            raise EvalRunnerError(
                "--gazebo-gui/--launch-rviz requested, but /tmp/.X11-unix was not found"
            )

        eval_environment = services["eval"]["environment"]
        eval_volumes = services["eval"]["volumes"]
        eval_environment.update(
            {
                "DISPLAY": display,
                "QT_X11_NO_MITSHM": "1",
            }
        )
        eval_volumes.append("/tmp/.X11-unix:/tmp/.X11-unix:rw")
        docker_xauthority_path = prepare_docker_xauthority(host_run_dir, display)
        eval_environment["XAUTHORITY"] = "/tmp/.docker.xauth"
        eval_volumes.append(f"{docker_xauthority_path}:/tmp/.docker.xauth:ro")

    if dockerized_model:
        services["model"] = {
            "image": model_image,
            "command": [
                "--ros-args",
                "-p",
                "use_sim_time:=true",
                "-p",
                f"policy:={policy}",
            ],
        }
    else:
        services["eval"]["ports"] = ["7447:7447"]

    return {"services": services}


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def write_metadata(
    path: Path,
    *,
    policy: str,
    policy_cmd: str | None,
    source_scenario_path: Path,
    num_trials: int | None,
    compose_file: Path,
    project_name: str,
    dockerized_model: bool,
    model_image: str | None = None,
) -> None:
    payload = {
        "policy": policy,
        "policy_cmd": policy_cmd,
        "source_scenario_path": str(source_scenario_path),
        "num_trials": num_trials,
        "docker_compose_file": str(compose_file),
        "project_name": project_name,
        "dockerized_model": dockerized_model,
        "model_image": model_image,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_yaml(path, payload)
