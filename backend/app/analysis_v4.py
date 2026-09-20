import numpy as np
import pandas as pd


def add_volume_indicators(a: pd.DataFrame) -> pd.DataFrame:
    x = a.copy()
    close = pd.to_numeric(x["Close"], errors="coerce")
    high = pd.to_numeric(x["High"], errors="coerce")
    low = pd.to_numeric(x["Low"], errors="coerce")
    volume = pd.to_numeric(x["Volume"], errors="coerce").fillna(0)

    # Relative volume / volume statistics
    x["VOL_MA20_V4"] = volume.rolling(20, min_periods=5).mean()
    x["RVOL20"] = volume / x["VOL_MA20_V4"].replace(0, np.nan)
    vol_std = volume.rolling(20, min_periods=5).std().replace(0, np.nan)
    x["VOL_Z20"] = (volume - x["VOL_MA20_V4"]) / vol_std

    # OBV
    direction = np.sign(close.diff()).fillna(0)
    x["OBV"] = (direction * volume).cumsum()
    x["OBV_EMA10"] = x["OBV"].ewm(span=10, adjust=False).mean()
    x["OBV_SLOPE5"] = x["OBV"] - x["OBV"].shift(5)

    # MFI 14
    typical = (high + low + close) / 3.0
    raw_flow = typical * volume
    tp_diff = typical.diff()
    pos_flow = raw_flow.where(tp_diff > 0, 0.0)
    neg_flow = raw_flow.where(tp_diff < 0, 0.0).abs()
    pos14 = pos_flow.rolling(14, min_periods=14).sum()
    neg14 = neg_flow.rolling(14, min_periods=14).sum()
    ratio = pos14 / neg14.replace(0, np.nan)
    x["MFI14"] = 100 - (100 / (1 + ratio))

    # Chaikin Money Flow 20
    spread = (high - low).replace(0, np.nan)
    mfm = (((close - low) - (high - close)) / spread).fillna(0)
    mfv = mfm * volume
    x["CMF20"] = (
        mfv.rolling(20, min_periods=10).sum()
        / volume.rolling(20, min_periods=10).sum().replace(0, np.nan)
    )

    # Price structure
    x["PRIOR_HIGH20_V4"] = high.shift(1).rolling(20, min_periods=20).max()
    x["PRIOR_LOW20_V4"] = low.shift(1).rolling(20, min_periods=20).min()
    x["BREAKOUT20"] = close > x["PRIOR_HIGH20_V4"]
    x["PRICE_ROC5"] = (close / close.shift(5) - 1) * 100

    return x


def volume_score_series(a: pd.DataFrame) -> pd.DataFrame:
    x = add_volume_indicators(a)
    score = pd.Series(0.0, index=x.index)

    rvol = x["RVOL20"]
    obv_slope = x["OBV_SLOPE5"]
    mfi = x["MFI14"]
    cmf = x["CMF20"]
    vol_z = x["VOL_Z20"]
    breakout = x["BREAKOUT20"]
    roc5 = x["PRICE_ROC5"]

    # RVOL: 0-2.5
    score += (rvol >= 1.50).astype(float) * 2.5
    score += ((rvol >= 1.20) & (rvol < 1.50)).astype(float) * 2.0
    score += ((rvol >= 1.00) & (rvol < 1.20)).astype(float) * 1.0

    # OBV trend: 0-2
    score += (obv_slope > 0).astype(float) * 2.0

    # CMF: 0-2
    score += (cmf >= 0.10).astype(float) * 2.0
    score += ((cmf > 0) & (cmf < 0.10)).astype(float) * 1.0

    # MFI: 0-1.5
    score += ((mfi >= 45) & (mfi <= 75)).astype(float) * 1.5
    score += ((mfi >= 35) & (mfi < 45)).astype(float) * 0.5

    # Price-volume confirmation: 0-1
    score += ((roc5 > 0) & (rvol >= 1.10)).astype(float) * 1.0

    # Breakout with volume: 0-1
    score += (breakout & (rvol >= 1.30)).astype(float) * 1.0

    # Abnormal volume bonus: 0-0.5
    score += (vol_z >= 1.5).astype(float) * 0.5

    # Penalties
    score -= (mfi > 85).astype(float) * 0.75
    score -= ((roc5 < 0) & (rvol >= 1.5)).astype(float) * 1.0
    score -= (cmf < -0.10).astype(float) * 1.0

    x["VOLUME_SCORE"] = score.clip(0, 10).round(2)
    x["VOLUME_GATE"] = (
        (x["VOLUME_SCORE"] >= 6.0)
        & (x["CMF20"] > 0)
        & (x["OBV_SLOPE5"] > 0)
    )
    return x


def volume_latest_summary(a: pd.DataFrame) -> dict:
    x = volume_score_series(a)
    l = x.iloc[-1]
    reasons = []

    rvol = l.get("RVOL20")
    cmf = l.get("CMF20")
    mfi = l.get("MFI14")
    obv_slope = l.get("OBV_SLOPE5")
    vol_z = l.get("VOL_Z20")

    if pd.notna(rvol):
        if rvol >= 1.5:
            reasons.append(f"Güçlü relatif hacim: {float(rvol):.2f}x")
        elif rvol >= 1.2:
            reasons.append(f"Hacim ortalamanın üzerinde: {float(rvol):.2f}x")
        elif rvol < 0.8:
            reasons.append(f"Hacim zayıf: {float(rvol):.2f}x")

    if pd.notna(obv_slope):
        reasons.append("OBV yükseliyor" if obv_slope > 0 else "OBV yükselişi teyit etmiyor")

    if pd.notna(cmf):
        if cmf > 0.10:
            reasons.append(f"CMF güçlü para girişi: {float(cmf):.2f}")
        elif cmf > 0:
            reasons.append(f"CMF pozitif: {float(cmf):.2f}")
        else:
            reasons.append(f"CMF negatif: {float(cmf):.2f}")

    if pd.notna(mfi):
        reasons.append(f"MFI(14): {float(mfi):.1f}")

    if bool(l.get("BREAKOUT20", False)):
        reasons.append("20 günlük direnç üstü fiyat")
        if pd.notna(rvol) and rvol >= 1.3:
            reasons.append("Kırılım hacimle teyitli")

    score = float(l["VOLUME_SCORE"])
    if score >= 8:
        state = "GÜÇLÜ HACİM TEYİDİ"
    elif score >= 6:
        state = "HACİM TEYİTLİ"
    elif score >= 4:
        state = "ORTA"
    else:
        state = "ZAYIF HACİM"

    return {
        "score": round(score, 2),
        "state": state,
        "gate_passed": bool(l["VOLUME_GATE"]),
        "rvol": round(float(rvol), 2) if pd.notna(rvol) else None,
        "cmf": round(float(cmf), 3) if pd.notna(cmf) else None,
        "mfi": round(float(mfi), 2) if pd.notna(mfi) else None,
        "obv_slope_positive": bool(obv_slope > 0) if pd.notna(obv_slope) else None,
        "vol_z": round(float(vol_z), 2) if pd.notna(vol_z) else None,
        "reasons": reasons,
    }


def market_regime_from_index(index_df: pd.DataFrame) -> dict:
    if index_df is None or len(index_df) < 60:
        return {
            "state": "BİLİNMİYOR",
            "score": 0,
            "positive": False,
            "reason": "Endeks verisi yetersiz",
        }

    d = index_df.copy()
    close = pd.to_numeric(d["Close"], errors="coerce")
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    rsi_delta = close.diff()
    gain = rsi_delta.clip(lower=0)
    loss = -rsi_delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    slope = (ema20 / ema20.shift(5) - 1) * 100

    score = 0
    reasons = []
    if close.iloc[-1] > ema50.iloc[-1]:
        score += 1
        reasons.append("Endeks EMA50 üzerinde")
    else:
        reasons.append("Endeks EMA50 altında")

    if ema20.iloc[-1] > ema50.iloc[-1]:
        score += 1
        reasons.append("Endeks EMA20 > EMA50")

    if pd.notna(slope.iloc[-1]) and slope.iloc[-1] > 0:
        score += 1
        reasons.append("Endeks kısa trend eğimi pozitif")

    if pd.notna(rsi.iloc[-1]) and 45 <= rsi.iloc[-1] <= 70:
        score += 1
        reasons.append(f"Endeks RSI dengeli: {float(rsi.iloc[-1]):.1f}")

    positive = score >= 3
    state = "POZİTİF" if positive else ("NÖTR" if score == 2 else "ZAYIF")
    return {
        "state": state,
        "score": score,
        "positive": positive,
        "reason": " • ".join(reasons),
        "rsi": round(float(rsi.iloc[-1]), 2) if pd.notna(rsi.iloc[-1]) else None,
    }
