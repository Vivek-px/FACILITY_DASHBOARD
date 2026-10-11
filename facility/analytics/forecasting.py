"""24-hour Holt-Winters forecast (PRD §7.2, decision A2).

Model: additive level + damped additive trend + additive 24-hour season, fitted on
the last `fit_days` days only (speed, and recent behaviour matters most).

Band (deviation D4 in BUILD_SPEC): ExponentialSmoothing gives no intervals, so the
band is yhat +/- 1.96 * sigma. The PDF used sigma = std(residuals); past anomalies
inside the fit window inflate that std (energy: 24 kWh instead of ~9). We use the
robust sigma = 1.4826 * MAD(residuals), which ignores those few extreme residuals.
It is an approximate 95% one-step band; it does not widen with the horizon, and the
UI says so. Interface `forecast_metric` is unchanged, so Prophet/ETS can be swapped in.
"""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from facility.contracts import INDEX_NAME

Z95 = 1.96


def robust_sigma(resid):
    r = np.asarray(resid, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(r - np.median(r))))


def _seasonal_naive(y, horizon_h, seasonal_periods):
    """Fallback if the optimiser fails: repeat the mean daily profile of the last week."""
    last = y.iloc[-7 * seasonal_periods:]
    profile = last.groupby(last.index.hour).mean()
    ts = pd.date_range(y.index[-1] + pd.Timedelta(hours=1), periods=horizon_h, freq="h")
    yhat = profile.reindex(ts.hour).values
    resid = last.values - profile.reindex(last.index.hour).values
    return yhat, robust_sigma(resid)


def forecast_metric(series, horizon_h=24, seasonal_periods=24, fit_days=28):
    """Return DataFrame[timestamp, yhat, yhat_lower, yhat_upper]; first row = last index + 1h."""
    y = series.iloc[-fit_days * 24:].astype(float).asfreq("h")
    if len(y) < 2 * seasonal_periods:
        raise ValueError("Need at least two full seasons to fit Holt-Winters")
    method = "holt_winters"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(y, trend="add", damped_trend=True, seasonal="add",
                                       seasonal_periods=seasonal_periods).fit()
        yhat = np.asarray(fit.forecast(horizon_h), dtype=float)
        sigma = robust_sigma(fit.resid)
        if not np.all(np.isfinite(yhat)):
            raise ValueError("non-finite forecast")
    except Exception:
        yhat, sigma = _seasonal_naive(y, horizon_h, seasonal_periods)
        method = "seasonal_naive_fallback"

    yhat = np.clip(yhat, 0, None)
    ts = pd.date_range(y.index[-1] + pd.Timedelta(hours=1), periods=horizon_h, freq="h", name=INDEX_NAME)
    out = pd.DataFrame({"timestamp": ts, "yhat": yhat,
                        "yhat_lower": np.clip(yhat - Z95 * sigma, 0, None),
                        "yhat_upper": yhat + Z95 * sigma})
    out.attrs["method"] = method
    out.attrs["sigma"] = sigma
    return out
