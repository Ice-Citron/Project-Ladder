#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import shlex
from datetime import datetime
from pathlib import Path

from generate_fixed_scene_batch import (
    MODE_SPECS,
    OUTPUT_ROOT,
    SceneVariant,
    ensure_dir,
    run_case,
    write_case_manifest,
    write_outputs,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay planned fixed-scene cases from an existing cases.csv into a fresh "
            "recorded batch."
        )
    )
    parser.add_argument("--cases-csv", required=True, help="Source planned cases.csv to replay.")
    parser.add_argument(
        "--session-prefix",
        required=True,
        help="Output batch prefix under rangers_data/outputs/fixed_scene_batches/.",
    )
    parser.add_argument(
        "--recommended-collection-mode",
        action="append",
        dest="recommended_collection_modes",
        default=[],
        help=(
            "Only replay rows whose recommended_collection_mode matches one of these values. "
            "Repeatable."
        ),
    )
    parser.add_argument(
        "--planned-demo-bucket",
        action="append",
        dest="planned_demo_buckets",
        default=[],
        help="Only replay rows whose planned_demo_bucket matches one of these values. Repeatable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of rows to replay after filtering.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Do not run dataset auditing on recorded outputs.",
    )
    parser.add_argument(
        "--engine-wait",
        type=float,
        default=12.0,
        help="Seconds to wait after Gazebo bringup for each case.",
    )
    parser.add_argument(
        "--policy-wait",
        type=float,
        default=4.0,
        help="Seconds to wait after policy startup for each case.",
    )
    parser.add_argument(
        "--result-timeout",
        type=int,
        default=260,
        help="Maximum wall time to wait for recorder completion per case. Default: 260.",
    )
    parser.add_argument(
        "--policy-import",
        help="Optional policy import override. Defaults to the normal CheatCode policy.",
    )
    parser.add_argument(
        "--policy-mode",
        choices=("full", "handoff", "auto_rescue"),
        default="full",
        help=(
            "Policy mode for replayed cases. Use 'handoff' for manual rescue collection "
            "cases that should pause at pre-insert and wait for teleop completion. "
            "Use 'auto_rescue' for integrated scripted retry/reseat collection."
        ),
    )
    parser.add_argument(
        "--handoff-z-offset-m",
        type=float,
        default=0.05,
        help="Pre-insert stop height for handoff mode. Default: 0.05.",
    )
    parser.add_argument(
        "--handoff-settle-s",
        type=float,
        default=1.5,
        help="Settle time before announcing handoff_ready. Default: 1.5.",
    )
    return parser.parse_args()


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _matches_filters(row: dict[str, str], args: argparse.Namespace) -> bool:
    if args.recommended_collection_modes:
        if row.get("recommended_collection_mode", "") not in set(args.recommended_collection_modes):
            return False
    if args.planned_demo_buckets:
        if row.get("planned_demo_bucket", "") not in set(args.planned_demo_buckets):
            return False
    return True


def _parse_json_field(raw: str, default: dict[str, str] | None = None) -> dict[str, str]:
    value = (raw or "").strip()
    if not value:
        return {} if default is None else dict(default)
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object field, got: {value[:120]}")
    return {str(key): str(val) for key, val in payload.items()}


def _build_scene_variant(row: dict[str, str]) -> SceneVariant:
    scene_env = _parse_json_field(row.get("scene_env", ""))
    policy_env = _parse_json_field(row.get("policy_env", ""))
    task_args = tuple(shlex.split(row.get("task_args", "")))
    return SceneVariant(
        env_overrides=scene_env,
        task_args=task_args,
        target_name=row.get("target_name", ""),
        rollout_profile=row.get("rollout_profile", "clean") or "clean",
        perturbation_profile=row.get("perturbation_profile", "none") or "none",
        policy_env_overrides=policy_env,
        planned_demo_bucket=row.get("planned_demo_bucket", "clean_nominal_candidate")
        or "clean_nominal_candidate",
        expected_primary_stage=row.get("expected_primary_stage", "approach") or "approach",
        recommended_collection_mode=row.get("recommended_collection_mode", "scripted")
        or "scripted",
        collection_notes=row.get("collection_notes", ""),
    )


def main() -> int:
    args = parse_args()
    source_cases_csv = Path(args.cases_csv).expanduser().resolve()
    if not source_cases_csv.is_file():
        raise SystemExit(f"cases.csv not found: {source_cases_csv}")

    all_rows = _load_rows(source_cases_csv)
    selected_rows = [row for row in all_rows if _matches_filters(row, args)]
    if args.limit > 0:
        selected_rows = selected_rows[: args.limit]

    if not selected_rows:
        raise SystemExit("No rows matched the requested replay filters.")

    batch_root = ensure_dir(OUTPUT_ROOT / args.session_prefix)
    audit_root = ensure_dir(batch_root / "audits")
    executed_rows: list[dict[str, object]] = []

    first_mode = selected_rows[0].get("mode", "")
    if first_mode not in MODE_SPECS:
        raise SystemExit(f"Unsupported mode in first selected row: {first_mode!r}")
    first_scene_profile = selected_rows[0].get("scene_profile", "")
    first_nic_count_profile = selected_rows[0].get("nic_count_profile", "")
    first_sfp_target_pool = selected_rows[0].get("sfp_target_pool", "")
    first_seed = int(selected_rows[0].get("seed", "0") or 0)
    first_rollout_profile = selected_rows[0].get("rollout_profile", "clean") or "clean"
    first_perturbation_profile = (
        selected_rows[0].get("perturbation_profile", "none") or "none"
    )

    for row in selected_rows:
        mode = row.get("mode", "")
        if mode not in MODE_SPECS:
            raise SystemExit(f"Unsupported mode in row {row.get('case_name', '')}: {mode!r}")

        scene_variant = _build_scene_variant(row)
        source_case_name = row.get("case_name", "")
        case_suffix = source_case_name.rsplit("_", 1)[-1]
        case_name = f"{args.session_prefix}_{case_suffix}"

        executed = run_case(
            case_name=case_name,
            mode_spec=MODE_SPECS[mode],
            scene_variant=scene_variant,
            batch_root=batch_root,
            record=True,
            skip_audit=args.skip_audit,
            engine_wait=args.engine_wait,
            policy_wait=args.policy_wait,
            keep_running=False,
            audit_root=audit_root,
            scene_profile=row.get("scene_profile", ""),
            policy_import=args.policy_import or (row.get("policy_import") or None),
            policy_mode=args.policy_mode,
            handoff_z_offset_m=(
                args.handoff_z_offset_m
                if args.policy_mode in {"handoff", "auto_rescue"}
                else None
            ),
            handoff_settle_s=(
                args.handoff_settle_s
                if args.policy_mode in {"handoff", "auto_rescue"}
                else None
            ),
            result_timeout_seconds=args.result_timeout,
        )
        executed["source_case_name"] = source_case_name
        executed["source_cases_csv"] = str(source_cases_csv)
        executed["generation_mode"] = "replayed_executed"
        executed["seed"] = int(row.get("seed", "0") or 0)
        executed["nic_count_profile"] = row.get("nic_count_profile", "")
        executed["sfp_target_pool"] = row.get("sfp_target_pool", "")
        executed["sc_demo_bucket_profile"] = row.get("sc_demo_bucket_profile", "")
        executed["replayed_at"] = datetime.now().isoformat()

        write_case_manifest(executed)
        executed_rows.append(executed)
        write_outputs(
            batch_root,
            executed_rows,
            mode=first_mode,
            scene_profile=first_scene_profile,
            nic_count_profile=first_nic_count_profile,
            sfp_target_pool=first_sfp_target_pool,
            seed=first_seed,
            rollout_profile=first_rollout_profile,
            perturbation_profile=first_perturbation_profile,
        )

    print(f"Replay batch written to: {batch_root}")
    print(f"Source cases: {source_cases_csv}")
    print(f"Cases replayed: {len(executed_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
