"""DJI Tello real/sim runner."""

from __future__ import annotations

from typing import Any


def run_script(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from tello_demo.runner import run_script as _run_script

    return _run_script(*args, **kwargs)


__all__ = ["run_script"]
