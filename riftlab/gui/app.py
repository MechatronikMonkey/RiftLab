"""PySide6 + pyqtgraph main window (M1: linked HR/HRV/event timelines).

Thin wiring only: open a .sqlite, pick a session from the dropdown, and draw
three X-linked panels - HR, HRV (rolling RMSSD) and a game-event lane. Zooming
or panning any panel moves all of them together (`setXLink`). Every classified
event is a coloured vertical line across all panels plus a hoverable dot in the
event lane. All data/HRV/classification logic lives in `loader`, `metrics` and
`model` (pure); this file only puts the arrays on screen.
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
from PySide6.QtWidgets import (
    QApplication,
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
from ..loader import SessionData, SessionInfo, list_sessions, load_session
from ..plot import _ROW_LABELS
from .model import (
    EventMarker,
    HrPlotModel,
    HrvPlotModel,
    axis_bounds,
    default_region,
    event_markers,
    hr_plot_model,
    hrv_plot_model,
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

        open_btn = QPushButton("Open .sqlite...")
        open_btn.clicked.connect(self._choose_file)

        self._session_box = QComboBox()
        self._session_box.setMinimumWidth(320)
        self._session_box.currentIndexChanged.connect(self._on_session_changed)
        self._session_box.setEnabled(False)

        self._export_view_btn = QPushButton("Export view...")
        self._export_view_btn.clicked.connect(lambda: self._export(selection=False))
        self._export_sel_btn = QPushButton("Export selection...")
        self._export_sel_btn.clicked.connect(lambda: self._export(selection=True))
        for b in (self._export_view_btn, self._export_sel_btn):
            b.setEnabled(False)

        top = QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(QLabel("Session:"))
        top.addWidget(self._session_box)
        top.addStretch(1)
        top.addWidget(self._export_view_btn)
        top.addWidget(self._export_sel_btn)

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

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(self._glw, 1)
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
            self._clear_panels()
            self._region = None
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

        hr = hr_plot_model(data)
        hrv = hrv_plot_model(data, window=self._rmssd_window)
        markers = event_markers(data)

        self._p_hr.setTitle(hr.title)
        if hr.has_data:
            self._p_hr.plot(hr.t_s, hr.hr_bpm, pen=_HR_PEN)
        if hrv.has_data:
            # RMSSD is NaN before the first full window; skip those gaps.
            self._p_hrv.plot(hrv.t_s, hrv.rmssd_ms, pen=_HRV_PEN, connect="finite")

        self._draw_events(markers)

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
