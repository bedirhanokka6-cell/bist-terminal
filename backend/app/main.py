from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from .analysis import indicators, technical_state
from .data import BIST30, load_chart
from .news import company_news, kap_notifications
from .db import get_db
from .models import Signal, SignalResult
from .signal_service import create_signal_from_analysis, evaluate_signal, serialize_signal, serialize_result

app = FastAPI(title='BIST Terminal API', version='0.2.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:3000',
        'http://localhost:3001',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:3001',
        'https://bist-terminal-8z507aj5e-a-7401.vercel.app',
    ],
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


# ==========================================================
# SİNYAL KAYDI + GEÇMİŞ + BAŞARI TAKİBİ
# ==========================================================

@app.post('/api/signals/{symbol}')
def save_signal(symbol: str, period: str = '1A', db: Session = Depends(get_db)):
    """Seçili hisseyi o an analiz eder ve sonucu PostgreSQL'e kaydeder."""
    try:
        signal = create_signal_from_analysis(db, symbol, period)
        return {'ok': True, 'signal': serialize_signal(signal)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get('/api/signals')
def signal_history(
    symbol: str | None = None,
    signal_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Signal)
    if symbol:
        q = q.filter(Signal.symbol == symbol.upper())
    if signal_type:
        q = q.filter(Signal.signal_type == signal_type.upper())
    rows = q.order_by(Signal.created_at.desc()).limit(limit).all()
    return {'count': len(rows), 'items': [serialize_signal(x) for x in rows]}


@app.get('/api/signals/{signal_id}')
def signal_detail(signal_id: int, db: Session = Depends(get_db)):
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(404, 'Sinyal bulunamadı')
    results = (
        db.query(SignalResult)
        .filter(SignalResult.signal_id == signal_id)
        .order_by(SignalResult.horizon_days.asc())
        .all()
    )
    return {
        'signal': serialize_signal(signal),
        'results': [serialize_result(x) for x in results],
    }


@app.post('/api/signals/{signal_id}/evaluate')
def evaluate_one_signal(
    signal_id: int,
    horizon_days: int = Query(default=5),
    db: Session = Depends(get_db),
):
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(404, 'Sinyal bulunamadı')
    try:
        result, ready = evaluate_signal(db, signal, horizon_days)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {
        'ready': ready,
        'message': 'Sonuç hesaplandı.' if ready else 'Henüz yeterli işlem günü geçmedi.',
        'signal': serialize_signal(signal),
        'result': serialize_result(result),
    }


@app.post('/api/signals/evaluate-pending/all')
def evaluate_pending_signals(
    horizon_days: int = Query(default=5),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if horizon_days not in {1, 3, 5, 10}:
        raise HTTPException(400, 'horizon_days yalnızca 1, 3, 5 veya 10 olabilir')

    signals = db.query(Signal).order_by(Signal.created_at.asc()).limit(limit).all()
    evaluated = 0
    waiting = 0
    errors = []
    for signal in signals:
        try:
            _, ready = evaluate_signal(db, signal, horizon_days)
            evaluated += int(ready)
            waiting += int(not ready)
        except Exception as e:
            errors.append({'signal_id': signal.id, 'symbol': signal.symbol, 'error': str(e)})
    return {'evaluated': evaluated, 'waiting': waiting, 'errors': errors}


@app.get('/api/signals/stats/summary')
def signal_stats(
    horizon_days: int = Query(default=5),
    db: Session = Depends(get_db),
):
    q = db.query(SignalResult).filter(
        SignalResult.horizon_days == horizon_days,
        SignalResult.evaluated_at.isnot(None),
    )
    rows = q.all()
    directional = [r for r in rows if r.successful is not None]
    successful = sum(1 for r in directional if r.successful is True)
    failed = sum(1 for r in directional if r.successful is False)
    avg_return = None
    returns = [float(r.return_pct) for r in rows if r.return_pct is not None]
    if returns:
        avg_return = sum(returns) / len(returns)
    success_rate = (successful / len(directional) * 100) if directional else None
    return {
        'horizon_days': horizon_days,
        'evaluated_total': len(rows),
        'directional_total': len(directional),
        'successful': successful,
        'failed': failed,
        'success_rate_pct': success_rate,
        'average_return_pct': avg_return,
        'note': 'BEKLE sinyalleri başarı oranına dahil edilmez.',
    }
