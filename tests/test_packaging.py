"""What the packaged build promises.

RiftLab's dependency stack is the heavier of the two tools - Qt, pyqtgraph,
matplotlib, numpy - and in a frozen, windowed build every missing piece looks
identical from outside: a window that never opens, with nothing on screen to
explain it. These tests pin the agreements that keep that from shipping.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "packaging" / "riftlab.spec").read_text(encoding="utf-8")
ISS = (ROOT / "packaging" / "riftlab.iss").read_text(encoding="utf-8")
BUILD = (ROOT / "packaging" / "build.ps1").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
ACTION = (ROOT / ".github" / "actions" / "build-installer"
          / "action.yml").read_text(encoding="utf-8")


def test_the_installer_is_labelled_with_the_package_version() -> None:
    """The .iss fallback and riftlab.__version__ must not drift apart, or a
    bare ISCC run produces a setup file claiming the wrong version."""
    from riftlab import __version__

    fallback = re.search(r'#define AppVersion "([^"]+)"', ISS)
    assert fallback, "no AppVersion fallback in riftlab.iss"
    assert fallback.group(1) == __version__


def test_selfcheck_covers_every_riftlab_module() -> None:
    """A new module has to join the list, or a frozen build can drop it and the
    only symptom is a window that never opens."""
    from riftlab.cli import _RUNTIME_MODULES

    listed = set(_RUNTIME_MODULES)
    for package in ("", "gui"):
        folder = ROOT / "riftlab" / package if package else ROOT / "riftlab"
        for module in folder.glob("*.py"):
            if module.stem in ("__init__", "__main__", "cli"):
                continue
            dotted = f"riftlab.{package}.{module.stem}" if package else f"riftlab.{module.stem}"
            assert dotted in listed, module


def test_selfcheck_verifies_the_qt_binding() -> None:
    """pyqtgraph picks its Qt binding at import time and silently falls back to
    another one. A build bound to something PySide6 is not would draw nothing."""
    from riftlab.cli import _selfcheck

    source = (ROOT / "riftlab" / "cli.py").read_text(encoding="utf-8")
    assert "QT_LIB" in source
    assert _selfcheck() == 0        # and it passes in this environment


def test_the_frozen_build_has_somewhere_to_print() -> None:
    """console=False means sys.stdout is None. Without the redirect, selfcheck
    could only ever report an exit code - "something is missing, but not what"
    is barely better than silence."""
    assert "console=False" in SPEC
    source = (ROOT / "riftlab" / "cli.py").read_text(encoding="utf-8")
    assert "_redirect_output_if_windowless" in source
    assert "riftlab.log" in source


def test_the_build_is_not_packed_and_not_onefile() -> None:
    """Packed executables are a favourite antivirus heuristic, and --onefile
    unpacks the whole runtime into %TEMP% on every launch."""
    assert "upx=False" in SPEC
    assert "COLLECT(" in SPEC       # one folder, not one file


def test_qt_is_pruned_but_not_the_parts_the_viewer_uses() -> None:
    """Trimming unused Qt frameworks is most of the download size. Trimming one
    that is used would break the window instead."""
    for gone in ("PySide6.QtWebEngineCore", "PySide6.Qt3DRender", "tkinter"):
        assert f'"{gone}"' in SPEC, gone
    for kept in ("QtCore", "QtGui", "QtWidgets"):
        assert f'"PySide6.{kept}"' not in SPEC, kept


def test_the_installer_never_touches_recordings() -> None:
    """A recording is somebody's study data and the only copy. An uninstaller
    has no business anywhere near it."""
    # Strip Inno's comments first: the file *says* ".sqlite" precisely to
    # explain why it never deletes one.
    directives = [line for line in ISS.splitlines()
                  if not line.lstrip().startswith(";")]
    body = "\n".join(directives)
    assert "sqlite" not in body.lower()
    uninstall = body.split("[UninstallDelete]")[1] if "[UninstallDelete]" in body else ""
    assert not uninstall.strip(), uninstall


def test_the_install_needs_no_administrator() -> None:
    """So it can go on a university machine without a UAC prompt."""
    assert "PrivilegesRequired=lowest" in ISS


def test_signing_is_prepared_but_not_required() -> None:
    """Certificate lead time is weeks; the build does not wait for it."""
    assert "#ifdef SIGN" in ISS
    assert "SignCommand" in BUILD


def test_the_build_steps_exist_once_and_both_workflows_use_them() -> None:
    """CI and release must not grow separate build paths - the installer people
    download has to come from the steps that were green on the pull request."""
    for step in ("riftlab.spec", "riftlab.iss", "selfcheck", "make_icon.py"):
        assert step in ACTION, step
    for workflow in (CI, RELEASE):
        assert "./.github/actions/build-installer" in workflow
        assert "pyinstaller --noconfirm" not in workflow   # only in the action


def test_the_release_publishes_a_checksum() -> None:
    """The only way to check a downloaded file is the one that was built, which
    matters more than usual while the build is unsigned."""
    assert "sha256" in RELEASE.lower()
    assert "RiftLab-Setup-" in RELEASE
