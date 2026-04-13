from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

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
from tello_demo.sim.state import DroneState

MotionCommand = (
    BodyTranslationCommand
    | RotationCommand
    | TakeoffCommand
    | LandCommand
    | FlipCommand
    | GoCommand
    | CurveCommand
)


@dataclass(slots=True)
class MotionProfile:
    move_speed_cm_s: float = 45.0
    vertical_speed_cm_s: float = 30.0
    yaw_speed_deg_s: float = 120.0
    takeoff_height_cm: float = 70.0
    takeoff_speed_cm_s: float = 35.0
    landing_speed_cm_s: float = 30.0
    rc_linear_speed_cm_s: float = 55.0
    rc_vertical_speed_cm_s: float = 40.0
    rc_yaw_speed_deg_s: float = 140.0
    move_tilt_deg: float = 10.0
    move_roll_deg: float = 10.0
    flip_duration_s: float = 1.0
    flip_arc_height_cm: float = 25.0
    flip_body_excursion_cm: float = 12.0
    battery_drain_per_s: float = 0.02
    default_speed_cm_s: int = 30


@dataclass(slots=True)
class MotionPlan:
    label: str
    duration_s: float
    sampler: Callable[[float], DroneState]

    def sample(self, elapsed_s: float) -> DroneState:
        elapsed = min(max(0.0, elapsed_s), self.duration_s)
        return self.sampler(elapsed)


class MotionModel(Protocol):
    profile: MotionProfile

    def plan(self, state: DroneState, command: MotionCommand) -> MotionPlan: ...

    def advance_rc(
        self, state: DroneState, rc: RcControl, dt_s: float
    ) -> DroneState: ...
