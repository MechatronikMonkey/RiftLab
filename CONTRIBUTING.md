# Contributing to RiftLab

RiftLab reads and visualises recordings made by
[RiftRec](https://github.com/MechatronikMonkey/RiftRec) during a research study.
The recordings cannot be repeated — the games were played once — so the tool
that reads them has one job before all others: **never destroy, alter, or
quietly misrepresent what is in the file.**

## The rules that are not negotiable

1. **No real participant data in this repository.** It is public. No `.sqlite`
   files, no exported plots of real sessions, no Riot IDs, no screenshots
   showing a participant. Test fixtures are hand-written SQL — see
   `tests/test_loader.py`. A single raw payload contains the Riot IDs of ten
   people, nine of whom never consented to anything.
2. **RiftLab never imports RiftRec.** The SQLite schema
   (`RiftRec/riftrec/storage/schema.sql`) is the *entire* coupling between the
   two repositories, and the tests prove it by rebuilding that schema by hand.
   If RiftLab needed RiftRec's code, the two would have to be released together
   forever.
3. **Recordings are opened read-only** (`mode=ro`) and are never migrated,
   rewritten or "repaired". A recording is evidence. If a file is odd, the
   analysis says so — it does not fix it.
4. **Every RiftRec version must keep loading.** Files written before a table or
   column existed are ordinary older files, not errors. Check with
   `_columns(conn, table)` and degrade; never let a missing column raise.
5. **Never silently drop what you do not understand.** An unknown gap source, an
   unknown event type, a value out of range — surface it. The whole point of
   this tool is to show what is in the file, and the dangerous failure is a
   viewer that quietly looks tidy.
6. **Every change needs a test**, and `PYTHONPATH=. python -m pytest tests/`
   has to be green before a pull request is opened.

## How the code is laid out, and why

```
loader.py    SQLite -> plain arrays and value objects.  Knows the schema.
metrics.py   pure numbers from numbers (RMSSD).          Knows no schema.
plot.py      the drawing vocabulary + a matplotlib figure.
gui/model.py pure SessionData -> plot-model transforms.  No Qt.
gui/app.py   Qt wiring only: takes models, hands arrays to pyqtgraph.
```

The split exists so the interesting logic is testable **without opening a
window**. `gui/model.py` and `plot.py` contain decisions (what counts as a
death, how a gap is shaded, where an event marker sits); `gui/app.py` contains
no decisions worth testing. When you add a feature, put the judgement in the
pure layer and let the Qt layer stay boring — that is what keeps the test suite
fast and meaningful.

`plot.py` holds the shared vocabulary (`_EVENT_DEF`, `GAP_STYLE`, `gap_bands`)
and `gui/model.py` imports from it, never the other way round.

## Reading a new part of the schema

When RiftRec gains a table or column you want to use:

1. Check `RiftRec/riftrec/storage/schema.sql` — it is the contract and it
   documents the traps (for example: the Polar H10 does **not** report contact
   status, so `hr_sample.contact` is always NULL with our hardware).
2. Load it defensively, so older files still work.
3. Raise `SUPPORTED_SCHEMA_VERSION` in `riftlab/__init__.py` **and** add a line
   to the comment above it saying what that version added and whether this
   reader now uses it. That comment is the changelog that matters here.
4. Add a fixture at the new schema version rather than changing the old one —
   the old fixture is what proves older files still load.

## Working on a change

`main` is protected: it takes no direct pushes. Everything goes through a pull
request, including one-line fixes.

```bash
git switch main && git pull
git switch -c feat/gap-shading        # or ew-<ticket>-<what>, fix/, docs/, chore/
# ... work, with tests ...
PYTHONPATH=. python -m pytest tests/
git commit
git push -u origin feat/gap-shading
gh pr create --fill                   # or open it in the web UI
```

**Commit messages** are conventional commits with a scope and a body that says
*why* — scopes: `loader`, `metrics`, `plot`, `gui`, `docs`, `ci`.

**Pull requests** are squash-merged, so the PR title becomes the commit on main.
One check has to be green before the merge button unlocks: **`tests`**.

No approving review is required while the project has one maintainer — GitHub
does not allow approving your own pull request. Raise it to `1` in
`.github/rulesets/main.json` once a second person is actually working here.

## Releasing

```bash
# 1. bump the version through a normal pull request
#    riftlab/__init__.py:  __version__ = "0.2.0"

# 2. tag the merge commit on main
git switch main && git pull
git tag v0.2.0
git push origin v0.2.0
```

There is no installer to attach: RiftLab is run from a source checkout, by
people who edit it. A release marks a state — above all **which RiftRec schema
version it reads** — so that a recording and the tool that read it can be named
together in a report or a thesis.

## First-time repository setup

Once, by someone with admin rights, and **in this order**:

1. Push `main` while direct pushes are still allowed.
2. Let CI run once, so GitHub has seen the check name `tests`.
3. Apply the rules — they live in [`.github/rulesets/`](.github/rulesets/) as
   importable JSON. In the web UI: **Settings → Rules → Rulesets → New ruleset →
   Import a ruleset**. Or `.github\setup-repo-rules.ps1`.
4. Tag the first release.

## Running things locally

```bash
pip install -r requirements.txt
PYTHONPATH=. python -m pytest tests/     # no Qt, no recording needed
python -m riftlab gui                    # the viewer
```

## What to expect from a review

- Would this misrepresent a recording, or hide something the file contains?
- Does it still load a file written by an older RiftRec?
- Is the judgement in the pure layer, where it can be tested?
- Is there a test that would fail if this regressed?
