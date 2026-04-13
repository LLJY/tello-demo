from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tello_demo.studio.models import ScriptKind


@dataclass(frozen=True, slots=True)
class ScriptClassification:
    kind: ScriptKind
    has_djitellopy_import: bool
    has_tello_constructor: bool
    syntax_error: SyntaxError | None = None


@dataclass(slots=True)
class _ClassifierState:
    has_djitellopy_import: bool = False
    has_tello_constructor: bool = False
    direct_tello_names: set[str] = field(default_factory=set)
    tello_attribute_paths: set[str] = field(default_factory=set)


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


class _ClassifierVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.state = _ClassifierState()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "djitellopy":
                self.state.has_djitellopy_import = True
                self.state.tello_attribute_paths.add(
                    f"{alias.asname or 'djitellopy'}.Tello"
                )
            elif alias.name == "djitellopy.tello":
                self.state.has_djitellopy_import = True
                bound_name = alias.asname or alias.name
                self.state.tello_attribute_paths.add(f"{bound_name}.Tello")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level != 0 or node.module not in {"djitellopy", "djitellopy.tello"}:
            self.generic_visit(node)
            return

        self.state.has_djitellopy_import = True
        for alias in node.names:
            if alias.name == "Tello":
                self.state.direct_tello_names.add(alias.asname or alias.name)
            elif node.module == "djitellopy" and alias.name == "tello":
                self.state.tello_attribute_paths.add(
                    f"{alias.asname or alias.name}.Tello"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        if dotted is not None:
            if dotted in self.state.direct_tello_names:
                self.state.has_tello_constructor = True
            elif dotted in self.state.tello_attribute_paths:
                self.state.has_tello_constructor = True
        self.generic_visit(node)


def classify_source(source: str, *, filename: str = "<string>") -> ScriptClassification:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return ScriptClassification(
            kind=ScriptKind.PYTHON,
            has_djitellopy_import=False,
            has_tello_constructor=False,
            syntax_error=exc,
        )

    visitor = _ClassifierVisitor()
    visitor.visit(tree)
    kind = (
        ScriptKind.TELLO
        if visitor.state.has_djitellopy_import and visitor.state.has_tello_constructor
        else ScriptKind.PYTHON
    )
    return ScriptClassification(
        kind=kind,
        has_djitellopy_import=visitor.state.has_djitellopy_import,
        has_tello_constructor=visitor.state.has_tello_constructor,
    )


def classify_script(path: str | Path) -> ScriptClassification:
    script_path = Path(path)
    return classify_source(
        script_path.read_text(encoding="utf-8", errors="replace"),
        filename=str(script_path),
    )
