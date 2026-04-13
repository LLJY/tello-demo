from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from tello_demo.clock import Clock
from tello_demo.sim.motion import MotionProfile, RailsMotionModel
from tello_demo.sim.render import Matplotlib3DRenderer

if TYPE_CHECKING:
    from tello_demo.sim.motion.base import MotionModel
    from tello_demo.sim.tello import SimTello


@dataclass(slots=True)
class RuntimeOptions:
    step_s: float = 0.05
    show: bool = True
    hold: bool = True


class SimulationRuntime:
    def __init__(
        self,
        *,
        clock: Clock,
        options: RuntimeOptions | None = None,
        motion_model: MotionModel | None = None,
    ) -> None:
        self.clock = clock
        self.options = options or RuntimeOptions()
        if self.options.step_s <= 0:
            raise ValueError("Simulation step size must be greater than zero")
        self.motion_model = motion_model or RailsMotionModel(MotionProfile())
        self._renderer = Matplotlib3DRenderer() if self.options.show else None
        self._drones: list[SimTello] = []

    def register(self, drone: "SimTello") -> None:
        self._drones.append(drone)
        self.render()

    @property
    def drones(self) -> Sequence["SimTello"]:
        return tuple(self._drones)

    def time(self) -> float:
        return self.clock.time()

    def monotonic(self) -> float:
        return self.clock.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")
        remaining = max(0.0, seconds)
        while remaining > 1e-9:
            dt_s = min(self.options.step_s, remaining)
            self.clock.sleep(dt_s)
            for drone in self._drones:
                drone.advance(dt_s)
            self.render()
            remaining -= dt_s

    def render(self) -> None:
        if self._renderer is None or not self._drones:
            return
        drone = self._drones[0]
        self._renderer.render(drone.state, drone.history)

    def hold(self) -> None:
        if self._renderer is not None and self.options.hold:
            self._renderer.hold()

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
