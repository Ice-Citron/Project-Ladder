"""Approach-stage geometry and trajectory generation (M1, ladder stage 1 of 4).

Pure math: numpy only, NO ROS imports, so this module is developed and
unit-tested on the laptop without Gazebo (tests/test_approach.py). The ROS
side of the stage lives in MyCheatCode._approach, which stays a thin driver:

    # inside MyCheatCode._approach (sketch — the only part touching ROS):
    tcp, plug = self._get_tcp_pose(), self._get_plug_tip_pose()
    plan = plan_approach(to_pose_arr(tcp), to_pose_arr(plug),
                         to_pose_arr(port_pose))
    for pos, quat_xyzw in plan.commands:
        self.set_pose_target(move_robot=move_robot, pose=make_pose(pos, quat_xyzw))
        self.sleep_for(plan.params.dt_s)
    # then: convergence check against plan.waypoints[-1] / plan.quat_target

Corridor (snag fix — never a direct diagonal; see MyCheatCode module docstring):

    W0 = current TCP position
    W1 = (W0.x, W0.y, z_travel)      leg A: vertical rise, orientation held
    W2 = (tgt.x, tgt.y, z_travel)    leg B: lateral move, full rotation slerped
                                     here, at height, in free space
    W3 = (tgt.x, tgt.y, z_hover)     leg C: vertical-only descent to hover

Each leg follows a minimum-jerk time profile (zero velocity and acceleration
at both ends), so corridor corners cost nothing under the smoothness metric
(jerk is only integrated while speed > 0.01 m/s) and peak jerk stays orders of
magnitude below the 50 m/s^3 zero-score threshold. This replaces stock
CheatCode's linear interpolation, whose constant-velocity profile has step
discontinuities at the ends of every move.

Conventions:
- Quaternions are **xyzw** throughout (geometry_msgs field order). Stock
  CheatCode builds **wxyz** tuples for transforms3d — the driver converts at
  the boundary; nothing in this module ever sees a wxyz quaternion.
- All positions are meters in base_link.

Transcribed-from-stock semantics (do not "fix" without a sim run): the TCP
hover height compensates the plug->TCP offset exactly as stock CheatCode does
(z_hover_tcp = port.z + hover - (tcp.z - plug.z), CheatCode.py:166), and the
TCP xy target is the port xy verbatim — residual xy error is the align
stage's job. Stock scores 278.64/300 with this arithmetic; the first sim run's
convergence check (plug ~hover above the port) is the arbiter of the sign.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

import numpy as np

_EPS_DIST_M = 1.0e-4
_EPS_ANGLE_RAD = 1.0e-3


# ---------------------------------------------------------------------------
# Quaternion helpers (xyzw).
# ---------------------------------------------------------------------------


def quat_normalize(quat_xyzw: np.ndarray) -> np.ndarray:
    quat = np.asarray(quat_xyzw, dtype=np.float64)
    norm = float(np.linalg.norm(quat))
    if norm <= 1.0e-9:
        return np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    return quat / norm


def quat_conjugate(quat_xyzw: np.ndarray) -> np.ndarray:
    x, y, z, w = quat_xyzw
    return np.array([-x, -y, -z, w], dtype=np.float64)


def quat_multiply(q1_xyzw: np.ndarray, q2_xyzw: np.ndarray) -> np.ndarray:
    """Hamilton product q1 * q2: rotation q2 applied first, then q1."""
    x1, y1, z1, w1 = q1_xyzw
    x2, y2, z2, w2 = q2_xyzw
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ],
        dtype=np.float64,
    )


def quat_rotate_vec(quat_xyzw: np.ndarray, vec: np.ndarray) -> np.ndarray:
    """Rotate a 3-vector by a unit quaternion: v' = q v q^-1."""
    q_vec = np.asarray(quat_xyzw[:3], dtype=np.float64)
    w = float(quat_xyzw[3])
    t = 2.0 * np.cross(q_vec, vec)
    return np.asarray(vec, dtype=np.float64) + w * t + np.cross(q_vec, t)


def quat_angle_rad(q0_xyzw: np.ndarray, q1_xyzw: np.ndarray) -> float:
    """Angle of the rotation carrying q0 onto q1 (shortest path)."""
    dot = abs(float(np.dot(quat_normalize(q0_xyzw), quat_normalize(q1_xyzw))))
    return 2.0 * float(np.arccos(np.clip(dot, -1.0, 1.0)))


def quat_slerp(q0_xyzw: np.ndarray, q1_xyzw: np.ndarray, alpha: float) -> np.ndarray:
    """Shortest-path spherical interpolation, alpha in [0, 1]."""
    q0 = quat_normalize(q0_xyzw)
    q1 = quat_normalize(q1_xyzw)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:  # shortest path: q and -q are the same rotation
        q1 = -q1
        dot = -dot
    if dot > 1.0 - 1.0e-9:  # nearly identical: nlerp avoids division by ~0
        return quat_normalize(q0 + alpha * (q1 - q0))
    theta = float(np.arccos(np.clip(dot, -1.0, 1.0)))
    sin_theta = float(np.sin(theta))
    return quat_normalize(
        (np.sin((1.0 - alpha) * theta) / sin_theta) * q0
        + (np.sin(alpha * theta) / sin_theta) * q1
    )


# ---------------------------------------------------------------------------
# Minimum-jerk time profile.
# ---------------------------------------------------------------------------


def min_jerk(tau: float) -> float:
    """Quintic minimum-jerk profile s(tau), tau in [0, 1].

    s(0)=0, s(1)=1, with zero first and second derivatives at both ends, so
    every leg starts and stops at rest — corridor corners add no jerk while
    moving. Peak factors over a leg of length d and duration T:
    |v|max = 1.875 d/T, |j|max = 60 d/T^3.
    """
    tau = float(np.clip(tau, 0.0, 1.0))
    return 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5


# ---------------------------------------------------------------------------
# Data types.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PoseArr:
    """Minimal pose: position (3,) meters, quaternion (4,) xyzw, base_link."""

    position: np.ndarray
    quat_xyzw: np.ndarray


@dataclass(frozen=True)
class ApproachParams:
    hover_offset_m: float = 0.20  # plug hovers this far above the port (stock z_offset)
    travel_offset_m: float = 0.20  # corridor height above the target port.
    # UNVALIDATED (M1 task): must clear a NIC card + hanging cable — check on hc01-03.
    v_nom_mps: float = 0.12  # nominal translation speed per leg
    omega_nom_rps: float = 0.4  # nominal rotation speed (leg B)
    t_min_s: float = 1.5  # floor on any leg duration
    dt_s: float = 0.05  # 20 Hz command tick (stock's rate)


@dataclass(frozen=True)
class ApproachPlan:
    waypoints: list  # [W0, W1, W2, W3] positions actually planned (skipped legs removed)
    quat_target: np.ndarray  # gripper orientation that aligns plug axis to port axis
    commands: list  # [(position (3,), quat_xyzw (4,)), ...] at dt_s spacing
    leg_durations_s: list  # per emitted leg, for telemetry
    params: ApproachParams = field(default_factory=ApproachParams)


# ---------------------------------------------------------------------------
# Goal and corridor geometry.
# ---------------------------------------------------------------------------


def compute_gripper_goal(
    port: PoseArr, plug: PoseArr, tcp: PoseArr, params: ApproachParams
) -> tuple[np.ndarray, float, np.ndarray]:
    """Target TCP (xy, hover z, orientation) that hovers the plug over the port.

    Orientation: q_diff is the world-frame rotation carrying the plug's
    current orientation onto the port's; pre-multiplying the gripper by it
    (stock CheatCode.py:104-116) yields the gripper orientation at which the
    plug axis matches the port axis.
    """
    q_diff = quat_multiply(quat_normalize(port.quat_xyzw), quat_conjugate(quat_normalize(plug.quat_xyzw)))
    quat_target = quat_normalize(quat_multiply(q_diff, quat_normalize(tcp.quat_xyzw)))

    target_xy = np.array([port.position[0], port.position[1]], dtype=np.float64)
    # Stock's z compensation, transcribed verbatim (see module docstring).
    z_hover_tcp = (
        float(port.position[2])
        + params.hover_offset_m
        - (float(tcp.position[2]) - float(plug.position[2]))
    )
    return target_xy, z_hover_tcp, quat_target


def compute_corridor(
    tcp_position: np.ndarray,
    target_xy: np.ndarray,
    z_hover_tcp: float,
    port_z: float,
    params: ApproachParams,
) -> list:
    """[W1, W2, W3] — see module docstring. z_travel is never below the
    current TCP height or the hover height, so legs A and C never descend
    except for C's final vertical drop over the port.

    The port-clearance term exists only to protect the lateral traversal
    (leg B); when the TCP is already above the port xy there is nothing to
    traverse, so it is dropped — otherwise a re-approach from hover (retry
    path) would pointlessly rise and descend in place."""
    lateral_m = float(np.linalg.norm(np.asarray(tcp_position[:2]) - target_xy))
    z_travel = max(float(tcp_position[2]), z_hover_tcp)
    if lateral_m >= _EPS_DIST_M:
        z_travel = max(z_travel, port_z + params.travel_offset_m)
    w1 = np.array([tcp_position[0], tcp_position[1], z_travel], dtype=np.float64)
    w2 = np.array([target_xy[0], target_xy[1], z_travel], dtype=np.float64)
    w3 = np.array([target_xy[0], target_xy[1], z_hover_tcp], dtype=np.float64)
    return [w1, w2, w3]


def leg_duration(dist_m: float, angle_rad: float, params: ApproachParams) -> float:
    return max(
        dist_m / params.v_nom_mps,
        angle_rad / params.omega_nom_rps,
        params.t_min_s,
    )


def iter_leg(
    p0: np.ndarray,
    p1: np.ndarray,
    q0_xyzw: np.ndarray,
    q1_xyzw: np.ndarray,
    duration_s: float,
    dt_s: float,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (position, quat_xyzw) samples along one min-jerk leg.

    The tau=0 sample is NOT emitted (it equals the previous leg's endpoint /
    the current pose); the tau=1 sample is emitted exactly.
    """
    n_steps = max(1, int(np.ceil(duration_s / dt_s)))
    for k in range(1, n_steps + 1):
        s = min_jerk(min(1.0, (k * dt_s) / duration_s))
        yield (
            (1.0 - s) * np.asarray(p0, dtype=np.float64) + s * np.asarray(p1, dtype=np.float64),
            quat_slerp(q0_xyzw, q1_xyzw, s),
        )


# ---------------------------------------------------------------------------
# The plan.
# ---------------------------------------------------------------------------


def plan_approach(
    tcp: PoseArr,
    plug: PoseArr,
    port: PoseArr,
    params: ApproachParams | None = None,
) -> ApproachPlan:
    """Full approach trajectory: W0 -> W1 -> W2 -> W3 with rotation on leg B.

    Legs whose translation AND rotation are both negligible are skipped (e.g.
    already at travel height, or already above the port xy). A degenerate
    leg B with rotation still to do is emitted as a rotate-in-place leg.
    """
    params = params or ApproachParams()
    target_xy, z_hover_tcp, quat_target = compute_gripper_goal(port, plug, tcp, params)
    w1, w2, w3 = compute_corridor(
        np.asarray(tcp.position, dtype=np.float64),
        target_xy,
        z_hover_tcp,
        float(port.position[2]),
        params,
    )
    q_start = quat_normalize(tcp.quat_xyzw)

    legs = [  # (from, to, q_from, q_to)
        (np.asarray(tcp.position, dtype=np.float64), w1, q_start, q_start),
        (w1, w2, q_start, quat_target),
        (w2, w3, quat_target, quat_target),
    ]

    commands: list = []
    durations: list = []
    waypoints: list = [np.asarray(tcp.position, dtype=np.float64)]
    for p0, p1, q0, q1 in legs:
        dist = float(np.linalg.norm(p1 - p0))
        angle = quat_angle_rad(q0, q1)
        if dist < _EPS_DIST_M and angle < _EPS_ANGLE_RAD:
            continue
        duration = leg_duration(dist, angle, params)
        commands.extend(iter_leg(p0, p1, q0, q1, duration, params.dt_s))
        durations.append(duration)
        waypoints.append(p1)

    return ApproachPlan(
        waypoints=waypoints,
        quat_target=quat_target,
        commands=commands,
        leg_durations_s=durations,
        params=params,
    )
