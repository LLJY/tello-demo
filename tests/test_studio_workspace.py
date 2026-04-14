from __future__ import annotations

from pathlib import Path

from tello_demo.studio.workspace import (
    ensure_workspace_dirs,
    list_scripts,
    resolve_workspace,
)


def test_resolve_workspace_uses_expected_layout(tmp_path: Path) -> None:
    workspace = resolve_workspace(tmp_path, scripts_dir=tmp_path / "scripts")

    assert workspace.root == tmp_path.resolve()
    assert workspace.scripts_dir.name == "scripts"
    assert workspace.venv_dir == tmp_path.resolve() / "venv"
    assert workspace.logs_dir == tmp_path.resolve() / "logs"


def test_list_scripts_filters_hidden_cache_and_init_files(tmp_path: Path) -> None:
    workspace = resolve_workspace(tmp_path, scripts_dir=tmp_path / "scripts")
    ensure_workspace_dirs(workspace)

    (workspace.scripts_dir / "lesson1.py").write_text("print('hi')\n", encoding="utf-8")
    nested = workspace.scripts_dir / "nested"
    nested.mkdir()
    (nested / "mission.py").write_text("print('mission')\n", encoding="utf-8")
    (nested / "__init__.py").write_text("", encoding="utf-8")
    hidden = workspace.scripts_dir / ".hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text("print('nope')\n", encoding="utf-8")
    pycache = workspace.scripts_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text("print('nope')\n", encoding="utf-8")

    scripts = list_scripts(workspace)

    assert scripts == [workspace.scripts_dir / "lesson1.py", nested / "mission.py"]
