from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

from tello_demo.runner import run_script


def test_runner_executes_djitellopy_script_in_sim_mode(tmp_path: Path) -> None:
    script = tmp_path / "user_script.py"
    script.write_text(
        "from djitellopy import Tello\n"
        "import time\n\n"
        "tello = Tello()\n"
        "tello.connect()\n"
        "tello.takeoff()\n"
        "tello.send_rc_control(0, 50, 0, 0)\n"
        "time.sleep(2)\n"
        "tello.send_rc_control(0, 0, 0, 0)\n"
        "tello.land()\n"
    )

    result = run_script(script, mode="sim", show=False, hold=False, realtime=False)
    runtime = result["runtime"]

    assert runtime is not None
    assert len(runtime.drones) == 1
    drone = runtime.drones[0]
    assert drone.state.x_cm > 50.0
    assert drone.state.z_cm == 0.0


def test_runner_rejects_non_positive_step(tmp_path: Path) -> None:
    script = tmp_path / "noop.py"
    script.write_text("print('ok')\n")

    with pytest.raises(ValueError, match="step size"):
        run_script(
            script, mode="sim", show=False, hold=False, realtime=False, step_s=0.0
        )


def test_runner_patches_time_time_and_monotonic(tmp_path: Path) -> None:
    script = tmp_path / "time_script.py"
    script.write_text(
        "import time\n\n"
        "start_time = time.time()\n"
        "start_mono = time.monotonic()\n"
        "time.sleep(1.5)\n"
        "elapsed_time = time.time() - start_time\n"
        "elapsed_mono = time.monotonic() - start_mono\n"
    )

    result = run_script(script, mode="sim", show=False, hold=False, realtime=False)
    globals_after_run = result["globals"]

    assert round(globals_after_run["elapsed_time"], 3) == 1.5
    assert round(globals_after_run["elapsed_mono"], 3) == 1.5


def test_runner_real_mode_supports_sibling_imports(tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 123\n")
    script = tmp_path / "main.py"
    script.write_text("import helper\nresult = helper.VALUE\n")

    result = run_script(script, mode="real")

    assert result["globals"]["result"] == 123


def test_runner_sim_mode_supports_sibling_imports(tmp_path: Path) -> None:
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 456\n")
    script = tmp_path / "main.py"
    script.write_text(
        "import helper\n"
        "from djitellopy import Tello\n"
        "tello = Tello()\n"
        "tello.connect()\n"
        "result = helper.VALUE\n"
    )

    result = run_script(script, mode="sim", show=False, hold=False, realtime=False)

    assert result["globals"]["result"] == 456


def test_runner_real_mode_refreshes_package_submodule_between_runs(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    helper = package / "helper.py"
    helper.write_text("VALUE = 1\n")
    script = tmp_path / "main.py"
    script.write_text("from pkg.helper import VALUE\nresult = VALUE\n")

    first = run_script(script, mode="real")
    helper.write_text("VALUE = 2\nUPDATED = True\n")
    importlib.invalidate_caches()
    second = run_script(script, mode="real")

    assert first["globals"]["result"] == 1
    assert second["globals"]["result"] == 2


def test_runner_sim_mode_refreshes_package_submodule_between_runs(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    helper = package / "helper.py"
    helper.write_text("VALUE = 1\n")
    script = tmp_path / "main.py"
    script.write_text(
        "from pkg.helper import VALUE\n"
        "from djitellopy import Tello\n"
        "tello = Tello()\n"
        "tello.connect()\n"
        "result = VALUE\n"
    )

    first = run_script(script, mode="sim", show=False, hold=False, realtime=False)
    helper.write_text("VALUE = 2\nUPDATED = True\n")
    importlib.invalidate_caches()
    second = run_script(script, mode="sim", show=False, hold=False, realtime=False)

    assert first["globals"]["result"] == 1
    assert second["globals"]["result"] == 2


def test_runner_real_mode_restores_modules_after_exception(tmp_path: Path) -> None:
    original = types.ModuleType("helper")
    original.VALUE = "original"
    previous = sys.modules.get("helper")
    sys.modules["helper"] = original
    script = tmp_path / "main.py"
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 'script'\n")
    script.write_text("import helper\nraise RuntimeError(helper.VALUE)\n")

    try:
        with pytest.raises(RuntimeError, match="script"):
            run_script(script, mode="real")
        assert sys.modules["helper"] is original
    finally:
        if previous is None:
            sys.modules.pop("helper", None)
        else:
            sys.modules["helper"] = previous
