from __future__ import annotations

from tello_demo.clock import ManualClock
from tello_demo.sim.commands import CurveCommand, GoCommand
from tello_demo.sim.motion import MotionProfile, RailsMotionModel
from tello_demo.sim.runtime import RuntimeOptions, SimulationRuntime
from tello_demo.sim.tello import SimTello, TelloException


def make_tello() -> SimTello:
    runtime = SimulationRuntime(
        clock=ManualClock(),
        options=RuntimeOptions(show=False, hold=False, step_s=0.05),
        motion_model=RailsMotionModel(MotionProfile()),
    )
    tello = SimTello(runtime=runtime, motion_model=runtime.motion_model)
    tello.connect()
    return tello


def test_discrete_flight_plan_updates_pose() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.move_forward(100)
    tello.rotate_clockwise(90)
    tello.move_forward(50)

    assert tello.get_height() == 70
    assert round(tello.state.x_cm, 1) == 100.0
    assert round(tello.state.y_cm, 1) == -50.0
    assert tello.get_yaw() == -90


def test_rc_control_moves_during_runtime_sleep() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.send_rc_control(0, 50, 0, 0)
    tello.runtime.sleep(2.0)
    tello.send_rc_control(0, 0, 0, 0)

    assert tello.state.x_cm > 50.0
    assert abs(tello.state.y_cm) < 1.0


def test_rc_left_right_axis_matches_tello_direction() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.send_rc_control(100, 0, 0, 0)
    tello.runtime.sleep(1.0)

    assert tello.state.y_cm < 0.0
    assert tello.state.roll_deg > 0.0

    tello.send_rc_control(-100, 0, 0, 0)
    tello.runtime.sleep(2.0)

    assert tello.state.y_cm > 0.0
    assert tello.state.roll_deg < 0.0


def test_flip_keeps_hover_pose_after_completion() -> None:
    tello = make_tello()

    tello.takeoff()
    start = tello.state.copy()
    tello.flip_left()

    assert round(tello.state.x_cm, 3) == round(start.x_cm, 3)
    assert round(tello.state.y_cm, 3) == round(start.y_cm, 3)
    assert round(tello.state.z_cm, 3) == round(start.z_cm, 3)
    assert tello.state.roll_deg == 0.0


def test_set_speed_changes_move_timing_and_query() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.set_speed(20)
    slow_start = tello.runtime.time()
    tello.move_forward(100)
    slow_elapsed = tello.runtime.time() - slow_start

    tello.rotate_counter_clockwise(180)
    tello.set_speed(60)
    fast_start = tello.runtime.time()
    tello.move_forward(100)
    fast_elapsed = tello.runtime.time() - fast_start

    assert tello.query_speed() == 60
    assert slow_elapsed > fast_elapsed


def test_blocking_motion_accumulates_flight_time_and_battery() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.set_speed(10)
    tello.move_forward(500)

    assert tello.get_flight_time() >= 50
    assert tello.get_current_state()["time"] >= 50
    assert tello.get_battery() < 100


def test_repeated_takeoff_is_rejected() -> None:
    tello = make_tello()

    tello.takeoff()

    try:
        tello.takeoff()
    except TelloException as exc:
        assert "already flying" in str(exc)
    else:
        raise AssertionError("Repeated takeoff() did not raise TelloException")


def test_unsupported_api_raises_tello_exception() -> None:
    tello = make_tello()

    try:
        tello.emergency()
    except TelloException as exc:
        assert "does not support 'emergency'" in str(exc)
    else:
        raise AssertionError("Unsupported API did not raise TelloException")


def test_counter_clockwise_rotation_allows_large_angles() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.rotate_counter_clockwise(720)

    assert tello.get_yaw() == 0


def test_helpers_require_connect() -> None:
    runtime = SimulationRuntime(
        clock=ManualClock(),
        options=RuntimeOptions(show=False, hold=False, step_s=0.05),
        motion_model=RailsMotionModel(MotionProfile()),
    )
    tello = SimTello(runtime=runtime, motion_model=runtime.motion_model)

    for method in (tello.streamon, lambda: tello.set_speed(20), tello.query_battery):
        try:
            method()
        except TelloException as exc:
            assert "connect()" in str(exc)
        else:
            raise AssertionError("Helper method did not require connect()")


def test_curve_rejects_invalid_arc() -> None:
    tello = make_tello()

    tello.takeoff()

    try:
        tello.curve_xyz_speed(10, 0, 0, 20, 0, 0, 20)
    except TelloException as exc:
        assert "curve_xyz_speed" in str(exc)
    else:
        raise AssertionError("Invalid curve did not raise TelloException")


def test_curve_rejects_small_axis_pair_when_other_is_zero() -> None:
    tello = make_tello()

    tello.takeoff()

    try:
        tello.curve_xyz_speed(0, 50, 0, 10, 100, 0, 20)
    except TelloException as exc:
        assert "curve_xyz_speed" in str(exc)
    else:
        raise AssertionError("Invalid curve axis pair did not raise TelloException")


def test_negative_sim_sleep_matches_python_error() -> None:
    tello = make_tello()

    try:
        tello.runtime.sleep(-1.0)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("Negative sleep did not raise ValueError")


def test_end_before_connect_is_safe() -> None:
    runtime = SimulationRuntime(
        clock=ManualClock(),
        options=RuntimeOptions(show=False, hold=False, step_s=0.05),
        motion_model=RailsMotionModel(MotionProfile()),
    )
    tello = SimTello(runtime=runtime, motion_model=runtime.motion_model)

    tello.end()

    assert tello.state.current_command == "idle"


def test_end_closes_session_for_future_commands() -> None:
    tello = make_tello()

    tello.end()

    try:
        tello.takeoff()
    except TelloException as exc:
        assert "ended" in str(exc)
    else:
        raise AssertionError("Commands after end() did not fail")

    try:
        tello.get_current_state()
    except TelloException as exc:
        assert "ended" in str(exc)
    else:
        raise AssertionError("Telemetry after end() did not fail")


def test_moving_down_to_floor_lands_drone() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.move_down(500)

    assert tello.state.z_cm == 0.0
    assert tello.state.flying is False

    try:
        tello.move_forward(20)
    except TelloException as exc:
        assert "must be flying" in str(exc)
    else:
        raise AssertionError("Grounded drone should not accept move commands")


def test_get_current_state_requires_connect() -> None:
    runtime = SimulationRuntime(
        clock=ManualClock(),
        options=RuntimeOptions(show=False, hold=False, step_s=0.05),
        motion_model=RailsMotionModel(MotionProfile()),
    )
    tello = SimTello(runtime=runtime, motion_model=runtime.motion_model)

    try:
        tello.get_current_state()
    except TelloException as exc:
        assert "connect()" in str(exc)
    else:
        raise AssertionError("get_current_state() did not require connect()")


def test_get_current_state_exposes_expected_telemetry_keys() -> None:
    tello = make_tello()

    state = tello.get_current_state()

    expected_keys = {
        "mid",
        "x",
        "y",
        "z",
        "pitch",
        "roll",
        "yaw",
        "vgx",
        "vgy",
        "vgz",
        "templ",
        "temph",
        "tof",
        "h",
        "bat",
        "baro",
        "time",
        "agx",
        "agy",
        "agz",
    }

    assert expected_keys.issubset(state.keys())


def test_battery_drains_over_simulated_flight_time() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.runtime.sleep(60.0)

    assert tello.get_battery() < 100


def test_go_to_floor_lands_drone() -> None:
    tello = make_tello()

    tello.takeoff()
    planned = tello.motion_model.plan(
        tello.state,
        GoCommand(x_cm=0, y_cm=0, z_cm=-500, speed_cm_s=10),
    )
    start = tello.runtime.time()
    tello.go_xyz_speed(0, 0, -500, 10)
    elapsed = tello.runtime.time() - start

    assert tello.state.z_cm == 0.0
    assert tello.state.flying is False
    assert elapsed < planned.duration_s


def test_rc_descent_to_floor_lands_drone() -> None:
    tello = make_tello()

    tello.takeoff()
    tello.send_rc_control(0, 0, -100, 0)
    tello.runtime.sleep(3.0)

    assert tello.state.z_cm == 0.0
    assert tello.state.flying is False


def test_curve_descent_to_floor_lands_drone() -> None:
    tello = make_tello()

    tello.takeoff()
    planned = tello.motion_model.plan(
        tello.state,
        CurveCommand(
            x1_cm=100,
            y1_cm=100,
            z1_cm=0,
            x2_cm=0,
            y2_cm=200,
            z2_cm=-200,
            speed_cm_s=20,
        ),
    )
    start = tello.runtime.time()
    tello.curve_xyz_speed(100, 100, 0, 0, 200, -200, 20)
    elapsed = tello.runtime.time() - start

    assert tello.state.z_cm == 0.0
    assert tello.state.flying is False
    assert elapsed < planned.duration_s
