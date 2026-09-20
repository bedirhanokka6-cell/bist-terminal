import numpy as np
import pandas as pd

from .analysis_v2 import indicators_v2, quality_score_series
from .analysis_v4 import volume_score_series


def prepare_v5(df: pd.DataFrame) -> pd.DataFrame:
    """
    V5 signal engine:
    - EARLY_TREND: trend is forming before a full-strength V4 signal
    - BREAKOUT: prior 20-bar high broken with volume confirmation
    - STRONG_CONFIRMATION: strict V4-style quality + volume confirmation
    Works on daily or intraday OHLCV data.
    """
    q = quality_score_series(indicators_v2(df))
    x = volume_score_series(q)

    close = pd.to_numeric(x["Close"], errors="coerce")
    ema20 = pd.to_numeric(x["EMA20"], errors="coerce")
    ema50 = pd.to_numeric(x["EMA50"], errors="coerce")
    ema200 = pd.to_numeric(x["EMA200"], errors="coerce")
    rsi = pd.to_numeric(x["RSI"], errors="coerce")
    macd = pd.to_numeric(x["MACD"], errors="coerce")
    macds = pd.to_numeric(x["MACDS"], errors="coerce")

    x["EMA20_SLOPE3"] = (ema20 / ema20.shift(3) - 1) * 100
    x["EMA20_SLOPE5_V5"] = (ema20 / ema20.shift(5) - 1) * 100

    # Momentum is starting before the strict quality gate.
    x["EARLY_TREND"] = (
        (close > ema20)
        & (ema20 > ema50)
        & (x["EMA20_SLOPE3"] > 0)
        & (macd > macds)
        & (rsi >= 48)
        & (rsi <= 72)
        & (x["OBV_SLOPE5"] > 0)
        & (x["CMF20"] >= -0.03)
        & (x["RVOL20"] >= 0.90)
    )

    # Breakout must be confirmed by volume/flow so ordinary price spikes do not count.
    x["BREAKOUT_V5"] = (
        (close > x["PRIOR_HIGH20_V4"] * 1.002)
        & (x["RVOL20"] >= 1.25)
        & (x["OBV_SLOPE5"] > 0)
        & (x["CMF20"] > 0)
        & (rsi <= 78)
    )

    # Near-breakout watch: useful as an early warning, not a full entry confirmation.
    distance_to_high = ((x["PRIOR_HIGH20_V4"] - close) / x["PRIOR_HIGH20_V4"]) * 100
    x["NEAR_BREAKOUT"] = (
        (distance_to_high >= 0)
        & (distance_to_high <= 1.5)
        & (x["RVOL20"] >= 1.0)
        & (x["OBV_SLOPE5"] > 0)
        & (x["CMF20"] >= 0)
    )
    x["DIST_TO_HIGH_PCT"] = distance_to_high

    # Strict technical + volume confirmation. Market regime is applied outside this function.
    x["STRONG_CONFIRMATION_BASE"] = (
        x["QUALITY_GATE"]
        & (x["QUALITY_SCORE"] >= 8.25)
        & x["VOLUME_GATE"]
        & (x["VOLUME_SCORE"] >= 6.0)
    )

    # Composite early-move score. This is used for ranking, not as a guaranteed trade signal.
    score = pd.Series(0.0, index=x.index)
    score += (close > ema20).astype(float) * 1.0
    score += (ema20 > ema50).astype(float) * 1.5
    score += (x["EMA20_SLOPE3"] > 0).astype(float) * 1.0
    score += (macd > macds).astype(float) * 1.0
    score += ((rsi >= 50) & (rsi <= 68)).astype(float) * 1.0
    score += (x["RVOL20"] >= 1.0).astype(float) * 1.0
    score += (x["RVOL20"] >= 1.25).astype(float) * 0.5
    score += (x["OBV_SLOPE5"] > 0).astype(float) * 1.0
    score += (x["CMF20"] > 0).astype(float) * 1.0
    score += x["BREAKOUT_V5"].astype(float) * 1.0
    score -= (rsi > 78).astype(float) * 1.0
    score -= (x["CMF20"] < -0.10).astype(float) * 1.0
    x["EARLY_MOVE_SCORE"] = score.clip(0, 10).round(2)

    return x


def latest_v5(df: pd.DataFrame, market_positive: bool | None = None) -> dict:
    x = prepare_v5(df)
    if len(x) == 0:
        return {"signal": "NO_DATA", "reasons": []}

    l = x.iloc[-1]
    p = x.iloc[-2] if len(x) >= 2 else l

    signal = "IZLE"
    reasons = []

    breakout_now = bool(l.get("BREAKOUT_V5", False))
    breakout_prev = bool(p.get("BREAKOUT_V5", False))
    early_now = bool(l.get("EARLY_TREND", False))
    early_prev = bool(p.get("EARLY_TREND", False))
    near_now = bool(l.get("NEAR_BREAKOUT", False))
    strong_base = bool(l.get("STRONG_CONFIRMATION_BASE", False))

    if strong_base and market_positive is True:
        signal = "GUCLU_TEKNIK_TEYIT"
        reasons.append("Kalite + hacim + piyasa filtresi birlikte olumlu")
    elif breakout_now and not breakout_prev:
        signal = "BREAKOUT"
        reasons.append("20 dönem direnç hacim teyidiyle kırıldı")
    elif early_now and not early_prev:
        signal = "ERKEN_TREND"
        reasons.append("EMA/MACD/OBV yapısı yeni pozitif trende dönüyor")
    elif near_now:
        signal = "KIRILIM_YAKIN"
        reasons.append("Fiyat önceki 20 dönem zirvesine %1.5 içinde")
    elif early_now:
        signal = "TREND_DEVAM"
        reasons.append("Erken trend koşulları halen geçerli")

    if pd.notna(l.get("RVOL20")):
        reasons.append(f"RVOL {float(l['RVOL20']):.2f}x")
    if pd.notna(l.get("CMF20")):
        reasons.append(f"CMF {float(l['CMF20']):.3f}")
    if pd.notna(l.get("RSI")):
        reasons.append(f"RSI {float(l['RSI']):.1f}")
    if bool(l.get("OBV_SLOPE5", 0) > 0):
        reasons.append("OBV yükseliyor")

    return {
        "signal": signal,
        "early_move_score": round(float(l.get("EARLY_MOVE_SCORE", 0)), 2),
        "quality_score": round(float(l.get("QUALITY_SCORE", 0)), 2),
        "volume_score": round(float(l.get("VOLUME_SCORE", 0)), 2),
        "rvol": round(float(l["RVOL20"]), 2) if pd.notna(l.get("RVOL20")) else None,
        "cmf": round(float(l["CMF20"]), 3) if pd.notna(l.get("CMF20")) else None,
        "mfi": round(float(l["MFI14"]), 2) if pd.notna(l.get("MFI14")) else None,
        "distance_to_high_pct": round(float(l["DIST_TO_HIGH_PCT"]), 2) if pd.notna(l.get("DIST_TO_HIGH_PCT")) else None,
        "market_positive": market_positive,
        "reasons": reasons,
    }
