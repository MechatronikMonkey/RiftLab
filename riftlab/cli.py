"""CLI: python -m riftlab plot <session.sqlite> [--out chart.png]

Without --out a window is opened (show); with --out the chart is rendered
headlessly to a PNG. --session selects a specific session id (otherwise the
most recent one).

`python -m riftlab gui [session.sqlite]` opens the interactive viewer (EW-53).
"""

from __future__ import annotations

import argparse

import importlib
from pathlib import Path

from . import SUPPORTED_SCHEMA_VERSION
from .loader import load_session
from .plot import render_to_file, show


# Everything the viewer touches at runtime, including the modules that are only
# reached once a window opens or a chart is drawn. A frozen build that is
# missing one of these shows a window that never appears - and nothing else.
_RUNTIME_MODULES = (
    "sqlite3", "json", "zlib", "datetime", "dataclasses", "configparser",
    "numpy",
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "pyqtgraph", "pyqtgraph.exporters",
    "matplotlib", "matplotlib.pyplot",
    "riftlab.loader", "riftlab.metrics", "riftlab.plot", "riftlab.recordings",
    "riftlab.gui.model", "riftlab.gui.app",
)


def _redirect_output_if_windowless() -> None:
    """Give a windowed build somewhere to print to.

    A frozen GUI build has no console, so `sys.stdout` and `sys.stderr` are
    None and every print() would raise. Without this, `RiftLab.exe selfcheck`
    could only ever report an exit code - and "something is missing, but not
    what" is barely better than silence. The same file doubles as the log to
    ask for when the viewer misbehaves on somebody else's machine.
    """
    import os
    import sys

    if sys.stdout is not None and sys.stderr is not None:
        return                      # normal console run - leave the streams alone

    log_dir = Path(os.environ.get("APPDATA") or Path.home()) / "RiftLab"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        sink = open(log_dir / "riftlab.log", "a", buffering=1, encoding="utf-8")
    except OSError:
        import io

        sink = io.StringIO()        # last resort: swallow rather than crash
    if sys.stdout is None:
        sys.stdout = sink
    if sys.stderr is None:
        sys.stderr = sink


def _selfcheck() -> int:
    """Import every runtime dependency of the packaged viewer.

    This is the packaging smoke test, and it exists because of what happened to
    RiftRec: a missing Python dependency is exactly what stopped its zipped
    version from ever starting on somebody else's PC. In a frozen, windowed
    build that failure produces **no error at all** - just a window that never
    appears. Running this against the built exe turns it into a failed build
    instead of a failed evening.

    RiftLab's dependency stack is the heavier of the two (Qt, pyqtgraph,
    matplotlib, numpy), so it has more ways to go wrong, not fewer.

    Returns a process exit code: 0 = everything imports, 1 = something is
    missing, with each miss printed.
    """
    problems: list[str] = []
    for name in _RUNTIME_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # a broken C extension can raise anything
            problems.append(f"import {name}: {exc}")

    # pyqtgraph picks its Qt binding at import time and silently prefers a
    # different one if PySide6 did not make it into the bundle.
    try:
        import pyqtgraph as pg

        if "PySide6" not in str(pg.Qt.QT_LIB):
            problems.append(f"pyqtgraph bound to {pg.Qt.QT_LIB}, expected PySide6")
    except Exception as exc:
        problems.append(f"pyqtgraph Qt binding: {exc}")

    if problems:
        print(f"[selfcheck] FAILED - {len(problems)} problem(s):")
        for line in problems:
            print(f"[selfcheck]   {line}")
        return 1
    print(f"[selfcheck] OK - {len(_RUNTIME_MODULES)} modules, Qt binding PySide6")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="riftlab", description="RiftLab session viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plot", help="Plot the HR/HRV trend of a session")
    p.add_argument("db_path", help="Path to the RiftRec .sqlite session")
    p.add_argument("--session", default=None, help="Session id (otherwise the latest)")
    p.add_argument("--out", default=None, help="PNG output (otherwise a window)")
    p.add_argument("--rmssd-window", type=int, default=10)
    p.add_argument("--active-player", default=None,
                   help="Riot name of the player, to split kill/death/assist "
                        "(otherwise the participant_id is used)")

    sub.add_parser("selfcheck",
                   help="Verify the packaged build can import everything it needs")

    g = sub.add_parser("gui", help="Open the interactive viewer (EW-53)")
    g.add_argument("db_path", nargs="?", default=None,
                   help="Optional .sqlite to open on start (otherwise use the file dialog)")

    args = parser.parse_args(argv)

    if args.command == "selfcheck":
        _redirect_output_if_windowless()
        raise SystemExit(_selfcheck())

    if args.command == "gui":
        _redirect_output_if_windowless()
        from .gui.app import run_gui  # local import: Qt only needed for the GUI
        raise SystemExit(run_gui(args.db_path))

    data = load_session(args.db_path, session_id=args.session)
    if data.schema_version > SUPPORTED_SCHEMA_VERSION:
        print(f"[warn] session schema v{data.schema_version} > supported "
              f"v{SUPPORTED_SCHEMA_VERSION}; display may be incomplete.")

    if args.out:
        render_to_file(data, args.out, rmssd_window=args.rmssd_window,
                       active_player=args.active_player)
        print(f"Chart written: {args.out}")
    else:
        show(data, rmssd_window=args.rmssd_window, active_player=args.active_player)


if __name__ == "__main__":
    main()
