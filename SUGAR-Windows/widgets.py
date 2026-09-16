from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.setSpacing(10)
        if title:
            label = QLabel(title)
            label.setObjectName("cardTitle")
            self.layout.addWidget(label)
        if subtitle:
            label = QLabel(subtitle)
            label.setObjectName("muted")
            label.setWordWrap(True)
            self.layout.addWidget(label)


class LabeledRow(QWidget):
    def __init__(self, label: str, widget: QWidget, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        caption = QLabel(label)
        caption.setObjectName("fieldLabel")
        root.addWidget(caption)
        root.addWidget(widget)
        if hint:
            detail = QLabel(hint)
            detail.setObjectName("hint")
            detail.setWordWrap(True)
            root.addWidget(detail)


class PathField(QWidget):
    changed = Signal(str)

    def __init__(
        self,
        *,
        mode: str = "file",
        extensions: Iterable[str] = (),
        save_extension: str = "",
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.extensions = tuple(extensions)
        self.save_extension = save_extension
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        root.addWidget(self.edit, 1)
        root.addWidget(browse)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, value: str) -> None:
        self.edit.setText(value)

    def browse(self) -> None:
        if self.mode == "directory":
            path = QFileDialog.getExistingDirectory(self, "Choose folder", self.text() or str(Path.home()))
        elif self.mode == "save":
            suffix = self.save_extension.lstrip(".")
            filter_text = f"{suffix.upper()} files (*.{suffix})" if suffix else "All files (*)"
            path, _ = QFileDialog.getSaveFileName(self, "Choose output file", self.text(), filter_text)
        else:
            patterns = " ".join(f"*.{value.lstrip('.')}" for value in self.extensions)
            filter_text = f"Supported files ({patterns})" if patterns else "All files (*)"
            path, _ = QFileDialog.getOpenFileName(self, "Choose file", self.text() or str(Path.home()), filter_text)
        if path:
            self.setText(path)


class PasswordField(QWidget):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setEchoMode(QLineEdit.Password)
        self.toggle = QToolButton()
        self.toggle.setText("Show")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._toggle)
        root.addWidget(self.edit, 1)
        root.addWidget(self.toggle)

    def _toggle(self, checked: bool) -> None:
        self.edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self.toggle.setText("Hide" if checked else "Show")

    def text(self) -> str:
        return self.edit.text()

    def clear(self) -> None:
        self.edit.clear()


class SourceSelector(QWidget):
    def __init__(self, sources: Iterable[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        self.boxes: dict[str, QCheckBox] = {}
        for source in sources:
            box = QCheckBox(source.upper() if source == "x" else source.title())
            self.boxes[source] = box
            root.addWidget(box)
        root.addStretch(1)

    def selected(self) -> list[str]:
        return [key for key, box in self.boxes.items() if box.isChecked() and box.isEnabled()]

    def set_available(self, availability: dict[str, bool]) -> None:
        for key, box in self.boxes.items():
            enabled = availability.get(key, True)
            box.setEnabled(enabled)
            if not enabled:
                box.setChecked(False)


class NumberField(QSpinBox):
    def __init__(self, minimum: int, maximum: int, value: int, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        if suffix:
            self.setSuffix(suffix)


class EnumCombo(QComboBox):
    def __init__(self, values: Iterable[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        for label, value in values:
            self.addItem(label, value)

    def value(self) -> str:
        return str(self.currentData())


class OutputChip(QPushButton):
    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(Path(path).name, parent)
        self.path = path
        self.setToolTip(f"Open {path}")
        self.clicked.connect(self.open_output)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def open_output(self) -> None:
        path = Path(self.path)
        target = path if path.exists() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


class StatusPill(QLabel):
    def __init__(self, text: str = "Unknown", tone: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
