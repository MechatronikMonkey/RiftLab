"""Demo-Viewer: HR- und HRV-Verlauf einer Session mit Event-Markern (EW-31/36).

Zwei gestapelte Achsen mit gemeinsamer Zeitachse (Sekunden seit Start): oben
Herzfrequenz, unten rollierender RMSSD. Game-Events werden als farbige
vertikale Marker ueber beide Achsen gelegt, damit sichtbar wird, wie die
Physiologie auf Spielereignisse reagiert (z. B. HR-Anstieg im Teamfight).
"""

from __future__ import annotations

from typing import Optional

from .loader import SessionData
from .metrics import rolling_rmssd

# Farbcodierung nach Event-Klasse (colorblind-tauglich) + Anzeigelabel.
_EVENT_STYLE: dict[str, tuple[str, str]] = {
    "ChampionKill": ("#d62728", "Kill/Death"),
    "TurretKilled": ("#ff7f0e", "Turm"),
    "InhibKilled": ("#ff7f0e", "Inhibitor"),
    "DragonKill": ("#2ca02c", "Drache"),
    "BaronKill": ("#9467bd", "Baron"),
    "HeraldKill": ("#8c564b", "Herald"),
    "GameStart": ("#7f7f7f", "Start"),
    "GameEnd": ("#7f7f7f", "Ende"),
}
_EVENT_DEFAULT = ("#17becf", "Event")


def _style_for(event_type: str) -> tuple[str, str]:
    return _EVENT_STYLE.get(event_type, _EVENT_DEFAULT)


def make_figure(data: SessionData, rmssd_window: int = 10):
    """Baut die matplotlib-Figure. Rendering/Backend legt der Aufrufer fest."""
    import matplotlib.pyplot as plt

    fig, (ax_hr, ax_hrv) = plt.subplots(
        2, 1, sharex=True, figsize=(12, 7),
        gridspec_kw={"height_ratios": [2, 1]},
    )

    # -- Herzfrequenz -----------------------------------------------------
    if data.hr_t.size:
        ax_hr.plot(data.hr_t, data.hr_bpm, color="#c0392b", lw=1.6, label="HR")
    ax_hr.set_ylabel("Herzfrequenz (bpm)")
    ax_hr.grid(True, alpha=0.25)

    # -- HRV (rollierender RMSSD) ----------------------------------------
    rmssd = rolling_rmssd(data.rr_ms, window=rmssd_window)
    if rmssd.size:
        ax_hrv.plot(data.rr_t[1:], rmssd, color="#2c7fb8", lw=1.4,
                    label=f"RMSSD (Fenster {rmssd_window})")
    ax_hrv.set_ylabel("HRV RMSSD (ms)")
    ax_hrv.set_xlabel("Zeit seit Session-Start (s)")
    ax_hrv.grid(True, alpha=0.25)

    # -- Event-Marker ueber beide Achsen ---------------------------------
    seen: set[str] = set()
    for ev in data.events:
        color, label = _style_for(ev.event_type)
        legend_label = label if label not in seen else None
        seen.add(label)
        for ax in (ax_hr, ax_hrv):
            ax.axvline(ev.t_s, color=color, ls="--", lw=1.1, alpha=0.7,
                       label=legend_label if ax is ax_hr else None)

    handles, labels = ax_hr.get_legend_handles_labels()
    if handles:
        ax_hr.legend(loc="upper right", fontsize=8, ncol=2)

    who = data.participant_id or "anonym"
    sess = f" · Session {data.session_index}" if data.session_index is not None else ""
    fig.suptitle(f"RiftLab — {who}{sess} · {data.started_utc[:19]}", fontsize=12)
    fig.tight_layout()
    return fig


def render_to_file(data: SessionData, out_path: str, rmssd_window: int = 10) -> None:
    import matplotlib
    matplotlib.use("Agg")  # headless: kein Fenster noetig
    fig = make_figure(data, rmssd_window=rmssd_window)
    fig.savefig(out_path, dpi=120)


def show(data: SessionData, rmssd_window: int = 10) -> None:
    import matplotlib.pyplot as plt
    make_figure(data, rmssd_window=rmssd_window)
    plt.show()
