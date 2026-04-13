from __future__ import annotations

import argparse
import sys
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, SimpleQueue
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from tello_demo.studio.classifier import classify_script
from tello_demo.studio.models import (
    AppState,
    BootstrapProgress,
    BootstrapReady,
    ConsoleChunk,
    Phase,
    ProcessExited,
    ProcessStarted,
    ScriptKind,
    ScriptRow,
    StudioEvent,
)
from tello_demo.studio.process_runner import (
    LaunchSpec,
    RunningProcess,
    build_plain_python_launch,
    build_tello_launch,
)
from tello_demo.studio.real_mode_gate import RealModeGate
from tello_demo.studio.runtime_env import (
    RuntimeEnv,
    ensure_runtime_env,
    runtime_env_is_current,
)
from tello_demo.studio.workspace import (
    StudioWorkspace,
    ensure_workspace_dirs,
    list_scripts,
    open_in_file_manager,
    resolve_workspace,
)


class StudioApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        workspace: StudioWorkspace,
        event_queue: SimpleQueue[StudioEvent] | None = None,
        real_mode_gate: RealModeGate | None = None,
    ) -> None:
        self.root = root
        self.workspace = workspace
        self.event_queue = event_queue or SimpleQueue()
        self.real_mode_gate = real_mode_gate or RealModeGate()
        self.runtime_env: RuntimeEnv | None = None
        self.state = AppState(real_unlocked=self.real_mode_gate.unlocked)
        self._running_process: RunningProcess | None = None
        self._bootstrap_thread: threading.Thread | None = None
        self._event_pump_id: str | None = None
        self._progress_running = False
        self._close_after_stop = False

        self._scripts_dir_var = tk.StringVar(value=str(self.workspace.scripts_dir))
        self._status_var = tk.StringVar(value="Starting studio...")

        self._scripts_tree: ttk.Treeview
        self._console: ScrolledText
        self._run_button: ttk.Button
        self._run_real_button: ttk.Button
        self._stop_button: ttk.Button
        self._refresh_button: ttk.Button
        self._open_folder_button: ttk.Button
        self._progress_bar: ttk.Progressbar

    def start(self) -> None:
        ensure_workspace_dirs(self.workspace)
        self.root.title("Tello Studio")
        self.root.geometry("1100x720")
        self.root.minsize(840, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build_ui()
        self.refresh_scripts()
        self._apply_state()
        self._schedule_event_pump()
        self._start_bootstrap()

    def refresh_scripts(self) -> None:
        selected_path = self.state.selected_script
        rows: list[ScriptRow] = []
        for path in list_scripts(self.workspace):
            classification = classify_script(path)
            if classification.syntax_error is not None:
                note = "syntax error"
            elif (
                classification.has_djitellopy_import
                and not classification.has_tello_constructor
            ):
                note = "djitellopy only"
            elif (
                classification.has_tello_constructor
                and not classification.has_djitellopy_import
            ):
                note = "Tello() only"
            else:
                note = ""
            rows.append(
                ScriptRow(
                    path=path,
                    display_name=str(path.relative_to(self.workspace.scripts_dir)),
                    kind=classification.kind,
                    note=note,
                )
            )

        self.state.scripts = rows
        self._scripts_tree.delete(*self._scripts_tree.get_children())
        for row in rows:
            self._scripts_tree.insert(
                "",
                tk.END,
                iid=str(row.path),
                text=row.display_name,
                values=(row.kind.value, row.note),
            )

        if selected_path is not None and str(
            selected_path
        ) in self._scripts_tree.get_children(""):
            self._scripts_tree.selection_set(str(selected_path))
            self._scripts_tree.focus(str(selected_path))
            self.state.selected_script = selected_path
        else:
            self.state.selected_script = None
        self._apply_state()

    def run_selected(self) -> None:
        row = self._selected_script()
        if row is None or self.state.phase != Phase.READY:
            return
        if not self._ensure_runtime_current():
            return

        if row.kind is ScriptKind.TELLO:
            spec = build_tello_launch(
                self.runtime_env.python_executable,
                row.path,
                mode="sim",
            )
            self._start_process(row=row, spec=spec, mode="sim")
            return

        spec = build_plain_python_launch(self.runtime_env.python_executable, row.path)
        self._start_process(row=row, spec=spec, mode=None)

    def run_selected_real(self) -> None:
        row = self._selected_script()
        if row is None or row.kind is not ScriptKind.TELLO:
            return
        if self.state.phase != Phase.READY:
            return
        if not self._ensure_runtime_current():
            return

        if not self.real_mode_gate.unlocked:
            pin = simpledialog.askstring(
                "Unlock real mode",
                "Enter today's UTC real-mode PIN:",
                show="*",
                parent=self.root,
            )
            if pin is None:
                return
            try:
                unlocked = self.real_mode_gate.unlock(pin)
            except ValueError as exc:
                messagebox.showerror("Invalid gate state", str(exc), parent=self.root)
                return
            self.state.real_unlocked = self.real_mode_gate.unlocked
            self._apply_state()
            if not unlocked:
                messagebox.showerror(
                    "Incorrect PIN",
                    "That PIN is not valid for today.",
                    parent=self.root,
                )
                return
            self._append_console(
                "Real mode unlocked for this session.\n", stream="system"
            )

        confirmed = messagebox.askokcancel(
            "Run in real mode",
            "Real mode will talk to the connected drone over Wi-Fi. Continue?",
            parent=self.root,
        )
        if not confirmed:
            return

        spec = build_tello_launch(
            self.runtime_env.python_executable,
            row.path,
            mode="real",
        )
        self._start_process(row=row, spec=spec, mode="real")

    def stop_running(self) -> None:
        if self._running_process is None:
            return
        self.state.phase = Phase.STOPPING
        self._apply_state()
        threading.Thread(target=self._running_process.stop, daemon=True).start()

    def on_close(self) -> None:
        if self._running_process is None:
            self._shutdown()
            return

        confirmed = messagebox.askyesno(
            "Quit Tello Studio",
            "A script is still running. Stop it and quit?",
            parent=self.root,
        )
        if not confirmed:
            return
        self._close_after_stop = True
        self.stop_running()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Scripts folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(
            top_frame,
            textvariable=self._scripts_dir_var,
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self._open_folder_button = ttk.Button(
            top_frame,
            text="Open Scripts Folder",
            command=lambda: open_in_file_manager(self.workspace.scripts_dir),
        )
        self._open_folder_button.grid(row=0, column=2, padx=(0, 8))

        self._refresh_button = ttk.Button(
            top_frame,
            text="Refresh",
            command=self.refresh_scripts,
        )
        self._refresh_button.grid(row=0, column=3)

        panes = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        panes.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        scripts_frame = ttk.Frame(panes, padding=10)
        scripts_frame.columnconfigure(0, weight=1)
        scripts_frame.rowconfigure(0, weight=1)

        self._scripts_tree = ttk.Treeview(
            scripts_frame,
            columns=("kind", "note"),
            selectmode="browse",
        )
        self._scripts_tree.heading("#0", text="Script")
        self._scripts_tree.heading("kind", text="Kind")
        self._scripts_tree.heading("note", text="Note")
        self._scripts_tree.column("#0", width=360, stretch=True)
        self._scripts_tree.column("kind", width=100, stretch=False)
        self._scripts_tree.column("note", width=120, stretch=False)
        self._scripts_tree.grid(row=0, column=0, sticky="nsew")
        self._scripts_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        scripts_scroll = ttk.Scrollbar(
            scripts_frame,
            orient="vertical",
            command=self._scripts_tree.yview,
        )
        scripts_scroll.grid(row=0, column=1, sticky="ns")
        self._scripts_tree.configure(yscrollcommand=scripts_scroll.set)
        panes.add(scripts_frame, weight=1)

        console_frame = ttk.Frame(panes, padding=10)
        console_frame.columnconfigure(0, weight=1)
        console_frame.rowconfigure(0, weight=1)
        self._console = ScrolledText(console_frame, wrap=tk.WORD, state="disabled")
        self._console.grid(row=0, column=0, sticky="nsew")
        self._console.tag_configure("stdout", foreground="#1f1f1f")
        self._console.tag_configure("stderr", foreground="#a00000")
        self._console.tag_configure("system", foreground="#005c99")
        panes.add(console_frame, weight=2)

        actions_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        actions_frame.grid(row=2, column=0, sticky="ew")

        self._run_button = ttk.Button(
            actions_frame, text="Run", command=self.run_selected
        )
        self._run_button.grid(row=0, column=0)

        self._run_real_button = ttk.Button(
            actions_frame,
            text="Run Real",
            command=self.run_selected_real,
        )
        self._run_real_button.grid(row=0, column=1, padx=(8, 0))

        self._stop_button = ttk.Button(
            actions_frame,
            text="Stop",
            command=self.stop_running,
        )
        self._stop_button.grid(row=0, column=2, padx=(8, 0))

        status_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self._progress_bar = ttk.Progressbar(
            status_frame, mode="indeterminate", length=140
        )
        self._progress_bar.grid(row=0, column=0, sticky="w")
        ttk.Label(status_frame, textvariable=self._status_var).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
        )

    def _on_tree_select(self, _event: tk.Event) -> None:
        selection = self._scripts_tree.selection()
        self.state.selected_script = Path(selection[0]) if selection else None
        self._apply_state()

    def _schedule_event_pump(self) -> None:
        self._event_pump_id = self.root.after(50, self._pump_events)

    def _pump_events(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except Empty:
                break
            self._handle_event(event)

        if self.root.winfo_exists():
            self._schedule_event_pump()

    def _handle_event(self, event: StudioEvent) -> None:
        if isinstance(event, BootstrapProgress):
            self._append_console(f"[studio] {event.message}\n", stream="system")
            if event.is_error:
                self.state.phase = Phase.ENV_ERROR
                self.state.env_error = event.message
        elif isinstance(event, BootstrapReady):
            self.runtime_env = event.runtime_env
            self.state.env_ready = True
            self.state.env_error = None
            if self.state.phase is not Phase.RUNNING:
                self.state.phase = Phase.READY
        elif isinstance(event, ProcessStarted):
            self.state.phase = Phase.RUNNING
            self.state.running_script = event.script
            self.state.run_mode = event.mode
            self.state.last_exit_code = None
            self._append_console(
                f"[studio] Running: {' '.join(event.command)}\n",
                stream="system",
            )
        elif isinstance(event, ConsoleChunk):
            self._append_console(event.text, stream=event.stream)
        elif isinstance(event, ProcessExited):
            self._running_process = None
            self.state.phase = Phase.READY if self.state.env_ready else Phase.ENV_ERROR
            self.state.running_script = None
            self.state.run_mode = None
            self.state.last_exit_code = event.returncode
            self._append_console(
                f"[studio] Process exited with code {event.returncode}.\n",
                stream="system",
            )
            if self._close_after_stop:
                self._shutdown()
                return

        self.state.real_unlocked = self.real_mode_gate.unlocked
        self._apply_state()

    def _apply_state(self) -> None:
        selected = self._selected_script()
        ready = self.state.phase is Phase.READY and self.runtime_env is not None
        can_run = ready and selected is not None
        can_run_real = can_run and selected.kind is ScriptKind.TELLO
        is_running = self.state.phase in {Phase.RUNNING, Phase.STOPPING}

        self._run_button.state(
            ["!disabled"] if can_run and not is_running else ["disabled"]
        )
        self._run_real_button.state(
            ["!disabled"] if can_run_real and not is_running else ["disabled"]
        )
        self._stop_button.state(["!disabled"] if is_running else ["disabled"])

        if self.state.phase is Phase.BOOTSTRAPPING and not self._progress_running:
            self._progress_bar.start(12)
            self._progress_running = True
        elif self.state.phase is not Phase.BOOTSTRAPPING and self._progress_running:
            self._progress_bar.stop()
            self._progress_running = False

        selection_label = selected.display_name if selected is not None else "none"
        parts = [
            f"phase={self.state.phase.value}",
            f"env={'ready' if self.state.env_ready else 'bootstrapping'}",
            f"real={'unlocked' if self.state.real_unlocked else 'locked'}",
            f"selected={selection_label}",
        ]
        if selected is not None:
            parts.append(f"kind={selected.kind.value}")
        if self.state.last_exit_code is not None:
            parts.append(f"last_exit={self.state.last_exit_code}")
        if self.state.env_error:
            parts.append(f"env_error={self.state.env_error}")
        self._status_var.set(" | ".join(parts))

    def _append_console(self, text: str, *, stream: str) -> None:
        self._console.configure(state="normal")
        self._console.insert(tk.END, text, (stream,))
        self._console.see(tk.END)
        self._console.configure(state="disabled")

    def _selected_script(self) -> ScriptRow | None:
        selected_path = self.state.selected_script
        if selected_path is None:
            return None
        for row in self.state.scripts:
            if row.path == selected_path:
                return row
        return None

    def _start_bootstrap(self) -> None:
        if self._bootstrap_thread is not None and self._bootstrap_thread.is_alive():
            return
        self.state.phase = Phase.BOOTSTRAPPING

        def worker() -> None:
            try:
                runtime_env = ensure_runtime_env(
                    self.workspace,
                    progress=lambda message: self.event_queue.put(
                        BootstrapProgress(message=message)
                    ),
                )
            except Exception as exc:
                self.event_queue.put(BootstrapProgress(message=str(exc), is_error=True))
                return
            self.event_queue.put(BootstrapReady(runtime_env=runtime_env))

        self._bootstrap_thread = threading.Thread(target=worker, daemon=True)
        self._bootstrap_thread.start()

    def _start_process(
        self,
        *,
        row: ScriptRow,
        spec: LaunchSpec,
        mode: str | None,
    ) -> None:
        if self._running_process is not None:
            return

        try:
            running_process = RunningProcess(
                spec,  # type: ignore[arg-type]
                on_output=lambda event: self.event_queue.put(
                    ConsoleChunk(stream=event.stream, text=event.text)
                ),
                on_exit=lambda returncode: self.event_queue.put(
                    ProcessExited(returncode=returncode)
                ),
            )
            running_process.start()
        except OSError as exc:
            messagebox.showerror("Process launch failed", str(exc), parent=self.root)
            return

        self._running_process = running_process
        self.event_queue.put(
            ProcessStarted(command=spec.argv, script=row.path, mode=mode)
        )

    def _ensure_runtime_current(self) -> bool:
        if self.runtime_env is None:
            return False
        if runtime_env_is_current(self.runtime_env):
            return True

        self._append_console(
            "[studio] Runtime changed on disk. Rebootstrapping before launch.\n",
            stream="system",
        )
        self.runtime_env = None
        self.state.env_ready = False
        self.state.phase = Phase.BOOTSTRAPPING
        self._apply_state()
        self._start_bootstrap()
        return False

    def _shutdown(self) -> None:
        if self._event_pump_id is not None:
            try:
                self.root.after_cancel(self._event_pump_id)
            except tk.TclError:
                pass
            self._event_pump_id = None
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tello-studio")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Override the default studio workspace root",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = resolve_workspace(args.workspace_root)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Unable to start Tello Studio UI: {exc}", file=sys.stderr)
        return 1

    app = StudioApp(root, workspace=workspace)
    app.start()
    root.mainloop()
    return 0
