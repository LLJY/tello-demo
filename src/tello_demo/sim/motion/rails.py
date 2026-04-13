from __future__ import annotations

import math
from dataclasses import dataclass, field

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
from tello_demo.sim.motion.base import (
    MotionCommand,
    MotionModel,
    MotionPlan,
    MotionProfile,
)
from tello_demo.sim.state import DroneState, normalize_angle


def smoothstep(progress: float) -> float:
    clamped = min(max(progress, 0.0), 1.0)
    return clamped * clamped * (3.0 - 2.0 * clamped)


def wave(progress: float) -> float:
    return math.sin(math.pi * min(max(progress, 0.0), 1.0))


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def body_to_world(
    forward_cm: float, left_cm: float, yaw_deg: float
) -> tuple[float, float]:
    yaw_rad = math.radians(yaw_deg)
    x_cm = math.cos(yaw_rad) * forward_cm - math.sin(yaw_rad) * left_cm
    y_cm = math.sin(yaw_rad) * forward_cm + math.cos(yaw_rad) * left_cm
    return x_cm, y_cm


def dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(dot(vector, vector))


def normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = norm(vector)
    return (vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude)


@dataclass(slots=True)
class RailsMotionModel(MotionModel):
    profile: MotionProfile = field(default_factory=MotionProfile)

    def plan(self, state: DroneState, command: MotionCommand) -> MotionPlan:
        if isinstance(command, TakeoffCommand):
            return self._plan_takeoff(state, command)
        if isinstance(command, LandCommand):
            return self._plan_land(state)
        if isinstance(command, BodyTranslationCommand):
            return self._plan_body_translation(state, command)
        if isinstance(command, RotationCommand):
            return self._plan_rotation(state, command)
        if isinstance(command, GoCommand):
            return self._plan_go(state, command)
        if isinstance(command, CurveCommand):
            return self._plan_curve(state, command)
        if isinstance(command, FlipCommand):
            return self._plan_flip(state, command)
        raise TypeError(f"Unsupported motion command: {type(command)!r}")

    def advance_rc(self, state: DroneState, rc: RcControl, dt_s: float) -> DroneState:
        rc = rc.clamped()
        next_state = state.copy()
        if not next_state.flying:
            next_state.current_command = "idle"
            next_state.speed_x_cm_s = 0.0
            next_state.speed_y_cm_s = 0.0
            next_state.speed_z_cm_s = 0.0
            next_state.yaw_rate_deg_s = 0.0
            next_state.pitch_deg = 0.0
            next_state.roll_deg = 0.0
            return next_state

        forward_speed = (rc.forward_back / 100.0) * self.profile.rc_linear_speed_cm_s
        left_speed = -(rc.left_right / 100.0) * self.profile.rc_linear_speed_cm_s
        up_speed = (rc.up_down / 100.0) * self.profile.rc_vertical_speed_cm_s
        yaw_rate = -(rc.yaw / 100.0) * self.profile.rc_yaw_speed_deg_s

        dx_cm, dy_cm = body_to_world(
            forward_speed * dt_s, left_speed * dt_s, next_state.yaw_deg
        )
        next_state.x_cm += dx_cm
        next_state.y_cm += dy_cm
        next_state.z_cm = max(0.0, next_state.z_cm + up_speed * dt_s)
        next_state.yaw_deg = normalize_angle(next_state.yaw_deg + yaw_rate * dt_s)

        next_state.speed_x_cm_s = dx_cm / dt_s if dt_s else 0.0
        next_state.speed_y_cm_s = dy_cm / dt_s if dt_s else 0.0
        next_state.speed_z_cm_s = up_speed
        next_state.yaw_rate_deg_s = yaw_rate
        next_state.pitch_deg = (
            -wave(0.5) * (rc.forward_back / 100.0) * self.profile.move_tilt_deg
        )
        next_state.roll_deg = (
            wave(0.5) * (rc.left_right / 100.0) * self.profile.move_roll_deg
        )
        next_state.current_command = (
            f"rc({rc.left_right},{rc.forward_back},{rc.up_down},{rc.yaw})"
        )
        return next_state

    def _plan_takeoff(self, state: DroneState, command: TakeoffCommand) -> MotionPlan:
        start = state.copy()
        target_height = max(command.target_height_cm, start.z_cm, 20.0)
        climb = target_height - start.z_cm
        duration_s = max(climb / self.profile.takeoff_speed_cm_s, 0.25)

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            sample = start.copy()
            sample.connected = True
            sample.flying = True
            sample.current_command = "takeoff"
            sample.z_cm = start.z_cm + climb * progress
            return sample

        return MotionPlan(label="takeoff", duration_s=duration_s, sampler=sampler)

    def _plan_land(self, state: DroneState) -> MotionPlan:
        start = state.copy()
        duration_s = max(start.z_cm / self.profile.landing_speed_cm_s, 0.25)

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            sample = start.copy()
            sample.current_command = "land"
            sample.z_cm = max(0.0, start.z_cm * (1.0 - progress))
            if progress >= 1.0:
                sample.flying = False
                sample.pitch_deg = 0.0
                sample.roll_deg = 0.0
            return sample

        return MotionPlan(label="land", duration_s=duration_s, sampler=sampler)

    def _plan_body_translation(
        self, state: DroneState, command: BodyTranslationCommand
    ) -> MotionPlan:
        start = state.copy()
        distance = float(command.distance_cm)
        if command.axis == "down":
            distance = min(distance, start.z_cm)
        speed = clamp(float(start.configured_speed_cm_s), 10.0, 100.0)
        duration_s = max(distance / speed, 0.2)

        forward = 0.0
        left = 0.0
        up = 0.0
        if command.axis == "forward":
            forward = distance
        elif command.axis == "back":
            forward = -distance
        elif command.axis == "left":
            left = distance
        elif command.axis == "right":
            left = -distance
        elif command.axis == "up":
            up = distance
        elif command.axis == "down":
            up = -distance

        dx_cm, dy_cm = body_to_world(forward, left, start.yaw_deg)
        tilt_sign = 0.0
        roll_sign = 0.0
        if command.axis == "forward":
            tilt_sign = -1.0
        elif command.axis == "back":
            tilt_sign = 1.0
        elif command.axis == "left":
            roll_sign = -1.0
        elif command.axis == "right":
            roll_sign = 1.0

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            arch = wave(elapsed_s / duration_s)
            sample = start.copy()
            sample.current_command = f"move_{command.axis}({command.distance_cm})"
            sample.x_cm = start.x_cm + dx_cm * progress
            sample.y_cm = start.y_cm + dy_cm * progress
            sample.z_cm = max(0.0, start.z_cm + up * progress)
            if command.axis == "down" and sample.z_cm <= 0.0:
                sample.flying = False
            sample.pitch_deg = tilt_sign * self.profile.move_tilt_deg * arch
            sample.roll_deg = roll_sign * self.profile.move_roll_deg * arch
            return sample

        return MotionPlan(
            label=f"move_{command.axis}", duration_s=duration_s, sampler=sampler
        )

    def _plan_rotation(self, state: DroneState, command: RotationCommand) -> MotionPlan:
        start = state.copy()
        direction = -1.0 if command.direction == "cw" else 1.0
        delta = direction * float(command.angle_deg)
        duration_s = max(abs(delta) / self.profile.yaw_speed_deg_s, 0.2)

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            sample = start.copy()
            sample.current_command = (
                "rotate_clockwise"
                if command.direction == "cw"
                else "rotate_counter_clockwise"
            )
            sample.yaw_deg = normalize_angle(start.yaw_deg + delta * progress)
            return sample

        return MotionPlan(
            label=f"rotate_{command.direction}", duration_s=duration_s, sampler=sampler
        )

    def _plan_go(self, state: DroneState, command: GoCommand) -> MotionPlan:
        start = state.copy()
        dx_cm, dy_cm = body_to_world(command.x_cm, command.y_cm, start.yaw_deg)
        dz_cm = float(command.z_cm)
        distance = math.sqrt(dx_cm**2 + dy_cm**2 + dz_cm**2)
        speed = clamp(float(command.speed_cm_s), 10.0, 100.0)
        duration_s = max(distance / speed, 0.2)

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            sample = start.copy()
            sample.current_command = (
                f"go({command.x_cm},{command.y_cm},{command.z_cm},{command.speed_cm_s})"
            )
            sample.x_cm = start.x_cm + dx_cm * progress
            sample.y_cm = start.y_cm + dy_cm * progress
            sample.z_cm = max(0.0, start.z_cm + dz_cm * progress)
            sample.pitch_deg = -self.profile.move_tilt_deg * wave(
                elapsed_s / duration_s
            )
            return sample

        return MotionPlan(label="go_xyz_speed", duration_s=duration_s, sampler=sampler)

    def _plan_curve(self, state: DroneState, command: CurveCommand) -> MotionPlan:
        start = state.copy()
        control_dx, control_dy = body_to_world(
            command.x1_cm, command.y1_cm, start.yaw_deg
        )
        end_dx, end_dy = body_to_world(command.x2_cm, command.y2_cm, start.yaw_deg)
        p0 = (start.x_cm, start.y_cm, start.z_cm)
        p1 = (
            start.x_cm + control_dx,
            start.y_cm + control_dy,
            start.z_cm + command.z1_cm,
        )
        p2 = (start.x_cm + end_dx, start.y_cm + end_dy, start.z_cm + command.z2_cm)

        ab = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        ac = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        normal = normalize(cross(ab, ac))
        e1 = normalize(ab)
        e2 = cross(normal, e1)

        chord_length = math.dist(p0, p1)
        p2_local_x = dot(ac, e1)
        p2_local_y = dot(ac, e2)
        center_local_x = chord_length / 2.0
        center_local_y = (p2_local_x**2 + p2_local_y**2 - chord_length * p2_local_x) / (
            2.0 * p2_local_y
        )
        center = (
            p0[0] + center_local_x * e1[0] + center_local_y * e2[0],
            p0[1] + center_local_x * e1[1] + center_local_y * e2[1],
            p0[2] + center_local_x * e1[2] + center_local_y * e2[2],
        )

        radius = math.dist(center, p0)
        radial_start = normalize(
            (p0[0] - center[0], p0[1] - center[1], p0[2] - center[2])
        )
        tangent_start = normalize(cross(normal, radial_start))

        def angle_for(point: tuple[float, float, float]) -> float:
            offset = (point[0] - center[0], point[1] - center[1], point[2] - center[2])
            return math.atan2(dot(offset, tangent_start), dot(offset, radial_start))

        via_angle = angle_for(p1) % (2.0 * math.pi)
        end_angle_ccw = angle_for(p2) % (2.0 * math.pi)
        sweep_angle = end_angle_ccw
        if not (0.0 < via_angle < end_angle_ccw):
            sweep_angle = end_angle_ccw - (2.0 * math.pi)

        length = radius * abs(sweep_angle)
        speed = clamp(float(command.speed_cm_s), 10.0, 60.0)
        duration_s = max(length / speed, 0.4)

        def sampler(elapsed_s: float) -> DroneState:
            progress = smoothstep(elapsed_s / duration_s)
            sample = start.copy()
            sample.current_command = "curve_xyz_speed"
            angle = sweep_angle * progress
            x_cm = center[0] + radius * (
                math.cos(angle) * radial_start[0] + math.sin(angle) * tangent_start[0]
            )
            y_cm = center[1] + radius * (
                math.cos(angle) * radial_start[1] + math.sin(angle) * tangent_start[1]
            )
            z_cm = center[2] + radius * (
                math.cos(angle) * radial_start[2] + math.sin(angle) * tangent_start[2]
            )
            sample.x_cm = x_cm
            sample.y_cm = y_cm
            sample.z_cm = max(0.0, z_cm)
            sample.pitch_deg = -self.profile.move_tilt_deg * wave(progress)
            sample.roll_deg = (
                self.profile.move_roll_deg * math.sin(2.0 * math.pi * progress) * 0.5
            )
            return sample

        return MotionPlan(
            label="curve_xyz_speed", duration_s=duration_s, sampler=sampler
        )

    def _plan_flip(self, state: DroneState, command: FlipCommand) -> MotionPlan:
        start = state.copy()
        duration_s = max(self.profile.flip_duration_s, 0.2)

        if command.direction in {"forward", "back"}:
            axis = "pitch"
            rotation_sign = -1.0 if command.direction == "forward" else 1.0
            forward_sign = 1.0 if command.direction == "forward" else -1.0
            left_sign = 0.0
        else:
            axis = "roll"
            rotation_sign = 1.0 if command.direction == "right" else -1.0
            forward_sign = 0.0
            left_sign = -1.0 if command.direction == "right" else 1.0

        excursion_forward = self.profile.flip_body_excursion_cm * forward_sign
        excursion_left = self.profile.flip_body_excursion_cm * left_sign

        def sampler(elapsed_s: float) -> DroneState:
            progress = min(max(elapsed_s / duration_s, 0.0), 1.0)
            sample = start.copy()
            sample.current_command = f"flip_{command.direction}"
            dx_cm, dy_cm = body_to_world(
                excursion_forward * wave(progress),
                excursion_left * wave(progress),
                start.yaw_deg,
            )
            sample.x_cm = start.x_cm + dx_cm
            sample.y_cm = start.y_cm + dy_cm
            sample.z_cm = start.z_cm + self.profile.flip_arc_height_cm * wave(progress)
            if axis == "pitch":
                sample.pitch_deg = rotation_sign * 360.0 * progress
                sample.roll_deg = 0.0
            else:
                sample.roll_deg = rotation_sign * 360.0 * progress
                sample.pitch_deg = 0.0
            if progress >= 1.0:
                sample.pitch_deg = 0.0
                sample.roll_deg = 0.0
            return sample

        return MotionPlan(
            label=f"flip_{command.direction}", duration_s=duration_s, sampler=sampler
        )
