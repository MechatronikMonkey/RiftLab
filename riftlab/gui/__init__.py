"""Interactive RiftLab viewer (EW-53).

Additive to the matplotlib `plot.py`: PySide6 + pyqtgraph desktop GUI for
reviewing recorded sessions with built-in zoom/pan. Reuses the tested data
layer (`loader`, `metrics`) unchanged; the SessionData -> plot-model transform
lives in `model.py` as a pure function, the Qt wiring in `app.py`.
"""
