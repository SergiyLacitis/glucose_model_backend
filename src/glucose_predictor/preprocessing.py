from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .schemas import GlucoseReading

TIME_FEATS = ["hour_sin", "hour_cos", "min_sin", "min_cos", "dow_sin", "dow_cos"]


@dataclass
class PreprocessedHistory:
    glucose: np.ndarray  # (N,) float32, mg/dL
    time_features: np.ndarray  # (N, 6) float32, sin/cos
    timestamps: np.ndarray  # (N,) datetime64[ns]
    pt_mean: float
    pt_std: float


def _compute_time_features(ts: pd.DatetimeIndex) -> np.ndarray:
    h = ts.hour.values  # type: ignore
    m = ts.minute.values  # type: ignore
    d = ts.dayofweek.values  # type: ignore
    feats = np.stack(
        [
            np.sin(2 * np.pi * h / 24),
            np.cos(2 * np.pi * h / 24),
            np.sin(2 * np.pi * m / 60),
            np.cos(2 * np.pi * m / 60),
            np.sin(2 * np.pi * d / 7),
            np.cos(2 * np.pi * d / 7),
        ],
        axis=1,
    ).astype(np.float32)
    return feats


def preprocess_history(
    readings: Sequence[GlucoseReading],
    sample_min: int = 5,
    gap_threshold_min: int = 30,
    min_glucose: float = 40.0,
    max_glucose: float = 400.0,
    pt_mean: float | None = None,
    pt_std: float | None = None,
) -> PreprocessedHistory:
    if len(readings) == 0:
        raise ValueError("Empty history")

    df = pd.DataFrame([{"ts": r.ts, "glucose": r.glucose} for r in readings])
    df["ts"] = pd.to_datetime(df["ts"])
    df = df.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")

    mask = (df["glucose"] >= min_glucose) & (df["glucose"] <= max_glucose)
    df.loc[~mask, "glucose"] = np.nan

    df = df.set_index("ts").resample(f"{sample_min}min").mean()

    gap_pts = gap_threshold_min // sample_min
    is_nan = df["glucose"].isna()
    run_id = (is_nan != is_nan.shift()).cumsum()
    run_lens = is_nan.groupby(run_id).transform("size")
    big_gap = is_nan & (run_lens > gap_pts)

    seg_id = big_gap.cumsum()
    df = df[~big_gap].copy()
    df["seg_id"] = seg_id[~big_gap]

    if df.empty:
        raise ValueError("All data filtered out as large gaps")

    last_seg = df["seg_id"].iloc[-1]
    seg = df[df["seg_id"] == last_seg].copy()

    seg["glucose"] = seg["glucose"].interpolate(method="linear", limit_direction="both")
    seg = seg.dropna(subset=["glucose"])

    if seg.empty:
        raise ValueError("Segment is empty after interpolation")

    glucose = seg["glucose"].to_numpy(dtype=np.float32)
    timestamps = seg.index.to_numpy()
    time_feats = _compute_time_features(seg.index)

    if pt_mean is None:
        pt_mean = float(np.mean(glucose))
    if pt_std is None:
        pt_std = float(np.std(glucose)) + 1e-6

    return PreprocessedHistory(
        glucose=glucose,
        time_features=time_feats,
        timestamps=timestamps,
        pt_mean=pt_mean,
        pt_std=pt_std,
    )
