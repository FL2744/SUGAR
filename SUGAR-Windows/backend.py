from __future__ import annotations

import csv
import json
import os
import subprocess
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

        # Packaged smoke tests execute the backend embedded inside the one-file
        # Windows application. Ordinary launches do not pay this startup cost.
        if (
            os.environ.get("SUGAR_VERIFY_EMBEDDED_BACKEND", "").strip() == "1"
            or "--smoke-test" in sys.argv
        ):
            self._verify_embedded_backend()

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
        bundle_dir = Path(getattr(sys, "_MEIPASS", app_dir))
        embedded = bundle_dir / "sugar-bridge.exe"
        if embedded.is_file():
            return str(embedded), []

        packaged = app_dir / "sugar-bridge.exe"
        if packaged.is_file():
            return str(packaged), []

        bridge = BackendRunner._repo_root() / "sugar_bridge.py"
        return sys.executable, [str(bridge)]

    @staticmethod
    def _json_events(stdout: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    @classmethod
    def _run_embedded_command(
        cls,
        program: str,
        prefix: list[str],
        command: str,
        *,
        config: dict[str, Any] | None = None,
        workdir: Path | None = None,
        timeout: int = 180,
    ) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
        args = [program, *prefix, command]
        config_path: Path | None = None
        if config is not None:
            directory = workdir or Path(tempfile.mkdtemp(prefix="sugar-embedded-"))
            directory.mkdir(parents=True, exist_ok=True)
            config_path = directory / f"{command}-config.json"
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            args.extend(["--config", str(config_path)])
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        events = cls._json_events(completed.stdout)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
            raise RuntimeError(f"Embedded SUGAR backend {command} failed: {detail}")
        error = next((event for event in reversed(events) if event.get("event") == "error"), None)
        if error:
            raise RuntimeError(f"Embedded SUGAR backend {command} failed: {error.get('message', 'unknown error')}")
        return completed, events

    @classmethod
    def _verify_embedded_backend(cls) -> None:
        if not getattr(sys, "frozen", False):
            return
        program, prefix = cls._bridge_location()
        _, events = cls._run_embedded_command(program, prefix, "diagnostics", timeout=120)
        if not events:
            raise RuntimeError("Embedded SUGAR backend diagnostics returned no output.")
        payload = events[-1]
        if payload.get("event") != "diagnostics" or int(payload.get("bridge_protocol", -1)) != 3:
            raise RuntimeError("Embedded SUGAR backend diagnostics returned an unexpected protocol response.")

        if os.environ.get("SUGAR_INCIDENT_DRILL", "").strip() != "1":
            return

        # Pre-demo certification: make the exact embedded worker perform a real,
        # anonymous network collection and then process the collected artifact.
        # Keep the volume bounded so CI validates rate-limit behaviour without
        # generating abusive traffic or depending on private API credentials.
        with tempfile.TemporaryDirectory(prefix="sugar-incident-") as temp:
            root = Path(temp)
            search_config = {
                "sources": ["bluesky", "bilibili"],
                "terms": ["artificial intelligence", "人工智能"],
                "translate_posts": False,
                "infer_locations": False,
                "max_posts_per_query": 20,
                "max_pages_per_query": 1,
                "output_directory": str(root),
            }
            _, search_events = cls._run_embedded_command(
                program,
                prefix,
                "search",
                config=search_config,
                workdir=root,
                timeout=240,
            )
            complete = next(
                (event for event in reversed(search_events) if event.get("event") == "complete"),
                None,
            )
            outputs = [Path(value) for value in (complete or {}).get("outputs", [])]
            csv_path = next((path for path in outputs if path.suffix.casefold() == ".csv"), None)
            if csv_path is None or not csv_path.is_file():
                raise RuntimeError("Incident drill produced no normalized CSV output.")
            with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) < 5:
                raise RuntimeError(f"Incident drill collected only {len(rows)} records; expected at least 5 live records.")
            observed_sources = {str(row.get("platform") or "").casefold() for row in rows}
            if not observed_sources.intersection({"bluesky", "bilibili"}):
                raise RuntimeError("Incident drill did not preserve a live source platform in normalized output.")

            report_stem = root / "incident-live-report"
            analysis_config = {
                "source_file": str(csv_path),
                "output_stem": str(report_stem),
                "output_format": "pdf",
            }
            cls._run_embedded_command(
                program,
                prefix,
                "analysis",
                config=analysis_config,
                workdir=root,
                timeout=240,
            )
            report = report_stem.with_suffix(".pdf")
            if not report.is_file() or report.stat().st_size < 1000:
                raise RuntimeError("Incident drill failed to produce a usable PDF report from live collection data.")

    def diagnostics(self) -> None:
        self.run("diagnostics", {}, {})

    def run(self, command: str, config: dict[str, Any], secrets: dict[str, str]) -> None:
        if self.is_running:
            raise RuntimeError("A SUGAR operation is already running.")
        self._cleanup_config()
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self._active_command = command

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
            "zhihu_access_secret": "SUGAR_ZHIHU_ACCESS_SECRET",
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
                "The SUGAR backend could not start. Re-download the current Windows SUGAR.exe or set SUGAR_BRIDGE to a valid bridge executable for development debugging."
            )

    def _process_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        if self._stdout_buffer.strip():
            self._handle_stdout_line(self._stdout_buffer.strip())
        if self._stderr_buffer.strip():
            self.event.emit({"event": "backend_stderr", "message": self._stderr_buffer.strip()})
        self._stdout_buffer = ""
        self._stderr_buffer = ""
        self.running_changed.emit(False)
        self.finished.emit(int(exit_code))
        self._cleanup_config()
        self._active_command = ""

    def _cleanup_config(self) -> None:
        if self._config_path is None:
            return
        try:
            self._config_path.unlink(missing_ok=True)
        except OSError:
            pass
        self._config_path = None
