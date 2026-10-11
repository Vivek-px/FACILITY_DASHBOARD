"""Live anomaly injection. Pure function: the input frame is NEVER modified."""
import numpy as np
import pandas as pd

from facility.contracts import METRICS, InjectionEvent

KINDS = ("spike", "drop", "drift")


def inject_anomaly(df, metric, hours=6, magnitude=2.5, kind="spike", start=None):
    """Return (new_df, InjectionEvent).

    spike : value x magnitude          drop  : value / magnitude
    drift : ramps from x1 to x magnitude across the window (slow leak / creeping load)
    start=None -> the last `hours` rows (i.e. "happening right now").
    """
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if hours < 1 or hours > len(df):
        raise ValueError("hours must be between 1 and len(df)")
    if magnitude <= 0:
        raise ValueError("magnitude must be > 0")

    new = df.copy()
    start = pd.Timestamp(start) if start is not None else new.index[-hours]
    if start not in new.index:
        raise ValueError(f"start {start} not in index")
    end = start + pd.Timedelta(hours=hours - 1)
    seg = new.loc[start:end, metric]
    if kind == "spike":
        factor = magnitude
    elif kind == "drop":
        factor = 1.0 / magnitude
    else:
        factor = np.linspace(1.0, magnitude, len(seg))
    new.loc[start:end, metric] = (seg * factor).astype(float)
    return new, InjectionEvent(metric, start, int(len(seg)), float(magnitude), kind)
