"""PySide6 + pyqtgraph main window for the interactive RiftLab viewer (EW-53).

Thin wiring only: open a .sqlite, pick a session from the dropdown, and draw
three X-linked panels - HR, HRV (rolling RMSSD) and a game-event lane. Zooming
or panning any panel moves all of them together (`setXLink`). Every classified
event is a coloured vertical line across all panels plus a hoverable dot in the
event lane.

On top of that: a metadata header, an adjustable HRV (RMSSD) window, an event
colour legend, a mouse crosshair with a time/HR/RMSSD readout, a draggable
region to select and export a time window (or the current view) as PNG, and
keyboard shortcuts. All data/HRV/classification logic lives in `loader`,
`metrics` and `model` (pure); this file only puts the arrays on screen.
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

import numpy as np
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QWidget,
    QVBoxLayout,
)

from .. import SUPPORTED_SCHEMA_VERSION
from ..loader import SessionData, SessionInfo, list_sessions, load_session
from ..plot import _ROW_LABELS
from .model import (
    EventMarker,
    HrPlotModel,
    HrvPlotModel,
    RMSSD_WINDOW_MAX,
    RMSSD_WINDOW_MIN,
    axis_bounds,
    default_region,
    event_markers,
    hr_plot_model,
    hrv_plot_model,
    legend_entries,
    nearest_value,
    session_header,
    session_label,
)

_HR_PEN = pg.mkPen("#c0392b", width=2)
_HRV_PEN = pg.mkPen("#2c7fb8", width=2)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RiftLab viewer")
        self.resize(1100, 760)

        self._db_path: Optional[Path] = None
        self._sessions: list[SessionInfo] = []
        self._rmssd_window = 10
        self._region: Optional[pg.LinearRegionItem] = None
        self._data: Optional[SessionData] = None
        self._hrv_curve: Optional[pg.PlotDataItem] = None
        self._hrv_t = np.empty(0)
        self._hrv_v = np.empty(0)
        self._cross: list[pg.InfiniteLine] = []

        open_btn = QPushButton("Open .sqlite...")
        open_btn.clicked.connect(self._choose_file)
        open_btn.setShortcut(QKeySequence.StandardKey.Open)  # Ctrl+O

        self._session_box = QComboBox()
        self._session_box.setMinimumWidth(300)
        self._session_box.currentIndexChanged.connect(self._on_session_changed)
        self._session_box.setEnabled(False)

        self._hrv_spin = QSpinBox()
        self._hrv_spin.setRange(RMSSD_WINDOW_MIN, RMSSD_WINDOW_MAX)
        self._hrv_spin.setValue(self._rmssd_window)
        self._hrv_spin.setToolTip("RMSSD rolling-window length (beats)")
        self._hrv_spin.setEnabled(False)
        self._hrv_spin.valueChanged.connect(self._on_hrv_window_changed)

        self._export_view_btn = QPushButton("Export view...")
        self._export_view_btn.clicked.connect(lambda: self._export(selection=False))
        self._export_view_btn.setShortcut("Ctrl+E")
        self._export_sel_btn = QPushButton("Export selection...")
        self._export_sel_btn.clicked.connect(lambda: self._export(selection=True))
        self._export_sel_btn.setShortcut("Ctrl+Shift+E")
        for b in (self._export_view_btn, self._export_sel_btn):
            b.setEnabled(False)

        top = QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(QLabel("Session:"))
        top.addWidget(self._session_box)
        top.addSpacing(12)
        top.addWidget(QLabel("HRV window:"))
        top.addWidget(self._hrv_spin)
        top.addStretch(1)
        top.addWidget(self._export_view_btn)
        top.addWidget(self._export_sel_btn)

        # metadata header (left) + crosshair readout (right); colours are set
        # by _apply_theme_colors() so they stay readable in light and dark mode
        self._header = QLabel("")
        self._readout = QLabel("")
        header_row = QHBoxLayout()
        header_row.addWidget(self._header)
        header_row.addStretch(1)
        header_row.addWidget(self._readout)

        # -- three stacked, X-linked panels ---------------------------------
        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground("w")
        self._p_hr = self._glw.addPlot(row=0, col=0)
        self._p_hrv = self._glw.addPlot(row=1, col=0)
        self._p_ev = self._glw.addPlot(row=2, col=0)
        for p in (self._p_hr, self._p_hrv, self._p_ev):
            p.showGrid(x=True, y=True, alpha=0.2)
            # Fixed left-axis width + no SI prefix: otherwise the tick-label
            # width changes as values/zoom change, the layout re-flows, and the
            # linked views re-range in a feedback loop -> the panels visibly
            # jitter until the first manual zoom disables auto-range.
            axis = p.getAxis("left")
            axis.setWidth(92)
            axis.enableAutoSIPrefix(False)
        self._p_hrv.setXLink(self._p_hr)
        self._p_ev.setXLink(self._p_hr)

        self._p_hr.setLabel("left", "Heart rate (bpm)")
        self._p_hrv.setLabel("left", "HRV RMSSD (ms)")
        self._p_ev.setLabel("left", "LoL events")
        self._p_ev.setLabel("bottom", "Time since session start (s)")
        # event lane: fixed rows labelled like the matplotlib viewer
        self._p_ev.getAxis("left").setTicks(
            [[(i, lbl) for i, lbl in enumerate(_ROW_LABELS)]]
        )
        self._p_ev.setYRange(-0.6, len(_ROW_LABELS) - 0.2)
        self._p_ev.setMouseEnabled(y=False)

        layout_ratios = (2.0, 1.2, 2.4)
        for i, r in enumerate(layout_ratios):
            self._glw.ci.layout.setRowStretchFactor(i, int(r * 10))

        # event colour legend (static)
        self._legend = QLabel(self._legend_html())
        self._legend.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addLayout(header_row)
        layout.addWidget(self._glw, 1)
        layout.addWidget(self._legend)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        # crosshair readout follows the mouse across the linked panels
        self._glw.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # extra shortcuts (open/export are on their buttons)
        QShortcut(QKeySequence("Ctrl+0"), self, self._reset_zoom)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, lambda: self._step_session(1))
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, lambda: self._step_session(-1))

        self._apply_theme_colors()
        self.statusBar().showMessage(
            "Open a RiftRec .sqlite to begin.  (Ctrl+O open · Ctrl+E export · "
            "Ctrl+0 reset zoom · PgUp/PgDn session)"
        )

    @staticmethod
    def _legend_html() -> str:
        swatches = [
            f'<span style="color:{color};">&#9679;</span>&nbsp;{label}'
            for label, color in legend_entries()
        ]
        return "&nbsp;&nbsp;&nbsp;".join(swatches)

    def _apply_theme_colors(self) -> None:
        """Pick label text colours that contrast with the current window
        background, so the header/readout/legend stay legible in both light and
        dark mode. Re-run on palette changes (see changeEvent)."""
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        primary = "#dcdcdc" if dark else "#333333"
        secondary = "#b4b4b4" if dark else "#555555"
        self._header.setStyleSheet(f"color:{primary};")
        self._legend.setStyleSheet(f"color:{primary};")
        self._readout.setStyleSheet(f"color:{secondary}; font-family: monospace;")

    def changeEvent(self, event) -> None:
        if event.type() in (QEvent.Type.PaletteChange,
                             QEvent.Type.ApplicationPaletteChange):
            self._apply_theme_colors()
        super().changeEvent(event)

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
            self._clear_panels()
            self._region = None
            self._data = None
            self._cross = []
            self._header.setText("")
            self._readout.setText("")
            self._hrv_spin.setEnabled(False)
            self._export_view_btn.setEnabled(False)
            self._export_sel_btn.setEnabled(False)
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
                f"{self._db_path.name} - {data.hr_bpm.size} HR samples, "
                f"{len(data.events)} events"
            )
        self._draw(data)

    # -- drawing ------------------------------------------------------------
    def _clear_panels(self) -> None:
        for p in (self._p_hr, self._p_hrv, self._p_ev):
            p.clear()

    def _draw(self, data: SessionData) -> None:
        self._clear_panels()
        self._data = data

        hr = hr_plot_model(data)
        hrv = hrv_plot_model(data, window=self._rmssd_window)
        markers = event_markers(data)
        self._hrv_t, self._hrv_v = hrv.t_s, hrv.rmssd_ms

        self._p_hr.setTitle(hr.title)
        if hr.has_data:
            self._p_hr.plot(hr.t_s, hr.hr_bpm, pen=_HR_PEN)
        # keep a handle so the HRV window spinbox can update just this curve.
        # RMSSD is NaN before the first full window; connect="finite" skips gaps.
        self._hrv_curve = self._p_hrv.plot(
            hrv.t_s, hrv.rmssd_ms, pen=_HRV_PEN, connect="finite"
        )

        self._draw_events(markers)
        self._add_crosshair()

        # Set explicit ranges from the data instead of enableAutoRange(): this
        # both fixes the initial scaling (auto-range would otherwise fire
        # against a not-yet-sized viewport) and turns auto-range off, so the
        # view is static and does not keep recomputing every frame.
        xmax = max(data.duration_s, 1.0)
        self._p_hr.setXRange(0.0, xmax, padding=0.02)  # propagates via X-link
        self._set_yrange(self._p_hr, hr.hr_bpm)
        # HRV robust: one dropped RR interval spikes RMSSD and would otherwise
        # squash the real trend flat.
        self._set_yrange(self._p_hrv, hrv.rmssd_ms, robust=True)

        self._add_region(xmax)
        self._header.setText(session_header(data))
        self._readout.setText("")
        self._hrv_spin.setEnabled(True)
        self._export_view_btn.setEnabled(True)
        self._export_sel_btn.setEnabled(True)

    def _add_region(self, xmax: float) -> None:
        """Draggable time-window selector on the HR panel (recreated per draw,
        since _clear_panels() removes it). Its X-range drives 'Export
        selection'."""
        self._region = pg.LinearRegionItem(
            values=default_region(xmax), brush=(80, 120, 255, 40),
            hoverBrush=(80, 120, 255, 70), movable=True,
        )
        self._region.setZValue(-10)  # behind the curves
        self._region.setBounds((0.0, xmax))
        self._p_hr.addItem(self._region)

    def _add_crosshair(self) -> None:
        """A vertical time crosshair in every panel (recreated per draw, since
        _clear_panels() removes it); driven by _on_mouse_moved."""
        self._cross = []
        pen = pg.mkPen((120, 120, 120), width=1, style=pg.QtCore.Qt.DashLine)
        for p in (self._p_hr, self._p_hrv, self._p_ev):
            line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
            line.setZValue(20)
            line.hide()
            p.addItem(line, ignoreBounds=True)
            self._cross.append(line)

    # -- interaction --------------------------------------------------------
    def _on_hrv_window_changed(self, value: int) -> None:
        """Recompute RMSSD live and update only the HRV curve, keeping zoom."""
        self._rmssd_window = value
        if self._data is None or self._hrv_curve is None:
            return
        hrv = hrv_plot_model(self._data, window=value)
        self._hrv_t, self._hrv_v = hrv.t_s, hrv.rmssd_ms
        self._hrv_curve.setData(hrv.t_s, hrv.rmssd_ms, connect="finite")
        self._set_yrange(self._p_hrv, hrv.rmssd_ms, robust=True)

    def _on_mouse_moved(self, scene_pos) -> None:
        if self._data is None or not self._cross:
            return
        in_plots = any(
            p.sceneBoundingRect().contains(scene_pos)
            for p in (self._p_hr, self._p_hrv, self._p_ev)
        )
        if not in_plots:
            for line in self._cross:
                line.hide()
            self._readout.setText("")
            return
        # X is shared across the linked panels, so map through the HR view
        x = self._p_hr.getViewBox().mapSceneToView(scene_pos).x()
        for line in self._cross:
            line.setPos(x)
            line.show()

        hr_val = nearest_value(self._data.hr_t, self._data.hr_bpm, x)
        rmssd_val = nearest_value(self._hrv_t, self._hrv_v, x)
        parts = [f"t = {x:6.1f} s"]
        parts.append(f"HR = {hr_val:5.0f} bpm" if hr_val is not None else "HR =   -")
        parts.append(
            f"RMSSD = {rmssd_val:5.0f} ms" if rmssd_val is not None else "RMSSD =   -"
        )
        self._readout.setText("   ".join(parts))

    def _reset_zoom(self) -> None:
        if self._data is None:
            return
        self._p_hr.setXRange(0.0, max(self._data.duration_s, 1.0), padding=0.02)
        self._set_yrange(self._p_hr, self._data.hr_bpm)
        self._set_yrange(self._p_hrv, self._hrv_v, robust=True)

    def _step_session(self, delta: int) -> None:
        n = self._session_box.count()
        if n:
            self._session_box.setCurrentIndex((self._session_box.currentIndex() + delta) % n)

    @staticmethod
    def _set_yrange(plot: "pg.PlotItem", values: np.ndarray,
                    robust: bool = False) -> None:
        bounds = axis_bounds(values, robust=robust)
        if bounds is not None:
            plot.setYRange(bounds[0], bounds[1], padding=0.08)

    def _draw_events(self, markers: list[EventMarker]) -> None:
        if not markers:
            return
        # vertical guide line in every panel (a line item lives in one scene,
        # so one InfiniteLine per panel per event)
        for m in markers:
            pen = pg.mkPen(m.color, width=1, style=pg.QtCore.Qt.DashLine)
            for p in (self._p_hr, self._p_hrv, self._p_ev):
                p.addItem(pg.InfiniteLine(pos=m.t_s, angle=90, pen=pen, movable=False))

        # Coloured dots on the event lane, drawn through plot() so they anchor
        # in the view and track zoom/pan. (A bare ScatterPlotItem added via
        # addItem does not get parented into the ViewBox under this
        # PySide6/pyqtgraph combo and would render fixed near the top of the
        # window instead of following the time axis.)
        xs = np.fromiter((m.t_s for m in markers), float, len(markers))
        ys = np.fromiter((m.row for m in markers), float, len(markers))
        brushes = [pg.mkBrush(m.color) for m in markers]
        dots = self._p_ev.plot(
            xs, ys, pen=None, symbol="o", symbolSize=11,
            symbolBrush=brushes, symbolPen=pg.mkPen("k", width=0.5),
        )
        # hover tooltips (event details) on the underlying scatter
        dots.scatter.setData(
            x=xs, y=ys, size=11, brush=brushes, pen=pg.mkPen("k", width=0.5),
            hoverable=True, hoverSize=15,
            data=[m.tip for m in markers], tip=lambda x, y, data: data,
        )

    # -- export -------------------------------------------------------------
    def _export(self, selection: bool) -> None:
        """Save the three panels as a PNG - either the current view, or zoomed
        to the selection region."""
        if self._db_path is None or self._region is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"

        restore = None
        if selection:
            x0, x1 = self._region.getRegion()
            if x1 > x0:
                restore = self._p_hr.getViewBox().viewRange()[0]
                self._p_hr.setXRange(x0, x1, padding=0.0)  # propagates via link

        # hide the selector so it does not paint over the exported figure
        self._region.hide()
        QApplication.processEvents()
        try:
            exporter = ImageExporter(self._glw.scene())
            exporter.parameters()["width"] = 1600  # crisp, keeps aspect ratio
            exporter.export(path)
        finally:
            self._region.show()
            if restore is not None:
                self._p_hr.setXRange(restore[0], restore[1], padding=0.0)
        self.statusBar().showMessage(f"Exported {Path(path).name}")


def run_gui(db_path: Optional[str] = None) -> int:
    """Launch the viewer. Optionally open a file immediately."""
    app = pg.mkQApp("RiftLab viewer")
    win = MainWindow()
    if db_path:
        win.load_file(db_path)
    win.show()
    return app.exec()
