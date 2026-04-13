from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from tello_demo.sim.render.geometry import DroneGeometry, default_drone_geometry
from tello_demo.sim.state import DroneState


def _matmul(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]
) -> list[list[float]]:
    return [
        [
            sum(a[row][idx] * b[idx][col] for idx in range(len(b)))
            for col in range(len(b[0]))
        ]
        for row in range(len(a))
    ]


def _rotate(
    point: tuple[float, float, float],
    *,
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
) -> tuple[float, float, float]:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)

    rz = [
        [math.cos(yaw), -math.sin(yaw), 0.0],
        [math.sin(yaw), math.cos(yaw), 0.0],
        [0.0, 0.0, 1.0],
    ]
    ry = [
        [math.cos(pitch), 0.0, math.sin(pitch)],
        [0.0, 1.0, 0.0],
        [-math.sin(pitch), 0.0, math.cos(pitch)],
    ]
    rx = [
        [1.0, 0.0, 0.0],
        [0.0, math.cos(roll), -math.sin(roll)],
        [0.0, math.sin(roll), math.cos(roll)],
    ]
    rotation = _matmul(rz, _matmul(ry, rx))
    x_cm, y_cm, z_cm = point
    return (
        rotation[0][0] * x_cm + rotation[0][1] * y_cm + rotation[0][2] * z_cm,
        rotation[1][0] * x_cm + rotation[1][1] * y_cm + rotation[1][2] * z_cm,
        rotation[2][0] * x_cm + rotation[2][1] * y_cm + rotation[2][2] * z_cm,
    )


@dataclass
class Matplotlib3DRenderer:
    geometry: DroneGeometry = field(default_factory=default_drone_geometry)
    margin_cm: float = 50.0

    def __post_init__(self) -> None:
        import matplotlib.pyplot as plt

        self._plt = plt
        self._plt.ion()
        self._figure = self._plt.figure("Tello Simulation")
        self._axes = self._figure.add_subplot(projection="3d")
        self._axes.set_xlabel("X (cm)")
        self._axes.set_ylabel("Y (cm)")
        self._axes.set_zlabel("Z (cm)")
        self._axes.set_title("DJI Tello simulation", pad=18)

        (self._trail_artist,) = self._axes.plot(
            [], [], [], color="tab:blue", linewidth=1.5
        )
        self._body_artists = [
            self._axes.plot([], [], [], color="tab:orange", linewidth=1.2)[0]
            for _ in self.geometry.edges
        ]
        (self._nose_artist,) = self._axes.plot(
            [], [], [], color="tab:red", linewidth=2.0
        )
        self._status_artist = self._axes.text2D(
            0.02,
            0.92,
            "",
            transform=self._axes.transAxes,
            va="top",
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.8},
        )
        self._figure.tight_layout()

    def render(self, state: DroneState, history: Sequence[DroneState]) -> None:
        xs = [sample.x_cm for sample in history]
        ys = [sample.y_cm for sample in history]
        zs = [sample.z_cm for sample in history]
        self._trail_artist.set_data(xs, ys)
        self._trail_artist.set_3d_properties(zs)

        transformed = [
            _rotate(
                vertex,
                yaw_deg=state.yaw_deg,
                pitch_deg=state.pitch_deg,
                roll_deg=state.roll_deg,
            )
            for vertex in self.geometry.vertices
        ]
        translated = [
            (state.x_cm + x_cm, state.y_cm + y_cm, state.z_cm + z_cm)
            for x_cm, y_cm, z_cm in transformed
        ]

        for artist, edge in zip(self._body_artists, self.geometry.edges, strict=True):
            start = translated[edge[0]]
            end = translated[edge[1]]
            artist.set_data([start[0], end[0]], [start[1], end[1]])
            artist.set_3d_properties([start[2], end[2]])

        nose_point = _rotate(
            self.geometry.nose,
            yaw_deg=state.yaw_deg,
            pitch_deg=state.pitch_deg,
            roll_deg=state.roll_deg,
        )
        self._nose_artist.set_data(
            [state.x_cm, state.x_cm + nose_point[0]],
            [state.y_cm, state.y_cm + nose_point[1]],
        )
        self._nose_artist.set_3d_properties([state.z_cm, state.z_cm + nose_point[2]])

        self._status_artist.set_text(
            f"command={state.current_command}\n"
            f"xyz=({state.x_cm:.1f}, {state.y_cm:.1f}, {state.z_cm:.1f}) cm\n"
            f"yaw={state.yaw_deg:.1f}° pitch={state.pitch_deg:.1f}° roll={state.roll_deg:.1f}°"
        )

        all_x = xs + [state.x_cm]
        all_y = ys + [state.y_cm]
        all_z = zs + [state.z_cm, 0.0]
        min_x, max_x = min(all_x, default=-100.0), max(all_x, default=100.0)
        min_y, max_y = min(all_y, default=-100.0), max(all_y, default=100.0)
        min_z, max_z = min(all_z, default=0.0), max(all_z, default=100.0)
        span = max(max_x - min_x, max_y - min_y, max_z - min_z, 100.0)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        cz = (min_z + max_z) / 2.0
        half = span / 2.0 + self.margin_cm

        self._axes.set_xlim(cx - half, cx + half)
        self._axes.set_ylim(cy - half, cy + half)
        self._axes.set_zlim(max(0.0, cz - half), cz + half)

        self._figure.canvas.draw_idle()
        self._figure.canvas.flush_events()

    def hold(self) -> None:
        self._plt.ioff()
        self._plt.show()

    def close(self) -> None:
        self._plt.close(self._figure)
