"""Entry point for the frozen RiftLab build.

Started with no arguments - which is what a Start-menu shortcut does - this
opens the viewer. Everything else (`plot`, `selfcheck`) still works when the
exe is called from a terminal, so the packaged build can do what the source
checkout does rather than being a crippled subset.
"""

import multiprocessing
import sys

from riftlab.cli import main

if __name__ == "__main__":
    # PyInstaller + multiprocessing on Windows re-executes this file in each
    # child process. Without this the app would spawn copies of itself instead
    # of workers; numpy/matplotlib can start pools, so it is not hypothetical.
    multiprocessing.freeze_support()

    if len(sys.argv) == 1:
        sys.argv.append("gui")
    main()
