from __future__ import annotations

from tello_demo.sim.commands import (
    BodyTranslationCommand,
    CurveCommand,
    FlipCommand,
    RotationCommand,
    TakeoffCommand,
)
from tello_demo.sim.motion import MotionProfile, RailsMotionModel
from tello_demo.sim.state import DroneState


def test_body_translation_respects_yaw() -> None:
    model = RailsMotionModel(MotionProfile())
    start = DroneState(connected=True, flying=True, yaw_deg=90.0, z_cm=70.0)
    plan = model.plan(start, BodyTranslationCommand(axis="forward", distance_cm=100))

    end = plan.sample(plan.duration_s)

    assert round(end.x_cm, 3) == 0.0
    assert round(end.y_cm, 3) == 100.0
    assert round(end.z_cm, 3) == 70.0


def test_rotation_plan_updates_yaw() -> None:
    model = RailsMotionModel(MotionProfile())
    start = DroneState(connected=True, flying=True, yaw_deg=0.0, z_cm=70.0)
    plan = model.plan(start, RotationCommand(direction="ccw", angle_deg=90))

    end = plan.sample(plan.duration_s)

    assert round(end.yaw_deg, 3) == 90.0


def test_body_translation_uses_configured_speed() -> None:
    model = RailsMotionModel(MotionProfile())
    slow = DroneState(
        connected=True, flying=True, yaw_deg=0.0, z_cm=70.0, configured_speed_cm_s=20.0
    )
    fast = DroneState(
        connected=True, flying=True, yaw_deg=0.0, z_cm=70.0, configured_speed_cm_s=60.0
    )

    slow_plan = model.plan(
        slow, BodyTranslationCommand(axis="forward", distance_cm=120)
    )
    fast_plan = model.plan(
        fast, BodyTranslationCommand(axis="forward", distance_cm=120)
    )

    assert slow_plan.duration_s > fast_plan.duration_s


def test_flip_returns_to_original_position() -> None:
    model = RailsMotionModel(MotionProfile())
    start = DroneState(connected=True, flying=True, yaw_deg=0.0, z_cm=70.0)
    plan = model.plan(start, FlipCommand(direction="forward"))

    mid = plan.sample(plan.duration_s / 2.0)
    end = plan.sample(plan.duration_s)

    assert mid.z_cm > start.z_cm
    assert round(end.x_cm, 3) == round(start.x_cm, 3)
    assert round(end.y_cm, 3) == round(start.y_cm, 3)
    assert round(end.z_cm, 3) == round(start.z_cm, 3)
    assert round(end.pitch_deg, 3) == 0.0


def test_takeoff_reaches_target_height() -> None:
    model = RailsMotionModel(MotionProfile(takeoff_height_cm=80.0))
    start = DroneState(connected=True, flying=False, z_cm=0.0)
    plan = model.plan(start, TakeoffCommand(target_height_cm=80.0))

    end = plan.sample(plan.duration_s)

    assert end.flying is True
    assert round(end.z_cm, 3) == 80.0


def test_curve_plan_passes_through_declared_via_point() -> None:
    model = RailsMotionModel(MotionProfile())
    start = DroneState(connected=True, flying=True, yaw_deg=0.0, z_cm=70.0)
    plan = model.plan(
        start,
        CurveCommand(
            x1_cm=100,
            y1_cm=100,
            z1_cm=0,
            x2_cm=0,
            y2_cm=200,
            z2_cm=0,
            speed_cm_s=20,
        ),
    )

    midpoint = plan.sample(plan.duration_s / 2.0)

    assert round(midpoint.x_cm, 3) == 100.0
    assert round(midpoint.y_cm, 3) == 100.0
    assert round(midpoint.z_cm, 3) == 70.0
