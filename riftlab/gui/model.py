"""Pure SessionData -> plot-model transforms (no Qt, fully testable).

The GUI wiring stays thin: it calls these functions to turn loaded data into
plain value objects, then hands the arrays to pyqtgraph. Keeping the transform
here means the interesting logic is unit-tested without spinning up Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..loader import SessionData, SessionInfo
from ..metrics import rolling_rmssd
from ..plot import _EVENT_DEF, _ROWS, _norm, classify


@dataclass(frozen=True)
class HrPlotModel:
    """Everything a plot needs to draw the HR curve of one session."""
    t_s: np.ndarray          # seconds since session start
    hr_bpm: np.ndarray
    title: str
    x_label: str
    y_label: str

    @property
    def has_data(self) -> bool:
        return self.t_s.size > 0


@dataclass(frozen=True)
class HrvPlotModel:
    """HRV (rolling RMSSD) curve for one session, aligned to rr_t[1:]."""
    t_s: np.ndarray
    rmssd_ms: np.ndarray
    window: int
    x_label: str
    y_label: str

    @property
    def has_data(self) -> bool:
        return self.t_s.size > 0


@dataclass(frozen=True)
class EventMarker:
    """One classified game event, ready to draw as a coloured vertical marker.

    `row`/`row_label` place it on the event lane (same layout as plot.py); `tip`
    is the hover tooltip text.
    """
    t_s: float
    key: str
    color: str
    row: int
    row_label: str
    tip: str


def session_label(info: SessionInfo) -> str:
    """Human-readable dropdown label for a session (index + start time).

    The started_utc is trimmed to `YYYY-MM-DD HH:MM:SS`; the pseudonymous
    participant_id is shown (never a Riot id), so the label stays anonymous.
    """
    idx = "?" if info.session_index is None else str(info.session_index)
    who = info.participant_id or "anonymous"
    when = info.started_utc[:19].replace("T", " ")
    return f"#{idx} - {who} - {when}"


def hr_plot_model(data: SessionData) -> HrPlotModel:
    """Build the HR plot model from a loaded session (pure)."""
    who = data.participant_id or "anonymous"
    sess = "" if data.session_index is None else f" - session {data.session_index}"
    title = f"RiftLab - {who}{sess} - {data.started_utc[:19].replace('T', ' ')}"
    return HrPlotModel(
        t_s=data.hr_t,
        hr_bpm=data.hr_bpm,
        title=title,
        x_label="Time since session start (s)",
        y_label="Heart rate (bpm)",
    )


def hrv_plot_model(data: SessionData, window: int = 10) -> HrvPlotModel:
    """Build the HRV (rolling RMSSD) plot model (pure).

    RMSSD is aligned to rr_t[1:] (one value per successive RR difference), so
    both arrays share length and can be plotted directly.
    """
    rmssd = rolling_rmssd(data.rr_ms, window=window)
    t = data.rr_t[1:] if rmssd.size else np.empty(0)
    return HrvPlotModel(
        t_s=t,
        rmssd_ms=rmssd,
        window=window,
        x_label="Time since session start (s)",
        y_label=f"HRV RMSSD (ms, window {window})",
    )


def event_markers(data: SessionData,
                  active_player: Optional[str] = None) -> list[EventMarker]:
    """Classify the session's events into drawable markers (pure).

    Kill/death/assist are split relative to the active player exactly as the
    matplotlib viewer does (reuses `plot.classify`); unclassifiable events are
    dropped. Ordered by time.
    """
    active_norm = _norm(active_player or data.active_riot_id or data.participant_id)
    markers: list[EventMarker] = []
    for ev in sorted(data.events, key=lambda e: e.t_s):
        key = classify(ev, active_norm)
        if key is None:
            continue
        row_name, color, _emoji, label = _EVENT_DEF[key]
        gt = "" if ev.game_time_s is None else f"\ngame time {ev.game_time_s:.0f}s"
        markers.append(EventMarker(
            t_s=ev.t_s,
            key=key,
            color=color,
            row=_ROWS[row_name],
            row_label=label,
            tip=f"{label}\nt = {ev.t_s:.1f}s{gt}",
        ))
    return markers
