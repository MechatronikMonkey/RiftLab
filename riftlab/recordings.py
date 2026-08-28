r"""Where the recordings actually are.

RiftLab and RiftRec are separate programs, but they are used one after the
other on the same machine: record in the evening, look at it afterwards. Making
somebody navigate to a folder they picked in the *other* program weeks ago is a
small thing that costs a support message every single time.

RiftRec remembers its storage folder in ``%APPDATA%\RiftRec\prefs.ini``. Reading
that is the one place RiftLab knows anything about RiftRec beyond the SQLite
schema, and it is deliberately only a **hint**: if the file is missing,
unreadable, from a different RiftRec version, or points at a folder that no
longer exists, the dialog simply opens where it otherwise would. Nothing about
reading a recording depends on it, and RiftLab never writes to that file.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Mapping, Optional

# Mirrors riftrec/app/prefs.py. Duplicated rather than imported - on purpose:
# the two repositories are released separately, and RiftLab must not grow a code
# dependency on RiftRec for a convenience. If the key ever moves, this returns
# None and the dialog falls back, which is the correct amount of breakage.
_SECTION = "recorder"
_KEY = "storage_folder"


def _riftrec_prefs_path(env: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    appdata = env.get("APPDATA")                    # Windows
    if appdata:
        return Path(appdata) / "RiftRec" / "prefs.ini"
    xdg = env.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "riftrec" / "prefs.ini"


def riftrec_storage_folder(env: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """The folder RiftRec is configured to save into, if it can be determined.

    Returns None for every kind of "cannot tell" - not installed, never run,
    unreadable file, folder since deleted - so callers have one case to handle.
    """
    path = _riftrec_prefs_path(env)
    cp = configparser.ConfigParser()
    try:
        if not path.exists():
            return None
        cp.read(path, encoding="utf-8")
        raw = (cp.get(_SECTION, _KEY, fallback="") or "").strip()
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None                                 # a hint is never worth an error
    if not raw:
        return None
    folder = Path(raw)
    return folder if folder.is_dir() else None


def default_open_dir(last_used: Optional[str | Path] = None,
                     env: Optional[Mapping[str, str]] = None) -> str:
    """Where the "Open .sqlite" dialog should start.

    In order: wherever the user last opened something in this session, then the
    folder RiftRec records into, then the home directory. The middle one is the
    point - on the first open of the day it lands exactly where the files are.
    """
    if last_used:
        folder = Path(last_used)
        folder = folder if folder.is_dir() else folder.parent
        if folder.is_dir():
            return str(folder)

    recordings = riftrec_storage_folder(env)
    if recordings is not None:
        return str(recordings)

    return str(Path.home())
