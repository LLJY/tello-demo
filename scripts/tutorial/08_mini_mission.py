"""Lesson 8: combine the basics into a tiny mission script.

This does not control a real drone.
It only prints a mission plan, which makes it a good bridge to the real Tello API.
"""

mission_name = "Square Test"
speed_cm_s = 30
commands = [
    "takeoff",
    "forward 50",
    "rotate clockwise 90",
    "forward 50",
    "land",
]


def print_header(name: str, speed: int) -> None:
    print(f"Mission: {name}")
    print(f"Speed: {speed} cm/s")
    print("Starting mission...")


def run_mission(command_list: list[str]) -> None:
    for index, command in enumerate(command_list, start=1):
        print(f"{index}. {command}")


print_header(mission_name, speed_cm_s)
run_mission(commands)

# Try next:
# - Change the mission name.
# - Add another command.
# - Turn this into a triangle mission.
