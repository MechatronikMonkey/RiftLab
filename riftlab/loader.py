"""Liest eine RiftRec-SQLite-Session in speicherfreundliche Arrays.

Der gemeinsame Zeitnenner ist `t_s` = Sekunden seit Session-Start, abgeleitet
aus `mono_ns - session.mono_anchor_ns`. Dieselbe Uhr fuer HR, RR und Events
macht die Streams direkt uebereinanderlegbar (der "Merge" ist hier ein Join).
"""

from __future__ import annotations

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


@dataclass
class SessionData:
    session_id: str
    participant_id: Optional[str]
    session_index: Optional[int]
    started_utc: str
    schema_version: int
    hr_t: np.ndarray          # Sekunden seit Start
    hr_bpm: np.ndarray
    rr_t: np.ndarray          # Sekunden seit Start
    rr_ms: np.ndarray
    events: list[EventMark] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        candidates = [arr[-1] for arr in (self.hr_t, self.rr_t) if arr.size]
        candidates += [e.t_s for e in self.events]
        return max(candidates) if candidates else 0.0


def load_session(db_path: str | Path, session_id: Optional[str] = None) -> SessionData:
    """Laedt eine Session. Ohne `session_id` wird die zuletzt gestartete genommen."""
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
            raise ValueError(f"Keine Session in {db_path} gefunden")

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

        events = [
            EventMark(
                t_s=(r["mono_ns"] - anchor) / 1e9,
                event_type=r["event_type"],
                game_time_s=r["game_time_s"],
            )
            for r in conn.execute(
                "SELECT mono_ns, event_type, game_time_s FROM game_event "
                "WHERE session_id=? ORDER BY mono_ns",
                (sid,),
            ).fetchall()
        ]

        return SessionData(
            session_id=sid,
            participant_id=row["participant_id"],
            session_index=row["session_index"],
            started_utc=row["started_utc"],
            schema_version=row["schema_version"],
            hr_t=hr_t, hr_bpm=hr_bpm, rr_t=rr_t, rr_ms=rr_ms, events=events,
        )
    finally:
        conn.close()
