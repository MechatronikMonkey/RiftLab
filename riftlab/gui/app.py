"""PySide6 + pyqtgraph main window (M0 scaffold).

Thin wiring only: open a .sqlite, pick a session from the dropdown, and draw its
HR curve in a pyqtgraph plot with built-in zoom/pan (drag = pan, wheel = zoom,
right-drag = box zoom, 'A' / right-click "View All" = reset). All data logic
lives in `loader` and `model`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Pin pyqtgraph to PySide6 (our chosen binding, EW-53): several Qt bindings may
# be installed and pyqtgraph would otherwise auto-pick another (e.g. PyQt6),
# mixing incompatible QWidget classes. Import PySide6 before pyqtgraph too, so
# it is the already-loaded binding pyqtgraph adopts.
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
import PySide6.QtWidgets as _qtw  # noqa: F401  (ensures PySide6 is loaded first)

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from .. import SUPPORTED_SCHEMA_VERSION
from ..loader import SessionInfo, list_sessions, load_session
from .model import HrPlotModel, hr_plot_model, session_label

_HR_PEN = pg.mkPen("#c0392b", width=2)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RiftLab viewer")
        self.resize(1000, 600)

        self._db_path: Optional[Path] = None
        self._sessions: list[SessionInfo] = []

        open_btn = QPushButton("Open .sqlite...")
        open_btn.clicked.connect(self._choose_file)

        self._session_box = QComboBox()
        self._session_box.setMinimumWidth(320)
        self._session_box.currentIndexChanged.connect(self._on_session_changed)
        self._session_box.setEnabled(False)

        top = QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(QLabel("Session:"))
        top.addWidget(self._session_box)
        top.addStretch(1)

        self._plot = pg.PlotWidget()
        self._plot.setBackground("w")
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setLabel("bottom", "Time since session start (s)")
        self._plot.setLabel("left", "Heart rate (bpm)")

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self._plot, 1)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Open a RiftRec .sqlite to begin.")

    # -- file / session selection -------------------------------------------
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open RiftRec session", "", "SQLite session (*.sqlite);;All files (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str | Path) -> None:
        """Open a file, populate the session dropdown, show the first session."""
        self._db_path = Path(path)
        self._sessions = list_sessions(self._db_path)

        self._session_box.blockSignals(True)
        self._session_box.clear()
        for info in self._sessions:
            self._session_box.addItem(session_label(info), info.session_id)
        self._session_box.setEnabled(bool(self._sessions))
        self._session_box.setCurrentIndex(0 if self._sessions else -1)
        self._session_box.blockSignals(False)

        if self._sessions:
            self._show_selected()
        else:
            self._plot.clear()
            self.statusBar().showMessage(f"No sessions in {self._db_path.name}")

    def _on_session_changed(self, _index: int) -> None:
        self._show_selected()

    def _show_selected(self) -> None:
        if self._db_path is None:
            return
        session_id = self._session_box.currentData()
        if session_id is None:
            return
        data = load_session(self._db_path, session_id=session_id)
        if data.schema_version > SUPPORTED_SCHEMA_VERSION:
            self.statusBar().showMessage(
                f"[warn] session schema v{data.schema_version} > supported "
                f"v{SUPPORTED_SCHEMA_VERSION}; display may be incomplete."
            )
        else:
            self.statusBar().showMessage(
                f"{self._db_path.name} - {data.hr_bpm.size} HR samples"
            )
        self._draw(hr_plot_model(data))

    # -- drawing ------------------------------------------------------------
    def _draw(self, m: HrPlotModel) -> None:
        self._plot.clear()
        self._plot.setTitle(m.title)
        self._plot.setLabel("bottom", m.x_label)
        self._plot.setLabel("left", m.y_label)
        if m.has_data:
            self._plot.plot(m.t_s, m.hr_bpm, pen=_HR_PEN)
        self._plot.enableAutoRange()


def run_gui(db_path: Optional[str] = None) -> int:
    """Launch the viewer. Optionally open a file immediately."""
    app = pg.mkQApp("RiftLab viewer")
    win = MainWindow()
    if db_path:
        win.load_file(db_path)
    win.show()
    return app.exec()
