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

## 1 · Install

Download **`RiftLab-Setup-<version>.exe`** from the
[Releases page](https://github.com/MechatronikMonkey/RiftLab/releases) and run it.
That one file is everything — no Python, no pip. Installing needs no administrator
rights: it goes into your own user account and adds a **RiftLab** entry to the Start
menu.

Windows will show **"Windows protected your PC"**, because the build is not
code-signed yet: click **More info**, then **Run anyway**. Some antivirus products
run an unknown installer in a sandbox first, so it can take a while to appear — or
appear **twice**. Clicking through both is harmless.

RiftLab never writes to a recording. It opens `.sqlite` files read-only, and
uninstalling it does not touch them.

> Working *on* RiftLab instead of just using it? Then skip the installer and run
> it from a source checkout — see [For developers](#for-developers) below.

## 2 · Start the viewer

Open the **`RiftLab`** folder and double-click **`Start RiftLab.bat`**.

Windows may show a security warning because the file is not signed — untick
*"Always ask before opening this file"* and click **Run**. On the very first
launch RiftLab installs what it needs, which takes a moment (needs internet);
later launches start immediately. The window opens **empty** — that is correct,
you pick the file to view yourself in the next step.

## 3 · Open a session file

Click **`Open .sqlite...`** (top left) and choose a recording. These are the
`.sqlite` files that RiftRec wrote into its storage folder. One file holds a
whole evening: every match, and — from RiftRec 0.2.0 on, which records the heart
rate from the moment the chest strap connects — the stretches **between** the
matches too (client lobby, champion select, loading screen, after the game).
Pick what you want from the **Session** dropdown next to the button, or step
through it with **Page Up / Page Down**:

- **Matches** come first, in order: `#1 - P01 - 2026-10-14 17:42:00`, `#2 - …`
  (start time in UTC).
- **Between-match recordings** follow, by start time, labelled with the clock
  time they ran: `between matches · 19:42–20:05`. That is the participant's
  local time when the file records it; older or incomplete files show UTC and
  say so (`… UTC`).

A file opens on its **latest match**. Only a file without any match opens on its
latest between-match recording. A between-match recording has the heart-rate and
HRV panels as usual but no game events — that is expected, not missing data.

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

A **green band** marks the 60 s **resting measurement** of the daily check-in
that RiftRec offers before the first match — usually in the first
between-match recording of the evening — labelled `rest 60 s`. A measurement
that was aborted or skipped part-way is drawn fainter and labelled that way
(`rest aborted after 22 s`).

A **metadata line** under the toolbar shows participant, session (or "between
matches"), start time, duration and event count. Move the mouse over the panels and a **crosshair**
follows it, with a readout (top right) of the time and the HR / RMSSD value at
that moment.

## 4 · Zoom, pan and read the data

All three panels are linked on the time axis, so **any** zoom or pan moves all
of them together:

- **Mouse wheel** over a panel — zoom in / out on time.
- **Left-click + drag** — pan (move the view).
- **Right-click + drag** — stretch or squeeze the axes.
- **Right-click → View All**, or press **Ctrl+0** — reset back to the full
  session.

## 5 · Select a section and export a picture

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

# Specific session id (otherwise the latest match; a between-match
# recording only if the file holds no match)
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

## Schema versions

RiftLab reads RiftRec files up to **schema 5** (`SUPPORTED_SCHEMA_VERSION` in
`riftlab/__init__.py`, with the history of each step). Every change so far was
additive, and every file ever written still opens: a missing table or column
is read as an older file, never as an error. Schema 5 (RiftRec 0.2.0) added:

- `session.kind` — `'match'` or `'idle'` (heart rate between matches: no
  `game_*` rows, `session_index` and `active_riot_id` NULL). NULL in older
  files, read as `'match'`.
- `session.utc_offset_min` — local UTC offset at session start, minutes east of
  UTC; used for the local clock time in the session dropdown.
- `checkin` — the daily questionnaire plus a 60 s resting measurement. RiftLab
  uses only the resting window (`rest_status`, `rest_start_utc`,
  `rest_end_utc`), matched to a session by time; the answers are not analysed
  here.

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

---

## Licence

MIT — see [LICENSE](LICENSE). Use it, change it, build on it; keep the copyright
notice.

The licence covers the **software only**. Session recordings are never part of
this repository (`*.sqlite` is gitignored) and are not covered — they are
Art. 9 GDPR health data belonging to the study participants.

Note on dependencies: **PySide6 is LGPL**. It is used unmodified, as a library
installed via pip, which keeps this project's own MIT licensing intact — anyone
receiving it can replace the Qt bindings themselves. Do not vendor or patch
PySide6 into the source tree without revisiting that. matplotlib (PSF-based) and
pyqtgraph (MIT) are unproblematic.
