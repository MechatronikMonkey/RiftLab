"""Demo viewer: heart rate, HRV and a League-of-Legends event timeline (EW-31/36).

Three stacked axes sharing one time axis:
1. Heart rate
2. HRV (rolling RMSSD)
3. LoL event timeline with an icon per event, laid out in rows by category
   (your death / your kills / enemy kills / highlights / objectives /
   structures / game).

Every event is also drawn as a coloured vertical line across all three panels,
so the physiological reaction to an event can be read off directly.

Icons are loaded as PNGs from riftlab/assets/events/<key>.png; if a PNG is
missing the viewer falls back to an emoji automatically. `ChampionKill` is
split into kill / death / assist relative to the active player.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .loader import EventMark, SessionData
from .metrics import rolling_rmssd

_ASSET_DIR = Path(__file__).parent / "assets" / "events"
_EMOJI_FONT = "Segoe UI Emoji"

# Timeline rows. y position (0 = bottom, higher = up); combat events are split
# across several rows so their icons do not crowd each other.
_ROWS = {
    "death": 6, "selfkill": 5, "otherkill": 4, "highlight": 3,
    "obj": 2, "struct": 1, "spiel": 0,
}
# by y index 0..6:
_ROW_LABELS = ["Game", "Structures", "Objectives", "Highlights",
               "Enemy kills", "Your kills", "Your death"]

# key -> (row, colour, emoji fallback, label)
_EVENT_DEF: dict[str, tuple[str, str, str, str]] = {
    "death":      ("death",    "#d62728", "\U0001F480", "Death"),
    "kill":       ("selfkill", "#2ca02c", "⚔", "Kill"),
    "assist":     ("selfkill", "#7fbf7f", "\U0001F91D", "Assist"),
    "otherkill":  ("otherkill","#999999", "\U0001F5E1", "Enemy kill"),
    "firstblood": ("highlight","#d62728", "\U0001FA78", "First Blood"),
    "multikill":  ("highlight","#e377c2", "\U0001F525", "Multikill"),
    "ace":        ("highlight","#e377c2", "⭐", "Ace"),
    "dragon":     ("obj",   "#2ca02c", "\U0001F409", "Dragon"),
    "elder":      ("obj",   "#17becf", "\U0001F409", "Elder dragon"),
    "baron":      ("obj",   "#9467bd", "\U0001F451", "Baron"),
    "herald":     ("obj",   "#8c564b", "\U0001F441", "Herald"),
    "grubs":      ("obj",   "#8c564b", "\U0001F41B", "Void grubs"),
    "turret":     ("struct","#ff7f0e", "\U0001F3F0", "Turret"),
    "inhibitor":  ("struct","#ff7f0e", "\U0001F537", "Inhibitor"),
    "gamestart":  ("spiel", "#7f7f7f", "\U0001F3C1", "Start"),
    "gameend":    ("spiel", "#7f7f7f", "\U0001F3C6", "End"),
}

# Riot API EventName -> key (ChampionKill/DragonKill are handled separately).
_SIMPLE_MAP = {
    "FirstBlood": "firstblood", "Multikill": "multikill", "Ace": "ace",
    "BaronKill": "baron", "HeraldKill": "herald", "HordeKill": "grubs",
    "TurretKilled": "turret", "FirstBrick": "turret", "InhibKilled": "inhibitor",
    "GameStart": "gamestart", "GameEnd": "gameend",
}


def _norm(name: Optional[str]) -> str:
    """Normalise a Riot name to the lowercased game name (drop the #TAG)."""
    return (name or "").split("#")[0].strip().lower()


def classify(ev: EventMark, active_norm: str) -> Optional[str]:
    """Map an event to an icon key, or None if it should not be marked."""
    et = ev.event_type
    if et == "ChampionKill":
        p = ev.payload
        if active_norm and _norm(p.get("VictimName")) == active_norm:
            return "death"
        if active_norm and _norm(p.get("KillerName")) == active_norm:
            return "kill"
        if active_norm and active_norm in {_norm(a) for a in (p.get("Assisters") or [])}:
            return "assist"
        return "otherkill"
    if et == "DragonKill":
        return "elder" if _norm(ev.payload.get("DragonType")) == "elder" else "dragon"
    return _SIMPLE_MAP.get(et)


def _load_icon(key: str):
    """Load the PNG for a key (or None to fall back to an emoji)."""
    import matplotlib.pyplot as plt

    path = _ASSET_DIR / f"{key}.png"
    if path.exists():
        try:
            return plt.imread(path)
        except Exception:
            return None
    return None


def _place_icon(ax, x: float, y: float, key: str, target_px: int = 20) -> None:
    from matplotlib.offsetbox import AnnotationBbox, OffsetImage

    _row, color, emoji, _label = _EVENT_DEF[key]
    img = _load_icon(key)
    if img is not None:
        zoom = target_px / img.shape[0]
        ab = AnnotationBbox(OffsetImage(img, zoom=zoom), (x, y),
                            frameon=False, pad=0.0, zorder=5)
        ax.add_artist(ab)
    else:
        ax.text(x, y, emoji, fontfamily=_EMOJI_FONT, fontsize=11,
                ha="center", va="center", color=color, zorder=5)


def make_figure(data: SessionData, rmssd_window: int = 10,
                active_player: Optional[str] = None):
    import matplotlib.pyplot as plt

    # active_riot_id is used only to classify kill/death/assist below - it is
    # never rendered on the figure (title/labels stay on the pseudonymous
    # participant_id, see `who` further down) so the chart itself stays anonymous.
    active_norm = _norm(active_player or data.active_riot_id or data.participant_id)

    fig, (ax_hr, ax_hrv, ax_ev) = plt.subplots(
        3, 1, sharex=True, figsize=(13, 10),
        gridspec_kw={"height_ratios": [2.0, 1.2, 2.6]},
    )

    # -- Heart rate (no legend entry - the red line is self-explanatory) --
    if data.hr_t.size:
        ax_hr.plot(data.hr_t, data.hr_bpm, color="#c0392b", lw=1.6)
    ax_hr.set_ylabel("Heart rate (bpm)")
    ax_hr.grid(True, alpha=0.25)

    # -- HRV (rolling RMSSD) ---------------------------------------------
    rmssd = rolling_rmssd(data.rr_ms, window=rmssd_window)
    if rmssd.size:
        ax_hrv.plot(data.rr_t[1:], rmssd, color="#2c7fb8", lw=1.4,
                    label=f"RMSSD (window {rmssd_window})")
        ax_hrv.legend(loc="upper right", fontsize=8)
    ax_hrv.set_ylabel("HRV RMSSD (ms)")
    ax_hrv.grid(True, alpha=0.25)

    # -- Event timeline + vertical markers across ALL three panels -------
    # Stagger events that fall close together in the same row vertically, so
    # their icons do not overlap - the x position (time) stays exact.
    xspan = max(data.duration_s, 1.0)
    min_dt = 0.02 * xspan   # min spacing ~ icon width in data coordinates
    dy = 0.24
    row_lanes: dict[str, list[float]] = {}
    for ev in sorted(data.events, key=lambda e: e.t_s):
        key = classify(ev, active_norm)
        if key is None:
            continue
        row, color, _emoji, _label = _EVENT_DEF[key]
        for ax in (ax_hr, ax_hrv, ax_ev):
            ax.axvline(ev.t_s, color=color, ls="--", lw=1.0, alpha=0.45, zorder=1)
        lanes = row_lanes.setdefault(row, [])
        lane_idx = next((i for i, lx in enumerate(lanes) if ev.t_s - lx >= min_dt), None)
        if lane_idx is None:
            lanes.append(ev.t_s)
            lane_idx = len(lanes) - 1
        else:
            lanes[lane_idx] = ev.t_s
        _place_icon(ax_ev, ev.t_s, _ROWS[row] + min(lane_idx, 2) * dy, key)

    ax_ev.set_yticks(list(range(len(_ROW_LABELS))))
    ax_ev.set_yticklabels(_ROW_LABELS, fontsize=9)
    ax_ev.set_ylim(-0.6, 6.8)
    ax_ev.set_ylabel("LoL events")
    ax_ev.set_xlabel("Time since session start (s)")
    ax_ev.grid(True, axis="x", alpha=0.2)

    who = data.participant_id or "anonymous"
    sess = f" · session {data.session_index}" if data.session_index is not None else ""
    fig.suptitle(f"RiftLab — {who}{sess} · {data.started_utc[:19]}", fontsize=12)
    fig.tight_layout()
    return fig


def render_to_file(data: SessionData, out_path: str, rmssd_window: int = 10,
                   active_player: Optional[str] = None) -> None:
    import matplotlib
    matplotlib.use("Agg")  # headless: no window needed
    fig = make_figure(data, rmssd_window=rmssd_window, active_player=active_player)
    fig.savefig(out_path, dpi=120)


def show(data: SessionData, rmssd_window: int = 10,
         active_player: Optional[str] = None) -> None:
    import matplotlib.pyplot as plt
    make_figure(data, rmssd_window=rmssd_window, active_player=active_player)
    plt.show()
