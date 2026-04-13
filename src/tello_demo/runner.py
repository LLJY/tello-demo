from __future__ import annotations

import argparse
import contextlib
import runpy
import sys
import types
from pathlib import Path
from typing import Any
from unittest import mock

import time as _time

from tello_demo.clock import ManualClock, SystemClock
from tello_demo.sim.motion import MotionProfile, RailsMotionModel
from tello_demo.sim.runtime import RuntimeOptions, SimulationRuntime
from tello_demo.sim.tello import SimTello, TelloException

_ACTIVE_RUNTIME: SimulationRuntime | None = None


class ShimTello(SimTello):
    def __init__(
        self, host: str = "192.168.10.1", retry_count: int = 3, vs_udp: int = 11111
    ) -> None:
        runtime = _ACTIVE_RUNTIME
        if runtime is None:
            raise RuntimeError("Sim runtime is not active")
        super().__init__(
            runtime=runtime,
            motion_model=runtime.motion_model,
            host=host,
            retry_count=retry_count,
            vs_udp=vs_udp,
        )


def _make_sim_module() -> tuple[types.ModuleType, types.ModuleType]:
    module = types.ModuleType("djitellopy")
    module.Tello = ShimTello
    module.TelloException = TelloException
    module.__all__ = ["Tello", "TelloException", "tello"]

    tello_submodule = types.ModuleType("djitellopy.tello")
    tello_submodule.Tello = ShimTello
    tello_submodule.TelloException = TelloException
    module.tello = tello_submodule
    return module, tello_submodule


def _discover_script_local_module_names(directory: Path) -> set[str]:
    module_names = {
        path.stem for path in directory.glob("*.py") if path.name != "__init__.py"
    }
    package_names = {
        path.name
        for path in directory.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    return module_names | package_names


def _is_local_module_name(module_name: str, local_roots: set[str]) -> bool:
    return any(
        module_name == root or module_name.startswith(f"{root}.")
        for root in local_roots
    )


def run_script(
    script_path: str | Path,
    *,
    mode: str,
    show: bool = True,
    hold: bool = False,
    realtime: bool = True,
    step_s: float = 0.05,
    script_args: list[str] | None = None,
) -> dict[str, Any]:
    path = Path(script_path).resolve()
    script_dir = path.parent
    if not path.is_file():
        raise FileNotFoundError(path)
    if step_s <= 0:
        raise ValueError("Simulation step size must be greater than zero")

    argv = [str(path), *(script_args or [])]
    script_sys_path = [str(script_dir), *sys.path]
    globals_after_run: dict[str, Any]
    local_module_names = _discover_script_local_module_names(script_dir)
    saved_local_modules = {
        name: module
        for name, module in sys.modules.items()
        if _is_local_module_name(name, local_module_names)
    }

    def clear_local_modules() -> None:
        for module_name in list(sys.modules):
            if _is_local_module_name(module_name, local_module_names):
                sys.modules.pop(module_name, None)

    if mode == "real":
        try:
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(sys, "path", script_sys_path),
            ):
                clear_local_modules()
                globals_after_run = runpy.run_path(str(path), run_name="__main__")
            return {"globals": globals_after_run, "runtime": None}
        finally:
            clear_local_modules()
            for module_name, module in saved_local_modules.items():
                sys.modules[module_name] = module

    if mode != "sim":
        raise ValueError(f"Unsupported mode: {mode}")

    original_time = _time.time
    original_monotonic = _time.monotonic
    original_sleep = _time.sleep

    clock = (
        SystemClock(original_time, original_monotonic, original_sleep)
        if realtime
        else ManualClock()
    )
    runtime = SimulationRuntime(
        clock=clock,
        options=RuntimeOptions(step_s=step_s, show=show, hold=hold),
        motion_model=RailsMotionModel(MotionProfile()),
    )
    sim_module, tello_submodule = _make_sim_module()

    global _ACTIVE_RUNTIME
    previous_runtime = _ACTIVE_RUNTIME
    _ACTIVE_RUNTIME = runtime

    previous_main_module = sys.modules.get("djitellopy")
    previous_tello_module = sys.modules.get("djitellopy.tello")

    try:
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, "argv", argv))
            stack.enter_context(mock.patch.object(sys, "path", script_sys_path))
            stack.enter_context(mock.patch("time.sleep", runtime.sleep))
            stack.enter_context(mock.patch("time.time", runtime.time))
            stack.enter_context(mock.patch("time.monotonic", runtime.monotonic))
            clear_local_modules()
            sys.modules["djitellopy"] = sim_module
            sys.modules["djitellopy.tello"] = tello_submodule
            globals_after_run = runpy.run_path(str(path), run_name="__main__")
        if show and hold:
            runtime.hold()
        return {"globals": globals_after_run, "runtime": runtime}
    finally:
        clear_local_modules()
        for module_name, module in saved_local_modules.items():
            sys.modules[module_name] = module
        _ACTIVE_RUNTIME = previous_runtime
        if previous_main_module is None:
            sys.modules.pop("djitellopy", None)
        else:
            sys.modules["djitellopy"] = previous_main_module
        if previous_tello_module is None:
            sys.modules.pop("djitellopy.tello", None)
        else:
            sys.modules["djitellopy.tello"] = previous_tello_module
        runtime.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tello-demo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a Tello script")
    run_parser.add_argument("script", help="Path to the user script")
    run_parser.add_argument("--mode", choices=("real", "sim"), default="sim")
    run_parser.add_argument(
        "--step", type=float, default=0.05, help="Simulation step size in seconds"
    )
    run_parser.add_argument(
        "--no-show", action="store_true", help="Disable the live simulation window"
    )
    run_parser.add_argument(
        "--hold", action="store_true", help="Hold the final simulation frame open"
    )
    run_parser.add_argument(
        "--fast", action="store_true", help="Disable real-time delays in sim mode"
    )
    run_parser.add_argument("script_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "run":
        parser.error(f"Unsupported command: {args.command}")

    passthrough_args = args.script_args
    if passthrough_args and passthrough_args[0] == "--":
        passthrough_args = passthrough_args[1:]

    run_script(
        args.script,
        mode=args.mode,
        show=not args.no_show,
        hold=args.hold,
        realtime=not args.fast,
        step_s=args.step,
        script_args=passthrough_args,
    )
    return 0
