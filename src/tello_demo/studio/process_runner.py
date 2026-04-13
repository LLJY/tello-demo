from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

StreamName = Literal["stdout", "stderr"]
_SANITIZED_PYTHON_ENV_VARS = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")


@dataclass(frozen=True, slots=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class OutputEvent:
    stream: StreamName
    text: str


class RunningProcess:
    def __init__(
        self,
        spec: LaunchSpec,
        *,
        on_output: Callable[[OutputEvent], None],
        on_exit: Callable[[int], None] | None = None,
    ) -> None:
        self.spec = spec
        self._on_output = on_output
        self._on_exit = on_exit
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._waiter_thread: threading.Thread | None = None

    @property
    def pid(self) -> int | None:
        process = self._process
        return process.pid if process is not None else None

    @property
    def returncode(self) -> int | None:
        process = self._process
        return process.poll() if process is not None else None

    def start(self) -> None:
        with self._lock:
            if self._process is not None:
                raise RuntimeError("Process has already been started")
            self._process = subprocess.Popen(
                list(self.spec.argv),
                cwd=str(self.spec.cwd),
                env=dict(self.spec.env) if self.spec.env is not None else None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
            )

            self._stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(self._process.stdout, "stdout"),
                daemon=True,
            )
            self._stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(self._process.stderr, "stderr"),
                daemon=True,
            )
            self._waiter_thread = threading.Thread(
                target=self._wait_for_exit,
                daemon=True,
            )

            self._stdout_thread.start()
            self._stderr_thread.start()
            self._waiter_thread.start()

    def poll(self) -> int | None:
        process = self._process
        return process.poll() if process is not None else None

    def wait(self, timeout: float | None = None) -> int:
        process = self._process
        if process is None:
            raise RuntimeError("Process has not been started")
        return process.wait(timeout=timeout)

    def stop(self, *, kill_after_s: float = 2.0) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return

        process.terminate()
        deadline = time.monotonic() + kill_after_s
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            process.kill()

    def _read_stream(
        self,
        stream: subprocess.Popen[str] | None,
        stream_name: StreamName,
    ) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                self._on_output(OutputEvent(stream=stream_name, text=line))
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._on_output(
                OutputEvent(stream="stderr", text=f"[studio stream error] {exc}\n")
            )
        finally:
            stream.close()

    def _wait_for_exit(self) -> None:
        process = self._process
        if process is None:
            return
        returncode = process.wait()
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
        if self._on_exit is not None:
            self._on_exit(returncode)


def launch_process(
    spec: LaunchSpec,
    *,
    on_output: Callable[[OutputEvent], None],
    on_exit: Callable[[int], None] | None = None,
) -> RunningProcess:
    process = RunningProcess(spec, on_output=on_output, on_exit=on_exit)
    process.start()
    return process


def _build_child_env(
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    for key in _SANITIZED_PYTHON_ENV_VARS:
        env.pop(key, None)
    if extra_env is not None:
        env.update(extra_env)
    return env


def build_plain_python_launch(
    python_executable: Path,
    script_path: Path,
    *,
    script_args: Sequence[str] = (),
    extra_env: Mapping[str, str] | None = None,
) -> LaunchSpec:
    return LaunchSpec(
        argv=(str(python_executable), "-u", str(script_path), *script_args),
        cwd=script_path.parent,
        env=_build_child_env(extra_env),
        description=f"python {script_path.name}",
    )


def build_tello_launch(
    python_executable: Path,
    script_path: Path,
    *,
    mode: Literal["sim", "real"],
    script_args: Sequence[str] = (),
    extra_env: Mapping[str, str] | None = None,
) -> LaunchSpec:
    argv = [
        str(python_executable),
        "-u",
        "-P",
        "-m",
        "tello_demo.runner",
        "run",
        str(script_path),
        "--mode",
        mode,
    ]
    if script_args:
        argv.extend(("--", *script_args))
    return LaunchSpec(
        argv=tuple(argv),
        cwd=script_path.parent,
        env=_build_child_env(extra_env),
        description=f"tello-demo {mode} {script_path.name}",
    )
