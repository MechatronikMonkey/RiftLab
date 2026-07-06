"""CLI: python -m riftlab plot <session.sqlite> [--out chart.png]

Without --out a window is opened (show); with --out the chart is rendered
headlessly to a PNG. --session selects a specific session id (otherwise the
most recent one).
"""

from __future__ import annotations

import argparse

from . import SUPPORTED_SCHEMA_VERSION
from .loader import load_session
from .plot import render_to_file, show


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

    args = parser.parse_args(argv)
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
