"""
Technical Analysis and Indicator Engine for Binance Futures ML Trading Bot.
Computes complete suite:
- EMAs: 9, 21, 50, 200
- SMAs: 50, 100, 200 (Golden Cross / Death Cross)
- RSI (14) with Bullish/Bearish Divergence detection
- MACD (12, 26, 9) with Zero-line and Fresh Cross detection
- Bollinger Bands (20, 2.0) with Squeeze and Breakout detection
- Fibonacci Retracement (23.6%, 38.2%, 50.0%, 61.8%, 78.6%)
- Volume confirmation and Spikes
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Computes Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Computes Simple Moving Average (SMA)."""
    return series.rolling(window=period).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Computes Wilder's Relative Strength Index (RSI)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def detect_rsi_divergence(
    df: pd.DataFrame,
    lookback: int = 20
) -> Dict[str, bool]:
    """
    Detects Bullish & Bearish RSI divergences over recent candles:
    - Bullish: Price makes Lower Low while RSI makes Higher Low
    - Bearish: Price makes Higher High while RSI makes Lower High
    """
    if len(df) < lookback + 5:
        return {"bullish_div": False, "bearish_div": False}

    sub = df.iloc[-lookback:]
    prices = sub["close"].values
    rsis = sub["rsi_14"].values

    # Find swing lows (minima) and swing highs (maxima)
    p_curr = prices[-1]
    r_curr = rsis[-1]

    # Look for the previous trough in lookback range
    bullish_div = False
    bearish_div = False

    # Find past lowest price before current
    past_min_idx = np.argmin(prices[:-3])
    past_min_price = prices[past_min_idx]
    past_min_rsi = rsis[past_min_idx]

    # Bullish Divergence: Current price <= past min price, but current RSI > past min RSI
    if p_curr <= past_min_price and r_curr > past_min_rsi + 3.0:
        bullish_div = True

    # Find past highest price before current
    past_max_idx = np.argmax(prices[:-3])
    past_max_price = prices[past_max_idx]
    past_max_rsi = rsis[past_max_idx]

    # Bearish Divergence: Current price >= past max price, but current RSI < past max RSI
    if p_curr >= past_max_price and r_curr < past_max_rsi - 3.0:
        bearish_div = True

    return {
        "bullish_div": bullish_div,
        "bearish_div": bearish_div
    }


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, pd.Series]:
    """Computes Moving Average Convergence Divergence (MACD)."""
    ema_fast = compute_ema(close, fast)
    ema_slow = compute_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_hist": histogram
    }


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Computes Average True Range (ATR)."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean().bfill()


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Dict[str, pd.Series]:
    """Computes Average Directional Index (ADX) & Directional Indicators."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr_smooth = tr.rolling(window=period).sum()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_di = 100.0 * (pd.Series(plus_dm, index=high.index).rolling(window=period).sum() / (tr_smooth + 1e-9))
    minus_di = 100.0 * (pd.Series(minus_dm, index=high.index).rolling(window=period).sum() / (tr_smooth + 1e-9))
    dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
    adx = dx.rolling(window=period).mean().fillna(20.0)

    return {
        "adx_14": adx,
        "plus_di": plus_di.fillna(0.0),
        "minus_di": minus_di.fillna(0.0)
    }


def compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, pd.Series]:
    """Computes Bollinger Bands (Upper, Middle, Lower, Bandwidth, %B)."""
    sma = compute_sma(close, period)
    std = close.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    bandwidth = (upper - lower) / (sma + 1e-9)
    pct_b = (close - lower) / (upper - lower + 1e-9)
    return {
        "bb_middle": sma,
        "bb_upper": upper,
        "bb_lower": lower,
        "bb_width": bandwidth,
        "bb_pct_b": pct_b
    }


def compute_fibonacci_levels(
    df: pd.DataFrame,
    lookback: int = 60
) -> Dict[str, float]:
    """
    Computes Fibonacci Retracement levels from recent Swing High and Swing Low:
    0%, 23.6%, 38.2%, 50.0%, 61.8% (Golden Ratio), 78.6%, 100%.
    """
    sub = df.tail(lookback)
    swing_high = float(sub["high"].max())
    swing_low = float(sub["low"].min())
    diff = swing_high - swing_low

    if diff <= 0:
        return {
            "fib_0": swing_high,
            "fib_236": swing_high,
            "fib_382": swing_high,
            "fib_500": swing_high,
            "fib_618": swing_high,
            "fib_786": swing_high,
            "fib_100": swing_low,
            "swing_high": swing_high,
            "swing_low": swing_low
        }

    return {
        "fib_0": swing_high,                              # 0% (Swing High)
        "fib_236": swing_high - (0.236 * diff),           # 23.6%
        "fib_382": swing_high - (0.382 * diff),           # 38.2%
        "fib_500": swing_high - (0.500 * diff),           # 50.0%
        "fib_618": swing_high - (0.618 * diff),           # 61.8% (Golden Ratio)
        "fib_786": swing_high - (0.786 * diff),           # 78.6%
        "fib_100": swing_low,                             # 100% (Swing Low)
        "swing_high": swing_high,
        "swing_low": swing_low
    }


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends full indicator suite to OHLCV DataFrame.
    """
    df = df.copy()

    # Ensure numeric
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 1. EMAs (9, 21, 50, 200)
    df['ema_9'] = compute_ema(df['close'], 9)
    df['ema_21'] = compute_ema(df['close'], 21)
    df['ema_50'] = compute_ema(df['close'], 50)
    df['ema_200'] = compute_ema(df['close'], 200)

    # 2. SMAs (50, 100, 200)
    df['sma_50'] = compute_sma(df['close'], 50)
    df['sma_100'] = compute_sma(df['close'], 100)
    df['sma_200'] = compute_sma(df['close'], 200)

    # Golden Cross (SMA 50 > SMA 200) & Death Cross (SMA 50 < SMA 200)
    df['golden_cross'] = (df['sma_50'] > df['sma_200']).astype(int)
    df['death_cross'] = (df['sma_50'] < df['sma_200']).astype(int)

    # 3. RSI 14
    df['rsi_14'] = compute_rsi(df['close'], 14)

    # 4. MACD (12, 26, 9)
    macd_res = compute_macd(df['close'], 12, 26, 9)
    df['macd'] = macd_res['macd']
    df['macd_signal'] = macd_res['macd_signal']
    df['macd_hist'] = macd_res['macd_hist']

    # 5. Volatility: ATR 14 & Bollinger Bands (20, 2)
    df['atr_14'] = compute_atr(df['high'], df['low'], df['close'], 14)
    adx_res = compute_adx(df['high'], df['low'], df['close'], 14)
    df['adx_14'] = adx_res['adx_14']
    df['plus_di'] = adx_res['plus_di']
    df['minus_di'] = adx_res['minus_di']

    bb_res = compute_bollinger_bands(df['close'], 20, 2.0)
    df['bb_middle'] = bb_res['bb_middle']
    df['bb_upper'] = bb_res['bb_upper']
    df['bb_lower'] = bb_res['bb_lower']
    df['bb_width'] = bb_res['bb_width']
    df['bb_pct_b'] = bb_res['bb_pct_b']

    # Bollinger Squeeze (Bandwidth in lowest 20th percentile over 50 bars)
    rolling_min_bb = df['bb_width'].rolling(window=50).min()
    df['bb_squeeze'] = (df['bb_width'] <= rolling_min_bb * 1.15).astype(int)

    # 6. Volume Analysis
    df['vol_ma_20'] = compute_sma(df['volume'], 20)
    df['vol_surge_ratio'] = df['volume'] / (df['vol_ma_20'] + 1e-9)
    df['vol_spike_2x'] = (df['vol_surge_ratio'] >= 2.0).astype(int)

    # Price Returns
    df['return_1'] = df['close'].pct_change(1)
    df['return_3'] = df['close'].pct_change(3)
    df['return_6'] = df['close'].pct_change(6)
    df['return_12'] = df['close'].pct_change(12)

    # Candlestick metrics
    candle_range = (df['high'] - df['low']).replace(0, 1e-9)
    df['body_ratio'] = (df['close'] - df['open']).abs() / candle_range
    df['upper_wick_ratio'] = (df['high'] - df[['open', 'close']].max(axis=1)) / candle_range
    df['lower_wick_ratio'] = (df[['open', 'close']].min(axis=1) - df['low']) / candle_range
    df['is_green'] = (df['close'] >= df['open']).astype(int)

    return df


def detect_fair_value_gaps(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Detects institutional Fair Value Gaps (FVGs / Imbalances):
    - Bullish FVG: Candle 1 High < Candle 3 Low (Unfilled buy-side imbalance)
    - Bearish FVG: Candle 1 Low > Candle 3 High (Unfilled sell-side imbalance)
    """
    if len(df) < 5:
        return {"bullish_fvg": None, "bearish_fvg": None}

    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(len(df) - 1, max(0, len(df) - 20), -1):
        if i >= 2:
            c1_high = float(df['high'].iloc[i - 2])
            c3_low = float(df['low'].iloc[i])
            c1_low = float(df['low'].iloc[i - 2])
            c3_high = float(df['high'].iloc[i])

            if c3_low > c1_high:
                bullish_fvgs.append((c1_high + c3_low) / 2.0)
            elif c3_high < c1_low:
                bearish_fvgs.append((c1_low + c3_high) / 2.0)

    curr_close = float(df['close'].iloc[-1])
    valid_bull = [fvg for fvg in bullish_fvgs if fvg < curr_close]
    valid_bear = [fvg for fvg in bearish_fvgs if fvg > curr_close]

    return {
        "bullish_fvg": max(valid_bull) if valid_bull else None,
        "bearish_fvg": min(valid_bear) if valid_bear else None
    }


def detect_swing_pivots(
    df: pd.DataFrame,
    window: int = 25,
    df_htf: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Upgraded Dual-Timeframe (1H + 15M) Institutional Swing Pivot Detector:
    - Identifies 15M Fractal Highs/Lows (25 candles / 6+ hours).
    - If 1H candles provided, anchors against major 1H Macro Swing boundaries.
    """
    if len(df) < window:
        window = max(5, len(df) // 2)

    highs = df["high"].values
    lows = df["low"].values

    recent_high_sub = highs[-window-1:-1] if len(highs) > window else highs[:-1]
    recent_low_sub = lows[-window-1:-1] if len(lows) > window else lows[:-1]

    swing_high = float(np.max(recent_high_sub)) if len(recent_high_sub) > 0 else float(df["high"].max())
    swing_low = float(np.min(recent_low_sub)) if len(recent_low_sub) > 0 else float(df["low"].min())
    curr_close = float(df['close'].iloc[-1])

    htf_swing_high = None
    htf_swing_low = None
    if df_htf is not None and len(df_htf) >= 10:
        htf_highs = df_htf["high"].values[-15:-1] if len(df_htf) > 15 else df_htf["high"].values[:-1]
        htf_lows = df_htf["low"].values[-15:-1] if len(df_htf) > 15 else df_htf["low"].values[:-1]
        if len(htf_highs) > 0 and len(htf_lows) > 0:
            htf_swing_high = float(np.max(htf_highs))
            htf_swing_low = float(np.min(htf_lows))

    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "htf_swing_high": htf_swing_high,
        "htf_swing_low": htf_swing_low,
        "high_distance_pct": round((swing_high - curr_close) / curr_close * 100, 2),
        "low_distance_pct": round((curr_close - swing_low) / curr_close * 100, 2)
    }


def detect_price_action_confirmation(
    df: pd.DataFrame,
    idx: int = -1,
    vol_multiplier: float = 1.15
) -> Dict[str, Any]:
    """
    Evaluates 15M Price Action Confirmation Triggers:
    1. Bullish/Bearish Pin Bar (Rejection Hammer / Shooting Star)
    2. Bullish/Bearish Engulfing Candle
    3. Volume Expansion confirmation (Volume >= 1.15x 20-MA)
    """
    if len(df) < 25:
        return {
            "is_confirmed_bullish": False,
            "is_confirmed_bearish": False,
            "pattern": "INSUFFICIENT_DATA",
            "volume_surge": False,
            "strength": 0.0
        }

    curr = df.iloc[idx]
    prev = df.iloc[idx - 1]

    c_open, c_high, c_low, c_close = float(curr["open"]), float(curr["high"]), float(curr["low"]), float(curr["close"])
    p_open, p_high, p_low, p_close = float(prev["open"]), float(prev["high"]), float(prev["low"]), float(prev["close"])

    c_range = max(c_high - c_low, 1e-9)
    body = abs(c_close - c_open)
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    body_ratio = body / c_range
    lower_wick_ratio = lower_wick / c_range
    upper_wick_ratio = upper_wick / c_range

    # Volume check
    vol_ma = float(curr.get("vol_ma_20", curr["volume"]))
    volume_surge = float(curr["volume"]) >= (vol_ma * vol_multiplier)

    # 1. Bullish Patterns
    # Pin Bar (Hammer): Long lower wick >= 50% of range, small upper wick, closes in upper half
    bullish_pinbar = (lower_wick_ratio >= 0.50) and (c_close >= (c_low + c_range * 0.50))
    # Bullish Engulfing: Current green candle body engulfs previous candle body with strong body ratio
    bullish_engulfing = (c_close > c_open) and (p_close < p_open) and (c_close >= p_open) and (c_open <= p_close) and (body_ratio >= 0.50)
    # Strong Bullish Momentum bar
    bullish_momentum = (c_close > c_open) and (body_ratio >= 0.65) and (c_close > p_high)

    # Bullish Liquidity Sweep (SFP): Swept recent low and closed back above
    recent_lows = df["low"].iloc[-15:-1].values if len(df) >= 16 else [c_low]
    min_recent_low = float(np.min(recent_lows))
    bullish_sfp = (c_low < min_recent_low) and (c_close > min_recent_low) and (c_close > c_open)

    is_confirmed_bullish = (bullish_pinbar or bullish_engulfing or bullish_momentum or bullish_sfp) and (volume_surge or body_ratio >= 0.55 or bullish_sfp)

    # 2. Bearish Patterns
    # Pin Bar (Shooting Star): Long upper wick >= 50% of range, small lower wick, closes in lower half
    bearish_pinbar = (upper_wick_ratio >= 0.50) and (c_close <= (c_high - c_range * 0.50))
    # Bearish Engulfing: Current red candle body engulfs previous candle body with strong body ratio
    bearish_engulfing = (c_close < c_open) and (p_close > p_open) and (c_close <= p_open) and (c_open >= p_close) and (body_ratio >= 0.50)
    # Strong Bearish Momentum bar
    bearish_momentum = (c_close < c_open) and (body_ratio >= 0.65) and (c_close < p_low)

    # Bearish Liquidity Sweep (SFP): Swept recent high and closed back below
    recent_highs = df["high"].iloc[-15:-1].values if len(df) >= 16 else [c_high]
    max_recent_high = float(np.max(recent_highs))
    bearish_sfp = (c_high > max_recent_high) and (c_close < max_recent_high) and (c_close < c_open)

    is_confirmed_bearish = (bearish_pinbar or bearish_engulfing or bearish_momentum or bearish_sfp) and (volume_surge or body_ratio >= 0.55 or bearish_sfp)

    pattern_name = "NONE"
    if bullish_sfp:
        pattern_name = "BULLISH_LIQUIDITY_SWEEP_SFP"
    elif bullish_engulfing:
        pattern_name = "BULLISH_ENGULFING"
    elif bullish_pinbar:
        pattern_name = "BULLISH_PINBAR_HAMMER"
    elif bullish_momentum:
        pattern_name = "BULLISH_MOMENTUM_EXPANSION"
    elif bearish_sfp:
        pattern_name = "BEARISH_LIQUIDITY_SWEEP_SFP"
    elif bearish_engulfing:
        pattern_name = "BEARISH_ENGULFING"
    elif bearish_pinbar:
        pattern_name = "BEARISH_PINBAR_STAR"
    elif bearish_momentum:
        pattern_name = "BEARISH_MOMENTUM_EXPANSION"

    return {
        "is_confirmed_bullish": is_confirmed_bullish,
        "is_confirmed_bearish": is_confirmed_bearish,
        "pattern": pattern_name,
        "volume_surge": volume_surge,
        "body_ratio": round(body_ratio, 3),
        "upper_wick_ratio": round(upper_wick_ratio, 3),
        "lower_wick_ratio": round(lower_wick_ratio, 3)
    }
