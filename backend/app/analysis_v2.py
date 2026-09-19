import numpy as np
import pandas as pd


def indicators_v2(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    c = pd.to_numeric(x["Close"], errors="coerce")
    h = pd.to_numeric(x["High"], errors="coerce")
    l = pd.to_numeric(x["Low"], errors="coerce")
    v = pd.to_numeric(x["Volume"], errors="coerce")

    x["EMA20"] = c.ewm(span=20, adjust=False).mean()
    x["EMA50"] = c.ewm(span=50, adjust=False).mean()
    x["EMA200"] = c.ewm(span=200, adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    x["RSI"] = 100 - (100 / (1 + rs))

    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    x["MACD"] = e12 - e26
    x["MACDS"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_HIST"] = x["MACD"] - x["MACDS"]

    pc = c.shift(1)
    tr = pd.concat([
        (h-l).abs(),
        (h-pc).abs(),
        (l-pc).abs(),
    ], axis=1).max(axis=1)
    x["ATR"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x["ATR_PCT"] = (x["ATR"] / c.replace(0, np.nan)) * 100

    x["VOL_MA20"] = v.rolling(20, min_periods=5).mean()
    x["VOL_RATIO"] = v / x["VOL_MA20"].replace(0, np.nan)

    x["EMA20_SLOPE5"] = (x["EMA20"] / x["EMA20"].shift(5) - 1) * 100
    x["ROC20"] = (c / c.shift(20) - 1) * 100

    # Tamamen geçmiş veriden üretilen yapı seviyeleri.
    x["PRIOR_HIGH20"] = h.shift(1).rolling(20, min_periods=20).max()
    x["PRIOR_LOW20"] = l.shift(1).rolling(20, min_periods=20).min()
    x["DIST_HIGH20_PCT"] = ((x["PRIOR_HIGH20"] - c) / c.replace(0, np.nan)) * 100

    # Trend gücünü kaba ama stabil şekilde ölçmek için EMA ayrışması / ATR.
    x["TREND_STRENGTH"] = (x["EMA20"] - x["EMA50"]).abs() / x["ATR"].replace(0, np.nan)

    return x


def quality_score_series(a: pd.DataFrame) -> pd.DataFrame:
    """
    Long-only kalite modeli.
    Amaç: çok sinyal üretmek değil, daha seçici olmak.
    0-10 skor + hard gate üretir.
    """
    x = a.copy()
    score = pd.Series(0.0, index=x.index)

    price = x["Close"]
    e20 = x["EMA20"]
    e50 = x["EMA50"]
    e200 = x["EMA200"]
    rsi = x["RSI"]
    macd = x["MACD"]
    macds = x["MACDS"]
    hist = x["MACD_HIST"]
    vol = x["VOL_RATIO"]
    atrp = x["ATR_PCT"]
    slope = x["EMA20_SLOPE5"]
    prior_high = x["PRIOR_HIGH20"]
    dist_high = x["DIST_HIGH20_PCT"]
    trend_strength = x["TREND_STRENGTH"]

    # Trend: 4.0 puan
    score += (price > e200).astype(float) * 1.25
    score += (e20 > e50).astype(float) * 1.25
    score += (price > e20).astype(float) * 0.75
    score += (slope > 0).astype(float) * 0.75

    # Momentum: 2.5 puan
    score += (macd > macds).astype(float) * 1.00
    score += (hist > hist.shift(1)).astype(float) * 0.50
    score += ((rsi >= 48) & (rsi <= 68)).astype(float) * 1.00

    # Hacim: 1.25 puan
    score += (vol >= 1.20).astype(float) * 1.25
    score += ((vol >= 0.90) & (vol < 1.20)).astype(float) * 0.60

    # Fiyat yapısı: 1.50 puan
    breakout = price > prior_high
    near_high = (~breakout) & dist_high.between(0, 3.0, inclusive="both")
    score += breakout.astype(float) * 1.50
    score += near_high.astype(float) * 0.75

    # Risk / trend kalitesi: 0.75 puan
    score += ((atrp >= 0.8) & (atrp <= 5.5)).astype(float) * 0.35
    score += (trend_strength >= 0.75).astype(float) * 0.40

    # Aşırı ısınmış/zayıf durumlarda ceza.
    score -= (rsi > 75).astype(float) * 1.00
    score -= (atrp > 7.5).astype(float) * 0.75
    score -= (slope < -0.5).astype(float) * 0.75

    score = score.clip(0, 10).round(2)

    # Hard gate: skor yüksek olsa bile ana trend koşulları yoksa AL yok.
    gate = (
        (price > e200) &
        (e20 > e50) &
        (slope > 0) &
        (rsi >= 45) &
        (rsi <= 75) &
        (macd > macds) &
        (atrp <= 7.5)
    )

    x["QUALITY_SCORE"] = score
    x["QUALITY_GATE"] = gate
    x["QUALITY_BUY"] = gate & (score >= 7.25)

    return x


def explain_latest_v2(a: pd.DataFrame) -> dict:
    x = quality_score_series(indicators_v2(a))
    l = x.iloc[-1]

    reasons = []
    if bool(l["Close"] > l["EMA200"]): reasons.append("Fiyat EMA200 üzerinde")
    if bool(l["EMA20"] > l["EMA50"]): reasons.append("EMA20 > EMA50")
    if float(l["EMA20_SLOPE5"]) > 0: reasons.append("EMA20 eğimi pozitif")
    if float(l["MACD"]) > float(l["MACDS"]): reasons.append("MACD pozitif")
    if 48 <= float(l["RSI"]) <= 68: reasons.append(f"RSI dengeli: {float(l['RSI']):.1f}")
    if float(l["VOL_RATIO"]) >= 1.2: reasons.append(f"Hacim teyidi: {float(l['VOL_RATIO']):.2f}x")
    if pd.notna(l["PRIOR_HIGH20"]) and float(l["Close"]) > float(l["PRIOR_HIGH20"]):
        reasons.append("20 günlük direnç kırılımı")
    elif pd.notna(l["DIST_HIGH20_PCT"]) and 0 <= float(l["DIST_HIGH20_PCT"]) <= 3:
        reasons.append("20 günlük zirveye yakın")

    return {
        "score": round(float(l["QUALITY_SCORE"]), 2),
        "signal": "AL" if bool(l["QUALITY_BUY"]) else "IZLE",
        "gate_passed": bool(l["QUALITY_GATE"]),
        "rsi": round(float(l["RSI"]), 2) if pd.notna(l["RSI"]) else None,
        "volume_ratio": round(float(l["VOL_RATIO"]), 2) if pd.notna(l["VOL_RATIO"]) else None,
        "atr_pct": round(float(l["ATR_PCT"]), 2) if pd.notna(l["ATR_PCT"]) else None,
        "reasons": reasons,
    }
