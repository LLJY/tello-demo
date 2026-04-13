from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from tello_demo.studio.runtime_env import RuntimeEnv

RunMode = Literal["sim", "real"]
StreamName = Literal["stdout", "stderr", "system"]


class Phase(str, Enum):
    BOOTSTRAPPING = "bootstrapping"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    ENV_ERROR = "env_error"


class ScriptKind(str, Enum):
    PYTHON = "python"
    TELLO = "tello"


@dataclass(frozen=True, slots=True)
class ScriptRow:
    path: Path
    display_name: str
    kind: ScriptKind
    note: str = ""


@dataclass(slots=True)
class AppState:
    phase: Phase = Phase.BOOTSTRAPPING
    scripts: list[ScriptRow] = field(default_factory=list)
    selected_script: Path | None = None
    env_ready: bool = False
    env_error: str | None = None
    real_unlocked: bool = False
    running_script: Path | None = None
    run_mode: RunMode | None = None
    last_exit_code: int | None = None


@dataclass(frozen=True, slots=True)
class BootstrapProgress:
    message: str
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class BootstrapReady:
    runtime_env: "RuntimeEnv"


@dataclass(frozen=True, slots=True)
class ProcessStarted:
    command: tuple[str, ...]
    script: Path
    mode: RunMode | None = None


@dataclass(frozen=True, slots=True)
class ConsoleChunk:
    stream: StreamName
    text: str


@dataclass(frozen=True, slots=True)
class ProcessExited:
    returncode: int


StudioEvent = (
    BootstrapProgress | BootstrapReady | ProcessStarted | ConsoleChunk | ProcessExited
)
