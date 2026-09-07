"""Laptop-side verification for ladder/approach.py — no ROS, no Gazebo.

Run either way:
    python -m pytest tests/test_approach.py -q     (from the repo root)
    python tests/test_approach.py                  (standalone, plain asserts)

These are the numeric gate for the approach-stage geometry before it ever
touches the sim. What they can NOT verify: the sign of stock's plug->TCP z
compensation and the travel-height clearance over a NIC card — those are
checked by the first sim run's convergence check and hc01-03 respectively.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ladder.approach import (  # noqa: E402
    ApproachParams,
    PoseArr,
    compute_corridor,
    compute_gripper_goal,
    min_jerk,
    plan_approach,
    quat_angle_rad,
    quat_multiply,
    quat_normalize,
    quat_rotate_vec,
    quat_slerp,
)

QUAT_IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])


def _quat_about_z(angle_rad: float) -> np.ndarray:
    return np.array([0.0, 0.0, np.sin(angle_rad / 2.0), np.cos(angle_rad / 2.0)])


def _quat_about_x(angle_rad: float) -> np.ndarray:
    return np.array([np.sin(angle_rad / 2.0), 0.0, 0.0, np.cos(angle_rad / 2.0)])


def _default_scene():
    """A plausible hover scenario: arm parked high, port low on the board."""
    tcp = PoseArr(np.array([0.30, -0.40, 1.60]), _quat_about_x(np.pi))
    plug = PoseArr(np.array([0.31, -0.38, 1.52]), _quat_about_x(np.pi))
    port = PoseArr(np.array([0.15, -0.20, 1.20]), _quat_about_x(np.pi + 0.2))
    return tcp, plug, port


# ---------------------------------------------------------------------------
# Minimum-jerk profile.
# ---------------------------------------------------------------------------


def test_min_jerk_boundaries():
    assert min_jerk(0.0) == 0.0
    assert min_jerk(1.0) == 1.0
    h = 1.0e-5  # numeric first/second derivatives vanish at both ends
    for tau in (0.0, 1.0):
        lo, mid, hi = min_jerk(max(0.0, tau - h)), min_jerk(tau), min_jerk(min(1.0, tau + h))
        assert abs((hi - lo) / (2 * h)) < 1.0e-3, "endpoint velocity not ~0"
    # monotone: never overshoots or reverses
    s = np.array([min_jerk(t) for t in np.linspace(0, 1, 1001)])
    assert np.all(np.diff(s) >= -1e-12)


# ---------------------------------------------------------------------------
# Quaternions (xyzw): prove the ordering with rotations of actual vectors.
# ---------------------------------------------------------------------------


def test_quat_ordering_and_multiply():
    q90 = _quat_about_z(np.pi / 2.0)
    # xyzw ordering check: rotating +x by 90 deg about z must give +y
    assert np.allclose(quat_rotate_vec(q90, np.array([1.0, 0, 0])), [0, 1, 0], atol=1e-12)
    # 90 + 90 about z = 180 about z: +x -> -x
    q180 = quat_multiply(q90, q90)
    assert np.allclose(quat_rotate_vec(q180, np.array([1.0, 0, 0])), [-1, 0, 0], atol=1e-12)
    # identity is neutral
    assert np.allclose(quat_multiply(QUAT_IDENTITY, q90), q90)


def test_quat_slerp_midpoint_and_shortest_path():
    q90 = _quat_about_z(np.pi / 2.0)
    mid = quat_slerp(QUAT_IDENTITY, q90, 0.5)
    assert abs(quat_angle_rad(QUAT_IDENTITY, mid) - np.pi / 4.0) < 1e-9
    # q and -q are the same rotation; slerp must take the short way
    mid2 = quat_slerp(QUAT_IDENTITY, -q90, 0.5)
    assert abs(quat_angle_rad(QUAT_IDENTITY, mid2) - np.pi / 4.0) < 1e-9
    # endpoints exact
    assert quat_angle_rad(quat_slerp(QUAT_IDENTITY, q90, 1.0), q90) < 1e-9


# ---------------------------------------------------------------------------
# Goal computation.
# ---------------------------------------------------------------------------


def test_goal_identity_rotation_keeps_gripper_orientation():
    tcp, plug, port = _default_scene()
    port_aligned = PoseArr(port.position, plug.quat_xyzw)  # plug already aligned
    _, _, q_target = compute_gripper_goal(port_aligned, plug, tcp, ApproachParams())
    assert quat_angle_rad(q_target, tcp.quat_xyzw) < 1e-9


def test_goal_rotation_carries_plug_onto_port():
    tcp, plug, port = _default_scene()
    _, _, q_target = compute_gripper_goal(port, plug, tcp, ApproachParams())
    # q_diff = q_target * q_tcp^-1 applied to the plug must reproduce the port
    q_diff = quat_multiply(q_target, np.array([-tcp.quat_xyzw[0], -tcp.quat_xyzw[1], -tcp.quat_xyzw[2], tcp.quat_xyzw[3]]))
    plug_after = quat_multiply(q_diff, plug.quat_xyzw)
    assert quat_angle_rad(plug_after, port.quat_xyzw) < 1e-9


def test_goal_xy_and_hover_z_formula():
    tcp, plug, port = _default_scene()
    params = ApproachParams()
    target_xy, z_hover, _ = compute_gripper_goal(port, plug, tcp, params)
    assert np.allclose(target_xy, port.position[:2])
    expected = port.position[2] + params.hover_offset_m - (tcp.position[2] - plug.position[2])
    assert abs(z_hover - expected) < 1e-12  # transcribed-from-stock arithmetic


# ---------------------------------------------------------------------------
# Corridor geometry.
# ---------------------------------------------------------------------------


def test_corridor_shape():
    tcp, plug, port = _default_scene()
    params = ApproachParams()
    target_xy, z_hover, _ = compute_gripper_goal(port, plug, tcp, params)
    w1, w2, w3 = compute_corridor(tcp.position, target_xy, z_hover, port.position[2], params)
    # legs A and C are strictly vertical
    assert np.allclose(w1[:2], tcp.position[:2])
    assert np.allclose(w2[:2], w3[:2]) and np.allclose(w2[:2], target_xy)
    # travel height: shared by W1/W2, never below current TCP, hover, or clearance
    assert w1[2] == w2[2]
    assert w1[2] >= tcp.position[2] - 1e-12
    assert w1[2] >= z_hover - 1e-12
    assert w1[2] >= port.position[2] + params.travel_offset_m - 1e-12
    assert abs(w3[2] - z_hover) < 1e-12


# ---------------------------------------------------------------------------
# Full plan: endpoints, orientation policy, kinematic limits.
# ---------------------------------------------------------------------------


def test_plan_endpoints_and_orientation_policy():
    tcp, plug, port = _default_scene()
    plan = plan_approach(tcp, plug, port)
    assert len(plan.commands) > 10
    # final command is exactly the hover waypoint at the target orientation
    last_pos, last_quat = plan.commands[-1]
    assert np.allclose(last_pos, plan.waypoints[-1], atol=1e-12)
    assert quat_angle_rad(last_quat, plan.quat_target) < 1e-9
    # all quaternions normalized
    for _, q in plan.commands:
        assert abs(np.linalg.norm(q) - 1.0) < 1e-9
    # rotation happens only at travel height (leg B): any sample whose
    # orientation is strictly between start and target must be at z_travel
    z_travel = plan.waypoints[1][2]
    for pos, q in plan.commands:
        a0 = quat_angle_rad(q, tcp.quat_xyzw)
        a1 = quat_angle_rad(q, plan.quat_target)
        if a0 > 1e-6 and a1 > 1e-6:  # mid-rotation
            assert abs(pos[2] - z_travel) < 1e-9, "rotating outside travel height"


def test_plan_kinematic_limits():
    tcp, plug, port = _default_scene()
    params = ApproachParams()
    plan = plan_approach(tcp, plug, port, params)
    pos = np.array([p for p, _ in plan.commands])
    dt = params.dt_s
    speeds = np.linalg.norm(np.diff(pos, axis=0), axis=1) / dt
    # min-jerk peak velocity factor is 1.875 * d/T with d/T <= v_nom
    assert speeds.max() <= 1.875 * params.v_nom_mps * 1.05, f"v={speeds.max():.3f}"
    # numeric jerk (3rd difference) far below the scoring threshold of 50 m/s^3
    jerk = np.linalg.norm(np.diff(pos, n=3, axis=0), axis=1) / dt**3
    assert jerk.max() < 10.0, f"jerk={jerk.max():.2f} m/s^3"
    # continuity: no step larger than the velocity bound allows (checks leg seams)
    assert (speeds * dt).max() < 1.875 * params.v_nom_mps * dt * 1.05


def test_plan_degenerate_rotation_only():
    # already at travel height and above the port xy: only rotation remains
    params = ApproachParams()
    port = PoseArr(np.array([0.15, -0.20, 1.20]), _quat_about_x(np.pi + 0.3))
    plug = PoseArr(np.array([0.15, -0.20, 1.35]), _quat_about_x(np.pi))
    tcp = PoseArr(
        np.array([0.15, -0.20, port.position[2] + params.travel_offset_m + 0.10]),
        _quat_about_x(np.pi),
    )
    # make hover coincide with current height so legs A and C vanish
    hover = params.hover_offset_m - (tcp.position[2] - plug.position[2])
    port = PoseArr(np.array([0.15, -0.20, tcp.position[2] - hover]), port.quat_xyzw)
    plan = plan_approach(tcp, plug, port, params)
    positions = np.array([p for p, _ in plan.commands])
    assert np.allclose(positions, positions[0], atol=1e-9), "rotation-only leg moved"
    assert quat_angle_rad(plan.commands[-1][1], plan.quat_target) < 1e-9


def test_plan_already_hovering_is_empty():
    params = ApproachParams()
    tcp, plug, _ = _default_scene()
    aligned_port = PoseArr(
        np.array(
            [
                tcp.position[0],
                tcp.position[1],
                tcp.position[2] - params.hover_offset_m + (tcp.position[2] - plug.position[2]),
            ]
        ),
        plug.quat_xyzw,
    )
    # force z_travel == current height too
    params_low = ApproachParams(travel_offset_m=0.0)
    plan = plan_approach(tcp, plug, aligned_port, params_low)
    assert len(plan.commands) == 0


def _main() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print("all tests passed" if failures == 0 else f"{failures} test(s) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
