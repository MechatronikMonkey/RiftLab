# RiftLab

Auswertung und Visualisierung von **RiftRec**-Sessions. RiftLab kennt RiftRec
ausschliesslich ueber den **SQLite-Session-Vertrag** (`RiftRec/riftrec/storage/schema.sql`)
und importiert keinen RiftRec-Code — die beiden Repos sind nur ueber das Dateiformat
gekoppelt.

## Stand (2026-07-06)

Milestone 4 — Demo-Viewer (EW-31/36): plottet HR- und HRV-Verlauf (rollierender RMSSD)
einer Session ueber die Match-Timeline mit farbig markierten Game-Events (Kills/Deaths,
Tuerme, Drache/Baron). Zeigt z. B. den HR-Anstieg rund um Teamfights.

## Nutzung

```
pip install -r requirements.txt

# Fenster
python -m riftlab plot pfad/zur/session.sqlite

# Headless als PNG
python -m riftlab plot pfad/zur/session.sqlite --out chart.png

# Bestimmte Session-ID (sonst wird die zuletzt gestartete genommen)
python -m riftlab plot session.sqlite --session <uuid>
```

Test-DB ohne Match/Hardware erzeugen (aus dem RiftRec-Verzeichnis):

```
python -m riftrec record --source fake --seconds 60 --db demo.sqlite
```

## Aufbau

- `riftlab/loader.py` — liest den SQLite-Vertrag in Arrays; `t_s` = Sekunden seit
  Session-Start (aus `mono_ns - session.mono_anchor_ns`)
- `riftlab/metrics.py` — HRV (rollierender RMSSD) aus RR-Intervallen
- `riftlab/plot.py` — matplotlib-Figure (HR oben, HRV unten, Event-Marker)
- `riftlab/cli.py` — `python -m riftlab plot ...`
- `tests/test_loader.py` — gegen eine handgeschriebene Vertrags-DB (belegt die Entkopplung)

Tests: `PYTHONPATH=. python tests/test_loader.py` oder `python -m pytest tests/`.
