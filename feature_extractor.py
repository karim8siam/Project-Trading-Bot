"""
Feature Extraction Module.
Extracts normalized tabular feature vectors from market candles at signal/entry moments,
including granular 100-point scoring sub-metrics.
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime


FEATURE_COLUMNS = [
    "rsi_14",
    "macd_hist_pct",
    "macd_signal_ratio",
    "price_to_ema50_pct",
    "price_to_ema200_pct",
    "ema50_to_ema200_pct",
    "atr_pct",
    "bb_width",
    "bb_pct_b",
    "vol_surge_ratio",
    "return_1",
    "return_3",
    "return_6",
    "return_12",
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "consecutive_direction",
    "higher_tf_trend",
    "hour_sin",
    "hour_cos",
    "day_of_week",
    "direction_is_long",
    "confluence_score",
    "fib_distance_pct",
    "golden_cross_active",
    "bb_squeeze_active"
]


def extract_features_at_index(
    df: pd.DataFrame,
    idx: int = -1,
    direction: str = "LONG",
    higher_tf_df: Optional[pd.DataFrame] = None
) -> Dict[str, float]:
    """
    Extracts a normalized feature vector dictionary for the candle at `idx`.
    """
    row = df.iloc[idx]
    close = float(row["close"])
    ema50 = float(row["ema_50"])
    ema200 = float(row["ema_200"])
    atr = float(row["atr_14"])

    # Calculate consecutive green/red candles
    consecutive = 0
    sub_df = df.iloc[: idx + 1 if idx != -1 else len(df)]
    if len(sub_df) >= 2:
        recent_greens = sub_df["is_green"].tail(10).tolist()
        current_color = recent_greens[-1]
        for color in reversed(recent_greens):
            if color == current_color:
                consecutive += 1
            else:
                break
        if current_color == 0:
            consecutive = -consecutive

    # Higher timeframe trend filter
    higher_tf_trend = 0.0
    if higher_tf_df is not None and not higher_tf_df.empty:
        htf_close = float(higher_tf_df["close"].iloc[-1])
        htf_ema50 = float(higher_tf_df.get("ema_50", higher_tf_df["close"].ewm(span=50).mean()).iloc[-1])
        higher_tf_trend = 1.0 if htf_close > htf_ema50 else -1.0

    # Cyclic time
    timestamp_val = row.get("timestamp")
    if isinstance(timestamp_val, (int, float)):
        if timestamp_val > 1e11:
            timestamp_val /= 1000
        dt = datetime.utcfromtimestamp(timestamp_val)
    elif isinstance(timestamp_val, str):
        try:
            dt = datetime.fromisoformat(timestamp_val.replace("Z", "+00:00"))
        except Exception:
            dt = datetime.utcnow()
    else:
        dt = datetime.utcnow()

    hour = dt.hour + dt.minute / 60.0
    hour_sin = math.sin(2 * math.pi * hour / 24.0)
    hour_cos = math.cos(2 * math.pi * hour / 24.0)
    day_of_week = float(dt.weekday())

    # Build feature dictionary
    features = {
        "rsi_14": float(row["rsi_14"]),
        "macd_hist_pct": float(row["macd_hist"] / (close + 1e-9)),
        "macd_signal_ratio": float(row["macd"] / (row["macd_signal"] + 1e-9)),
        "price_to_ema50_pct": float((close - ema50) / (ema50 + 1e-9)),
        "price_to_ema200_pct": float((close - ema200) / (ema200 + 1e-9)),
        "ema50_to_ema200_pct": float((ema50 - ema200) / (ema200 + 1e-9)),
        "atr_pct": float(atr / (close + 1e-9)),
        "bb_width": float(row["bb_width"]),
        "bb_pct_b": float(row["bb_pct_b"]),
        "vol_surge_ratio": float(row["vol_surge_ratio"]),
        "return_1": float(row["return_1"]) if not pd.isna(row["return_1"]) else 0.0,
        "return_3": float(row["return_3"]) if not pd.isna(row["return_3"]) else 0.0,
        "return_6": float(row["return_6"]) if not pd.isna(row["return_6"]) else 0.0,
        "return_12": float(row["return_12"]) if not pd.isna(row["return_12"]) else 0.0,
        "body_ratio": float(row["body_ratio"]),
        "upper_wick_ratio": float(row["upper_wick_ratio"]),
        "lower_wick_ratio": float(row["lower_wick_ratio"]),
        "consecutive_direction": float(consecutive),
        "higher_tf_trend": float(higher_tf_trend),
        "hour_sin": float(hour_sin),
        "hour_cos": float(hour_cos),
        "day_of_week": float(day_of_week),
        "direction_is_long": 1.0 if direction.upper() == "LONG" else 0.0,
        "confluence_score": float(row.get("confluence_score", 70.0)),
        "fib_distance_pct": float(row.get("fib_distance_pct", 0.0)),
        "golden_cross_active": float(row.get("golden_cross", 1 if float(row.get("sma_50", 0)) > float(row.get("sma_200", 0)) else 0)),
        "bb_squeeze_active": float(row.get("bb_squeeze", 0))
    }

    # Clean any NaNs or Infs
    for k, v in features.items():
        if math.isnan(v) or math.isinf(v):
            features[k] = 0.0

    return features
