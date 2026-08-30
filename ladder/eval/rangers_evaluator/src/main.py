"""Main entrypoint for the AIC evaluation runner."""

from __future__ import annotations

import shutil
from pathlib import Path

from ladder.eval.rangers_evaluator.src.cli import parse_args
from ladder.eval.rangers_evaluator.src.errors import EvalRunnerError
from ladder.eval.rangers_evaluator.src.reporting import load_scoring, print_failure_summary, print_summary
from ladder.eval.rangers_evaluator.src.runtime import (
    compose_base_command,
    docker_image_exists,
    follow_container_logs,
    get_container_ip,
    get_eval_container_id,
    run_compose_build,
    run_compose_eval_detached,
    run_compose_up,
    start_local_policy,
    stop_process,
    teardown_compose,
    wait_for_eval_container,
    wait_for_tcp_port,
)
from ladder.eval.rangers_evaluator.src.workspace import (
    build_override_config,
    compute_tree_fingerprint,
    ensure_file_exists,
    make_run_directory,
    sanitize_project_name,
    trim_config,
    write_metadata,
    write_yaml,
)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    compose_file = Path(args.docker_compose_file).expanduser().resolve()
    scenario_path = Path(args.scenario).expanduser().resolve()
    use_dockerized_model = args.dockerized_model or not args.local_model
    policy_cwd = (
        Path(args.policy_cwd).expanduser().resolve() if args.policy_cwd else repo_root
    )

    ensure_file_exists(compose_file, "docker compose file")
    ensure_file_exists(scenario_path, "scenario file")
    if not policy_cwd.is_dir():
        raise EvalRunnerError(f"Policy working directory not found: {policy_cwd}")
    if use_dockerized_model and args.policy_cmd:
        raise EvalRunnerError("--policy-cmd is only supported with --local-model")
    if not use_dockerized_model and not shutil.which("pixi"):
        raise EvalRunnerError(
            "pixi is required for --local-model. "
            "Install pixi or use the default dockerized model mode."
        )

    run_dir = make_run_directory(args.results_dir, repo_root)
    (run_dir / "results").mkdir(parents=True, exist_ok=True)
    scenario_copy_path = run_dir / "config.yaml"
    override_path = run_dir / "docker-compose.override.yaml"
    compose_log_path = run_dir / "compose.log"
    eval_log_path = run_dir / "eval.log"
    policy_log_path = run_dir / "policy.log"
    scoring_path = run_dir / "results" / "scoring.yaml"
    metadata_path = run_dir / "run-metadata.yaml"
    model_image = None
    if use_dockerized_model:
        model_fingerprint = compute_tree_fingerprint(
            repo_root,
            [
                "docker/aic_model/Dockerfile",
                "aic_example_policies",
                "aic_interfaces",
                "aic_model",
            ],
        )
        model_image = f"rangers-evaluator-model:{model_fingerprint}"

    trimmed_config = trim_config(scenario_path, args.num_trials, scenario_copy_path)
    override = build_override_config(
        run_dir,
        ground_truth=args.ground_truth,
        gazebo_gui=args.gazebo_gui,
        launch_rviz=args.launch_rviz,
        dockerized_model=use_dockerized_model,
        model_image=model_image,
        policy=args.policy,
    )
    write_yaml(override_path, override)

    default_project_name = sanitize_project_name(
        f"aic-eval-{run_dir.name}-{__import__('os').getpid()}"
    )
    project_name = sanitize_project_name(args.project_name or default_project_name)
    write_metadata(
        metadata_path,
        policy=args.policy,
        policy_cmd=args.policy_cmd,
        source_scenario_path=scenario_path,
        num_trials=args.num_trials,
        compose_file=compose_file,
        project_name=project_name,
        dockerized_model=use_dockerized_model,
        model_image=model_image,
    )

    print(f"Run dir: {run_dir}")
    print(f"Effective scenario: {scenario_copy_path}")
    print(f"Compose override: {override_path}")
    print(f"Trial count: {len(trimmed_config['trials'])}")
    if model_image is not None:
        print(f"Model image: {model_image}")

    if args.dry_run:
        print("Dry run requested; no containers were started.")
        return 0

    compose_cmd = compose_base_command(project_name, compose_file, override_path)
    exit_code = 0
    scoring: dict[str, object] | None = None
    scoring_load_error: EvalRunnerError | None = None
    try:
        if use_dockerized_model:
            should_build_model = bool(model_image) and (
                args.build or not docker_image_exists(model_image)
            )
            if should_build_model:
                reason = "--build requested" if args.build else "cached image missing"
                print(f"Building dockerized model image ({reason})...")
                run_compose_build(
                    compose_cmd,
                    services=["model"],
                    log_path=compose_log_path,
                    timeout_seconds=args.timeout_seconds,
                )
            exit_code = run_compose_up(
                compose_cmd,
                build=False,
                log_path=compose_log_path,
                timeout_seconds=args.timeout_seconds,
                quiet_after_scoring_path=scoring_path,
            )
        else:
            run_compose_eval_detached(
                compose_cmd,
                build=args.build,
                log_path=compose_log_path,
                timeout_seconds=args.timeout_seconds,
            )
            container_id = get_eval_container_id(compose_cmd)
            container_ip = get_container_ip(container_id)
            print(f"Eval container IP: {container_ip}")
            log_process, log_thread = follow_container_logs(
                container_id,
                eval_log_path,
                quiet_after_scoring_path=scoring_path,
            )
            router_addr = f"{container_ip}:7447"
            print(f"Local policy router endpoint: {router_addr}")
            wait_for_tcp_port(container_ip, 7447, timeout_seconds=60)
            policy_process, policy_thread = start_local_policy(
                policy=args.policy,
                policy_cmd=args.policy_cmd,
                cwd=policy_cwd,
                log_path=policy_log_path,
                extra_env={
                    "AIC_EVAL_ROUTER_ADDR": router_addr,
                    "RMW_IMPLEMENTATION": "rmw_zenoh_cpp",
                },
            )
            try:
                exit_code = wait_for_eval_container(
                    container_id,
                    timeout_seconds=args.timeout_seconds,
                    policy_process=policy_process,
                )
            finally:
                stop_process(policy_process)
                stop_process(log_process)
                policy_thread.join(timeout=5)
                log_thread.join(timeout=5)

        try:
            scoring = load_scoring(scoring_path)
        except EvalRunnerError as exc:
            scoring_load_error = exc
    finally:
        if not args.keep_containers:
            teardown_compose(compose_cmd, compose_log_path)

    if scoring_load_error is not None:
        error_message = str(scoring_load_error)
        if not scoring_path.exists():
            error_message = (
                "Run failed before a real scoring file was produced. "
                f"docker compose exit code: {exit_code}. "
                "The model/eval stack exited before aic_engine could write "
                "results/scoring.yaml."
            )
        print_failure_summary(
            policy=args.policy,
            scenario_path=scenario_copy_path,
            run_dir=run_dir,
            scoring_path=scoring_path,
            compose_log_path=compose_log_path,
            eval_log_path=None if use_dockerized_model else eval_log_path,
            policy_log_path=None if use_dockerized_model else policy_log_path,
            error=error_message,
        )
        return exit_code or 1

    if scoring is None:
        raise EvalRunnerError("Internal error: scoring was not loaded")

    print_summary(
        policy=args.policy,
        scenario_path=scenario_copy_path,
        run_dir=run_dir,
        scoring_path=scoring_path,
        compose_log_path=compose_log_path,
        eval_log_path=None if use_dockerized_model else eval_log_path,
        policy_log_path=None if use_dockerized_model else policy_log_path,
        scoring=scoring,
    )

    if exit_code != 0:
        print(
            f"docker compose exited with code {exit_code}; "
            "see compose.log for details.",
            file=__import__("sys").stderr,
        )
        return exit_code
    return 0
