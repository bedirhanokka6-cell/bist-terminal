import numpy as np
import pandas as pd


def indicators(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    c = x['Close']
    x['EMA20'] = c.ewm(span=20, adjust=False).mean()
    x['EMA50'] = c.ewm(span=50, adjust=False).mean()
    x['EMA200'] = c.ewm(span=200, adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x['RSI'] = 100 - (100 / (1 + (ag / al.replace(0, np.nan))))

    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    x['MACD'] = e12 - e26
    x['MACDS'] = x['MACD'].ewm(span=9, adjust=False).mean()
    x['MACD_HIST'] = x['MACD'] - x['MACDS']

    x['BB_MID'] = c.rolling(20).mean()
    std = c.rolling(20).std()
    x['BB_UPPER'] = x['BB_MID'] + 2 * std
    x['BB_LOWER'] = x['BB_MID'] - 2 * std

    pc = c.shift(1)
    tr = pd.concat([
        (x['High'] - x['Low']).abs(),
        (x['High'] - pc).abs(),
        (x['Low'] - pc).abs(),
    ], axis=1).max(axis=1)
    x['ATR'] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    x['VOL_MA20'] = x['Volume'].rolling(20, min_periods=1).mean()
    x['VOL_RATIO'] = x['Volume'] / x['VOL_MA20'].replace(0, np.nan)
    return x


def technical_state(a: pd.DataFrame):
    l = a.iloc[-1]
    price = float(l['Close'])
    e20 = float(l['EMA20'])
    e50 = float(l['EMA50'])
    e200 = float(l['EMA200']) if pd.notna(l['EMA200']) else np.nan
    rsi = float(l['RSI']) if pd.notna(l['RSI']) else 50
    macd = float(l['MACD']) if pd.notna(l['MACD']) else 0
    sig = float(l['MACDS']) if pd.notna(l['MACDS']) else 0
    hist = float(l['MACD_HIST']) if pd.notna(l['MACD_HIST']) else 0
    vr = a.loc[a['Volume'] > 0, 'VOL_RATIO'].dropna()
    vol_ratio = float(vr.iloc[-1]) if len(vr) else 1.0
    bb = float(l['BB_MID']) if pd.notna(l['BB_MID']) else np.nan

    pts = 0.0
    reasons = []
    if price > e20:
        pts += 1.5; reasons.append('Fiyat EMA20 üzerinde')
    else:
        reasons.append('Fiyat EMA20 altında')
    if e20 > e50:
        pts += 1.5; reasons.append('EMA20, EMA50 üzerinde')
    else:
        reasons.append('EMA20, EMA50 altında')
    if pd.notna(e200) and price > e200:
        pts += 1.5; reasons.append('Fiyat EMA200 üzerinde')
    elif pd.notna(e200):
        reasons.append('Fiyat EMA200 altında')
    else:
        pts += .75; reasons.append('EMA200 için veri sınırlı')
    if macd > sig:
        pts += 1.5; reasons.append('MACD pozitif kesişimde')
    else:
        reasons.append('MACD sinyalin altında')
    if 45 <= rsi <= 65:
        pts += 1.5; reasons.append(f'RSI dengeli: {rsi:.1f}')
    elif 35 <= rsi <= 75:
        pts += .75; reasons.append(f'RSI sınır bölgede: {rsi:.1f}')
    else:
        pts += .25; reasons.append(f'RSI uç bölgede: {rsi:.1f}')
    if vol_ratio >= 1.2:
        pts += 1.0; reasons.append(f'Hacim teyidi güçlü: {vol_ratio:.2f}x')
    elif vol_ratio >= .8:
        pts += .5; reasons.append(f'Hacim normal: {vol_ratio:.2f}x')
    else:
        reasons.append(f'Hacim zayıf: {vol_ratio:.2f}x')
    if pd.notna(bb) and price >= bb:
        pts += 1.0; reasons.append('Bollinger orta bandı üzerinde')
    elif pd.notna(bb):
        pts += .5; reasons.append('Bollinger orta bandı altında')
    else:
        pts += .5
    if hist > 0:
        pts += .5; reasons.append('MACD histogramı pozitif')

    score = max(0, min(10, pts))
    if score >= 7.5:
        state, color = 'GÜÇLÜ POZİTİF', '#12d6a0'
    elif score >= 5.5:
        state, color = 'POZİTİF', '#58c7ff'
    elif score >= 4.0:
        state, color = 'NÖTR / İZLE', '#f8bd39'
    else:
        state, color = 'ZAYIF', '#ff4d61'
    return {'state': state, 'color': color, 'reasons': reasons, 'score': round(score, 2)}
