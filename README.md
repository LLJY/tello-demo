# tello-demo

Run the same DJI Tello Python script in two modes:

- `real`: use the actual Tello through `djitellopy`
- `sim`: run a real-time on-rails simulator with live 3D visualization

The main goal is to let people preview how their code will move the drone before flying it for real.

## What this project is

- A small Tello demo project
- A personal real-drone sanity test
- A simulation runner for `djitellopy`-style scripts
- A unit-testable motion engine with swappable motion/visual models

## What this project is not

- A full physics simulator
- A complete `djitellopy` replacement
- A validated flight-dynamics twin of the Tello

The simulator is designed to be:

- exact at the script/API level for a focused subset
- continuous and real-time in visualization
- easy to tune later
- structured so the motion model and visual model can be swapped later

## Verified dependency notes

- `djitellopy==2.5.0` is the latest PyPI release at the time of writing.
- `matplotlib==3.10.8` is the current stable release and supports interactive 3D updates via `draw_idle` and `flush_events`.
- `pytest==9.0.3` is the current stable release used for tests.

## Install

Using `uv`:

```bash
uv sync --extra dev
```

Using `pip`:

```bash
python -m pip install -r requirements.txt
```

For development and tests with `pip`:

```bash
python -m pip install -e ".[dev]"
```

## Usage

### Studio launcher

The project now includes a simple studio launcher for a fixed scripts folder workflow.

Run it with:

```bash
python -m tello_demo.studio
```

The studio launcher:

- uses a fixed workspace under `~/.tello-demo/studio/`
- shows scripts from `~/.tello-demo/studio/scripts/`
- keeps its own managed runtime venv under `~/.tello-demo/studio/venv/`
- runs regular Python scripts normally
- routes detected Tello scripts through the existing simulator by default

Current Tello detection rule:

- the script imports `djitellopy`
- and it creates a `Tello()` object

If both are true, the studio treats it as a Tello script. Otherwise it runs it as normal Python.

Notes:

- the studio opens the existing Matplotlib simulator in a separate window for sim runs
- real mode is gated by a daily UTC PIN inside the app
- on some Linux systems, `tkinter` may need to be installed separately by the OS package manager

### 1. Write a normal Tello script

Example: `examples/sanity_test.py`

```python
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
```

### 2. Run it in sim mode

```bash
uv run tello-demo run examples/sanity_test.py --mode sim
```

Pip-installed equivalent:

```bash
python -m tello_demo run examples/sanity_test.py --mode sim
```

This opens a live 3D view and executes the script in real time.

If you want to keep the final frame open after the script finishes, add `--hold`.

### 3. Run it in real mode

```bash
uv run tello-demo run examples/sanity_test.py --mode real
```

Pip-installed equivalent:

```bash
python -m tello_demo run examples/sanity_test.py --mode real
```

### Minimal real-drone sanity check

If you want the smallest possible Tello test, use:

```bash
uv run tello-demo run examples/takeoff_land.py --mode real
```

Pip-installed equivalent:

```bash
python -m tello_demo run examples/takeoff_land.py --mode real
```

Or preview it first in sim mode:

```bash
uv run tello-demo run examples/takeoff_land.py --mode sim
```

Pip-installed equivalent:

```bash
python -m tello_demo run examples/takeoff_land.py --mode sim
```

## Supported simulated command subset

The simulator intentionally focuses on a subset large enough for intro programming:

- lifecycle: `connect`, `takeoff`, `land`, `end`
- movement: `move_up`, `move_down`, `move_left`, `move_right`, `move_forward`, `move_back`
- rotation: `rotate_clockwise`, `rotate_counter_clockwise`
- maneuvers: `flip_left`, `flip_right`, `flip_forward`, `flip_back`
- path commands: `go_xyz_speed`, `curve_xyz_speed`
- continuous control: `send_rc_control`
- basic telemetry: `get_battery`, `get_height`, `get_yaw`, `get_speed_x`, `get_speed_y`, `get_speed_z`, `get_flight_time`, `get_current_state`
- helpers: `set_speed`, `query_speed`, `query_battery`, `query_height`, `query_flight_time`, `streamon`, `streamoff`

Unsupported APIs fail fast with `TelloException` instead of silently pretending to work.

## Important behavior notes

### `send_rc_control`

This is simulated as a latched continuous control command.

That means this common pattern works in sim mode:

```python
import time
from djitellopy import Tello

tello = Tello()
tello.connect()
tello.takeoff()
tello.send_rc_control(0, 50, 0, 0)
time.sleep(2)
tello.send_rc_control(0, 0, 0, 0)
```

The runner patches `time.sleep` in sim mode so the drone keeps moving while the script sleeps.

### Flips and curves

Flips and `curve_xyz_speed` are continuous kinematic approximations, not validated hardware-accurate flight dynamics.

### Matplotlib backend

Live sim mode needs a GUI-capable Matplotlib backend. Headless backends like `Agg` do not provide a live window.

By default the CLI does not hold the terminal open after the script completes. Use `--hold` only when you explicitly want that blocking behavior.

### Main-thread rendering

Matplotlib interactive rendering should stay on the main thread. This project keeps GUI updates in the same thread as script execution.

## Real drone sanity-test warnings

Use the real mode demo carefully:

- fly in open space
- use a charged battery
- keep the drone in visual line of sight
- keep the first real mission short and simple
- do not test flips indoors unless you know exactly what you are doing

The included `examples/sanity_test.py` avoids flips on purpose.

## Project layout

See `TECHNICAL_DESIGN.md` for the architecture and critical chain.

## Tests

```bash
uv run pytest
```

Pip users can run:

```bash
python -m pytest
```
