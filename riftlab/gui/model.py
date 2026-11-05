"""Pure SessionData -> plot-model transforms (no Qt, fully testable).

The GUI wiring stays thin: it calls these functions to turn loaded data into
plain value objects, then hands the arrays to pyqtgraph. Keeping the transform
here means the interesting logic is unit-tested without spinning up Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from ..loader import SessionData, SessionInfo, default_session
from ..metrics import rolling_rmssd
from ..plot import (
    _EVENT_DEF, _ROWS, GapBand, RestBand, _norm, classify, gap_bands, rest_bands,
)

# What a between-match (idle, schema 5) recording is called on screen.
IDLE_LABEL = "between matches"

# RMSSD rolling-window bounds offered by the GUI spinbox.
RMSSD_WINDOW_MIN = 3
RMSSD_WINDOW_MAX = 60


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


def format_duration(seconds: float) -> str:
    """Seconds as M:SS, or H:MM:SS once it passes an hour."""
    s = int(round(max(seconds, 0.0)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def session_header(data: SessionData) -> str:
    """One-line metadata summary for the header bar (pure).

    Shows the pseudonymous participant plus start time, duration and event
    count; the active Riot name is appended only if known (it stays out of the
    plot title/export, which remain anonymous - this label is not exported).
    """
    who = data.participant_id or "anonymous"
    parts = [f"Participant {who}"]
    if data.is_idle:
        parts.append(IDLE_LABEL)
    elif data.session_index is not None:
        parts.append(f"session {data.session_index}")
    parts.append(data.started_utc[:19].replace("T", " "))
    parts.append(f"duration {format_duration(data.duration_s)}")
    if not data.is_idle:            # an idle recording has no game data at all
        parts.append(f"{len(data.events)} events")
    if data.active_riot_id:
        parts.append(f"active: {data.active_riot_id}")
    return "   ·   ".join(parts)


def legend_entries() -> list[tuple[str, str]]:
    """(label, colour) for each distinct event type, in display order (pure)."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for _row, color, _emoji, label in _EVENT_DEF.values():
        if label not in seen:
            seen.add(label)
            out.append((label, color))
    return out


def nearest_value(t: np.ndarray, v: np.ndarray, x: float) -> Optional[float]:
    """Value of series (t, v) at the sample nearest to time x, or None.

    Returns None if the series is empty or x lies outside its time span, so a
    readout only shows a number where data actually exists.
    """
    t = np.asarray(t, dtype=float)
    if t.size == 0 or x < t[0] or x > t[-1]:
        return None
    i = int(np.argmin(np.abs(t - x)))
    val = float(np.asarray(v, dtype=float)[i])
    return None if np.isnan(val) else val


def clock_time(stamp: Optional[str], utc_offset_min: Optional[int]) -> Optional[str]:
    """An ISO-8601 UTC stamp as `HH:MM` wall-clock time, or None if unusable.

    Shifted by `utc_offset_min` (minutes east of UTC) when it is known - that
    is the time the participant saw on the clock. Without it the UTC time is
    returned unchanged; the caller says so, since an hour's difference is
    exactly the kind of error nobody notices.
    """
    if not stamp:
        return None
    try:
        t = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc)
    if utc_offset_min is not None:
        t += timedelta(minutes=utc_offset_min)
    return t.strftime("%H:%M")


def session_label(info: SessionInfo) -> str:
    """Human-readable dropdown label for a session (pure).

    A match shows index + start time, trimmed to `YYYY-MM-DD HH:MM:SS` (local
    time when the file carries the offset, schema 5; UTC before that); the
    pseudonymous participant_id is shown (never a Riot id), so the label stays
    anonymous. A between-match recording shows its clock span instead -
    local time when the file says what that is, otherwise UTC, marked as such.
    """
    if info.is_idle:
        start = clock_time(info.started_utc, info.utc_offset_min)
        end = clock_time(info.ended_utc, info.utc_offset_min)
        if start is None:
            span = info.started_utc or "?"
        elif end is None:
            span = f"from {start}"           # not closed (yet)
        else:
            span = f"{start}–{end}"
        zone = "" if info.utc_offset_min is not None else " UTC"
        return f"{IDLE_LABEL} · {span}{zone}"
    idx = "?" if info.session_index is None else str(info.session_index)
    who = info.participant_id or "anonymous"
    when = info.started_utc[:19].replace("T", " ")
    if info.utc_offset_min is not None:
        # Same clock as the between-match rows next to it in the dropdown:
        # a match at "09:03" between idle stretches at "11:03" reads as wrong.
        try:
            t = datetime.fromisoformat(info.started_utc)
            if t.tzinfo is not None:
                t = t.astimezone(timezone.utc)
            when = (t + timedelta(minutes=info.utc_offset_min)).strftime(
                "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return f"#{idx} - {who} - {when}"


def default_session_index(infos: list[SessionInfo]) -> int:
    """Position of `loader.default_session` in a listed file, -1 if empty.

    The dropdown opens on the latest match, the same session the CLI shows
    without --session.
    """
    pick = default_session(infos)
    return -1 if pick is None else infos.index(pick)


def hr_plot_model(data: SessionData) -> HrPlotModel:
    """Build the HR plot model from a loaded session (pure)."""
    who = data.participant_id or "anonymous"
    if data.is_idle:
        sess = f" - {IDLE_LABEL}"
    else:
        sess = "" if data.session_index is None else f" - session {data.session_index}"
    title = f"RiftLab - {who}{sess} - {data.started_utc[:19].replace('T', ' ')}"
    return HrPlotModel(
        t_s=data.hr_t,
        hr_bpm=data.hr_bpm,
        title=title,
        x_label="Time since session start (s)",
        y_label="Heart rate (bpm)",
    )


def default_region(duration_s: float, frac: float = 0.3) -> tuple[float, float]:
    """A centred default selection window covering `frac` of the session.

    e.g. frac=0.3 selects the middle 30% (35%..65%) of the timeline; used to
    seed the export-region so it starts on-screen rather than at zero width.
    """
    d = max(float(duration_s), 1.0)
    half = d * max(min(frac, 1.0), 0.0) / 2.0
    mid = d / 2.0
    return (mid - half, mid + half)


def axis_bounds(values: np.ndarray,
                robust: bool = False) -> Optional[tuple[float, float]]:
    """Y-axis (lo, hi) for a series, or None if it has no finite values.

    With `robust=True` the bounds come from the 2nd/98th percentile instead of
    the raw min/max, so a single artefact spike (common in RMSSD from a dropped
    RR interval) does not flatten the whole curve - the spike simply runs off
    the top of the panel. Falls back to min/max if percentiles collapse.
    """
    v = np.asarray(values, dtype=float)
    finite = v[np.isfinite(v)]
    if finite.size == 0:
        return None
    if robust and finite.size >= 5:
        lo, hi = (float(x) for x in np.percentile(finite, [2, 98]))
    else:
        lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:  # flat (or robust-collapsed) series: give breathing room
        return (lo - 1.0, hi + 1.0)
    return (lo, hi)


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
