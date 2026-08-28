"""Where the "Open .sqlite" dialog starts.

A convenience, but a real one: the alternative is asking somebody to remember a
folder they picked in a different program weeks ago, every time they want to
look at their own recording.

The whole point of these tests is that it stays a *hint*. RiftLab must not
acquire a dependency on RiftRec's settings file - every way of failing to read
it has to end in a sensible fallback, never an error.
"""

from __future__ import annotations

from pathlib import Path

from riftlab.recordings import default_open_dir, riftrec_storage_folder


def _write_prefs(appdata: Path, body: str) -> dict:
    """Lay out a RiftRec prefs.ini under a fake %APPDATA% and return the env."""
    prefs = appdata / "RiftRec" / "prefs.ini"
    prefs.parent.mkdir(parents=True, exist_ok=True)
    prefs.write_text(body, encoding="utf-8")
    return {"APPDATA": str(appdata)}


def test_the_folder_riftrec_records_into_is_found(tmp_path) -> None:
    recordings = tmp_path / "Recordings"
    recordings.mkdir()
    env = _write_prefs(tmp_path / "appdata",
                       f"[recorder]\nparticipant_id = P01\n"
                       f"storage_folder = {recordings}\n")

    assert riftrec_storage_folder(env) == recordings
    assert default_open_dir(env=env) == str(recordings)


def test_a_folder_that_no_longer_exists_is_not_offered(tmp_path) -> None:
    """The participant moved or deleted it. Opening a dialog on a dead path is
    worse than opening it at home."""
    env = _write_prefs(tmp_path / "appdata",
                       "[recorder]\nstorage_folder = X:\\\\gone\\\\nowhere\n")

    assert riftrec_storage_folder(env) is None
    assert default_open_dir(env=env) == str(Path.home())


def test_riftrec_never_run_is_not_an_error(tmp_path) -> None:
    """RiftLab may be installed on a machine that never recorded anything."""
    env = {"APPDATA": str(tmp_path / "empty")}

    assert riftrec_storage_folder(env) is None
    assert default_open_dir(env=env) == str(Path.home())


def test_a_corrupt_prefs_file_falls_back_quietly(tmp_path) -> None:
    """A hint is never worth an error message."""
    env = _write_prefs(tmp_path / "appdata", "this is not an ini file at all {{{")
    assert riftrec_storage_folder(env) is None


def test_a_prefs_file_without_the_key_falls_back(tmp_path) -> None:
    """A future RiftRec could rename it. Then this returns None and the dialog
    opens where it otherwise would - the correct amount of breakage."""
    env = _write_prefs(tmp_path / "appdata", "[recorder]\nparticipant_id = P01\n")
    assert riftrec_storage_folder(env) is None


def test_an_empty_setting_is_treated_as_unset(tmp_path) -> None:
    env = _write_prefs(tmp_path / "appdata", "[recorder]\nstorage_folder =   \n")
    assert riftrec_storage_folder(env) is None


def test_where_you_last_opened_something_wins(tmp_path) -> None:
    """Once somebody has navigated somewhere in this session, sending them back
    to the recordings folder on the next open would be the annoying kind of
    helpful."""
    recordings = tmp_path / "Recordings"
    recordings.mkdir()
    elsewhere = tmp_path / "Elsewhere"
    elsewhere.mkdir()
    env = _write_prefs(tmp_path / "appdata",
                       f"[recorder]\nstorage_folder = {recordings}\n")

    opened = elsewhere / "P01_2026-08-28.sqlite"
    opened.write_bytes(b"")
    assert default_open_dir(opened, env=env) == str(elsewhere)


def test_a_last_used_path_that_vanished_falls_through(tmp_path) -> None:
    """The drive was unplugged between two opens."""
    recordings = tmp_path / "Recordings"
    recordings.mkdir()
    env = _write_prefs(tmp_path / "appdata",
                       f"[recorder]\nstorage_folder = {recordings}\n")

    gone = tmp_path / "unplugged" / "old.sqlite"
    assert default_open_dir(gone, env=env) == str(recordings)


def test_riftlab_never_writes_to_riftrecs_settings() -> None:
    """Reading is a hint; writing would make RiftLab able to break the recorder's
    configuration, which is not a trade this convenience is worth."""
    source = (Path(__file__).resolve().parents[1]
              / "riftlab" / "recordings.py").read_text(encoding="utf-8")
    for forbidden in ("open(", ".write_text", ".write(", "save_prefs"):
        assert forbidden not in source, forbidden
