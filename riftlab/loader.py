"""Reads a RiftRec SQLite session into memory-friendly arrays.

The shared time base is `t_s` = seconds since session start, derived from
`mono_ns - session.mono_anchor_ns`. Using one clock for HR, RR and events makes
the streams directly overlayable (the "merge" is a join here).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class EventMark:
    t_s: float
    event_type: str
    game_time_s: Optional[float]
    payload: dict = field(default_factory=dict)


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

    @property
    def duration_s(self) -> float:
        candidates = [arr[-1] for arr in (self.hr_t, self.rr_t) if arr.size]
        candidates += [e.t_s for e in self.events]
        return max(candidates) if candidates else 0.0


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
        )
    finally:
        conn.close()
