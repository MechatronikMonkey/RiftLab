"""Loader-/Metrik-Tests gegen eine handgeschriebene Vertrags-DB.

Baut das RiftRec-Schema und ein paar Zeilen per rohem SQL nach - ganz ohne
RiftRec-Import. Damit ist bewiesen, dass RiftLab die Session allein ueber den
SQLite-Vertrag liest (die einzige Kopplung zwischen den beiden Repos).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import numpy as np

from riftlab.loader import load_session
from riftlab.metrics import rolling_rmssd

_SCHEMA = """
CREATE TABLE session (session_id TEXT PRIMARY KEY, participant_id TEXT,
  session_index INTEGER, started_utc TEXT, ended_utc TEXT, mono_anchor_ns INTEGER,
  app_version TEXT, schema_version INTEGER, notes TEXT);
CREATE TABLE hr_sample (session_id TEXT, mono_ns INTEGER, utc TEXT, hr_bpm INTEGER);
CREATE TABLE rr_interval (session_id TEXT, mono_ns INTEGER, utc TEXT, rr_ms REAL);
CREATE TABLE game_event (session_id TEXT, mono_ns INTEGER, utc TEXT, game_time_s REAL,
  event_id INTEGER, event_type TEXT, payload_json TEXT);
CREATE TABLE game_snapshot (session_id TEXT, mono_ns INTEGER, utc TEXT, game_time_s REAL,
  kills INTEGER, deaths INTEGER, assists INTEGER, cs INTEGER, gold REAL, level INTEGER);
CREATE TABLE gap (session_id TEXT, source TEXT, start_utc TEXT, end_utc TEXT);
"""


def _make_db(path: Path) -> str:
    sid = "sess-1"
    anchor = 1_000_000_000  # ns
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)",
                 (sid, "P01", 3, "2026-07-06T10:00:00+00:00", "2026-07-06T10:05:00+00:00",
                  anchor, "0.1.0", 1, None))
    # HR bei t = 0,1,2 s ; RR passend
    for i, hr in enumerate((80, 82, 84)):
        mono = anchor + i * 1_000_000_000
        conn.execute("INSERT INTO hr_sample VALUES (?,?,?,?)", (sid, mono, "u", hr))
        conn.execute("INSERT INTO rr_interval VALUES (?,?,?,?)",
                     (sid, mono, "u", 60000.0 / hr))
    # Ein Kill-Event bei t = 1,5 s
    conn.execute("INSERT INTO game_event VALUES (?,?,?,?,?,?,?)",
                 (sid, anchor + 1_500_000_000, "u", 30.0, 1, "ChampionKill", "{}"))
    conn.commit()
    conn.close()
    return sid


def test_load_session_maps_time_and_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "s.sqlite"
        sid = _make_db(db)
        data = load_session(db)

        assert data.session_id == sid
        assert data.participant_id == "P01"
        assert data.session_index == 3
        # t_s relativ zum Anker: 0,1,2
        assert np.allclose(data.hr_t, [0.0, 1.0, 2.0])
        assert np.allclose(data.hr_bpm, [80, 82, 84])
        assert len(data.events) == 1
        assert data.events[0].event_type == "ChampionKill"
        assert abs(data.events[0].t_s - 1.5) < 1e-9
        # duration deckt HR + Events ab
        assert data.duration_s >= 2.0


def test_load_specific_session_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "s.sqlite"
        sid = _make_db(db)
        data = load_session(db, session_id=sid)
        assert data.session_id == sid


def test_rolling_rmssd_shape_and_value() -> None:
    # RR = [1000, 900, 1000] -> diffs [-100, 100] -> RMSSD(window>=2)=100
    out = rolling_rmssd(np.array([1000.0, 900.0, 1000.0]), window=10)
    assert out.size == 2
    assert abs(out[-1] - 100.0) < 1e-9
    assert rolling_rmssd(np.array([1000.0]), window=10).size == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK - {name}")
    print("OK - alle Loader-Tests bestanden")
