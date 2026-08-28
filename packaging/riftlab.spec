# PyInstaller spec for the RiftLab viewer.
#
# One folder, not one file, and no UPX - the same reasoning as RiftRec: a
# --onefile build unpacks its whole runtime into %TEMP% on every launch, and
# packed executables are a favourite antivirus heuristic. The folder lives
# inside the installer, so a user still downloads and runs a single file.
#
# RiftLab bundles no data files. `plot.py` looks for optional event icons in
# riftlab/assets/events/ and falls back to emoji when they are absent, which
# they currently are - so there is nothing to lose here. If icons are ever
# added, they belong in `datas` and `riftlab selfcheck` should check for them.

from pathlib import Path

ROOT = Path(SPECPATH).parent                    # noqa: F821

datas = []

# Picked at import time rather than by a static analysis:
# - pyqtgraph resolves its Qt binding dynamically and its exporters lazily
# - matplotlib chooses a backend at runtime; with tkinter excluded (below) the
#   Qt backend is the one it must find, so it is named explicitly
hiddenimports = [
    "pyqtgraph.exporters",
    "pyqtgraph.exporters.ImageExporter",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
]

# PySide6 ships far more of Qt than a two-plot viewer needs, and PyInstaller's
# hook takes a generous view of what to include. Dropping the large unused
# frameworks is most of the difference between a ~300 MB and a manageable
# download. Anything removed here that turns out to be needed shows up in
# `riftlab selfcheck` or on the first window - not silently.
excludes = [
    # Qt frameworks this viewer does not touch
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtTest", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtNetworkAuth",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtSql", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtUiTools",
    # Toolkits and libraries RiftLab never uses
    "tkinter", "PyQt5", "PyQt6", "PySide2",
    "bleak", "pystray", "winrt", "httpx", "pandas", "scipy",
    "pytest", "IPython", "notebook", "riftrec",
]

_icon = ROOT / "packaging" / "riftlab.ico"

a = Analysis(                                   # noqa: F821
    [str(ROOT / "packaging" / "riftlab_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)                               # noqa: F821

exe = EXE(                                      # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RiftLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # packed executables trip antivirus heuristics
    console=False,      # a Qt viewer: no console window behind the window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_icon) if _icon.exists() else None,
)

coll = COLLECT(                                 # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="RiftLab",
)
