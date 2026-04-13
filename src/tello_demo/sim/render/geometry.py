from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DroneGeometry:
    vertices: tuple[tuple[float, float, float], ...]
    edges: tuple[tuple[int, int], ...]
    nose: tuple[float, float, float]


def default_drone_geometry(
    *,
    half_length_cm: float = 10.0,
    half_width_cm: float = 10.0,
    half_height_cm: float = 2.0,
) -> DroneGeometry:
    vertices = (
        (-half_length_cm, -half_width_cm, -half_height_cm),
        (-half_length_cm, half_width_cm, -half_height_cm),
        (half_length_cm, half_width_cm, -half_height_cm),
        (half_length_cm, -half_width_cm, -half_height_cm),
        (-half_length_cm, -half_width_cm, half_height_cm),
        (-half_length_cm, half_width_cm, half_height_cm),
        (half_length_cm, half_width_cm, half_height_cm),
        (half_length_cm, -half_width_cm, half_height_cm),
    )
    edges = (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    )
    nose = (half_length_cm * 1.4, 0.0, 0.0)
    return DroneGeometry(vertices=vertices, edges=edges, nose=nose)
