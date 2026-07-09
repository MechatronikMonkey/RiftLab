# RiftLab

Analysis and visualisation of **RiftRec** sessions. RiftLab knows RiftRec only
through the **SQLite session contract** (`RiftRec/riftrec/storage/schema.sql`)
and imports no RiftRec code — the two repos are coupled only by the file format.

## Status (2026-07-06)

Milestone 4 — demo viewer (EW-31/36): plots the heart-rate and HRV trend
(rolling RMSSD) of a session over the match timeline, with a third axis showing
a LoL event timeline (kills/deaths/assists, objectives, structures) as icons.
Shows e.g. the heart-rate rise around teamfights.

## Usage

```
pip install -r requirements.txt

# Window
python -m riftlab plot path/to/session.sqlite

# Headless PNG
python -m riftlab plot path/to/session.sqlite --out chart.png

# Specific session id (otherwise the most recently started one)
python -m riftlab plot session.sqlite --session <uuid>

# Split kill/death/assist by the player's Riot name
python -m riftlab plot session.sqlite --active-player "Name#TAG"
```

Interactive viewer (EW-53) — open a file, pick a session from the dropdown, and
review three X-linked panels (HR, HRV, LoL event lane) with synced zoom/pan;
events show as coloured markers with hover tooltips:

```
python -m riftlab gui                    # choose a file via dialog
python -m riftlab gui path/to/session.sqlite
```

Create a test DB without a match/hardware (from the RiftRec directory):

```
python -m riftrec record --source fake --seconds 60 --db demo.sqlite
```

## Layout

- `riftlab/loader.py` — reads the SQLite contract into arrays; `t_s` = seconds
  since session start (from `mono_ns - session.mono_anchor_ns`)
- `riftlab/metrics.py` — HRV (rolling RMSSD) from RR intervals
- `riftlab/plot.py` — matplotlib figure (HR, HRV, LoL event timeline)
- `riftlab/gui/` — interactive PySide6 + pyqtgraph viewer (`model.py` = pure
  SessionData→plot transform, `app.py` = the Qt window)
- `riftlab/assets/events/` — PNG event icons (emoji fallback if missing)
- `riftlab/cli.py` — `python -m riftlab plot ...`
- `tests/test_loader.py` — against a hand-written contract DB (proves the decoupling)

Tests: `PYTHONPATH=. python tests/test_loader.py` or `python -m pytest tests/`.
