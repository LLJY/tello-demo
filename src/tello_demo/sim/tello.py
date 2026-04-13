from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tello_demo.sim.commands import (
    BodyTranslationCommand,
    CurveCommand,
    FlipCommand,
    GoCommand,
    LandCommand,
    RcControl,
    RotationCommand,
    TakeoffCommand,
)
from tello_demo.sim.motion.base import MotionPlan
from tello_demo.sim.state import DroneState, normalize_angle

if TYPE_CHECKING:
    from tello_demo.sim.motion.base import MotionModel
    from tello_demo.sim.runtime import SimulationRuntime


class TelloException(RuntimeError):
    pass


@dataclass
class SimTello:
    runtime: "SimulationRuntime"
    motion_model: "MotionModel"
    host: str = "192.168.10.1"
    retry_count: int = 3
    vs_udp: int = 11111

    BITRATE_AUTO = 0
    RESOLUTION_480P = "low"
    RESOLUTION_720P = "high"
    FPS_5 = "low"
    FPS_15 = "middle"
    FPS_30 = "high"
    CAMERA_FORWARD = 0
    CAMERA_DOWNWARD = 1

    def __post_init__(self) -> None:
        self.state = DroneState()
        self.state.configured_speed_cm_s = self.motion_model.profile.default_speed_cm_s
        self.history: list[DroneState] = [self.state.copy()]
        self._active_plan: MotionPlan | None = None
        self._active_elapsed_s = 0.0
        self._rc_control = RcControl()
        self._ended = False
        self.runtime.register(self)

    def __getattr__(self, name: str) -> object:
        raise TelloException(f"SimTello does not support '{name}' yet")

    def advance(self, dt_s: float) -> None:
        previous = self.state.copy()
        if self._active_plan is not None:
            self._active_elapsed_s = min(
                self._active_elapsed_s + dt_s, self._active_plan.duration_s
            )
            sampled_state = self._active_plan.sample(self._active_elapsed_s)
            sampled_state.flight_time_s = self.state.flight_time_s
            sampled_state.battery_percent = self.state.battery_percent
            sampled_state.configured_speed_cm_s = self.state.configured_speed_cm_s
            sampled_state.connected = self.state.connected
            sampled_state.stream_on = self.state.stream_on
            self.state = sampled_state
            if self._active_elapsed_s >= self._active_plan.duration_s - 1e-9:
                self._active_plan = None
                self._active_elapsed_s = 0.0
        else:
            self.state = self.motion_model.advance_rc(
                self.state, self._rc_control, dt_s
            )

        self.state.yaw_deg = normalize_angle(self.state.yaw_deg)
        if (
            self.state.flying
            or previous.flying
            or self.state.current_command in {"takeoff", "land"}
        ):
            self.state.flight_time_s += dt_s
        if self.state.battery_percent > 0 and (
            self.state.flying or not self._rc_control.is_zero()
        ):
            drained = self.motion_model.profile.battery_drain_per_s * dt_s
            self.state.battery_percent = max(0.0, self.state.battery_percent - drained)

        if dt_s > 0:
            self.state.speed_x_cm_s = (self.state.x_cm - previous.x_cm) / dt_s
            self.state.speed_y_cm_s = (self.state.y_cm - previous.y_cm) / dt_s
            self.state.speed_z_cm_s = (self.state.z_cm - previous.z_cm) / dt_s
            self.state.yaw_rate_deg_s = (
                normalize_angle(self.state.yaw_deg - previous.yaw_deg) / dt_s
            )

        if self.state.z_cm <= 1e-6 and self.state.current_command != "takeoff":
            self.state.z_cm = 0.0
            self.state.flying = False
            self.state.pitch_deg = 0.0
            self.state.roll_deg = 0.0
            self._active_plan = None
            self._active_elapsed_s = 0.0
            self._rc_control = RcControl()

        if (
            self._active_plan is None
            and self._rc_control.is_zero()
            and self.state.flying
        ):
            self.state.current_command = "hover"
            self.state.pitch_deg = 0.0
            self.state.roll_deg = 0.0
            self.state.speed_x_cm_s = 0.0
            self.state.speed_y_cm_s = 0.0
            self.state.speed_z_cm_s = 0.0
            self.state.yaw_rate_deg_s = 0.0
        elif self._active_plan is None and not self.state.flying:
            self.state.current_command = "idle"
            self.state.pitch_deg = 0.0
            self.state.roll_deg = 0.0
            self.state.speed_x_cm_s = 0.0
            self.state.speed_y_cm_s = 0.0
            self.state.speed_z_cm_s = 0.0
            self.state.yaw_rate_deg_s = 0.0

        self.history.append(self.state.copy())

    def connect(self, wait_for_state: bool = True) -> None:
        del wait_for_state
        if self._ended:
            raise TelloException(
                "This Tello session has ended; create a new Tello() instance"
            )
        self.state.connected = True
        self.state.current_command = "connected"
        self.runtime.render()

    def end(self) -> None:
        if self._ended:
            return
        if self.state.connected and self.state.flying:
            self.land()
        if self.state.connected and self.state.stream_on:
            self.streamoff()
        self._stop_motion()
        self.state.connected = False
        self.state.stream_on = False
        self.state.flying = False
        self._ended = True

    def takeoff(self) -> None:
        self._require_connected()
        if self.state.flying:
            raise TelloException("The drone is already flying")
        self._run_plan(
            TakeoffCommand(target_height_cm=self.motion_model.profile.takeoff_height_cm)
        )

    def land(self) -> None:
        self._require_connected()
        if not self.state.flying and self.state.z_cm <= 0.0:
            return
        self._run_plan(LandCommand())
        self.state.flying = False
        self.state.z_cm = 0.0
        self.state.pitch_deg = 0.0
        self.state.roll_deg = 0.0

    def _stop_motion(self) -> None:
        self._rc_control = RcControl()
        if self._active_plan is None:
            self.state.current_command = "hover" if self.state.flying else "idle"
            self.state.speed_x_cm_s = 0.0
            self.state.speed_y_cm_s = 0.0
            self.state.speed_z_cm_s = 0.0
            self.state.yaw_rate_deg_s = 0.0

    def send_keepalive(self) -> None:
        self._require_connected()

    def streamon(self) -> None:
        self._require_connected()
        self.state.stream_on = True

    def streamoff(self) -> None:
        self._require_connected()
        self.state.stream_on = False

    def set_speed(self, speed: int) -> None:
        self._require_connected()
        if not 10 <= speed <= 100:
            raise TelloException("Speed must be in the range 10-100 cm/s")
        self.state.configured_speed_cm_s = float(speed)

    def query_speed(self) -> int:
        self._require_connected()
        return int(round(self.state.configured_speed_cm_s))

    def move_up(self, x: int) -> None:
        self._run_distance("up", x)

    def move_down(self, x: int) -> None:
        self._run_distance("down", x)

    def move_left(self, x: int) -> None:
        self._run_distance("left", x)

    def move_right(self, x: int) -> None:
        self._run_distance("right", x)

    def move_forward(self, x: int) -> None:
        self._run_distance("forward", x)

    def move_back(self, x: int) -> None:
        self._run_distance("back", x)

    def rotate_clockwise(self, x: int) -> None:
        self._run_rotation("cw", x)

    def rotate_counter_clockwise(self, x: int) -> None:
        self._run_rotation("ccw", x)

    def flip_left(self) -> None:
        self._run_flip("left")

    def flip_right(self) -> None:
        self._run_flip("right")

    def flip_forward(self) -> None:
        self._run_flip("forward")

    def flip_back(self) -> None:
        self._run_flip("back")

    def go_xyz_speed(self, x: int, y: int, z: int, speed: int) -> None:
        self._require_flying()
        self._validate_go_value(x)
        self._validate_go_value(y)
        self._validate_go_value(z)
        if not 10 <= speed <= 100:
            raise TelloException("go_xyz_speed speed must be in the range 10-100 cm/s")
        self._run_plan(GoCommand(x_cm=x, y_cm=y, z_cm=z, speed_cm_s=speed))

    def curve_xyz_speed(
        self, x1: int, y1: int, z1: int, x2: int, y2: int, z2: int, speed: int
    ) -> None:
        self._require_flying()
        for value in (x1, y1, z1, x2, y2, z2):
            self._validate_go_value(value)
        if not 10 <= speed <= 60:
            raise TelloException(
                "curve_xyz_speed speed must be in the range 10-60 cm/s"
            )
        self._validate_curve_points(x1, y1, z1, x2, y2, z2)
        self._run_plan(
            CurveCommand(
                x1_cm=x1,
                y1_cm=y1,
                z1_cm=z1,
                x2_cm=x2,
                y2_cm=y2,
                z2_cm=z2,
                speed_cm_s=speed,
            )
        )

    def send_rc_control(
        self,
        left_right_velocity: int,
        forward_backward_velocity: int,
        up_down_velocity: int,
        yaw_velocity: int,
    ) -> None:
        self._require_connected()
        self._rc_control = RcControl(
            left_right=left_right_velocity,
            forward_back=forward_backward_velocity,
            up_down=up_down_velocity,
            yaw=yaw_velocity,
        ).clamped()
        if not self.state.flying:
            return
        self.state.current_command = (
            f"rc({self._rc_control.left_right},{self._rc_control.forward_back},"
            f"{self._rc_control.up_down},{self._rc_control.yaw})"
        )

    def get_current_state(self) -> dict[str, int | float | str]:
        self._require_connected()
        return self.state.as_state_packet()

    def get_battery(self) -> int:
        self._require_connected()
        return int(self.state.battery_percent)

    def query_battery(self) -> int:
        return self.get_battery()

    def get_height(self) -> int:
        self._require_connected()
        return int(round(self.state.z_cm))

    def query_height(self) -> int:
        return self.get_height()

    def get_yaw(self) -> int:
        self._require_connected()
        return int(round(self.state.yaw_deg))

    def get_speed_x(self) -> int:
        self._require_connected()
        return int(round(self.state.speed_x_cm_s))

    def get_speed_y(self) -> int:
        self._require_connected()
        return int(round(self.state.speed_y_cm_s))

    def get_speed_z(self) -> int:
        self._require_connected()
        return int(round(self.state.speed_z_cm_s))

    def get_flight_time(self) -> int:
        self._require_connected()
        return int(round(self.state.flight_time_s))

    def query_flight_time(self) -> int:
        return self.get_flight_time()

    def _run_distance(self, axis: str, distance_cm: int) -> None:
        self._require_flying()
        if not 20 <= distance_cm <= 500:
            raise TelloException("Move distance must be in the range 20-500 cm")
        self._run_plan(BodyTranslationCommand(axis=axis, distance_cm=distance_cm))

    def _run_rotation(self, direction: str, angle_deg: int) -> None:
        self._require_flying()
        max_angle = 3600 if direction == "ccw" else 360
        if not 1 <= angle_deg <= max_angle:
            raise TelloException(
                f"Rotation angle must be in the range 1-{max_angle} degrees"
            )
        self._run_plan(RotationCommand(direction=direction, angle_deg=angle_deg))

    def _run_flip(self, direction: str) -> None:
        self._require_flying()
        self._run_plan(FlipCommand(direction=direction))

    def _run_plan(self, command: object) -> None:
        self._rc_control = RcControl()
        plan = self.motion_model.plan(self.state, command)  # type: ignore[arg-type]
        self._active_plan = plan
        self._active_elapsed_s = 0.0
        self.runtime.render()
        while self._active_plan is not None:
            remaining_s = self._active_plan.duration_s - self._active_elapsed_s
            self.runtime.sleep(min(self.runtime.options.step_s, remaining_s))

    def _require_connected(self) -> None:
        if self._ended:
            raise TelloException(
                "This Tello session has ended; create a new Tello() instance"
            )
        if not self.state.connected:
            raise TelloException("Call connect() before using Tello commands")

    def _require_flying(self) -> None:
        self._require_connected()
        if not self.state.flying:
            raise TelloException("The drone must be flying before this command can run")

    @staticmethod
    def _validate_go_value(value: int) -> None:
        if not -500 <= value <= 500:
            raise TelloException(
                "go/curve coordinates must be in the range -500..500 cm"
            )

    @staticmethod
    def _validate_curve_points(
        x1: int, y1: int, z1: int, x2: int, y2: int, z2: int
    ) -> None:
        for axis_name, first, second in (
            ("x", x1, x2),
            ("y", y1, y2),
            ("z", z1, z2),
        ):
            if (
                abs(first) <= 20
                and abs(second) <= 20
                and not (first == 0 and second == 0)
            ):
                raise TelloException(
                    f"curve_xyz_speed {axis_name}-axis values cannot both be inside [-20, 20] unless both are zero"
                )

        p0 = (0.0, 0.0, 0.0)
        p1 = (float(x1), float(y1), float(z1))
        p2 = (float(x2), float(y2), float(z2))
        v1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        v2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        cross = (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0],
        )
        area = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) / 2.0
        if area <= 1e-6:
            raise TelloException("curve_xyz_speed points must form a non-collinear arc")

        a = math.dist(p1, p2)
        b = math.dist(p0, p2)
        c = math.dist(p0, p1)
        radius = (a * b * c) / (4.0 * area)
        if not 50.0 <= radius <= 1000.0:
            raise TelloException(
                "curve_xyz_speed arc radius must be between 50 and 1000 cm"
            )
