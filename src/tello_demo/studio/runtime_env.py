from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tello_demo.studio.workspace import StudioWorkspace, ensure_workspace_dirs

_READY_MARKER = ".studio_runtime_ready"


@dataclass(frozen=True, slots=True)
class RuntimeEnv:
    workspace: StudioWorkspace
    project_root: Path
    python_executable: Path


def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("Could not locate project root from studio package")


def get_venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _ready_marker_path(venv_dir: Path) -> Path:
    return venv_dir / _READY_MARKER


def build_runtime_marker(project_root: Path) -> str:
    pyproject_path = project_root / "pyproject.toml"
    pyproject_hash = hashlib.sha256(pyproject_path.read_bytes()).hexdigest()
    payload = {
        "project_root": str(project_root),
        "python": current_python_version(),
        "pyproject_sha256": pyproject_hash,
    }
    return json.dumps(payload, sort_keys=True)


def current_python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def read_runtime_marker(ready_marker: Path) -> dict[str, str] | None:
    if not ready_marker.exists():
        return None
    try:
        marker = json.loads(ready_marker.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return marker if isinstance(marker, dict) else None


def runtime_env_is_current(runtime_env: RuntimeEnv) -> bool:
    ready_marker = _ready_marker_path(runtime_env.workspace.venv_dir)
    if not ready_marker.exists():
        return False
    return ready_marker.read_text(encoding="utf-8") == build_runtime_marker(
        runtime_env.project_root
    )


def install_project(
    python_executable: Path,
    *,
    project_root: Path,
    progress: Callable[[str], None] | None = None,
) -> None:
    if progress is not None:
        progress("Installing tello-demo into the studio runtime...")

    result = subprocess.run(
        [
            str(python_executable),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            str(project_root),
        ],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        output = result.stdout.strip()
        message = "Studio runtime installation failed"
        if output:
            message = f"{message}\n\n{output}"
        raise RuntimeError(message)


def ensure_runtime_env(
    workspace: StudioWorkspace,
    *,
    project_root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> RuntimeEnv:
    ensure_workspace_dirs(workspace)
    resolved_project_root = (project_root or get_project_root()).resolve()
    ready_marker = _ready_marker_path(workspace.venv_dir)

    python_executable = get_venv_python(workspace.venv_dir)
    if not python_executable.exists():
        if progress is not None:
            progress("Creating studio virtual environment...")
        venv.EnvBuilder(with_pip=True).create(str(workspace.venv_dir))

    python_executable = get_venv_python(workspace.venv_dir)
    if not python_executable.exists():
        raise RuntimeError(
            "Studio virtual environment is missing its Python executable"
        )

    expected_marker = build_runtime_marker(resolved_project_root)
    marker_contents = (
        ready_marker.read_text(encoding="utf-8") if ready_marker.exists() else None
    )
    marker = read_runtime_marker(ready_marker)
    marker_python = marker.get("python") if marker is not None else None
    if marker_python not in {None, current_python_version()}:
        if progress is not None:
            progress("Upgrading studio virtual environment for the current Python...")
        venv.EnvBuilder(with_pip=True, upgrade=True).create(str(workspace.venv_dir))
        python_executable = get_venv_python(workspace.venv_dir)
        if not python_executable.exists():
            raise RuntimeError(
                "Studio virtual environment upgrade did not produce a Python executable"
            )
        marker_contents = (
            ready_marker.read_text(encoding="utf-8") if ready_marker.exists() else None
        )
    if marker_contents != expected_marker:
        install_project(
            python_executable,
            project_root=resolved_project_root,
            progress=progress,
        )
        ready_marker.write_text(expected_marker, encoding="utf-8")

    if progress is not None:
        progress("Studio runtime ready.")

    return RuntimeEnv(
        workspace=workspace,
        project_root=resolved_project_root,
        python_executable=python_executable,
    )
