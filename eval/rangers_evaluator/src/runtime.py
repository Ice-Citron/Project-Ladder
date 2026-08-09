"""Docker and subprocess orchestration for the AIC evaluation runner."""

from __future__ import annotations

import datetime as dt
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from errors import EvalRunnerError

TEARDOWN_NOISE_PATTERNS = (
    "Physics.cc:3188",
    "corrupted size vs. prev_size",
    "double free or corruption",
    "process[gz-4] failed to terminate",
    "sending signal 'SIGTERM' to process[gz-4]",
    "sending signal 'SIGKILL' to process[gz-4]",
    "ExternalShutdownException",
)

POST_SCORE_MODEL_NOISE_PATTERNS = (
    "model-1  |",
    "model-1 exited with code ",
    "-model-1 Stopping",
    "-model-1 Stopped",
)


def compose_base_command(
    project_name: str, compose_file: Path, override_file: Path
) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        project_name,
        "-f",
        str(compose_file),
        "-f",
        str(override_file),
    ]


def stream_subprocess_output(
    process: subprocess.Popen[str],
    log_path: Path,
    timeout_seconds: int,
    *,
    quiet_after_scoring_path: Path | None = None,
) -> int:
    start = dt.datetime.now()
    timed_out = False
    suppressed_line_count = 0

    with log_path.open("w", encoding="utf-8") as log_handle:

        def pump() -> None:
            nonlocal suppressed_line_count
            assert process.stdout is not None
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                if should_suppress_console_line(
                    line, quiet_after_scoring_path=quiet_after_scoring_path
                ):
                    suppressed_line_count += 1
                    continue
                sys.stdout.write(line)
                sys.stdout.flush()

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.send_signal(signal.SIGINT)
            try:
                return_code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait(timeout=15)
        reader.join(timeout=5)

    duration = (dt.datetime.now() - start).total_seconds()
    if timed_out:
        raise EvalRunnerError(
            f"docker compose timed out after {duration:.1f}s; "
            f"see {log_path} for partial logs"
        )
    if suppressed_line_count:
        print(
            "Suppressed "
            f"{suppressed_line_count} known Gazebo shutdown-noise line(s) after "
            f"scoring completed. Full logs are preserved in {log_path}."
        )
    return return_code


def run_compose_up(
    compose_cmd: list[str],
    *,
    build: bool,
    log_path: Path,
    timeout_seconds: int,
    quiet_after_scoring_path: Path | None = None,
) -> int:
    cmd = compose_cmd + ["up", "--abort-on-container-exit", "--exit-code-from", "eval"]
    if build:
        cmd.append("--build")

    print("Running:", shlex.join(cmd))
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return stream_subprocess_output(
        process,
        log_path,
        timeout_seconds,
        quiet_after_scoring_path=quiet_after_scoring_path,
    )


def run_compose_build(
    compose_cmd: list[str],
    *,
    services: list[str],
    log_path: Path,
    timeout_seconds: int,
) -> None:
    cmd = compose_cmd + ["build", *services]
    print("Running:", shlex.join(cmd))
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return_code = stream_subprocess_output(process, log_path, timeout_seconds)
    if return_code != 0:
        service_list = ", ".join(services)
        raise EvalRunnerError(
            f"docker compose build {service_list} exited with {return_code}; "
            f"see {log_path}"
        )


def docker_image_exists(image_name: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0


def run_compose_eval_detached(
    compose_cmd: list[str], *, build: bool, log_path: Path, timeout_seconds: int
) -> None:
    cmd = compose_cmd + ["up", "-d", "eval"]
    if build:
        cmd.append("--build")

    print("Running:", shlex.join(cmd))
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return_code = stream_subprocess_output(process, log_path, timeout_seconds)
    if return_code != 0:
        raise EvalRunnerError(
            f"docker compose up -d eval exited with {return_code}; see {log_path}"
        )


def get_eval_container_id(compose_cmd: list[str]) -> str:
    cmd = compose_cmd + ["ps", "-q", "eval"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    container_id = result.stdout.strip()
    if not container_id:
        raise EvalRunnerError("Could not resolve the eval container id")
    return container_id


def get_container_ip(container_id: str) -> str:
    cmd = [
        "docker",
        "inspect",
        "-f",
        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
        container_id,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise EvalRunnerError(
            f"Could not inspect container {container_id} for IP address: {result.stderr.strip()}"
        )
    container_ip = result.stdout.strip()
    if not container_ip:
        raise EvalRunnerError(f"Container {container_id} does not have an IP address yet")
    return container_ip


def start_prefixed_log_pump(
    process: subprocess.Popen[str],
    log_path: Path,
    prefix: str,
    *,
    quiet_after_scoring_path: Path | None = None,
) -> threading.Thread:
    def pump() -> None:
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log_handle:
            for line in process.stdout:
                log_handle.write(line)
                log_handle.flush()
                if should_suppress_console_line(
                    line, quiet_after_scoring_path=quiet_after_scoring_path
                ):
                    continue
                sys.stdout.write(f"[{prefix}] {line}")
                sys.stdout.flush()

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    return thread


def follow_container_logs(
    container_id: str,
    log_path: Path,
    *,
    quiet_after_scoring_path: Path | None = None,
) -> tuple[subprocess.Popen[str], threading.Thread]:
    process = subprocess.Popen(
        ["docker", "logs", "-f", container_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return process, start_prefixed_log_pump(
        process,
        log_path,
        "eval",
        quiet_after_scoring_path=quiet_after_scoring_path,
    )


def build_policy_command(policy: str, policy_cmd: str | None) -> str:
    if policy_cmd:
        return policy_cmd
    policy_arg = shlex.quote(policy)
    return (
        "source docker/aic_model/zenoh_config_model_session.sh && "
        "export ZENOH_ROUTER_CHECK_ATTEMPTS=-1 && "
        "pixi run --as-is ros2 run aic_model aic_model "
        f"--ros-args -p use_sim_time:=true -p policy:={policy_arg}"
    )


def start_local_policy(
    *,
    policy: str,
    policy_cmd: str | None,
    cwd: Path,
    log_path: Path,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.Popen[str], threading.Thread]:
    command = build_policy_command(policy, policy_cmd)
    print("Running local policy:", command)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    process = subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    return process, start_prefixed_log_pump(process, log_path, "policy")


def wait_for_eval_container(
    container_id: str, *, timeout_seconds: int, policy_process: subprocess.Popen[str]
) -> int:
    wait_process = subprocess.Popen(
        ["docker", "wait", container_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = time.monotonic()
    policy_finished_logged = False

    while True:
        if wait_process.poll() is not None:
            stdout, stderr = wait_process.communicate()
            if wait_process.returncode != 0:
                raise EvalRunnerError(
                    f"docker wait failed for container {container_id}: {stderr.strip()}"
                )
            try:
                return int(stdout.strip())
            except ValueError as exc:
                raise EvalRunnerError(
                    f"Unexpected docker wait output for {container_id}: {stdout!r}"
                ) from exc

        if not policy_finished_logged and policy_process.poll() is not None:
            policy_finished_logged = True
            print(f"Local policy exited with code {policy_process.returncode}")

        if time.monotonic() - start > timeout_seconds:
            wait_process.kill()
            raise EvalRunnerError(
                f"Timed out waiting for eval container {container_id} after "
                f"{timeout_seconds}s"
            )

        time.sleep(1.0)


def wait_for_tcp_port(host: str, port: int, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.5)
    raise EvalRunnerError(
        f"Timed out waiting for TCP endpoint {host}:{port} after {timeout_seconds}s"
    )


def stop_process(process: subprocess.Popen[str], *, timeout_seconds: int = 15) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


def teardown_compose(compose_cmd: list[str], log_path: Path) -> None:
    cmd = compose_cmd + ["down", "-v", "--remove-orphans"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n===== docker compose down =====\n")
        handle.write(result.stdout)
        handle.write(result.stderr)
    if result.returncode != 0:
        print(
            f"Warning: docker compose down exited with {result.returncode}. "
            f"See {log_path} for details.",
            file=sys.stderr,
        )


def should_suppress_console_line(
    line: str, *, quiet_after_scoring_path: Path | None
) -> bool:
    if quiet_after_scoring_path is None or not quiet_after_scoring_path.exists():
        return False
    if any(pattern in line for pattern in POST_SCORE_MODEL_NOISE_PATTERNS):
        return True
    return any(pattern in line for pattern in TEARDOWN_NOISE_PATTERNS)
