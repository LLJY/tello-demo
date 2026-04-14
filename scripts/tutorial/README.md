# Beginner Python tutorial track

Suggested order for a single beginner day before introducing the Tello library:

1. `00_hello_world.py`
   - running a Python file
   - `print()`
   - strings
2. `02_variables.py`
   - variables
   - numbers, strings, booleans
   - f-strings
3. `03_conditionals.py`
   - `if`, `elif`, `else`
   - comparing values
4. `04_loops.py`
   - `for`
   - `while`
   - repetition and counting
5. `05_imports_and_sleep.py`
   - `import`
   - standard library modules
   - `time.sleep()`
   - using a loop with a visible delay
6. `06_functions.py`
   - defining functions
   - parameters
   - reusing logic
7. `07_lists.py`
   - lists
   - indexing
   - iterating through data
8. `08_mini_mission.py`
   - combines variables, loops, functions, and lists
   - acts as a bridge to drone-style command thinking without using `djitellopy`

## Suggested teaching flow

- Keep each file bite-sized and runnable.
- Edit the code live with students.
- After each file, ask them to change one thing and rerun it.
- Only introduce the Tello library once they are comfortable with:
  - changing values
  - reading simple `if` statements
  - reading a `for` loop
  - reading a function call

## Good student exercises

- change printed text
- change a sleep delay and feel the difference
- change a number and predict the output first
- add one more loop iteration
- write one new function
- add one more mission step
