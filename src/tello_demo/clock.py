from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class Clock(Protocol):
    def time(self) -> float: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass(slots=True)
class SystemClock:
    time_fn: Callable[[], float]
    monotonic_fn: Callable[[], float]
    sleep_fn: Callable[[float], None]

    def time(self) -> float:
        return self.time_fn()

    def monotonic(self) -> float:
        return self.monotonic_fn()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleep_fn(seconds)


@dataclass(slots=True)
class ManualClock:
    now_s: float = 0.0

    def time(self) -> float:
        return self.now_s

    def monotonic(self) -> float:
        return self.now_s

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.now_s += seconds
