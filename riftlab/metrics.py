"""HRV metrics from RR intervals.

For the demo viewer a rolling RMSSD (root mean square of successive differences)
is enough - the common short-term time-domain HRV measure. The rigorous HRV
analysis (Kubios, longer windows) comes later; here we only want a visible trend
along the match timeline.
"""

from __future__ import annotations

import numpy as np


def rolling_rmssd(rr_ms: np.ndarray, window: int = 10) -> np.ndarray:
    """Rolling RMSSD over the last `window` RR differences.

    The result is aligned to rr[1:] (one difference per pair); positions before
    the first full window are NaN. Length = len(rr) - 1.
    """
    rr = np.asarray(rr_ms, dtype=float)
    if rr.size < 2:
        return np.empty(0)
    diffs = np.diff(rr)
    out = np.full(diffs.size, np.nan)
    for i in range(diffs.size):
        lo = max(0, i - window + 1)
        seg = diffs[lo : i + 1]
        out[i] = float(np.sqrt(np.mean(seg**2)))
    return out
