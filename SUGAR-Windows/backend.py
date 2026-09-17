from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class BackendRunner(QObject):
    """Run the packaged SUGAR bridge as a cancellable child process."""

    event = Signal(dict)
    outputs_changed = Signal(list)
    error = Signal(str)
    running_changed = Signal(bool)
    finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.started.connect(lambda: self.running_changed.emit(True))
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._config_path: Path | None = None
        self._active_command = ""
        self._cancel_requested = False

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def _bridge_location() -> tuple[str, list[str]]:
        override = os.environ.get("SUGAR_BRIDGE", "").strip()
        if override:
            return override, []

        app_dir = Path(sys.executable).resolve().parent
        packaged = app_dir / "sugar-bridge.exe"
        if packaged.is_file():
            return str(packaged), []

        bridge = BackendRunner._repo_root() / "sugar_bridge.py"
        return sys.executable, [str(bridge)]

    def diagnostics(self) -> None:
        self.run("diagnostics", {}, {})

    def run(self, command: str, config: dict[str, Any], secrets: dict[str, str]) -> None:
        if self.is_running:
            raise RuntimeError("A SUGAR operation is already running.")
        self._cleanup_config()
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._active_command = command
        self._cancel_requested = False

        program, prefix = self._bridge_location()
        arguments = [*prefix, command]
        if command != "diagnostics":
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="sugar-desktop-",
                delete=False,
            )
            try:
                json.dump(config, handle, ensure_ascii=False, indent=2)
            finally:
                handle.close()
            self._config_path = Path(handle.name)
            arguments.extend(["--config", str(self._config_path)])

        environment = QProcessEnvironment.systemEnvironment()
        secret_mapping = {
            "llm_api_key": "SUGAR_LLM_API_KEY",
            "x_bearer_token": "SUGAR_X_BEARER_TOKEN",
            "bluesky_identifier": "SUGAR_BLUESKY_IDENTIFIER",
            "bluesky_app_password": "SUGAR_BLUESKY_APP_PASSWORD",
            "mastodon_token": "SUGAR_MASTODON_TOKEN",
            "weibo_cookie": "SUGAR_WEIBO_COOKIE",
        }
        for key, env_name in secret_mapping.items():
            value = str(secrets.get(key) or "")
            if value:
                environment.insert(env_name, value)
            else:
                environment.remove(env_name)
        environment.insert("PYTHONUTF8", "1")
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.start()

    def cancel(self) -> None:
        if not self.is_running:
            return
        self._cancel_requested = True
        self.event.emit({"event": "cancel_requested", "operation": self._active_command})
        self.process.terminate()
        if not self.process.waitForFinished(2500):
            self.process.kill()

    def _read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._stdout_buffer += data
        while "\n" in self._stdout_buffer:
            line, self._stdout_buffer = self._stdout_buffer.split("\n", 1)
            self._handle_stdout_line(line.strip())

    def _read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        self._stderr_buffer += data
        while "\n" in self._stderr_buffer:
            line, self._stderr_buffer = self._stderr_buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.event.emit({"event": "backend_stderr", "message": line})

    def _handle_stdout_line(self, line: str) -> None:
        if not line:
            return
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            self.event.emit({"event": "backend_output", "message": line})
            return
        if not isinstance(payload, dict):
            self.event.emit({"event": "backend_output", "message": line})
            return
        self.event.emit(payload)
        if payload.get("event") == "complete":
            outputs = [str(value) for value in payload.get("outputs") or [] if str(value)]
            self.outputs_changed.emit(outputs)
        elif payload.get("event") == "error":
            self.error.emit(str(payload.get("message") or "SUGAR operation failed."))

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self.error.emit(
                "The SUGAR backend could not start. Reinstall the Windows package or set SUGAR_BRIDGE to a valid bridge executable."
            )

    def _process_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        if self._stdout_buffer.strip():
            self._handle_stdout_line(self._stdout_buffer.strip())
        if self._stderr_buffer.strip():
            self.event.emit({"event": "backend_stderr", "message": self._stderr_buffer.strip()})
        if self._cancel_requested:
            self.event.emit(
                {
                    "event": "cancelled",
                    "code": "cancelled",
                    "message": "Operation cancelled by user.",
                }
            )
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self.running_changed.emit(False)
        self.finished.emit(int(exit_code))
        self._cleanup_config()
        self._active_command = ""
        self._cancel_requested = False

    def _cleanup_config(self) -> None:
        if self._config_path is None:
            return
        try:
            self._config_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._config_path = None
