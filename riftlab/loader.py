"""Reads a RiftRec SQLite session into memory-friendly arrays.

The shared time base is `t_s` = seconds since session start, derived from
`mono_ns - session.mono_anchor_ns`. Using one clock for HR, RR and events makes
the streams directly overlayable (the "merge" is a join here).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class EventMark:
    t_s: float
    event_type: str
    game_time_s: Optional[float]
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Gap:
    """A stretch in which a signal was not usable.

    Reading these before trusting a curve is not optional. An `h10_contact` gap
    is the dangerous kind: the chest strap stayed connected and kept reporting a
    *frozen* heart rate, so the HR curve shows a flat, entirely plausible
    plateau that a reader takes for a calm player. Only the absence of RR
    intervals gives it away, and the recorder writes that finding here.
    """

    source: str                    # 'h10' link down | 'h10_contact' | 'riot'
    start_t_s: float               # seconds since session start
    end_t_s: Optional[float]       # None = still open when the session ended

    @property
    def label(self) -> str:
        return {
            "h10": "no heart rate (strap disconnected)",
            "h10_contact": "strap lost skin contact - values not usable",
            "riot": "no game data",
        }.get(self.source, self.source)


@dataclass(frozen=True)
class DeathEpisode:
    """One death of the recording player, as the 5 s sampler saw it.

    `observed_timer_s` is the highest respawn timer actually sampled, and it is
    systematically too LOW: the first sample lands after the death, by up to one
    sampling interval. `timer_s` corrects that using the exact `EventTime` of
    the matching ChampionKill, and is the number to filter on - at a 30 s
    threshold the difference decides how a death is classified. Measured on the
    28.08.2026 test match: observed 27.3 / 31.8 / 37.7 s, actual 28.4 / 33.5 /
    40.8 s.
    """

    t_s: float                      # first sample that saw the player dead
    game_time_s: Optional[float]
    observed_timer_s: float
    timer_s: float                  # reconstructed; == observed if no event matched
    samples: int
    reconstructed: bool             # False when no ChampionKill could be matched


@dataclass(frozen=True)
class SessionInfo:
    """Lightweight session header for pickers - no sample arrays are read."""
    session_id: str
    session_index: Optional[int]
    participant_id: Optional[str]
    started_utc: str


def list_sessions(db_path: str | Path) -> list[SessionInfo]:
    """List the sessions in a file, ordered by session_index (then start time).

    Reads only the `session` table so a multi-session file can be offered in a
    dropdown without loading every sample.
    """
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT session_id, session_index, participant_id, started_utc "
            "FROM session ORDER BY session_index IS NULL, session_index, started_utc"
        ).fetchall()
        return [
            SessionInfo(
                session_id=r["session_id"],
                session_index=r["session_index"],
                participant_id=r["participant_id"],
                started_utc=r["started_utc"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@dataclass
class SessionData:
    session_id: str
    participant_id: Optional[str]
    session_index: Optional[int]
    started_utc: str
    schema_version: int
    hr_t: np.ndarray          # seconds since start
    hr_bpm: np.ndarray
    rr_t: np.ndarray          # seconds since start
    rr_ms: np.ndarray
    events: list[EventMark] = field(default_factory=list)
    active_riot_id: Optional[str] = None
    gaps: list[Gap] = field(default_factory=list)
    deaths: list[DeathEpisode] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        candidates = [arr[-1] for arr in (self.hr_t, self.rr_t) if arr.size]
        candidates += [e.t_s for e in self.events]
        return max(candidates) if candidates else 0.0


def normalise_name(name: Optional[str]) -> str:
    """A Riot name reduced to its lowercased game name, without the #TAG.

    The same person turns up written two ways: `allPlayers` carries
    "Name#TAG" while an event's Assisters carry the bare game name. Comparing
    anything but the normalised form silently fails to match.
    """
    return (name or "").split("#")[0].strip().lower()


def _columns(conn, table: str) -> set[str]:
    """Columns of `table`, or an empty set when it does not exist.

    RiftLab opens files written by every RiftRec version there has ever been,
    read-only, and cannot migrate them. A missing table or column is therefore
    an ordinary older file, not an error.
    """
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _seconds_since(started_utc: str, stamp: Optional[str]) -> Optional[float]:
    """ISO-8601 stamp as seconds since session start, or None if unusable."""
    if not stamp:
        return None
    try:
        return (datetime.fromisoformat(stamp)
                - datetime.fromisoformat(started_utc)).total_seconds()
    except ValueError:
        return None


def _read_gaps(conn, sid: str, started_utc: str) -> list[Gap]:
    """Stretches the recorder itself marked as not usable."""
    if not _columns(conn, "gap"):
        return []
    out: list[Gap] = []
    for r in conn.execute(
        "SELECT source, start_utc, end_utc FROM gap WHERE session_id=? "
        "ORDER BY start_utc",
        (sid,),
    ):
        start = _seconds_since(started_utc, r["start_utc"])
        if start is None:
            continue
        out.append(Gap(source=r["source"], start_t_s=start,
                       end_t_s=_seconds_since(started_utc, r["end_utc"])))
    return out


# A death sample lands within one snapshot interval (5 s) of the death itself.
# Anything further apart is not the same death, and reconstructing from it would
# invent a timer rather than correct one.
_MAX_DEATH_LAG_S = 8.0


def _own_death_times(events: list[EventMark], active_riot_id: Optional[str]) -> list[float]:
    """Game-clock times at which the recording player was killed."""
    me = normalise_name(active_riot_id)
    if not me:
        return []
    times = [
        ev.payload.get("EventTime")
        for ev in events
        if ev.event_type == "ChampionKill"
        and normalise_name(ev.payload.get("VictimName")) == me
    ]
    return sorted(t for t in times if isinstance(t, (int, float)))


def _read_deaths(conn, sid: str, anchor: int, started_utc: str,
                 events: list[EventMark],
                 active_riot_id: Optional[str]) -> list[DeathEpisode]:
    """Group the dead snapshots into deaths and recover the real respawn timer.

    Consecutive `is_dead` samples are one death. The highest timer seen is
    always too low, because the first sample lands after the death; the exact
    `EventTime` of the matching ChampionKill closes that gap. Where no event
    matches, the observed value is kept and `reconstructed` says so, rather than
    quietly presenting an estimate as a measurement.
    """
    if not {"is_dead", "respawn_timer_s"} <= _columns(conn, "game_snapshot"):
        return []           # written before RiftRec schema v4
    rows = conn.execute(
        "SELECT mono_ns, game_time_s, is_dead, respawn_timer_s FROM game_snapshot "
        "WHERE session_id=? ORDER BY mono_ns",
        (sid,),
    ).fetchall()

    episodes: list[list] = []
    run: list = []
    for r in rows:
        if r["is_dead"]:
            run.append(r)
        elif run:
            episodes.append(run)
            run = []
    if run:
        episodes.append(run)

    killed_at = _own_death_times(events, active_riot_id)
    out: list[DeathEpisode] = []
    for ep in episodes:
        timers = [r["respawn_timer_s"] for r in ep if r["respawn_timer_s"] is not None]
        if not timers:
            continue
        first = ep[0]
        observed = max(timers)
        timer, reconstructed = observed, False
        game_time = first["game_time_s"]
        if game_time is not None and first["respawn_timer_s"] is not None:
            before = [t for t in killed_at if t <= game_time]
            if before and 0.0 <= game_time - before[-1] <= _MAX_DEATH_LAG_S:
                timer = first["respawn_timer_s"] + (game_time - before[-1])
                reconstructed = True
        out.append(DeathEpisode(
            t_s=(first["mono_ns"] - anchor) / 1e9,
            game_time_s=game_time,
            observed_timer_s=float(observed),
            timer_s=float(timer),
            samples=len(ep),
            reconstructed=reconstructed,
        ))
    return out


def load_session(db_path: str | Path, session_id: Optional[str] = None) -> SessionData:
    """Load a session. Without `session_id` the most recently started one is used."""
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        if session_id is None:
            row = conn.execute(
                "SELECT * FROM session ORDER BY started_utc DESC LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM session WHERE session_id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"No session found in {db_path}")

        sid = row["session_id"]
        anchor = row["mono_anchor_ns"]

        def _series(table: str, value_col: str) -> tuple[np.ndarray, np.ndarray]:
            rows = conn.execute(
                f"SELECT mono_ns, {value_col} FROM {table} "
                "WHERE session_id=? ORDER BY mono_ns",
                (sid,),
            ).fetchall()
            if not rows:
                return np.empty(0), np.empty(0)
            t = np.fromiter(((r["mono_ns"] - anchor) / 1e9 for r in rows), float, len(rows))
            v = np.fromiter((r[value_col] for r in rows), float, len(rows))
            return t, v

        hr_t, hr_bpm = _series("hr_sample", "hr_bpm")
        rr_t, rr_ms = _series("rr_interval", "rr_ms")

        def _payload(raw: Optional[str]) -> dict:
            if not raw:
                return {}
            try:
                obj = json.loads(raw)
                return obj if isinstance(obj, dict) else {}
            except (ValueError, TypeError):
                return {}

        events = [
            EventMark(
                t_s=(r["mono_ns"] - anchor) / 1e9,
                event_type=r["event_type"],
                game_time_s=r["game_time_s"],
                payload=_payload(r["payload_json"]),
            )
            for r in conn.execute(
                "SELECT mono_ns, event_type, game_time_s, payload_json FROM game_event "
                "WHERE session_id=? ORDER BY mono_ns",
                (sid,),
            ).fetchall()
        ]

        # active_riot_id may be absent on a session table written before this
        # column existed (RiftLab is read-only and cannot migrate the file).
        row_keys = row.keys()
        return SessionData(
            session_id=sid,
            participant_id=row["participant_id"],
            session_index=row["session_index"],
            started_utc=row["started_utc"],
            schema_version=row["schema_version"],
            active_riot_id=row["active_riot_id"] if "active_riot_id" in row_keys else None,
            hr_t=hr_t, hr_bpm=hr_bpm, rr_t=rr_t, rr_ms=rr_ms, events=events,
            gaps=_read_gaps(conn, sid, row["started_utc"]),
            deaths=_read_deaths(conn, sid, anchor, row["started_utc"], events,
                                row["active_riot_id"]
                                if "active_riot_id" in row_keys else None),
        )
    finally:
        conn.close()
