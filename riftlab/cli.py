"""CLI: python -m riftlab plot <session.sqlite> [--out chart.png]

Ohne --out wird ein Fenster geoeffnet (show); mit --out headless als PNG
gerendert. --session waehlt eine bestimmte Session-ID (sonst die letzte).
"""

from __future__ import annotations

import argparse

from . import SUPPORTED_SCHEMA_VERSION
from .loader import load_session
from .plot import render_to_file, show


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="riftlab", description="RiftLab Session-Viewer")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plot", help="HR/HRV-Verlauf einer Session plotten")
    p.add_argument("db_path", help="Pfad zur RiftRec-.sqlite-Session")
    p.add_argument("--session", default=None, help="Session-ID (sonst die letzte)")
    p.add_argument("--out", default=None, help="PNG-Ausgabe (sonst Fenster)")
    p.add_argument("--rmssd-window", type=int, default=10)

    args = parser.parse_args(argv)
    data = load_session(args.db_path, session_id=args.session)
    if data.schema_version > SUPPORTED_SCHEMA_VERSION:
        print(f"[warn] Session-Schema v{data.schema_version} > unterstuetzt "
              f"v{SUPPORTED_SCHEMA_VERSION}; Anzeige evtl. unvollstaendig.")

    if args.out:
        render_to_file(data, args.out, rmssd_window=args.rmssd_window)
        print(f"Chart geschrieben: {args.out}")
    else:
        show(data, rmssd_window=args.rmssd_window)


if __name__ == "__main__":
    main()
