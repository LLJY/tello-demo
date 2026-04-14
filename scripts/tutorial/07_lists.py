"""Lesson 7: lists hold many values in one variable."""

commands = ["takeoff", "up 30", "forward 50", "land"]

print("First command:", commands[0])
print("How many commands?", len(commands))

commands.append("done")

print()
print("Mission steps:")
for index, command in enumerate(commands, start=1):
    print(f"{index}. {command}")

# Try next:
# - Add a new command.
# - Change one command.
# - Remove the last item and rerun.
