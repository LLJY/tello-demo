from __future__ import annotations

from dataclasses import asdict, dataclass, replace


def normalize_angle(angle_deg: float) -> float:
    wrapped = (angle_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0 and angle_deg > 0:
        return 180.0
    return wrapped


@dataclass(slots=True)
class DroneState:
    x_cm: float = 0.0
    y_cm: float = 0.0
    z_cm: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    speed_x_cm_s: float = 0.0
    speed_y_cm_s: float = 0.0
    speed_z_cm_s: float = 0.0
    yaw_rate_deg_s: float = 0.0
    battery_percent: float = 100.0
    configured_speed_cm_s: float = 30.0
    flight_time_s: float = 0.0
    connected: bool = False
    flying: bool = False
    stream_on: bool = False
    current_command: str = "idle"

    def copy(self) -> "DroneState":
        return replace(self)

    def as_state_packet(self) -> dict[str, int | float | str]:
        return {
            "mid": -1,
            "x": 0,
            "y": 0,
            "z": int(round(self.z_cm)),
            "pitch": int(round(self.pitch_deg)),
            "roll": int(round(self.roll_deg)),
            "yaw": int(round(self.yaw_deg)),
            "vgx": int(round(self.speed_x_cm_s)),
            "vgy": int(round(self.speed_y_cm_s)),
            "vgz": int(round(self.speed_z_cm_s)),
            "templ": 65,
            "temph": 67,
            "tof": int(round(max(self.z_cm, 0.0))),
            "h": int(round(self.z_cm)),
            "bat": int(self.battery_percent),
            "baro": round(self.z_cm / 100.0, 2),
            "time": int(round(self.flight_time_s)),
            "agx": 0.0,
            "agy": 0.0,
            "agz": 0.0,
            "command": self.current_command,
        }

    def as_debug_dict(self) -> dict[str, int | float | bool | str]:
        data = asdict(self)
        data["yaw_deg"] = normalize_angle(self.yaw_deg)
        return data
