from __future__ import annotations

from tello_demo.studio.classifier import classify_source
from tello_demo.studio.models import ScriptKind


def test_classifies_direct_tello_script() -> None:
    result = classify_source("from djitellopy import Tello\ndrone = Tello()\n")

    assert result.kind is ScriptKind.TELLO
    assert result.has_djitellopy_import is True
    assert result.has_tello_constructor is True


def test_classifies_module_alias_tello_script() -> None:
    result = classify_source("import djitellopy as dj\ndrone = dj.Tello()\n")

    assert result.kind is ScriptKind.TELLO


def test_classifies_tello_submodule_import_from_package() -> None:
    result = classify_source("from djitellopy import tello\ndrone = tello.Tello()\n")

    assert result.kind is ScriptKind.TELLO


def test_classifies_tello_submodule_alias_import_from_package() -> None:
    result = classify_source("from djitellopy import tello as dj\ndrone = dj.Tello()\n")

    assert result.kind is ScriptKind.TELLO


def test_classifies_import_only_as_regular_python() -> None:
    result = classify_source("import djitellopy\n")

    assert result.kind is ScriptKind.PYTHON
    assert result.has_djitellopy_import is True
    assert result.has_tello_constructor is False


def test_classifies_constructor_only_as_regular_python() -> None:
    result = classify_source("class Tello:\n    pass\nTello()\n")

    assert result.kind is ScriptKind.PYTHON
    assert result.has_djitellopy_import is False
    assert result.has_tello_constructor is False


def test_does_not_guess_star_import() -> None:
    result = classify_source("from djitellopy import *\nTello()\n")

    assert result.kind is ScriptKind.PYTHON
    assert result.has_djitellopy_import is True
    assert result.has_tello_constructor is False


def test_syntax_error_falls_back_to_regular_python() -> None:
    result = classify_source("def broken(:\n")

    assert result.kind is ScriptKind.PYTHON
    assert result.syntax_error is not None
