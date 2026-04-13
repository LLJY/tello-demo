# Technical design

## Document status

- Current shipped system: implemented
- Studio launcher app: implemented MVP

## 1. Current shipped system

### Goal

Run one user Tello script in two modes:

- `real`: actual `djitellopy.Tello`
- `sim`: simulated `Tello` with real-time 3D visualization

The simulation stays on-rails but is structured so both the motion model and visual model can be upgraded later.

### Architecture

#### Runner

`tello_demo.runner` executes the user script with `runpy.run_path`.

- real mode: runs the script normally
- sim mode:
  - injects a `djitellopy` shim into `sys.modules`
  - patches `time.sleep`, `time.time`, and `time.monotonic`
  - creates a `SimulationRuntime`

This keeps user scripts unchanged.

#### Runtime

`SimulationRuntime` is the authoritative sim clock/stepper.

It owns:

- active drones
- step size
- clock integration
- renderer updates

#### Simulated Tello

`SimTello` implements the focused `djitellopy` subset and translates API calls into:

- blocking motion plans
- latched RC control
- state/telemetry reads

#### Motion model seam

`MotionModel` plans continuous motion from discrete commands.

Current implementation:

- `RailsMotionModel`
- eased kinematic interpolation
- flip animation profiles
- RC integration

Future replacement:

- more accurate measured motion model
- recorded trajectory model
- hardware-derived model

#### Visual model seam

`DroneGeometry` defines the rendered body shape separately from the renderer.

Current implementation:

- simple wireframe body
- heading marker
- trail

Future replacement:

- actual Tello mesh/model
- richer camera/annotations

### Critical chain

1. runner + patched imports/time
2. runtime stepping
3. `SimTello` command surface
4. motion model
5. renderer
6. tests

## 2. Proposed studio launcher MVP

### Goal

Provide a single easy entrypoint that stays open in the background and lets users run either:

- regular Python scripts, with normal console output
- Tello scripts, with automatic simulation by default and explicit real-drone mode behind a gate

The user edits scripts in their own editor. The app only lists and runs them.

### Product constraints from current discussion

- no PyInstaller requirement
- no drag-and-drop requirement in the MVP
- fixed scripts folder instead of arbitrary dropped files
- same managed runtime environment for all launched scripts
- if a script does **not** look like a Tello script, it runs as normal Python
- if a script **does** look like a Tello script, default run behavior should route it through the Tello runner in sim mode
- real mode must be intentionally gated behind a daily UTC-derived PIN

### Non-goals for MVP

- built-in code editor
- embedded Matplotlib simulator inside the launcher window
- system tray integration
- standalone packaged executable
- full static analysis of arbitrary Python metaprogramming
- replacing the existing CLI runner

## 3. Proposed user experience

### Launch

The user starts the app with one command:

```bash
python -m tello_demo.studio
```

or, after installation:

```bash
tello-studio
```

### Script workflow

1. User opens the launcher.
2. The launcher shows a fixed scripts folder.
3. The user edits or adds `.py` files in that folder using any editor.
4. The launcher refreshes or rescans the folder.
5. The user selects one script and presses Run.
6. Behavior depends on script classification:
   - non-Tello script: run directly as normal Python
   - Tello script: run through `tello_demo.runner` in `sim` mode
7. If the user explicitly wants real flight, they unlock real mode and use `Run Real`.

### Example outcomes

- `print("hello world")` → console shows `hello world`
- `djitellopy` script with `Tello()` creation → simulator window opens and the script output still appears in the launcher console

## 4. Proposed filesystem layout

This path should remain configurable later, but the MVP should start with a single default location.

### Proposed default root

`~/.tello-demo/studio/`

### Proposed layout

- `scripts/` — user-managed Python scripts
- `venv/` — managed virtual environment for the launcher runtime
- `logs/` — run logs if persistent logging is added
- `config.json` — optional later; not required for first MVP

### Rationale

- keeps user scripts separate from the repository
- avoids drag/drop complexity
- gives a stable place for teachers/students to copy files
- allows the launcher to remain open while files change outside the app

## 5. Runtime environment design

### Managed venv

The launcher should manage its own virtual environment using stdlib `venv`.

Verified behavior from Python's `venv` docs:

- a venv can be created with `python -m venv <path>`
- activation is optional
- scripts can be run by invoking the venv's Python interpreter directly

### MVP behavior

On startup, the launcher should:

1. check whether the managed venv exists
2. create it if missing
3. install this project into that venv
4. run all child scripts using that venv's Python executable

### Why this is preferred

- single command for users
- no manual activation step
- consistent interpreter and dependency set
- easy to recreate if broken

## 6. Script classification

### Rule

A script is classified as a Tello script only if **both** are true:

1. it imports `djitellopy`
2. it creates a `Tello()` object

Otherwise it is treated as a regular Python script.

### Detection method

Use `ast` only. Do not import the user script during classification.

### Patterns to detect

- `import djitellopy`
- `from djitellopy import Tello`
- `from djitellopy.tello import Tello`
- `Tello()`
- `djitellopy.Tello()`

### Intentional limitation

This will not catch every possible dynamic pattern. That is acceptable for MVP.

The classifier should be conservative and explainable, not clever.

### Failure behavior

- classification failure or unknown pattern should fall back to regular Python execution
- syntax errors during parsing should not crash the launcher; they should result in non-Tello classification and the actual run can then fail normally with a Python error

## 7. Script execution model

### Core rule

Every selected script runs in a child process. The launcher process never executes user code in-process.

### Why

- protects the launcher UI from crashes
- makes stdout/stderr capture straightforward
- allows Stop to terminate the child process
- avoids Tkinter and Matplotlib event-loop conflicts in the same process

### Command mapping

#### Non-Tello script

```text
<venv-python> <script-path>
```

#### Tello script, default run

```text
<venv-python> -m tello_demo.runner run <script-path> --mode sim
```

#### Tello script, real mode

```text
<venv-python> -m tello_demo.runner run <script-path> --mode real
```

### Working directory

The child process should run with the selected script's parent directory as `cwd`.

That preserves simple sibling-import behavior for ordinary scripts and aligns with the runner's existing `sys.path` handling.

### Output handling

The launcher should:

- capture stdout and stderr
- stream them into an in-app console
- keep the process exit code visible
- allow the user to stop the running process

## 8. Real mode gate

### Purpose

The gate is a deliberate friction point before real drone use, not a serious security boundary.

### Required behavior

- `Run Real` is disabled until the user unlocks the session
- unlock applies only to the current launcher session
- the PIN is derived from the UTC date using a deterministic hash-based rule

### Important implementation constraint

Python's built-in `hash()` must **not** be used for this, because it is intentionally randomized between interpreter runs and is therefore not stable enough for a deterministic daily PIN.

### Design seam

Create a separate `RealModeGate` policy object so the gate logic can be changed later without affecting UI or script execution.

### Implemented PIN formula

The real-mode gate now derives a deterministic 6-digit PIN from:

- UTC date formatted as `ddMMyyyy`
- fixed pepper string: `tello-demo-real-v1`
- keyed `hashlib.blake2s`
- modulo `1_000_000`, zero-padded to 6 digits

This is intentionally just a friction gate, not a serious security boundary.

## 9. GUI architecture

### Toolkit

Use stdlib `tkinter` + `ttk`.

Verified from the current Python docs:

- Tkinter is the standard Python interface to Tcl/Tk
- it is available on Windows and macOS and on most Unix installs
- it is still optional on some Linux distributions, so documentation should mention that some users may need the OS Tk package

### MVP layout

- top: scripts folder path + open folder action
- left: script list
- right: output console
- bottom: Run, Run Real, Stop, Refresh, status text

### Recommended controls

- `Refresh`
- `Open Scripts Folder`
- `Run`
- `Run Real`
- `Stop`
- output pane
- status indicator (`env ready`, `running`, `last exit code`, `real unlocked`)

### Why not embed Matplotlib yet

The current simulator already works as a separate window.

Keeping the simulator window separate in MVP:

- reduces GUI complexity
- avoids Tkinter/Matplotlib embedding work too early
- keeps the launcher focused on script selection, process control, and output

## 10. Proposed module structure

New modules should be added under `src/tello_demo/studio/`.

### Proposed modules

- `studio/__init__.py`
- `studio/__main__.py`
- `studio/app.py` — Tkinter UI entrypoint
- `studio/workspace.py` — scripts folder and path discovery
- `studio/runtime_env.py` — managed venv creation and interpreter lookup
- `studio/classifier.py` — AST-based Tello classification
- `studio/process_runner.py` — subprocess lifecycle and output streaming
- `studio/real_mode_gate.py` — session unlock and daily PIN policy
- `studio/models.py` — small shared dataclasses if needed

### Current launcher entrypoint

The implemented studio launcher currently runs via:

- `python -m tello_demo.studio`

The current `tello-demo` runner entrypoint remains unchanged.

### Possible later convenience entrypoint

If desired later, a dedicated script entrypoint can be added:

- `tello-studio = "tello_demo.studio.app:main"`

## 11. Concurrency model

### GUI thread

Tkinter should remain on the main thread.

### Background work

Use a worker thread only for:

- reading child-process output
- environment bootstrapping progress

UI updates should be marshaled back onto the Tkinter thread.

### Child processes

Only one user script should run at a time in MVP.

That keeps process management simple and avoids overlapping simulator runs.

## 12. Failure handling

### Environment failures

- if venv creation or install fails, the launcher stays open and shows the error
- no partial UI success should be mistaken for a runnable environment

### Script failures

- syntax errors, exceptions, and non-zero exit codes are shown in the console
- launcher stays alive

### Classification mismatches

- false negatives are acceptable in MVP
- false positives should be minimized by requiring both `djitellopy` import and `Tello()` creation

## 13. Dependencies

### MVP should not add new third-party dependencies

The launcher can be built with:

- existing project dependencies
- stdlib `tkinter`
- stdlib `venv`
- stdlib `subprocess`
- stdlib `ast`
- stdlib `threading` / `queue`

That keeps installation simpler and matches the goal of a lightweight launcher.

## 14. Implementation critical chain

1. `runtime_env.py`
2. `process_runner.py`
3. `classifier.py`
4. `real_mode_gate.py`
5. `app.py` UI shell
6. tests and user docs

## 15. Verification plan for the studio MVP

### Automated

- classifier unit tests for supported import and constructor patterns
- runtime env tests for interpreter path resolution
- process-runner tests with temporary hello-world scripts
- gate tests for deterministic daily PIN derivation once the formula is finalized

### Manual smoke checks

- launcher opens and creates its managed venv
- selecting a plain script shows normal stdout
- selecting a Tello script launches sim mode through the existing runner
- `Run Real` stays locked until the session gate is satisfied
- Stop terminates a long-running child process

## 16. Scope discipline

The existing simulated command subset remains intentionally limited to commands useful for beginner drone programming.

The studio launcher does not expand the simulation surface by itself. It is a usability layer around the current runner and simulator.
