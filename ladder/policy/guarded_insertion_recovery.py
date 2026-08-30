from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from geometry_msgs.msg import Point, Pose, Quaternion


def _parse_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value is not None else default


def _parse_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value is not None else default


def _parse_mode(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip().lower()
    if value not in {"off", "shadow", "control"}:
        raise ValueError(f"{name} must be one of off/shadow/control, got {value!r}")
    return value


def _pose_position_array(pose: Pose) -> np.ndarray:
    return np.array(
        [float(pose.position.x), float(pose.position.y), float(pose.position.z)],
        dtype=np.float64,
    )


def _copy_pose(pose: Pose) -> Pose:
    return Pose(
        position=Point(
            x=float(pose.position.x),
            y=float(pose.position.y),
            z=float(pose.position.z),
        ),
        orientation=Quaternion(
            x=float(pose.orientation.x),
            y=float(pose.orientation.y),
            z=float(pose.orientation.z),
            w=float(pose.orientation.w),
        ),
    )


def _normalized(vector: np.ndarray, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1.0e-9:
        return fallback.copy()
    return vector / norm


def _clip_vector_norm(vector: np.ndarray, limit: float) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= limit or norm <= 1.0e-9:
        return vector
    return vector * (limit / norm)


def _quaternion_xyzw_to_array(quaternion: Quaternion) -> np.ndarray:
    quat = np.array(
        [
            float(quaternion.x),
            float(quaternion.y),
            float(quaternion.z),
            float(quaternion.w),
        ],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(quat))
    if norm <= 1.0e-9:
        return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    return quat / norm


def _array_to_quaternion_xyzw(quat: np.ndarray) -> Quaternion:
    return Quaternion(
        x=float(quat[0]),
        y=float(quat[1]),
        z=float(quat[2]),
        w=float(quat[3]),
    )


def _quat_slerp(q0: np.ndarray, q1: np.ndarray, alpha: float) -> np.ndarray:
    q0 = q0 / max(float(np.linalg.norm(q0)), 1.0e-9)
    q1 = q1 / max(float(np.linalg.norm(q1)), 1.0e-9)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    dot = float(np.clip(dot, -1.0, 1.0))
    if dot > 0.9995:
        blended = q0 + alpha * (q1 - q0)
        return blended / max(float(np.linalg.norm(blended)), 1.0e-9)
    theta_0 = float(np.arccos(dot))
    sin_theta_0 = float(np.sin(theta_0))
    theta = theta_0 * alpha
    sin_theta = float(np.sin(theta))
    s0 = float(np.sin(theta_0 - theta) / max(sin_theta_0, 1.0e-9))
    s1 = float(sin_theta / max(sin_theta_0, 1.0e-9))
    return (s0 * q0) + (s1 * q1)


def _quat_angle_rad(q0: np.ndarray, q1: np.ndarray) -> float:
    q0 = q0 / max(float(np.linalg.norm(q0)), 1.0e-9)
    q1 = q1 / max(float(np.linalg.norm(q1)), 1.0e-9)
    dot = float(np.clip(abs(np.dot(q0, q1)), -1.0, 1.0))
    return float(2.0 * np.arccos(dot))


def _quat_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ],
        dtype=np.float64,
    )


def _axis_angle_to_quat(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = _normalized(axis, np.array([0.0, 0.0, 1.0], dtype=np.float64))
    half = 0.5 * float(angle_rad)
    sin_half = float(np.sin(half))
    return np.array(
        [
            axis[0] * sin_half,
            axis[1] * sin_half,
            axis[2] * sin_half,
            float(np.cos(half)),
        ],
        dtype=np.float64,
    )


@dataclass
class GuardedInsertionRecoveryConfig:
    mode: str = "shadow"
    max_lateral_delta_m: float = 0.0010
    max_axial_insert_delta_m: float = 0.0008
    max_rotation_delta_rad: float = 0.035
    soft_force_threshold_n: float = 12.0
    hard_force_threshold_n: float = 18.0
    stall_progress_epsilon_m: float = 0.0005
    stall_speed_epsilon_mps: float = 0.0020
    stall_cycles: int = 6
    oscillation_window: int = 6
    oscillation_flip_threshold: int = 4
    insert_timeout_s: float = 1.5
    backout_distance_m: float = 0.004
    retry_budget: int = 2
    retry_bias_lateral_m: float = 0.00075
    retry_bias_rotation_rad: float = 0.0087
    unsafe_force_scale_decay: float = 0.5
    min_insert_scale: float = 0.25

    @classmethod
    def from_env(cls) -> "GuardedInsertionRecoveryConfig":
        return cls(
            mode=_parse_mode("AIC_ACT_GUARDED_RECOVERY_MODE", "shadow"),
            max_lateral_delta_m=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_MAX_LATERAL_DELTA_M", 0.0010
            ),
            max_axial_insert_delta_m=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_MAX_AXIAL_INSERT_DELTA_M", 0.0008
            ),
            max_rotation_delta_rad=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_MAX_ROTATION_DELTA_RAD", 0.035
            ),
            soft_force_threshold_n=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_SOFT_FORCE_THRESHOLD_N", 12.0
            ),
            hard_force_threshold_n=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_HARD_FORCE_THRESHOLD_N", 18.0
            ),
            stall_progress_epsilon_m=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_STALL_PROGRESS_EPS_M", 0.0005
            ),
            stall_speed_epsilon_mps=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_STALL_SPEED_EPS_MPS", 0.0020
            ),
            stall_cycles=_parse_int(
                "AIC_ACT_GUARDED_RECOVERY_STALL_CYCLES", 6
            ),
            oscillation_window=_parse_int(
                "AIC_ACT_GUARDED_RECOVERY_OSCILLATION_WINDOW", 6
            ),
            oscillation_flip_threshold=_parse_int(
                "AIC_ACT_GUARDED_RECOVERY_OSCILLATION_FLIP_THRESHOLD", 4
            ),
            insert_timeout_s=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_INSERT_TIMEOUT_S", 1.5
            ),
            backout_distance_m=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_BACKOUT_DISTANCE_M", 0.004
            ),
            retry_budget=_parse_int(
                "AIC_ACT_GUARDED_RECOVERY_RETRY_BUDGET", 2
            ),
            retry_bias_lateral_m=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_RETRY_BIAS_LATERAL_M", 0.00075
            ),
            retry_bias_rotation_rad=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_RETRY_BIAS_ROTATION_RAD", 0.0087
            ),
            unsafe_force_scale_decay=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_UNSAFE_FORCE_SCALE_DECAY", 0.5
            ),
            min_insert_scale=_parse_float(
                "AIC_ACT_GUARDED_RECOVERY_MIN_INSERT_SCALE", 0.25
            ),
        )


@dataclass
class GuardedInsertionRecoveryState:
    retries_used: int = 0
    scale_multiplier: float = 1.0
    phase_started_at_s: float = 0.0
    attempt_start_pos: np.ndarray | None = None
    best_progress_m: float = 0.0
    stall_cycles: int = 0
    max_force_seen_n: float = 0.0
    last_trigger_reason: str | None = None
    last_retry_target_pose: Pose | None = None
    lateral_sign_history: deque[int] = field(default_factory=lambda: deque(maxlen=6))
    bias_index: int = 0


@dataclass(frozen=True)
class GuardedInsertionDecision:
    bounded_pose: Pose
    action_clipped: bool
    would_trigger: bool
    would_trigger_reason: str | None
    triggered: bool
    trigger_reason: str | None
    should_retry: bool
    retry_target_pose: Pose | None
    should_fail: bool
    termination_reason: str | None
    force_scale: float
    axial_delta_m: float
    lateral_delta_m: float
    rotation_delta_rad: float
    stall_cycles: int
    progress_m: float
    retries_used: int


class GuardedInsertionRecoverySupervisor:
    """Deployable bounded insertion guard with shadow/control modes."""

    def __init__(self, config: GuardedInsertionRecoveryConfig):
        self.config = config
        self.state = GuardedInsertionRecoveryState()

    def reset(self) -> None:
        self.state = GuardedInsertionRecoveryState()
        self.state.lateral_sign_history = deque(
            maxlen=self.config.oscillation_window
        )

    def begin_insert_attempt(
        self,
        *,
        current_pose: Pose,
        now_s: float | None = None,
    ) -> None:
        self.state.phase_started_at_s = time.time() if now_s is None else float(now_s)
        self.state.attempt_start_pos = _pose_position_array(current_pose)
        self.state.best_progress_m = 0.0
        self.state.stall_cycles = 0
        self.state.lateral_sign_history.clear()

    def _clamp_pose_target(
        self,
        *,
        current_pose: Pose,
        proposed_pose: Pose,
        insert_direction_world: np.ndarray,
        force_scale: float,
    ) -> tuple[Pose, bool, float, float, float]:
        current_pos = _pose_position_array(current_pose)
        proposed_pos = _pose_position_array(proposed_pose)
        insert_axis = _normalized(
            insert_direction_world,
            np.array([0.0, 0.0, -1.0], dtype=np.float64),
        )
        raw_delta = proposed_pos - current_pos
        axial_delta = float(np.dot(raw_delta, insert_axis))
        axial_limit = self.config.max_axial_insert_delta_m * force_scale
        axial_delta_clamped = float(np.clip(axial_delta, -0.5 * axial_limit, axial_limit))
        lateral_vec = raw_delta - (axial_delta * insert_axis)
        lateral_clamped = _clip_vector_norm(
            lateral_vec, self.config.max_lateral_delta_m
        )
        bounded_pos = current_pos + (axial_delta_clamped * insert_axis) + lateral_clamped

        q_current = _quaternion_xyzw_to_array(current_pose.orientation)
        q_target = _quaternion_xyzw_to_array(proposed_pose.orientation)
        raw_rot_delta = _quat_angle_rad(q_current, q_target)
        if raw_rot_delta > self.config.max_rotation_delta_rad:
            alpha = self.config.max_rotation_delta_rad / max(raw_rot_delta, 1.0e-9)
            bounded_quat = _quat_slerp(q_current, q_target, alpha)
        else:
            bounded_quat = q_target

        bounded_pose = Pose(
            position=Point(
                x=float(bounded_pos[0]),
                y=float(bounded_pos[1]),
                z=float(bounded_pos[2]),
            ),
            orientation=_array_to_quaternion_xyzw(bounded_quat),
        )
        lateral_delta_m = float(np.linalg.norm(lateral_clamped))
        rotation_delta_rad = float(_quat_angle_rad(q_current, bounded_quat))
        action_clipped = (
            not np.allclose(bounded_pos, proposed_pos, atol=1.0e-9)
            or abs(rotation_delta_rad - raw_rot_delta) > 1.0e-9
        )
        return (
            bounded_pose,
            action_clipped,
            axial_delta_clamped,
            lateral_delta_m,
            rotation_delta_rad,
        )

    def _compute_force_scale(self, force_n: float | None) -> float:
        if force_n is None or force_n <= self.config.soft_force_threshold_n:
            return self.state.scale_multiplier
        ramp_span = max(
            self.config.hard_force_threshold_n - self.config.soft_force_threshold_n,
            1.0e-6,
        )
        force_scale = 1.0 - (
            (force_n - self.config.soft_force_threshold_n) / ramp_span
        )
        force_scale = float(np.clip(force_scale, self.config.min_insert_scale, 1.0))
        return min(self.state.scale_multiplier, force_scale)

    def _update_oscillation_history(self, lateral_vec: np.ndarray) -> int:
        if float(np.linalg.norm(lateral_vec)) < 5.0e-5:
            self.state.lateral_sign_history.append(0)
        else:
            dominant_axis = int(np.argmax(np.abs(lateral_vec)))
            sign = int(np.sign(lateral_vec[dominant_axis]))
            self.state.lateral_sign_history.append(sign)

        flips = 0
        history = list(self.state.lateral_sign_history)
        for prev, cur in zip(history, history[1:]):
            if prev != 0 and cur != 0 and prev != cur:
                flips += 1
        return flips

    def _build_retry_target_pose(
        self,
        *,
        current_pose: Pose,
        insert_direction_world: np.ndarray,
    ) -> Pose:
        current_pos = _pose_position_array(current_pose)
        insert_axis = _normalized(
            insert_direction_world,
            np.array([0.0, 0.0, -1.0], dtype=np.float64),
        )
        fallback = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        lateral_axis_a = np.cross(insert_axis, fallback)
        if float(np.linalg.norm(lateral_axis_a)) <= 1.0e-6:
            fallback = np.array([1.0, 0.0, 0.0], dtype=np.float64)
            lateral_axis_a = np.cross(insert_axis, fallback)
        lateral_axis_a = _normalized(lateral_axis_a, np.array([1.0, 0.0, 0.0]))
        lateral_axis_b = _normalized(
            np.cross(insert_axis, lateral_axis_a),
            np.array([0.0, 1.0, 0.0]),
        )
        bias_cycle = (
            lateral_axis_a,
            -lateral_axis_a,
            lateral_axis_b,
            -lateral_axis_b,
        )
        bias_axis = bias_cycle[self.state.bias_index % len(bias_cycle)]
        self.state.bias_index += 1
        backout = (
            (-self.config.backout_distance_m) * insert_axis
            + self.config.retry_bias_lateral_m * bias_axis
        )
        q_current = _quaternion_xyzw_to_array(current_pose.orientation)
        q_bias = _axis_angle_to_quat(
            insert_axis,
            self.config.retry_bias_rotation_rad
            * (1.0 if (self.state.bias_index % 2) else -1.0),
        )
        q_target = _quat_multiply(q_bias, q_current)
        retry_pose = _copy_pose(current_pose)
        retry_pose.position = Point(
            x=float(current_pos[0] + backout[0]),
            y=float(current_pos[1] + backout[1]),
            z=float(current_pos[2] + backout[2]),
        )
        retry_pose.orientation = _array_to_quaternion_xyzw(q_target)
        return retry_pose

    def evaluate_insert_step(
        self,
        *,
        current_pose: Pose,
        proposed_pose: Pose,
        insert_direction_world: np.ndarray,
        force_n: float | None,
        tcp_linear_speed_mps: float,
        now_s: float,
    ) -> GuardedInsertionDecision:
        if self.state.attempt_start_pos is None:
            self.begin_insert_attempt(current_pose=current_pose, now_s=now_s)

        if force_n is not None:
            self.state.max_force_seen_n = max(self.state.max_force_seen_n, float(force_n))

        force_scale = self._compute_force_scale(force_n)
        (
            bounded_pose,
            action_clipped,
            axial_delta_m,
            lateral_delta_m,
            rotation_delta_rad,
        ) = self._clamp_pose_target(
            current_pose=current_pose,
            proposed_pose=proposed_pose,
            insert_direction_world=insert_direction_world,
            force_scale=force_scale,
        )

        current_pos = _pose_position_array(current_pose)
        insert_axis = _normalized(
            insert_direction_world,
            np.array([0.0, 0.0, -1.0], dtype=np.float64),
        )
        progress_m = float(np.dot(current_pos - self.state.attempt_start_pos, insert_axis))
        self.state.best_progress_m = max(self.state.best_progress_m, progress_m)

        lateral_vec = (
            _pose_position_array(bounded_pose)
            - current_pos
            - (axial_delta_m * insert_axis)
        )
        oscillation_flips = self._update_oscillation_history(lateral_vec)

        making_progress = (
            progress_m >= self.state.best_progress_m - self.config.stall_progress_epsilon_m
            or tcp_linear_speed_mps > self.config.stall_speed_epsilon_mps
        )
        if axial_delta_m > self.config.stall_progress_epsilon_m and not making_progress:
            self.state.stall_cycles += 1
        else:
            self.state.stall_cycles = 0

        trigger_reason: str | None = None
        if force_n is not None and force_n >= self.config.hard_force_threshold_n:
            trigger_reason = "unsafe_force"
        elif (now_s - self.state.phase_started_at_s) >= self.config.insert_timeout_s:
            trigger_reason = "guard_timeout"
        elif self.state.stall_cycles >= self.config.stall_cycles:
            trigger_reason = "stalled"
        elif oscillation_flips >= self.config.oscillation_flip_threshold:
            trigger_reason = "oscillation"

        would_trigger = trigger_reason is not None
        triggered = would_trigger and self.config.mode == "control"
        retry_target_pose = None
        should_retry = False
        should_fail = False
        termination_reason = None

        if would_trigger and trigger_reason == "unsafe_force":
            self.state.scale_multiplier = max(
                self.config.min_insert_scale,
                self.state.scale_multiplier * self.config.unsafe_force_scale_decay,
            )

        if triggered:
            self.state.last_trigger_reason = trigger_reason
            if self.state.retries_used < self.config.retry_budget:
                retry_target_pose = self._build_retry_target_pose(
                    current_pose=current_pose,
                    insert_direction_world=insert_direction_world,
                )
                self.state.retries_used += 1
                self.state.last_retry_target_pose = retry_target_pose
                should_retry = True
            else:
                retry_target_pose = self._build_retry_target_pose(
                    current_pose=current_pose,
                    insert_direction_world=insert_direction_world,
                )
                self.state.last_retry_target_pose = retry_target_pose
                should_fail = True
                termination_reason = f"{trigger_reason}_retry_exhausted"

        return GuardedInsertionDecision(
            bounded_pose=bounded_pose,
            action_clipped=action_clipped,
            would_trigger=would_trigger,
            would_trigger_reason=trigger_reason,
            triggered=triggered,
            trigger_reason=trigger_reason if triggered else None,
            should_retry=should_retry,
            retry_target_pose=retry_target_pose,
            should_fail=should_fail,
            termination_reason=termination_reason,
            force_scale=force_scale,
            axial_delta_m=axial_delta_m,
            lateral_delta_m=lateral_delta_m,
            rotation_delta_rad=rotation_delta_rad,
            stall_cycles=self.state.stall_cycles,
            progress_m=progress_m,
            retries_used=self.state.retries_used,
        )
