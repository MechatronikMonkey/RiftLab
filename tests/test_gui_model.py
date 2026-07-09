"""Tests for the pure GUI plot-model transform and session listing.

No Qt is imported here - the interesting logic (SessionData -> plot model,
dropdown labels, session enumeration) is exercised without spinning up a window.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import numpy as np

from riftlab.gui.model import (
    axis_bounds,
    default_region,
    event_markers,
    format_duration,
    hr_plot_model,
    hrv_plot_model,
    legend_entries,
    nearest_value,
    session_header,
    session_label,
)
from riftlab.loader import EventMark, SessionData, SessionInfo, list_sessions

_SCHEMA = """
CREATE TABLE session (session_id TEXT PRIMARY KEY, participant_id TEXT,
  session_index INTEGER, started_utc TEXT, ended_utc TEXT, mono_anchor_ns INTEGER,
  app_version TEXT, schema_version INTEGER, notes TEXT);
CREATE TABLE hr_sample (session_id TEXT, mono_ns INTEGER, utc TEXT, hr_bpm INTEGER);
CREATE TABLE rr_interval (session_id TEXT, mono_ns INTEGER, utc TEXT, rr_ms REAL);
CREATE TABLE game_event (session_id TEXT, mono_ns INTEGER, utc TEXT, game_time_s REAL,
  event_id INTEGER, event_type TEXT, payload_json TEXT);
"""


def _make_multi_session_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    # inserted out of order to prove list_sessions sorts by session_index
    conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)",
                 ("sess-2", "P01", 2, "2026-07-06T11:00:00+00:00", None, 0, "0.1.0", 1, None))
    conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)",
                 ("sess-1", "P01", 1, "2026-07-06T10:00:00+00:00", None, 0, "0.1.0", 1, None))
    conn.commit()
    conn.close()


def test_list_sessions_ordered_by_index() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "multi.sqlite"
        _make_multi_session_db(db)
        infos = list_sessions(db)
        assert [i.session_index for i in infos] == [1, 2]
        assert [i.session_id for i in infos] == ["sess-1", "sess-2"]
        assert infos[0].participant_id == "P01"


def test_session_label_is_anonymous_and_readable() -> None:
    info = SessionInfo(session_id="x", session_index=3, participant_id="P01",
                       started_utc="2026-07-06T17:27:51.637859+00:00")
    label = session_label(info)
    assert label == "#3 - P01 - 2026-07-06 17:27:51"

    # missing index/participant degrade gracefully
    bare = SessionInfo(session_id="x", session_index=None, participant_id=None,
                       started_utc="2026-07-06T17:27:51+00:00")
    assert session_label(bare) == "#? - anonymous - 2026-07-06 17:27:51"


def test_hr_plot_model_carries_curve_and_labels() -> None:
    data = SessionData(
        session_id="x", participant_id="P01", session_index=3,
        started_utc="2026-07-06T17:27:51+00:00", schema_version=1,
        hr_t=np.array([0.0, 1.0, 2.0]), hr_bpm=np.array([80.0, 82.0, 84.0]),
        rr_t=np.empty(0), rr_ms=np.empty(0),
    )
    m = hr_plot_model(data)
    assert m.has_data
    assert np.allclose(m.t_s, [0.0, 1.0, 2.0])
    assert np.allclose(m.hr_bpm, [80, 82, 84])
    assert "P01" in m.title and "session 3" in m.title
    assert m.y_label == "Heart rate (bpm)"


def test_hr_plot_model_empty_session_has_no_data() -> None:
    data = SessionData(
        session_id="x", participant_id=None, session_index=None,
        started_utc="2026-07-06T17:27:51+00:00", schema_version=1,
        hr_t=np.empty(0), hr_bpm=np.empty(0), rr_t=np.empty(0), rr_ms=np.empty(0),
    )
    m = hr_plot_model(data)
    assert not m.has_data
    assert "anonymous" in m.title


def _session_with_events(events: list[EventMark], active: str = "P01") -> SessionData:
    return SessionData(
        session_id="x", participant_id="P01", session_index=1,
        started_utc="2026-07-06T17:27:51+00:00", schema_version=1,
        hr_t=np.empty(0), hr_bpm=np.empty(0),
        rr_t=np.array([0.0, 1.0, 2.0]), rr_ms=np.array([1000.0, 900.0, 1000.0]),
        events=events, active_riot_id=active,
    )


def test_hrv_plot_model_aligns_to_rr_tail() -> None:
    data = _session_with_events([])
    m = hrv_plot_model(data, window=10)
    # RMSSD has len(rr)-1 = 2 values, aligned to rr_t[1:]
    assert m.has_data
    assert m.t_s.size == m.rmssd_ms.size == 2
    assert np.allclose(m.t_s, [1.0, 2.0])
    assert m.window == 10
    assert "window 10" in m.y_label


def test_event_markers_split_kill_death_assist() -> None:
    events = [
        EventMark(t_s=5.0, event_type="ChampionKill", game_time_s=30.0,
                  payload={"VictimName": "P01#EUW"}),        # our death
        EventMark(t_s=2.0, event_type="ChampionKill", game_time_s=10.0,
                  payload={"KillerName": "P01#EUW"}),        # our kill
        EventMark(t_s=8.0, event_type="ChampionKill", game_time_s=50.0,
                  payload={"KillerName": "Foe", "VictimName": "Bar"}),  # enemy kill
    ]
    markers = event_markers(_session_with_events(events), active_player="P01#EUW")
    # ordered by time: kill(2) < death(5) < otherkill(8)
    assert [m.key for m in markers] == ["kill", "death", "otherkill"]
    by_key = {m.key: m for m in markers}
    assert by_key["death"].color == "#d62728"   # red
    assert by_key["kill"].color == "#2ca02c"    # green
    assert by_key["death"].row != by_key["kill"].row
    assert "t = 5.0s" in by_key["death"].tip
    assert "game time 30s" in by_key["death"].tip


def test_axis_bounds_robust_ignores_outlier_spike() -> None:
    # a ~50 ms RMSSD trend with a couple of artefact spikes (<2% of samples,
    # as in a real session of hundreds of RR intervals)
    vals = np.array([50.0] * 200 + [2000.0, 2100.0])
    raw = axis_bounds(vals, robust=False)
    rob = axis_bounds(vals, robust=True)
    assert raw is not None and raw[1] >= 2000.0        # min/max keeps the spike
    assert rob is not None and rob[1] < 200.0          # robust clips it away


def test_axis_bounds_handles_nan_and_empty() -> None:
    assert axis_bounds(np.array([])) is None
    assert axis_bounds(np.array([np.nan, np.nan])) is None
    # NaNs ignored, real values kept
    lo, hi = axis_bounds(np.array([np.nan, 10.0, 20.0]))
    assert (lo, hi) == (10.0, 20.0)
    # flat series gets breathing room instead of a zero-height range
    lo, hi = axis_bounds(np.array([5.0, 5.0, 5.0]))
    assert lo < 5.0 < hi


def test_default_region_centres_a_window() -> None:
    assert default_region(1000.0, frac=0.3) == (350.0, 650.0)
    # always a positive-width window inside [0, duration]
    lo, hi = default_region(1000.0)
    assert 0.0 <= lo < hi <= 1000.0
    # zero/short duration stays valid (falls back to a 1 s span)
    lo, hi = default_region(0.0)
    assert lo < hi


def test_format_duration() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(65) == "1:05"
    assert format_duration(3661) == "1:01:01"


def test_session_header_fields_and_active_player() -> None:
    data = SessionData(
        session_id="x", participant_id="P01", session_index=2,
        started_utc="2026-07-06T17:27:51+00:00", schema_version=1,
        hr_t=np.array([0.0, 90.0]), hr_bpm=np.array([80.0, 82.0]),
        rr_t=np.empty(0), rr_ms=np.empty(0),
        events=[EventMark(t_s=10.0, event_type="GameStart", game_time_s=0.0, payload={})],
        active_riot_id="Player#EUW",
    )
    h = session_header(data)
    assert "P01" in h and "session 2" in h and "2026-07-06 17:27:51" in h
    assert "1:30" in h              # 90 s duration
    assert "1 events" in h
    assert "active: Player#EUW" in h
    # no active id -> the field is omitted
    object.__setattr__(data, "active_riot_id", None)
    assert "active:" not in session_header(data)


def test_legend_entries_deduped_with_colours() -> None:
    entries = legend_entries()
    labels = [lbl for lbl, _ in entries]
    assert len(labels) == len(set(labels))          # no duplicate labels
    assert ("Death", "#d62728") in entries
    assert any(lbl == "Dragon" for lbl, _ in entries)


def test_nearest_value_inside_outside_and_nan() -> None:
    t = np.array([0.0, 1.0, 2.0])
    v = np.array([10.0, 20.0, 30.0])
    assert nearest_value(t, v, 0.9) == 20.0          # nearest sample
    assert nearest_value(t, v, 5.0) is None          # outside span
    assert nearest_value(np.empty(0), np.empty(0), 1.0) is None
    assert nearest_value(t, np.array([np.nan, 20.0, 30.0]), 0.0) is None


def test_event_markers_drops_unclassifiable() -> None:
    events = [EventMark(t_s=1.0, event_type="SomethingUnknown", game_time_s=None,
                        payload={})]
    assert event_markers(_session_with_events(events)) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK - {name}")
    print("OK - all gui model tests passed")
