<!--
The title becomes the commit on main (squash merge), so give it the shape of a
commit message:  feat(loader): read the gap table
-->

## What and why

<!-- What changes, and what problem it solves. The diff shows the "what" -
     the "why" is the part worth writing down. -->

## How it was verified

<!-- Which tests, and anything checked against a real recording. If you looked
     at a plot, say what you were looking for. -->

## Checklist

- [ ] `PYTHONPATH=. python -m pytest tests/` is green
- [ ] The change has a test that would fail without it
- [ ] Files written by older RiftRec versions still load
- [ ] Recordings are still only ever opened read-only
- [ ] No real participant data: no `.sqlite` files, no real Riot IDs, no plots or screenshots of real sessions
- [ ] Nothing the file contains is silently dropped (unknown sources, unknown event types)
- [ ] The judgement lives in the pure layer (`loader` / `metrics` / `gui.model`), not in the Qt wiring
- [ ] If a new part of the schema is read: `SUPPORTED_SCHEMA_VERSION` raised **and** its comment extended

<!-- Jira: EW-___ -->
