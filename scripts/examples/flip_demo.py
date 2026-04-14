from __future__ import annotations

from djitellopy import Tello


def main() -> None:
    tello = Tello()
    tello.connect()
    print(f"Battery: {tello.get_battery()}%")

    tello.takeoff()
    tello.flip_forward()
    tello.land()
    tello.end()


if __name__ == "__main__":
    main()
