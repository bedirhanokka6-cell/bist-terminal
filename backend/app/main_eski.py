from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd

from .analysis import indicators, technical_state
from .data import BIST30, load_chart
from .news import company_news, kap_notifications

app = FastAPI(title='BIST Terminal API', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

def clean_num(v):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return float(v)

@app.get('/health')
def health():
    return {'ok': True}

@app.get('/api/bist30')
def bist30():
    rows = []
    for s in BIST30:
        try:
            d = load_chart(s, '5G')
            if len(d) < 2: continue
            p = float(d['Close'].iloc[-1]); prev = float(d['Close'].iloc[-2])
            rows.append({'symbol': s, 'price': p, 'change_pct': ((p/prev)-1)*100 if prev else 0})
        except Exception:
            continue
    return rows

@app.get('/api/stock/{symbol}')
def stock(symbol: str, period: str = '1A'):
    symbol = symbol.upper()
    if symbol not in BIST30:
        raise HTTPException(404, 'BIST30 hissesi bulunamadı')
    d = load_chart(symbol, period)
    if d.empty:
        raise HTTPException(503, 'Fiyat verisi alınamadı')
    a = indicators(d)
    t = technical_state(a)
    l = a.iloc[-1]
    support = float(a['Low'].tail(min(50, len(a))).min())
    resistance = float(a['High'].tail(min(50, len(a))).max())
    candles = []
    for idx, row in a.iterrows():
        candles.append({
            'time': idx.isoformat(),
            'open': clean_num(row['Open']), 'high': clean_num(row['High']),
            'low': clean_num(row['Low']), 'close': clean_num(row['Close']),
            'volume': clean_num(row['Volume']), 'ema20': clean_num(row['EMA20']),
            'ema50': clean_num(row['EMA50']), 'ema200': clean_num(row['EMA200']),
            'rsi': clean_num(row['RSI']), 'macd': clean_num(row['MACD']),
            'macd_signal': clean_num(row['MACDS']), 'macd_hist': clean_num(row['MACD_HIST']),
            'bb_upper': clean_num(row['BB_UPPER']), 'bb_mid': clean_num(row['BB_MID']),
            'bb_lower': clean_num(row['BB_LOWER']), 'atr': clean_num(row['ATR']),
            'vol_ratio': clean_num(row['VOL_RATIO']),
        })
    return {
        'symbol': symbol,
        'period': period,
        'price': float(l['Close']),
        'open': float(l['Open']), 'high': float(l['High']), 'low': float(l['Low']),
        'support': support, 'resistance': resistance,
        'technical': t,
        'candles': candles,
    }

@app.get('/api/scanner')
def scanner(min_score: float = 0):
    rows = []
    for s in BIST30:
        try:
            d = load_chart(s, '1Y')
            if len(d) < 30: continue
            a = indicators(d)
            t = technical_state(a)
            if t['score'] < min_score: continue
            l = a.iloc[-1]; p = a.iloc[-2]
            price = float(l['Close']); prev = float(p['Close'])
            rows.append({
                'symbol': s, 'price': price,
                'change_pct': ((price/prev)-1)*100 if prev else 0,
                'score': t['score'], 'state': t['state'],
                'rsi': clean_num(l['RSI']), 'vol_ratio': clean_num(l['VOL_RATIO']),
                'support': float(a['Low'].tail(50).min()),
                'resistance': float(a['High'].tail(50).max()),
            })
        except Exception:
            continue
    return sorted(rows, key=lambda x: (x['score'], x['change_pct']), reverse=True)

@app.get('/api/news/{symbol}')
def news(symbol: str):
    symbol = symbol.upper()
    return {'symbol': symbol, 'news': company_news(symbol), 'kap': kap_notifications(symbol)}
