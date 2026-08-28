"""Generate the application icon from the viewer's own palette.

Derived rather than committed, for the same reason RiftRec does it: the icon
cannot drift away from what the program actually draws, and the repository stays
free of binary assets.

The glyph is the two curves the viewer is built around - heart rate above, HRV
below - in the exact colours `plot.py` uses. Sibling to RiftRec's icon (same
dark tile) but not confusable with it: the two will sit next to each other in
the Start menu.

    python packaging/make_icon.py [out.ico]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

# Windows picks the size it needs per context (taskbar, alt-tab, installer
# header) and scales badly from a single bitmap - so ship all of them.
SIZES = [16, 24, 32, 48, 64, 128, 256]
DEFAULT_OUT = Path(__file__).with_name("riftlab.ico")

_TILE = "#1e2430"        # same tile as RiftRec: the two are a pair
_HR = "#c0392b"          # plot.py heart-rate curve
_HRV = "#2c7fb8"         # plot.py RMSSD curve

# Curve shapes in unit coordinates (0..1), so they scale to any icon size.
# A heartbeat spike on top, a calmer trace below - recognisable at 16 px as
# "two stacked signals" even when the individual points are a blur.
_HR_PATH = [(0.10, 0.34), (0.26, 0.34), (0.34, 0.14), (0.44, 0.50),
            (0.53, 0.30), (0.62, 0.34), (0.90, 0.34)]
_HRV_PATH = [(0.10, 0.72), (0.24, 0.62), (0.36, 0.78), (0.50, 0.64),
             (0.64, 0.76), (0.78, 0.66), (0.90, 0.70)]


def render(size: int) -> Image.Image:
    """The two curves on a dark rounded tile - readable on any taskbar."""
    # Draw oversized and downsample: PIL has no antialiased line drawing, and
    # at 16 px an aliased curve is mush.
    scale = 8
    big = size * scale
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = max(2, big // 5)
    draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=radius, fill=_TILE)

    width = max(scale, big // 12)
    for path, color in ((_HR_PATH, _HR), (_HRV_PATH, _HRV)):
        points = [(x * big, y * big) for x, y in path]
        draw.line(points, fill=color, width=width, joint="curve")

    return img.resize((size, size), Image.LANCZOS)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    frames = [render(s) for s in SIZES]
    frames[-1].save(out, format="ICO",
                    sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print(f"wrote {out} ({', '.join(f'{s}x{s}' for s in SIZES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
