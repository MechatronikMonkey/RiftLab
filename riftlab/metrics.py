"""HRV-Metriken aus RR-Intervallen.

Fuer den Demo-Viewer genuegt ein rollierender RMSSD (root mean square of
successive differences) - das gaengige zeitbasierte Kurzzeit-HRV-Mass. Die
belastbare HRV-Auswertung (Kubios, laengere Fenster) kommt spaeter; hier geht
es nur um einen sichtbaren Verlauf entlang der Match-Timeline.
"""

from __future__ import annotations

import numpy as np


def rolling_rmssd(rr_ms: np.ndarray, window: int = 10) -> np.ndarray:
    """Rollierender RMSSD ueber die letzten `window` RR-Differenzen.

    Rueckgabe ist an rr[1:] ausgerichtet (eine Differenz je Paar); vor dem
    ersten vollstaendigen Fenster stehen NaN. Laenge = len(rr) - 1.
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
