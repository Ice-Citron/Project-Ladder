from __future__ import annotations

import sys
import argparse
import json
import math
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from rangers_training.vision import TASK_CONDITION_NAMES  # noqa: E402
from rangers_training.vision.localization_dataset import TaskConditionedLocalizationDataset  # noqa: E402
from rangers_training.vision.localization_losses import localization_loss  # noqa: E402
from rangers_training.vision.localization_metrics import compute_localization_metrics  # noqa: E402
from rangers_training.vision.localization_model import (  # noqa: E402
    LOCALIZATION_LABEL_NAMES,
    TaskConditionedPortLocalizer,
    load_port_localizer_checkpoint,
    save_port_localizer_checkpoint,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train the learned task-conditioned target-center / plug-tip localization model."
    )
    parser.add_argument("--train-manifest", required=True)
    parser.add_argument("--val-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--data-root",
        default=None,
        help=(
            "Optional root directory used to resolve relative image paths inside the manifests. "
            "Defaults to each manifest's parent directory."
        ),
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--base-channels", type=int, default=32)
    parser.add_argument("--image-width", type=int, default=224)
    parser.add_argument("--image-height", type=int, default=224)
    parser.add_argument("--sigma-px", type=float, default=4.0)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument(
        "--resume-from",
        default=None,
        help=(
            "Optional localization checkpoint to resume from. When provided, "
            "the model weights are loaded and optimizer state is restored when available."
        ),
    )
    parser.add_argument(
        "--reset-optimizer",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Do not restore optimizer state when resuming from a checkpoint.",
    )
    parser.add_argument(
        "--amp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use autocast on CUDA when available.",
    )
    return parser.parse_args()


def _nanmean(values: list[float]) -> float:
    valid = [value for value in values if not math.isnan(value)]
    if not valid:
        return math.nan
    return float(sum(valid) / len(valid))


def _mean_tensor_dict(rows: list[dict[str, torch.Tensor]]) -> dict[str, float]:
    aggregate: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            aggregate.setdefault(key, []).append(float(value.item()))
    return {key: _nanmean(values) for key, values in aggregate.items()}


def _mean_float_dict(rows: list[dict[str, float]]) -> dict[str, float]:
    aggregate: dict[str, list[float]] = {}
    for row in rows:
        for key, value in row.items():
            aggregate.setdefault(key, []).append(float(value))
    return {key: _nanmean(values) for key, values in aggregate.items()}


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    image_size = (int(args.image_width), int(args.image_height))
    train_dataset = TaskConditionedLocalizationDataset(
        args.train_manifest,
        root_dir=args.data_root,
        image_size=image_size,
        augment=True,
        sigma_px=float(args.sigma_px),
    )
    val_dataset = TaskConditionedLocalizationDataset(
        args.val_manifest,
        root_dir=args.data_root,
        image_size=image_size,
        augment=False,
        sigma_px=float(args.sigma_px),
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    device = torch.device(args.device)
    resume_payload: dict[str, Any] | None = None
    if args.resume_from is not None:
        model, resume_payload = load_port_localizer_checkpoint(
            args.resume_from,
            map_location=device,
        )
        model = model.to(device)
    else:
        model = TaskConditionedPortLocalizer(base_channels=args.base_channels).to(device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    use_amp = bool(args.amp) and device.type == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    config = {
        "train_manifest": str(Path(args.train_manifest).expanduser().resolve()),
        "val_manifest": str(Path(args.val_manifest).expanduser().resolve()),
        "output_dir": str(output_dir),
        "data_root": (
            str(Path(args.data_root).expanduser().resolve())
            if args.data_root is not None
            else None
        ),
        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "num_workers": int(args.num_workers),
        "learning_rate": float(args.learning_rate),
        "weight_decay": float(args.weight_decay),
        "base_channels": int(args.base_channels),
        "image_size": list(image_size),
        "sigma_px": float(args.sigma_px),
        "device": str(device),
        "resume_from": (
            str(Path(args.resume_from).expanduser().resolve())
            if args.resume_from is not None
            else None
        ),
        "reset_optimizer": bool(args.reset_optimizer),
        "task_condition_names": list(TASK_CONDITION_NAMES),
        "label_names": list(LOCALIZATION_LABEL_NAMES),
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    metrics_path = output_dir / "metrics.jsonl"
    best_target_center_error = float("inf")
    best_mean_point_error = float("inf")
    best_visibility_accuracy = float("-inf")
    global_step = 0
    start_epoch = 0
    if resume_payload is not None:
        start_epoch = int(resume_payload.get("epoch", -1)) + 1
        global_step = int(resume_payload.get("step", 0))
        resume_metrics = resume_payload.get("metrics", {})
        best_target_center_error = float(
            resume_metrics.get("val.target_center_error_px", float("inf"))
        )
        best_mean_point_error = float(
            resume_metrics.get("val.mean_point_error_px", float("inf"))
        )
        best_visibility_accuracy = float(
            resume_metrics.get("val.mean_visibility_accuracy", float("-inf"))
        )
        if not args.reset_optimizer and "optimizer_state_dict" in resume_payload:
            optimizer.load_state_dict(resume_payload["optimizer_state_dict"])

    for epoch in range(start_epoch, start_epoch + args.epochs):
        model.train()
        train_loss_rows: list[dict[str, torch.Tensor]] = []
        for batch in train_loader:
            images = batch["image"].to(device, non_blocking=True)
            heatmaps = batch["heatmaps"].to(device, non_blocking=True)
            points = batch["points"].to(device, non_blocking=True)
            visibility = batch["visibility"].to(device, non_blocking=True)
            task_condition = batch["task_condition"].to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)
            autocast_kwargs: dict[str, Any] = {
                "device_type": device.type,
                "enabled": use_amp,
            }
            if device.type == "cuda":
                autocast_kwargs["dtype"] = torch.float16
            with torch.autocast(**autocast_kwargs):
                outputs = model(images, task_condition)
                loss, loss_dict = localization_loss(outputs, heatmaps, points, visibility)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            train_loss_rows.append(loss_dict)
            global_step += images.shape[0]

        train_metrics = _mean_tensor_dict(train_loss_rows)

        model.eval()
        val_loss_rows: list[dict[str, torch.Tensor]] = []
        val_metric_rows: list[dict[str, float]] = []
        with torch.no_grad():
            for batch in val_loader:
                images = batch["image"].to(device, non_blocking=True)
                heatmaps = batch["heatmaps"].to(device, non_blocking=True)
                points = batch["points"].to(device, non_blocking=True)
                visibility = batch["visibility"].to(device, non_blocking=True)
                task_condition = batch["task_condition"].to(device, non_blocking=True)

                outputs = model(images, task_condition)
                _, loss_dict = localization_loss(outputs, heatmaps, points, visibility)
                val_loss_rows.append(loss_dict)
                val_metric_rows.append(compute_localization_metrics(outputs, points, visibility))

        val_loss_metrics = _mean_tensor_dict(val_loss_rows)
        val_eval_metrics = _mean_float_dict(val_metric_rows)
        epoch_row = {
            "epoch": epoch,
            "global_step": global_step,
            **{f"train.{key}": value for key, value in train_metrics.items()},
            **{f"val.{key}": value for key, value in val_loss_metrics.items()},
            **{f"val.{key}": value for key, value in val_eval_metrics.items()},
        }

        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(epoch_row, sort_keys=True) + "\n")

        print(json.dumps(epoch_row, sort_keys=True), flush=True)

        save_port_localizer_checkpoint(
            output_dir / "last.pt",
            model=model,
            epoch=epoch,
            step=global_step,
            optimizer=optimizer,
            metrics=epoch_row,
            config=config,
        )

        target_center_error = float(
            val_eval_metrics.get("target_center_error_px", float("inf"))
        )
        if math.isfinite(target_center_error) and target_center_error < best_target_center_error:
            best_target_center_error = target_center_error
            save_port_localizer_checkpoint(
                output_dir / "best_target_center_error.pt",
                model=model,
                epoch=epoch,
                step=global_step,
                optimizer=optimizer,
                metrics=epoch_row,
                config=config,
            )
            save_port_localizer_checkpoint(
                output_dir / "best.pt",
                model=model,
                epoch=epoch,
                step=global_step,
                optimizer=optimizer,
                metrics=epoch_row,
                config=config,
            )

        mean_point_error = float(
            val_eval_metrics.get("mean_point_error_px", float("inf"))
        )
        if math.isfinite(mean_point_error) and mean_point_error < best_mean_point_error:
            best_mean_point_error = mean_point_error
            save_port_localizer_checkpoint(
                output_dir / "best_mean_point_error.pt",
                model=model,
                epoch=epoch,
                step=global_step,
                optimizer=optimizer,
                metrics=epoch_row,
                config=config,
            )

        visibility_accuracy = float(
            val_eval_metrics.get("mean_visibility_accuracy", float("-inf"))
        )
        if visibility_accuracy > best_visibility_accuracy:
            best_visibility_accuracy = visibility_accuracy
            save_port_localizer_checkpoint(
                output_dir / "best_visibility_accuracy.pt",
                model=model,
                epoch=epoch,
                step=global_step,
                optimizer=optimizer,
                metrics=epoch_row,
                config=config,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
