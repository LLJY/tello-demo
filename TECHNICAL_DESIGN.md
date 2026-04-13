# Technical design

## Goal

Run one user Tello script in two modes:

- `real`: actual `djitellopy.Tello`
- `sim`: simulated `Tello` with real-time 3D visualization

The simulation must stay on-rails but be structured so both the motion model and visual model can be upgraded later.

## Architecture

### Runner

`tello_demo.runner` executes the user script with `runpy.run_path`.

- real mode: runs the script normally
- sim mode:
  - injects a `djitellopy` shim into `sys.modules`
  - patches `time.sleep`, `time.time`, and `time.monotonic`
  - creates a `SimulationRuntime`

This keeps user scripts unchanged.

### Runtime

`SimulationRuntime` is the authoritative sim clock/stepper.

It owns:

- active drones
- step size
- clock integration
- renderer updates

### Simulated Tello

`SimTello` implements the focused `djitellopy` subset and translates API calls into:

- blocking motion plans
- latched RC control
- state/telemetry reads

### Motion model seam

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

### Visual model seam

`DroneGeometry` defines the rendered body shape separately from the renderer.

Current implementation:

- simple wireframe body
- heading marker
- trail

Future replacement:

- actual Tello mesh/model
- richer camera/annotations

## Critical chain

1. runner + patched imports/time
2. runtime stepping
3. `SimTello` command surface
4. motion model
5. renderer
6. tests

## Dependency notes

- `djitellopy==2.5.0`
- `matplotlib==3.10.8`
- `pytest==9.0.3`
- `hatchling==1.29.0`

## Scope discipline

The supported command subset is intentionally limited to commands that are useful for beginner drone programming while keeping the visualizer/tester maintainable.
