"""MyCheatCode — Project-Ladder scripted insertion ladder (M1).

Written from scratch against the stock CheatCode source (submodules/aic/
aic_example_policies/aic_example_policies/ros/CheatCode.py). Not a copy.

Architecture rules (LADDER-M-STAGES-03, M1):
- ALL scene knowledge enters through the two seam methods below:
    _get_port_pose(target_frame)   -- the swap point. v1 = ground-truth TF
                                      lookup; v2 (M3) = keypoint CNN + PnP.
    _get_plug_tip_pose()           -- plug-tip seam. Candidate resolution: a
                                      fixed TCP->plug transform captured once
                                      per trial (see _capture_plug_tip_offset);
                                      decision pending the fixed-offset test.
  No other method may read TF or any scene state.
- Target port comes from the Task object only.
- Motion goes through Policy.set_pose_target() only.
- Approach travels at a safe height corridor (rise, translate, descend) so a
  tall NIC card between the arm and an SC port cannot snag the cable. The
  stock straight-line interpolation is the known snag failure; do not
  reintroduce it.

Ladder: APPROACH -> ALIGN -> INSERT -> RETRY_OR_FINISH.
Stage status (one commit per stage):
  skeleton  DONE (this commit)
  approach  stub
  align     stub
  insert    stub
  retry     stub
"""

from enum import Enum

from aic_model.policy import (
    GetObservationCallback,
    MoveRobotCallback,
    Policy,
    SendFeedbackCallback,
)
from aic_task_interfaces.msg import Task
from geometry_msgs.msg import Transform
from rclpy.duration import Duration
from rclpy.time import Time
from tf2_ros import TransformException

from ladder.guarded_insertion_recovery import (
    GuardedInsertionRecoveryConfig,
    GuardedInsertionRecoverySupervisor,
)


class Stage(Enum):
    APPROACH = "approach"
    ALIGN = "align"
    INSERT = "insert"
    RETRY_OR_FINISH = "retry_or_finish"
    DONE = "done"
    FAILED = "failed"


class MyCheatCode(Policy):
    # Guards transcribed from the quantarune archive (RunACTStaged tuning).
    XY_TOLERANCE_M = 0.015
    ANGULAR_TOLERANCE_RAD = 0.12
    PROGRESS_EPSILON_M = 0.0015
    FORCE_RAMP_START_N = 12.0
    FORCE_RAMP_STOP_N = 19.0
    # Lateral compliance on contact; identical to the set_pose_target default,
    # restated here because insert-stage commands will pass it explicitly.
    CONTACT_WRENCH_GAINS = [0.5, 0.5, 0.5, 0.0, 0.0, 0.0]

    # Approach corridor: travel height above the task-board surface that
    # clears every mounted card. Value to be validated in the approach stage.
    SAFE_TRAVEL_Z_OFFSET_M = 0.20

    MAX_RETRIES = 3
    TF_WAIT_TIMEOUT_S = 10.0

    def __init__(self, parent_node):
        self._task: Task | None = None
        self._plug_tip_offset: Transform | None = None
        self._recovery = GuardedInsertionRecoverySupervisor(
            GuardedInsertionRecoveryConfig.from_env()
        )
        super().__init__(parent_node)

    # ------------------------------------------------------------------
    # Scene-knowledge seams. Nothing outside these two methods (and the
    # capture helper) may touch TF.
    # ------------------------------------------------------------------

    def _get_port_pose(self, target_frame: str) -> Transform | None:
        """THE swap point. Returns the target port pose in base_link.

        v1 (this milestone): ground-truth TF lookup, requires
        ground_truth:=true. v2 (M3) replaces this body with keypoint
        CNN + PnP from the wrist cameras. Callers must not care which.
        """
        if not self._wait_for_tf("base_link", target_frame):
            return None
        try:
            stamped = self._parent_node._tf_buffer.lookup_transform(
                "base_link", target_frame, Time()
            )
        except TransformException as ex:
            self.get_logger().error(f"_get_port_pose({target_frame}): {ex}")
            return None
        return stamped.transform

    def _get_plug_tip_pose(self) -> Transform | None:
        """Plug-tip seam. Returns the plug tip pose in base_link.

        Currently a per-tick ground-truth TF lookup, same as stock. The
        fixed-offset test (M1 requirement) runs in the align stage: if the
        TCP->plug transform is constant over a trial, this body switches to
        composing the captured offset onto the TCP pose from
        controller_state, and the per-tick GT dependency disappears.
        """
        frame = f"{self._task.cable_name}/{self._task.plug_name}_link"
        try:
            stamped = self._parent_node._tf_buffer.lookup_transform(
                "base_link", frame, Time()
            )
        except TransformException as ex:
            self.get_logger().error(f"_get_plug_tip_pose(): {ex}")
            return None
        return stamped.transform

    def _wait_for_tf(self, target_frame: str, source_frame: str) -> bool:
        start = self.time_now()
        timeout = Duration(seconds=self.TF_WAIT_TIMEOUT_S)
        attempt = 0
        while (self.time_now() - start) < timeout:
            try:
                self._parent_node._tf_buffer.lookup_transform(
                    target_frame, source_frame, Time()
                )
                return True
            except TransformException:
                if attempt % 20 == 0:
                    self.get_logger().info(
                        f"Waiting for TF '{source_frame}' -> '{target_frame}'"
                        " -- is the eval running with ground_truth:=true?"
                    )
                attempt += 1
                self.sleep_for(0.1)
        self.get_logger().error(
            f"TF '{source_frame}' unavailable after {self.TF_WAIT_TIMEOUT_S}s"
        )
        return False

    # ------------------------------------------------------------------
    # Ladder stages. Each is one commit; stubs fail loudly until built.
    # ------------------------------------------------------------------

    def _approach(self, port_pose: Transform, move_robot: MoveRobotCallback) -> bool:
        """Rise to safe travel height, translate over the port, hold above it.

        Path shape (snag fix): straight up from the current TCP position to
        SAFE_TRAVEL_Z_OFFSET_M above the board, lateral move at that height,
        then a vertical-only descent corridor. Never a direct diagonal.
        """
        self.get_logger().error("APPROACH stage not implemented yet")
        return False

    def _align(self, port_pose: Transform, move_robot: MoveRobotCallback) -> bool:
        self.get_logger().error("ALIGN stage not implemented yet")
        return False

    def _insert(self, port_pose: Transform, move_robot: MoveRobotCallback) -> bool:
        self.get_logger().error("INSERT stage not implemented yet")
        return False

    def _retry_or_finish(self, move_robot: MoveRobotCallback) -> Stage:
        self.get_logger().error("RETRY stage not implemented yet")
        return Stage.FAILED

    # ------------------------------------------------------------------
    # Entry point.
    # ------------------------------------------------------------------

    def insert_cable(
        self,
        task: Task,
        get_observation: GetObservationCallback,
        move_robot: MoveRobotCallback,
        send_feedback: SendFeedbackCallback,
    ) -> bool:
        self._task = task
        self._recovery.reset()

        # The one and only place the target is chosen: from the Task object.
        port_frame = f"task_board/{task.target_module_name}/{task.port_name}_link"
        self.get_logger().info(
            f"MyCheatCode: target port '{port_frame}' "
            f"(cable '{task.cable_name}', plug '{task.plug_name}')"
        )

        port_pose = self._get_port_pose(port_frame)
        if port_pose is None:
            return False

        stage = Stage.APPROACH
        retries = 0
        while stage not in (Stage.DONE, Stage.FAILED):
            self.get_logger().info(f"MyCheatCode stage: {stage.value}")
            send_feedback(f"stage={stage.value} retries={retries}")
            if stage is Stage.APPROACH:
                stage = Stage.ALIGN if self._approach(port_pose, move_robot) else Stage.FAILED
            elif stage is Stage.ALIGN:
                stage = Stage.INSERT if self._align(port_pose, move_robot) else Stage.RETRY_OR_FINISH
            elif stage is Stage.INSERT:
                stage = Stage.DONE if self._insert(port_pose, move_robot) else Stage.RETRY_OR_FINISH
            elif stage is Stage.RETRY_OR_FINISH:
                retries += 1
                if retries > self.MAX_RETRIES:
                    self.get_logger().error("Retry budget exhausted")
                    stage = Stage.FAILED
                else:
                    # Re-estimate through the seam on every retry; when v2
                    # perception lands, each retry gets a fresh estimate.
                    port_pose = self._get_port_pose(port_frame) or port_pose
                    stage = self._retry_or_finish(move_robot)

        return stage is Stage.DONE
