"""Focused checks for the Windows workbench's user-facing operation flow."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "SUGAR-Windows"))
from app import ActivityDock, date_range_error  # noqa: E402
from backend import BackendRunner  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize(
    ("since", "until", "expected"),
    [
        ("", "", None),
        ("2026-09-01", "2026-09-24", None),
        ("2026-02-30", "", "Since must be a valid date"),
        ("", "2026-9-24", "Until must be a valid date"),
        ("2026-09-24", "2026-09-01", "Since must be on or before Until"),
    ],
)
def test_date_range_feedback(since, until, expected):
    result = date_range_error(since, until)
    assert result is None if expected is None else expected in result


def test_every_output_remains_accessible(qt_app):
    dock = ActivityDock()
    paths = [f"C:/research/result-{index}.csv" for index in range(15)]
    dock.set_outputs(paths)
    assert dock.output_choice.count() == len(paths)
    assert dock.output_choice.itemData(14) == paths[14]
    assert dock.open_output.isEnabled()
    dock.set_outputs([])
    assert dock.output_choice.count() == 0
    assert not dock.open_output.isEnabled()


def test_unexpected_backend_exit_is_visible(qt_app, monkeypatch):
    monkeypatch.setattr(
        BackendRunner,
        "_bridge_location",
        staticmethod(lambda: (sys.executable, ["-c", "import sys; sys.exit(7)"])),
    )
    runner = BackendRunner()
    errors = []
    runner.error.connect(errors.append)
    loop = QEventLoop()
    runner.finished.connect(loop.quit)
    runner.run("diagnostics", {}, {})
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert not runner.is_running
    assert len(errors) == 1
    assert "exit code 7" in errors[0]


def test_cancel_returns_to_event_loop_without_failure_dialog(qt_app, monkeypatch):
    monkeypatch.setattr(
        BackendRunner,
        "_bridge_location",
        staticmethod(lambda: (sys.executable, ["-c", "import time; time.sleep(10)"])),
    )
    runner = BackendRunner()
    errors = []
    events = []
    runner.error.connect(errors.append)
    runner.event.connect(events.append)
    loop = QEventLoop()
    runner.finished.connect(loop.quit)
    runner.run("diagnostics", {}, {})
    QTimer.singleShot(100, runner.cancel)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert not runner.is_running
    assert not errors
    assert any(event["event"] == "cancelled" for event in events)
