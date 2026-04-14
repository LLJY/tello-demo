"""Lesson 6: functions let us name and reuse code."""


def greet(name: str) -> None:
    print(f"Hello, {name}!")


def repeat_command(command: str, times: int) -> None:
    for step in range(1, times + 1):
        print(f"{step}. {command}")


greet("Ada")
print()
repeat_command("Move forward", 3)

# Try next:
# - Call greet() with your own name.
# - Change the command text.
# - Change the repeat count.
