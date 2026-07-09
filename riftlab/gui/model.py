"""Pure SessionData -> plot-model transforms (no Qt, fully testable).

The GUI wiring stays thin: it calls these functions to turn loaded data into
plain value objects, then hands the arrays to pyqtgraph. Keeping the transform
here means the interesting logic is unit-tested without spinning up Qt.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..loader import SessionData, SessionInfo


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
