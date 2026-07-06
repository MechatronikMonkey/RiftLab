# Event icons

PNG icons for the LoL event timeline in the viewer. The viewer loads
`riftlab/assets/events/<key>.png`; if a PNG is missing an emoji fallback is
drawn automatically.

**Format:** square, transparent background, ~128×128 px (scaled down).

## Expected file names (key)

Combat: `kill` · `death` · `assist` · `firstblood` · `multikill` · `ace`
Objectives: `dragon` · `elder` · `baron` · `herald` · `grubs`
Structures: `turret` · `inhibitor`
Game (optional): `gamestart` · `gameend`

`otherkill` (a kill by another player) currently uses only the emoji fallback.
Dragon element types (Fire/Ocean/…) can be added later as `dragon_<type>.png` —
extend the classification in `riftlab/plot.py` for that.
