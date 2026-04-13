from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StudioWorkspace:
    root: Path
    scripts_dir: Path
    venv_dir: Path
    logs_dir: Path


def default_workspace_root() -> Path:
    try:
        home = Path.home()
    except RuntimeError:
        return Path(".tello-demo/studio").resolve()
    return home / ".tello-demo" / "studio"


def resolve_workspace(root: Path | None = None) -> StudioWorkspace:
    workspace_root = (root or default_workspace_root()).expanduser().resolve()
    return StudioWorkspace(
        root=workspace_root,
        scripts_dir=workspace_root / "scripts",
        venv_dir=workspace_root / "venv",
        logs_dir=workspace_root / "logs",
    )


def ensure_workspace_dirs(workspace: StudioWorkspace) -> None:
    for path in (workspace.root, workspace.scripts_dir, workspace.logs_dir):
        path.mkdir(parents=True, exist_ok=True)


def list_scripts(workspace: StudioWorkspace) -> list[Path]:
    if not workspace.scripts_dir.exists():
        return []

    scripts: list[Path] = []
    for path in workspace.scripts_dir.rglob("*.py"):
        relative_parts = path.relative_to(workspace.scripts_dir).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if "__pycache__" in relative_parts or path.name == "__init__.py":
            continue
        scripts.append(path)

    return sorted(
        scripts,
        key=lambda path: str(path.relative_to(workspace.scripts_dir)).casefold(),
    )


def open_in_file_manager(path: Path) -> None:
    target = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
        return
    subprocess.Popen(["xdg-open", str(target)])
