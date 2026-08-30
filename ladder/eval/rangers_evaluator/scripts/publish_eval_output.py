#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi


def sanitize_branch_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._/-]+", "-", value.strip())
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-/. ")
    if sanitized:
        return sanitized
    return f"run-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"


def repo_web_url(repo_id: str, repo_type: str, revision: str | None = None) -> str:
    if repo_type == "dataset":
        base = f"https://huggingface.co/datasets/{repo_id}"
    elif repo_type == "space":
        base = f"https://huggingface.co/spaces/{repo_id}"
    else:
        base = f"https://huggingface.co/{repo_id}"
    if revision and revision != "main":
        return f"{base}/tree/{revision}"
    return base


def create_branch_if_needed(api: HfApi, repo_id: str, branch_name: str, repo_type: str) -> None:
    try:
        api.create_branch(
            repo_id=repo_id,
            branch=branch_name,
            repo_type=repo_type,
            exist_ok=True,
        )
    except TypeError:
        try:
            api.create_branch(repo_id=repo_id, branch=branch_name, repo_type=repo_type)
        except Exception as exc:  # pragma: no cover
            message = str(exc).lower()
            if "already exists" not in message and "409" not in message:
                raise
    except Exception as exc:  # pragma: no cover
        message = str(exc).lower()
        if "already exists" not in message and "409" not in message:
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish one evaluator output directory to a Hugging Face dataset repo."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Evaluator output directory, e.g. rangers_evaluator/outputs/act97_gt_on_sweep_20260421",
    )
    parser.add_argument(
        "--repo-id",
        default="rangers-intrinsic/aic-evaluator-artifacts",
        help="Destination HF dataset repo id.",
    )
    parser.add_argument(
        "--branch-prefix",
        default="eval-output",
        help="Prefix for the upload branch name.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional README title. Defaults to the output directory name.",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional one-paragraph summary for the README.",
    )
    parser.add_argument(
        "--private",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create or keep the repo private. Default: true.",
    )
    parser.add_argument(
        "--upload-main",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also sync the output folder to main. Default: false.",
    )
    return parser.parse_args()


def load_best_checkpoints(output_dir: Path) -> dict | None:
    path = output_dir / "best_checkpoints.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_summary_rows(output_dir: Path) -> list[dict[str, str]]:
    path = output_dir / "summary.csv"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def count_files(output_dir: Path, relative_dir: str, suffix: str = "") -> int:
    root = output_dir / relative_dir
    if not root.is_dir():
        return 0
    if suffix:
        return sum(1 for _ in root.rglob(f"*{suffix}"))
    return sum(1 for _ in root.rglob("*") if _.is_file())


def build_readme(
    *,
    output_dir: Path,
    repo_id: str,
    branch_name: str,
    title: str,
    summary: str,
    best_checkpoints: dict | None,
    summary_rows: list[dict[str, str]],
) -> str:
    lines = [
        f"# {title}",
        "",
        summary,
        "",
        "## Publishing Metadata",
        "",
        f"- repo_id: `{repo_id}`",
        f"- branch: `{branch_name}`",
        f"- published_at: `{datetime.now(timezone.utc).isoformat()}`",
        f"- source_output_dir: `{output_dir}`",
        "",
        "## Contents",
        "",
        f"- top-level files: `{sum(1 for p in output_dir.iterdir() if p.is_file())}`",
        f"- log files: `{count_files(output_dir, 'logs', '.log')}`",
        f"- scenario files: `{count_files(output_dir, 'scenarios')}`",
        f"- video files: `{count_files(output_dir, 'videos', '.mp4')}`",
    ]

    if best_checkpoints:
        lines.extend(
            [
                "",
                "## Best Checkpoints",
                "",
                f"- 198 best: step `{best_checkpoints['198']['step']}`, mean_all `{best_checkpoints['198']['mean_total_all']:.3f}`, mean_sfp `{best_checkpoints['198']['mean_total_sfp']:.3f}`",
                f"- 246 best: step `{best_checkpoints['246']['step']}`, mean_all `{best_checkpoints['246']['mean_total_all']:.3f}`, mean_sfp `{best_checkpoints['246']['mean_total_sfp']:.3f}`",
            ]
        )

    if summary_rows:
        lines.extend(
            [
                "",
                "## Sweep Shape",
                "",
                f"- summary rows: `{len(summary_rows)}`",
                "- trial mix per checkpoint: `3x SFP + 1x SC`",
                "- note: SC is expected to flatline for these SFP-only models",
            ]
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This upload stores evaluator artifacts, not model checkpoints.",
            "- `summary.csv`, `summary_arrays.npz`, and `numpy_plots.html` are the main analysis entrypoints.",
            "- `logs/` contains per-checkpoint per-case evaluator logs for post-hoc debugging.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not output_dir.is_dir():
        raise SystemExit(f"Evaluator output directory not found: {output_dir}")
    if not (output_dir / "summary.csv").is_file():
        raise SystemExit(f"Missing summary.csv in evaluator output: {output_dir}")

    branch_name = sanitize_branch_name(f"{args.branch_prefix}-{output_dir.name}")
    title = args.title or output_dir.name
    best_checkpoints = load_best_checkpoints(output_dir)
    summary_rows = load_summary_rows(output_dir)
    summary = args.summary or (
        "Evaluator artifacts for ACT97 checkpoint sweeps, including aggregate CSV/JSON summaries, "
        "NumPy arrays, SVG/HTML plots, deterministic scenario manifests, and per-run evaluator logs."
    )

    readme_path = output_dir / "README.md"
    readme_path.write_text(
        build_readme(
            output_dir=output_dir,
            repo_id=args.repo_id,
            branch_name=branch_name,
            title=title,
            summary=summary,
            best_checkpoints=best_checkpoints,
            summary_rows=summary_rows,
        ),
        encoding="utf-8",
    )

    publish_manifest = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "repo_id": args.repo_id,
        "repo_type": "dataset",
        "branch": branch_name,
        "private": args.private,
        "upload_main": args.upload_main,
        "output_dir": str(output_dir),
    }
    (output_dir / "publish_manifest.json").write_text(
        json.dumps(publish_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    api = HfApi()
    api.create_repo(
        repo_id=args.repo_id,
        repo_type="dataset",
        private=args.private,
        exist_ok=True,
    )
    create_branch_if_needed(api, args.repo_id, branch_name, "dataset")

    ignore_patterns = [
        "**/__pycache__/**",
        "**/*.pyc",
    ]

    api.upload_folder(
        repo_id=args.repo_id,
        repo_type="dataset",
        folder_path=str(output_dir),
        path_in_repo=".",
        revision=branch_name,
        ignore_patterns=ignore_patterns,
        commit_message=f"Upload evaluator artifacts {output_dir.name}",
    )

    branch_url = repo_web_url(args.repo_id, "dataset", revision=branch_name)
    print(f"HF branch URL: {branch_url}")

    if args.upload_main:
        api.upload_folder(
            repo_id=args.repo_id,
            repo_type="dataset",
            folder_path=str(output_dir),
            path_in_repo=".",
            revision="main",
            ignore_patterns=ignore_patterns,
            commit_message=f"Sync evaluator artifacts {output_dir.name}",
        )
        print(f"HF main URL: {repo_web_url(args.repo_id, 'dataset', revision='main')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
