from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Axis = Literal["forward", "back", "left", "right", "up", "down"]
FlipDirection = Literal["left", "right", "forward", "back"]


@dataclass(frozen=True, slots=True)
class BodyTranslationCommand:
    axis: Axis
    distance_cm: int


@dataclass(frozen=True, slots=True)
class RotationCommand:
    direction: Literal["cw", "ccw"]
    angle_deg: int


@dataclass(frozen=True, slots=True)
class TakeoffCommand:
    target_height_cm: float


@dataclass(frozen=True, slots=True)
class LandCommand:
    pass


@dataclass(frozen=True, slots=True)
class FlipCommand:
    direction: FlipDirection


@dataclass(frozen=True, slots=True)
class GoCommand:
    x_cm: int
    y_cm: int
    z_cm: int
    speed_cm_s: int


@dataclass(frozen=True, slots=True)
class CurveCommand:
    x1_cm: int
    y1_cm: int
    z1_cm: int
    x2_cm: int
    y2_cm: int
    z2_cm: int
    speed_cm_s: int


@dataclass(frozen=True, slots=True)
class RcControl:
    left_right: int = 0
    forward_back: int = 0
    up_down: int = 0
    yaw: int = 0

    def clamped(self) -> "RcControl":
        return RcControl(
            left_right=max(-100, min(100, self.left_right)),
            forward_back=max(-100, min(100, self.forward_back)),
            up_down=max(-100, min(100, self.up_down)),
            yaw=max(-100, min(100, self.yaw)),
        )

    def is_zero(self) -> bool:
        return not any((self.left_right, self.forward_back, self.up_down, self.yaw))
