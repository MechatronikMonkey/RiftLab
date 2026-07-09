"""Tests for the pure GUI plot-model transform and session listing.

No Qt is imported here - the interesting logic (SessionData -> plot model,
dropdown labels, session enumeration) is exercised without spinning up a window.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import numpy as np

from riftlab.gui.model import hr_plot_model, session_label
from riftlab.loader import SessionData, SessionInfo, list_sessions

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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK - {name}")
    print("OK - all gui model tests passed")
