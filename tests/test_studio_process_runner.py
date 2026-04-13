from __future__ import annotations

import sys
import threading
from pathlib import Path

from tello_demo.studio.process_runner import (
    LaunchSpec,
    OutputEvent,
    RunningProcess,
    build_plain_python_launch,
    build_tello_launch,
)


def test_running_process_captures_stdout_and_stderr(tmp_path: Path) -> None:
    script = tmp_path / "script.py"
    script.write_text(
        "import sys\nprint('hello')\nprint('oops', file=sys.stderr)\n",
        encoding="utf-8",
    )

    outputs: list[OutputEvent] = []
    exit_codes: list[int] = []
    exited = threading.Event()
    process = RunningProcess(
        LaunchSpec(argv=(sys.executable, "-u", str(script)), cwd=tmp_path),
        on_output=outputs.append,
        on_exit=lambda returncode: (exit_codes.append(returncode), exited.set()),
    )

    process.start()

    assert exited.wait(10.0) is True
    assert exit_codes == [0]
    assert any(event.stream == "stdout" and "hello" in event.text for event in outputs)
    assert any(event.stream == "stderr" and "oops" in event.text for event in outputs)


def test_running_process_can_be_stopped(tmp_path: Path) -> None:
    script = tmp_path / "sleeper.py"
    script.write_text(
        "import time\nprint('start', flush=True)\ntime.sleep(30)\n",
        encoding="utf-8",
    )

    outputs: list[OutputEvent] = []
    exit_codes: list[int] = []
    exited = threading.Event()
    process = RunningProcess(
        LaunchSpec(argv=(sys.executable, "-u", str(script)), cwd=tmp_path),
        on_output=outputs.append,
        on_exit=lambda returncode: (exit_codes.append(returncode), exited.set()),
    )

    process.start()

    for _ in range(50):
        if any("start" in event.text for event in outputs):
            break
        exited.wait(0.05)

    process.stop(kill_after_s=0.2)

    assert exited.wait(10.0) is True
    assert exit_codes
    assert process.returncode is not None


def test_build_tello_launch_uses_runner_module_and_safe_path_flag() -> None:
    spec = build_tello_launch(
        Path("/tmp/python"),
        Path("/tmp/script.py"),
        mode="sim",
    )

    assert spec.argv[:6] == (
        "/tmp/python",
        "-u",
        "-P",
        "-m",
        "tello_demo.runner",
        "run",
    )


def test_launch_specs_sanitize_parent_python_environment(monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/tmp/pythonpath")
    monkeypatch.setenv("PYTHONHOME", "/tmp/pythonhome")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/venv")
    monkeypatch.setenv("MPLBACKEND", "Agg")

    plain = build_plain_python_launch(Path("/tmp/python"), Path("/tmp/script.py"))
    tello = build_tello_launch(Path("/tmp/python"), Path("/tmp/script.py"), mode="sim")

    assert plain.env is not None
    assert tello.env is not None
    for spec in (plain, tello):
        assert "PYTHONPATH" not in spec.env
        assert "PYTHONHOME" not in spec.env
        assert "VIRTUAL_ENV" not in spec.env
        assert spec.env["MPLBACKEND"] == "Agg"
