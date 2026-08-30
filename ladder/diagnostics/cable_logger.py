#!/usr/bin/env python3
"""Record cable poses from the ground-truth TF tree."""

import argparse
import json
from pathlib import Path
from typing import TextIO

import rclpy
import yaml
from geometry_msgs.msg import Transform
from rclpy.node import Node
from rclpy.time import Time
from rclpy.executors import ExternalShutdownException
from tf2_ros import Buffer, TransformException, TransformListener


class CableLogger(Node):
    """Write cable poses to one JSONL file."""

    def __init__(self, output_path: Path, plug_frame: str) -> None:
        super().__init__("cable_logger")
        self._output_path = output_path
        self._plug_frame = plug_frame
        self._cable_name = plug_frame.split("/", maxsplit=1)[0]
        self._tcp_frame = "gripper/tcp"
        self._world_frame = "world"

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        self._cable_frames: list[str] = []
        self._output: TextIO | None = None
        self._record_timer = None
        self.exit_code = 0

        self._startup_timer = self.create_timer(3.0, self._check_precondition)

    def _check_precondition(self) -> None:
        """Check all required frames after one finite delay."""
        self._startup_timer.cancel()
        raw_frame_yaml = self._tf_buffer.all_frames_as_yaml()
        # Example: "base_link:\n  parent: 'world'\ncable_1/link_1:..."

        frame_map = yaml.safe_load(raw_frame_yaml) or {}
        # Example: {"base_link": {...}, "cable_1/link_1": {...}}

        frame_names = list(frame_map)
        # Example: ["base_link", "gripper/tcp", "cable_1/link_1"]

        prefix = f"{self._cable_name}/link_"
        # Example: "cable_1/link_"

        cable_frames = [
            frame
            for frame in frame_names
            if frame.startswith(prefix) and frame[len(prefix):].isdigit()
        ]
        # Example: ["cable_1/link_2", "cable_1/link_1"]

        self._cable_frames = sorted(
            cable_frames,
            key=lambda frame: int(frame[len(prefix):]),
        )
        # Example: ["cable_1/link_1", "cable_1/link_2"]

        if not self._cable_frames:
            self.get_logger().error("ground_truth is not true — cable frames "
                                    "are missing")
            self.exit_code = 1
            rclpy.shutdown()
            return

        required_frames = [self._tcp_frame, self._plug_frame, 
                           *self._cable_frames]
        # Example: ["gripper/tcp", "cable_1/sc_tip_link", "cable_1/link_1", 
        #           "cable_1/link_2"]

        missing_frames = [
            frame
            for frame in required_frames
            if not self._tf_buffer.can_transform(
                self._world_frame, frame, Time()
            )
        ]
        # A success gives []. An error can give ["cable_1/sc_tip_link"].

        if missing_frames:
            self.get_logger().error(
                f"Required TF frames are missing: {missing_frames}"
            )
            self.exit_code = 1
            rclpy.shutdown()
            return

        if not self._open_output():
            return
        self._record_timer = self.create_timer(0.1, self._record_tick)

    def _lookup_transform(self, target_frame: str, source_frame: str
                          ) -> Transform:
        """Return the source pose in the target frame."""
        stamped_transform = self._tf_buffer.lookup_transform(
            target_frame,
            source_frame,
            Time(),
        )
        return stamped_transform.transform

    @staticmethod
    def _serialize_transform(transform: Transform) -> dict[str, dict[str, float]]:
        """Return JSON data for one transform."""
        translation = transform.translation
        quaternion = transform.rotation
        return {
            "translation": {
                "x": translation.x,
                "y": translation.y,
                "z": translation.z,
            },
            "quaternion": {
                "x": quaternion.x,
                "y": quaternion.y,
                "z": quaternion.z,
                "w": quaternion.w,
            },
        }

    def _record_tick(self) -> None:
        """Record one complete TF sample."""
        try:
            plug_pose = self._lookup_transform(
                self._world_frame, self._plug_frame
            )
            tcp_pose = self._lookup_transform(
                self._world_frame, self._tcp_frame
            )
            tcp_to_plug = self._lookup_transform(
                self._tcp_frame, self._plug_frame
            )
            cable_link_z = {
                frame: self._lookup_transform(
                    self._world_frame, frame
                ).translation.z
                for frame in self._cable_frames
            }
        except TransformException as error:
            self.get_logger().warning(f"Skip incomplete TF tick: {error}")
            return

        record = {
            "timestamp": (
                self.get_clock().now().nanoseconds / 1_000_000_000
            ),
            "world_frame": self._world_frame,
            "plug_frame": self._plug_frame,
            "tcp_frame": self._tcp_frame,
            "plug_tip_pose": self._serialize_transform(plug_pose),
            "tcp_pose": self._serialize_transform(tcp_pose),
            "tcp_to_plug_tip": self._serialize_transform(tcp_to_plug),
            "cable_link_z": cable_link_z,
        }
        self._write_record(record)

    def _open_output(self) -> bool:
        """Open the JSONL output file."""
        try:
            self._output = self._output_path.open("w", encoding="utf-8")
        except OSError as error:
            self.get_logger().error(f"Cannot open output file: {error}")
            self.exit_code = 1
            rclpy.shutdown()
            return False
        return True

    def _write_record(self, record: dict[str, object]) -> None:
        """Write and flush one JSON record."""
        if self._output is None:
            raise RuntimeError("The output file is not open.")

        try:
            line = json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
            )
            self._output.write(line + "\n")
            self._output.flush()
        except OSError as error:
            self.get_logger().error(f"Cannot write the output file: {error}")
            self.exit_code = 1
            rclpy.shutdown()

    def close_output(self) -> None:
        """Close the JSONL output file."""
        if self._output is not None:
            self._output.close()


def parse_args() -> argparse.Namespace:
    """Parse the command arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output_path",
        type=Path,
        help="Path for the JSONL output file.",
    )
    parser.add_argument(
        "--active-plug-frame",
        required=True,
        type=str,
        help="Name of the active plug-tip frame, e.g. 'cable_1/sc_tip_link'.",
    )
    args = parser.parse_args()

    if "/" not in args.active_plug_frame:
        parser.error("--active-plug-frame must include the cable name.")

    return args


def main() -> None:
    """Run the cable logger."""
    args = parse_args()
    rclpy.init()
    node = CableLogger(args.output_path, args.active_plug_frame)

    try:
        rclpy.spin(node)
    finally:
        exit_code = node.exit_code
        node.close_output()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
