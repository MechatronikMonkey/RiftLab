# RiftLab

RiftLab is the desktop viewer for sessions recorded by **RiftRec**. It reads a
recorded `.sqlite` file and shows the **heart rate**, the **HRV** (rolling
RMSSD) and a **League-of-Legends event timeline** on one shared time axis, so
you can see how the player's physiology reacts over the course of a match.
RiftLab knows RiftRec only through the SQLite session contract
(`RiftRec/riftrec/storage/schema.sql`) and imports no RiftRec code — the two
tools are coupled only by the file format.

---

# User guide (Windows)

Two steps: **start** the viewer, then **open** a recorded session file.

## 1 · Start the viewer

Open the **`RiftLab`** folder and double-click **`Start RiftLab.bat`**.

Windows may show a security warning because the file is not signed — untick
*"Always ask before opening this file"* and click **Run**. On the very first
launch RiftLab installs what it needs, which takes a moment (needs internet);
later launches start immediately. The window opens **empty** — that is correct,
you pick the file to view yourself in the next step.

## 2 · Open a session file

Click **`Open .sqlite...`** (top left) and choose a recording. These are the
`.sqlite` files that RiftRec wrote into its storage folder (one file can hold
several matches). If the file contains more than one session, pick the one you
want from the **Session** dropdown next to the button — you can also step
through them with **Page Up / Page Down**.

Once a session is loaded you see three stacked panels sharing one time axis:

- **Heart rate (bpm)** — the red curve.
- **HRV RMSSD (ms)** — the blue curve. It reacts slowly and reflects the
  overall stress/recovery level, *not* single events; a single dropped beat can
  spike it, which is why the scale ignores such outliers. You can change how
  many beats it averages over with the **HRV window** box at the top (small =
  responsive but noisy, large = smooth).
- **LoL events** — coloured dots per game event (your deaths/kills/assists,
  enemy kills, objectives, structures, …), one row per category. The **legend**
  under the panels explains the colours. Every event is also a dashed vertical
  line across all three panels, so you can read the physical reaction to it.
  Hover a dot to see the event details.

A **metadata line** under the toolbar shows participant, session, start time,
duration and event count. Move the mouse over the panels and a **crosshair**
follows it, with a readout (top right) of the time and the HR / RMSSD value at
that moment.

## 3 · Zoom, pan and read the data

All three panels are linked on the time axis, so **any** zoom or pan moves all
of them together:

- **Mouse wheel** over a panel — zoom in / out on time.
- **Left-click + drag** — pan (move the view).
- **Right-click + drag** — stretch or squeeze the axes.
- **Right-click → View All**, or press **Ctrl+0** — reset back to the full
  session.

## 4 · Select a section and export a picture

The **blue band** in the heart-rate panel marks a time window:

- **Drag the middle** of the band to move it to another part of the match.
- **Drag either edge** to make the window wider or narrower.

Then export a PNG image (a save dialog asks where to put it):

- **`Export view...`** (or **Ctrl+E**) — saves exactly what is currently on
  screen (all three panels at the current zoom).
- **`Export selection...`** (or **Ctrl+Shift+E**) — saves just the window
  marked by the blue band. The view jumps back to normal afterwards.

The blue band itself is hidden in the exported image.

### Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Open a `.sqlite` file |
| `Ctrl+E` | Export the current view |
| `Ctrl+Shift+E` | Export the selected window |
| `Ctrl+0` | Reset zoom to the full session |
| `Page Up` / `Page Down` | Previous / next session in the file |

---

# For developers

RiftLab reuses a tested, pure data layer (`loader` → `SessionData`,
`metrics.rolling_rmssd`, `plot.classify`). There are two front-ends on top of
it: the interactive `gui` (PySide6 + pyqtgraph) and the static matplotlib
`plot` (for report PNGs / CLI). The interesting logic lives in pure, unit-tested
functions in `riftlab/gui/model.py`; the Qt window is thin wiring.

## Setup & run

```
pip install -r requirements.txt

# Interactive viewer (what Start RiftLab.bat runs)
python -m riftlab gui                     # empty window; open a file inside
python -m riftlab gui path/to/session.sqlite

# Static matplotlib chart — window, or headless PNG with --out
python -m riftlab plot path/to/session.sqlite
python -m riftlab plot path/to/session.sqlite --out chart.png

# Specific session id (otherwise the most recently started one)
python -m riftlab plot session.sqlite --session <uuid>

# Split kill/death/assist by the player's Riot name
python -m riftlab plot session.sqlite --active-player "Name#TAG"
```

Create a test DB without a match/hardware (from the RiftRec directory):

```
python -m riftrec record --source fake --seconds 60 --db demo.sqlite
```

> **pyside6 >= 6.9.3 is required.** PySide6 6.9.1 has a shiboken bug where
> pyqtgraph items are never anchored in the ViewBox (curves and markers render
> in the wrong place and do not track zoom). See the pin in `requirements.txt`.

## Layout

- `riftlab/loader.py` — reads the SQLite contract into arrays; `t_s` = seconds
  since session start (from `mono_ns - session.mono_anchor_ns`)
- `riftlab/metrics.py` — HRV (rolling RMSSD) from RR intervals
- `riftlab/plot.py` — matplotlib figure (HR, HRV, LoL event timeline)
- `riftlab/gui/` — interactive PySide6 + pyqtgraph viewer (`model.py` = pure
  SessionData→plot transforms, `app.py` = the Qt window)
- `riftlab/assets/events/` — PNG event icons (emoji fallback if missing)
- `riftlab/cli.py` — `python -m riftlab plot ...` / `... gui ...`
- `tests/` — `test_loader.py` (contract DB, proves the decoupling) and
  `test_gui_model.py` (the pure GUI transforms)

Tests: `PYTHONPATH=. python -m pytest tests/`.
