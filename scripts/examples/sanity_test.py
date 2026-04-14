from __future__ import annotations

from djitellopy import Tello


def main() -> None:
    tello = Tello()
    tello.connect()
    print(f"Battery: {tello.get_battery()}%")

    tello.takeoff()
    tello.move_up(30)
    tello.move_forward(50)
    tello.rotate_clockwise(90)
    tello.move_forward(50)
    tello.land()
    tello.end()


if __name__ == "__main__":
    main()
