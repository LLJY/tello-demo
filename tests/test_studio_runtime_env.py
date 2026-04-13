from __future__ import annotations

import json
from pathlib import Path

from tello_demo.studio import runtime_env
from tello_demo.studio.workspace import resolve_workspace


def test_runtime_env_reinstalls_when_marker_points_to_other_project(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = resolve_workspace(tmp_path / "workspace")
    workspace.venv_dir.mkdir(parents=True)
    python_executable = runtime_env.get_venv_python(workspace.venv_dir)
    python_executable.parent.mkdir(parents=True, exist_ok=True)
    python_executable.write_text("", encoding="utf-8")
    ready_marker = workspace.venv_dir / ".studio_runtime_ready"
    ready_marker.write_text("/old/project", encoding="utf-8")

    installed_roots: list[Path] = []

    def fake_install_project(
        python_executable: Path,
        *,
        project_root: Path,
        progress=None,
    ) -> None:
        del python_executable, progress
        installed_roots.append(project_root)

    monkeypatch.setattr(runtime_env, "install_project", fake_install_project)

    project_root = tmp_path / "new-project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname='demo'\n", encoding="utf-8"
    )

    runtime = runtime_env.ensure_runtime_env(workspace, project_root=project_root)

    assert installed_roots == [project_root.resolve()]
    assert ready_marker.read_text(encoding="utf-8") == runtime_env.build_runtime_marker(
        project_root.resolve()
    )
    assert runtime.project_root == project_root.resolve()
    assert runtime_env.runtime_env_is_current(runtime) is True


def test_runtime_env_upgrades_when_marker_python_version_differs(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = resolve_workspace(tmp_path / "workspace")
    workspace.venv_dir.mkdir(parents=True)
    python_executable = runtime_env.get_venv_python(workspace.venv_dir)
    python_executable.parent.mkdir(parents=True, exist_ok=True)
    python_executable.write_text("", encoding="utf-8")
    ready_marker = workspace.venv_dir / ".studio_runtime_ready"

    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\nname='demo'\n", encoding="utf-8"
    )
    ready_marker.write_text(
        json.dumps(
            {
                "project_root": str(project_root.resolve()),
                "python": "0.0",
                "pyproject_sha256": "stale",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    builder_calls: list[bool] = []
    installed_roots: list[Path] = []

    class FakeEnvBuilder:
        def __init__(self, *, with_pip: bool, upgrade: bool = False) -> None:
            assert with_pip is True
            builder_calls.append(upgrade)

        def create(self, env_dir: str) -> None:
            del env_dir
            python_executable.write_text("", encoding="utf-8")

    def fake_install_project(
        python_executable: Path,
        *,
        project_root: Path,
        progress=None,
    ) -> None:
        del python_executable, progress
        installed_roots.append(project_root)

    monkeypatch.setattr(runtime_env.venv, "EnvBuilder", FakeEnvBuilder)
    monkeypatch.setattr(runtime_env, "install_project", fake_install_project)

    runtime = runtime_env.ensure_runtime_env(workspace, project_root=project_root)

    assert builder_calls == [True]
    assert installed_roots == [project_root.resolve()]
    assert ready_marker.read_text(encoding="utf-8") == runtime_env.build_runtime_marker(
        project_root.resolve()
    )
    assert runtime_env.runtime_env_is_current(runtime) is True
