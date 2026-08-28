"""Loader/metric tests against a hand-written contract DB.

Recreates the RiftRec schema and a few rows via raw SQL - with no RiftRec
import. This proves that RiftLab reads the session purely through the SQLite
contract (the only coupling between the two repos).
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
    # HR at t = 0,1,2 s ; matching RR
    for i, hr in enumerate((80, 82, 84)):
        mono = anchor + i * 1_000_000_000
        conn.execute("INSERT INTO hr_sample VALUES (?,?,?,?)", (sid, mono, "u", hr))
        conn.execute("INSERT INTO rr_interval VALUES (?,?,?,?)",
                     (sid, mono, "u", 60000.0 / hr))
    # One kill event at t = 1.5 s
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
        # t_s relative to the anchor: 0,1,2
        assert np.allclose(data.hr_t, [0.0, 1.0, 2.0])
        assert np.allclose(data.hr_bpm, [80, 82, 84])
        assert len(data.events) == 1
        assert data.events[0].event_type == "ChampionKill"
        assert abs(data.events[0].t_s - 1.5) < 1e-9
        # duration covers HR + events
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
    print("OK - all loader tests passed")


# -- RiftRec schema v4: gaps and the death timer (EW-61) -------------------

_SCHEMA_V4 = """
CREATE TABLE session (session_id TEXT PRIMARY KEY, participant_id TEXT,
  session_index INTEGER, started_utc TEXT, ended_utc TEXT, mono_anchor_ns INTEGER,
  app_version TEXT, schema_version INTEGER, notes TEXT, active_riot_id TEXT);
CREATE TABLE hr_sample (session_id TEXT, mono_ns INTEGER, utc TEXT, hr_bpm INTEGER,
  contact INTEGER);
CREATE TABLE rr_interval (session_id TEXT, mono_ns INTEGER, utc TEXT, rr_ms REAL);
CREATE TABLE game_event (session_id TEXT, mono_ns INTEGER, utc TEXT, game_time_s REAL,
  event_id INTEGER, event_type TEXT, payload_json TEXT);
CREATE TABLE game_snapshot (session_id TEXT, mono_ns INTEGER, utc TEXT, game_time_s REAL,
  kills INTEGER, deaths INTEGER, assists INTEGER, cs INTEGER, gold REAL, level INTEGER,
  is_dead INTEGER, respawn_timer_s REAL);
CREATE TABLE gap (session_id TEXT, source TEXT, start_utc TEXT, end_utc TEXT);
"""

_START = "2026-08-28T10:00:00+00:00"
_ANCHOR = 1_000_000_000


def _make_v4_db(path: Path, *, with_kill_event: bool = True) -> str:
    """A file the way RiftRec 0.1.0 writes it: one death, one contact gap.

    The death is sampled every 5 s starting 2 s after it happened, so the
    highest timer seen (28.0 s) is lower than the real one (30.0 s) - the bias
    the reconstruction exists to remove.
    """
    sid = "sess-v4"
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_V4)
    conn.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (sid, "P01", 1, _START, "2026-08-28T10:10:00+00:00", _ANCHOR,
                  "0.1.0", 4, None, "Stomper#8252"))

    # Killed at game clock 100.0 s; first snapshot 2 s later shows 28 s left.
    if with_kill_event:
        conn.execute(
            "INSERT INTO game_event VALUES (?,?,?,?,?,?,?)",
            (sid, _ANCHOR + 100_000_000_000, "u", 100.0, 1, "ChampionKill",
             '{"EventName": "ChampionKill", "EventTime": 100.0, '
             '"VictimName": "Stomper", "KillerName": "p_abc"}'))

    for i, (gt, timer) in enumerate([(102.0, 28.0), (107.0, 23.0), (112.0, 18.0)]):
        conn.execute(
            "INSERT INTO game_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, _ANCHOR + int(gt * 1e9), "u", gt, 0, 1, 0, 10, 500.0, 5, 1, timer))
    # alive again
    conn.execute(
        "INSERT INTO game_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, _ANCHOR + int(117 * 1e9), "u", 117.0, 0, 1, 0, 11, 520.0, 5, 0, 0.0))

    conn.execute("INSERT INTO gap VALUES (?,?,?,?)",
                 (sid, "h10_contact", "2026-08-28T10:02:00+00:00",
                  "2026-08-28T10:02:30+00:00"))
    conn.execute("INSERT INTO gap VALUES (?,?,?,?)",
                 (sid, "h10", "2026-08-28T10:09:00+00:00", None))
    conn.commit()
    conn.close()
    return sid


def test_older_files_have_no_gaps_or_deaths_and_still_load() -> None:
    """RiftLab reads every RiftRec version there has ever been. A file written
    before these columns existed must load, not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "old.sqlite"
        _make_db(db)
        data = load_session(db)
        assert data.gaps == []
        assert data.deaths == []
        assert data.hr_t.size == 3        # the rest still works


def test_gaps_are_read_with_times_relative_to_the_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "v4.sqlite"
        _make_v4_db(db)
        gaps = load_session(db).gaps

        assert [g.source for g in gaps] == ["h10_contact", "h10"]
        assert gaps[0].start_t_s == 120.0 and gaps[0].end_t_s == 150.0
        assert "not usable" in gaps[0].label


def test_a_gap_still_open_at_the_end_has_no_end() -> None:
    """The strap dropped and never came back before the match finished."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "v4.sqlite"
        _make_v4_db(db)
        assert load_session(db).gaps[1].end_t_s is None


def test_consecutive_dead_samples_are_one_death() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "v4.sqlite"
        _make_v4_db(db)
        deaths = load_session(db).deaths

        assert len(deaths) == 1
        assert deaths[0].samples == 3


def test_the_respawn_timer_is_corrected_for_the_sampling_lag() -> None:
    """The sampler sees the timer only after the death, so the highest value it
    reports is too low. At a 30 s threshold that decides the classification:
    28.0 s observed would be discarded, 30.0 s actual would be counted."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "v4.sqlite"
        _make_v4_db(db)
        death = load_session(db).deaths[0]

        assert death.observed_timer_s == 28.0
        assert death.timer_s == 30.0          # 28.0 + (102.0 - 100.0)
        assert death.reconstructed is True


def test_without_a_matching_kill_event_the_measurement_is_kept_as_is() -> None:
    """Better an honest 28.0 s flagged as unreconstructed than an invented 30."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "v4.sqlite"
        _make_v4_db(db, with_kill_event=False)
        death = load_session(db).deaths[0]

        assert death.timer_s == death.observed_timer_s == 28.0
        assert death.reconstructed is False


def test_a_riot_name_matches_in_either_spelling() -> None:
    """The same person is written "Name#TAG" in the scoreboard and "Name" in an
    event payload; comparing anything but the normalised form misses."""
    from riftlab.loader import normalise_name

    assert normalise_name("Stomper85#8252") == normalise_name("Stomper85") == "stomper85"
    assert normalise_name(None) == ""
