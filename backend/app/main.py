from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import yfinance as yf
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import func

from .analysis import indicators, technical_state
from .data import BIST30, load_chart
from .news import company_news, kap_notifications
from .db import get_db
from .models import Signal, SignalResult, NotificationToken, NotificationEvent
from .signal_service import create_signal_from_analysis, evaluate_signal, serialize_signal, serialize_result
from .push_service import send_push

app = FastAPI(title='BIST Terminal API', version='0.2.2')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:3000',
        'http://localhost:3001',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:3001',
        'https://bist-terminal-sable.vercel.app',
        'https://bist-terminal-8z507aj5e-a-7401.vercel.app',
    ],
    allow_origin_regex=r'https://bist-terminal-.*\.vercel\.app',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

def clean_num(v):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return float(v)

def bist_market_status():
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    today = now.date()
    date_text = today.isoformat()

    # Hafta sonu
    if now.weekday() >= 5:
        return {
            "market_open": False,
            "market_status": "PIYASA KAPALI",
            "reason": "Hafta sonu",
        }

    # 2026 tam gün kapalı günler
    closed_2026 = {
        "2026-01-01",
        "2026-03-20",
        "2026-03-21",
        "2026-03-22",
        "2026-04-23",
        "2026-05-01",
        "2026-05-19",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
        "2026-05-30",
        "2026-07-15",
        "2026-08-30",
        "2026-10-29",
    }

    if date_text in closed_2026:
        return {
            "market_open": False,
            "market_status": "PIYASA KAPALI",
            "reason": "Resmi tatil",
        }

    # 2026 yarım günler
    half_days_2026 = {
        "2026-03-19",
        "2026-05-26",
        "2026-10-28",
    }

    open_time = time(10, 0)
    close_time = time(13, 0) if date_text in half_days_2026 else time(18, 0)

    if open_time <= now.time() < close_time:
        return {
            "market_open": True,
            "market_status": "PIYASA ACIK",
            "reason": "Islem saatleri",
        }

    return {
        "market_open": False,
        "market_status": "PIYASA KAPALI",
        "reason": "Islem saatleri disinda",
    }

def data_freshness(index_value):
    try:
        ts = pd.Timestamp(index_value)

        if ts.tzinfo is None:
            ts = ts.tz_localize("Europe/Istanbul")
        else:
            ts = ts.tz_convert("Europe/Istanbul")

        now = pd.Timestamp.now(tz="Europe/Istanbul")
        age_minutes = max(0, (now - ts).total_seconds() / 60)

        market = bist_market_status()

        if not market["market_open"]:
            status = "PIYASA KAPALI"
        elif age_minutes <= 5:
            status = "GUNCEL"
        elif age_minutes <= 20:
            status = "GECIKMELI"
        else:
            status = "ESKI"

        return {
            "data_source": "Yahoo Finance / yfinance",
            "last_data_time": ts.isoformat(),
            "data_age_minutes": round(age_minutes, 1),
            "data_status": status,
            "market_open": market["market_open"],
            "market_status": market["market_status"],
            "market_reason": market["reason"],
        }

    except Exception:
        market = bist_market_status()

        return {
            "data_source": "Yahoo Finance / yfinance",
            "last_data_time": str(index_value),
            "data_age_minutes": None,
            "data_status": market["market_status"],
            "market_open": market["market_open"],
            "market_status": market["market_status"],
            "market_reason": market["reason"],
        }

@app.get('/health')
def health():
    market = bist_market_status()
    return {
        'ok': True,
        'version': '0.2.2',
        'market_open': market['market_open'],
        'market_status': market['market_status'],
        'market_reason': market['reason'],
    }

@app.get('/api/bist30')
def bist30():
    # 30 hisseyi tek tek indirmek yerine tek toplu istekte al.
    # Bu, özellikle Render üzerinde sol BIST30 listesinin çok daha hızlı dolmasını sağlar.
    tickers = [s + '.IS' for s in BIST30]
    rows = []

    try:
        data = yf.download(
            tickers=tickers,
            period='5d',
            interval='15m',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )

        for s in BIST30:
            ticker = s + '.IS'
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.get_level_values(0):
                        continue
                    d = data[ticker].dropna(how='all')
                else:
                    # Tek sembol benzeri dönüş ihtimaline karşı.
                    d = data.dropna(how='all')

                if 'Close' not in d.columns:
                    continue

                closes = pd.to_numeric(d['Close'], errors='coerce').dropna()
                if len(closes) < 2:
                    continue

                p = float(closes.iloc[-1])
                prev = float(closes.iloc[-2])
                rows.append({
                    'symbol': s,
                    'price': p,
                    'change_pct': ((p / prev) - 1) * 100 if prev else 0,
                })
            except Exception:
                continue

    except Exception:
        # Toplu istek başarısız olursa eski yöntem yedek olarak çalışsın.
        for s in BIST30:
            try:
                d = load_chart(s, '5G')
                if len(d) < 2:
                    continue
                p = float(d['Close'].iloc[-1])
                prev = float(d['Close'].iloc[-2])
                rows.append({
                    'symbol': s,
                    'price': p,
                    'change_pct': ((p / prev) - 1) * 100 if prev else 0,
                })
            except Exception:
                continue

    # Her zaman BIST30 sırasını koru.
    order = {s: i for i, s in enumerate(BIST30)}
    rows.sort(key=lambda x: order.get(x['symbol'], 999))
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
            'open': clean_num(row['Open']),
            'high': clean_num(row['High']),
            'low': clean_num(row['Low']),
            'close': clean_num(row['Close']),
            'volume': clean_num(row['Volume']),
            'ema20': clean_num(row['EMA20']),
            'ema50': clean_num(row['EMA50']),
            'ema200': clean_num(row['EMA200']),
            'rsi': clean_num(row['RSI']),
            'macd': clean_num(row['MACD']),
            'macd_signal': clean_num(row['MACDS']),
            'macd_hist': clean_num(row['MACD_HIST']),
            'bb_upper': clean_num(row['BB_UPPER']),
            'bb_mid': clean_num(row['BB_MID']),
            'bb_lower': clean_num(row['BB_LOWER']),
            'atr': clean_num(row['ATR']),
            'vol_ratio': clean_num(row['VOL_RATIO']),
        })

    freshness = data_freshness(a.index[-1])

    return {
        'symbol': symbol,
        'period': period,
        'price': float(l['Close']),
        'open': float(l['Open']),
        'high': float(l['High']),
        'low': float(l['Low']),
        'support': support,
        'resistance': resistance,
        'technical': t,
        'data_source': freshness['data_source'],
        'last_data_time': freshness['last_data_time'],
        'data_age_minutes': freshness['data_age_minutes'],
        'data_status': freshness['data_status'],
        'market_open': freshness['market_open'],
        'market_status': freshness['market_status'],
        'market_reason': freshness['market_reason'],
        'candles': candles,
    }

@app.get('/api/scanner')
def scanner(min_score: float = 0):
    rows = []
    for s in BIST30:
        try:
            d = load_chart(s, '1Y')
            if len(d) < 30:
                continue

            a = indicators(d)
            t = technical_state(a)

            if t['score'] < min_score:
                continue

            l = a.iloc[-1]
            p = a.iloc[-2]
            price = float(l['Close'])
            prev = float(p['Close'])

            rows.append({
                'symbol': s,
                'price': price,
                'change_pct': ((price / prev) - 1) * 100 if prev else 0,
                'score': t['score'],
                'state': t['state'],
                'rsi': clean_num(l['RSI']),
                'vol_ratio': clean_num(l['VOL_RATIO']),
                'support': float(a['Low'].tail(50).min()),
                'resistance': float(a['High'].tail(50).max()),
            })
        except Exception:
            continue

    return sorted(
        rows,
        key=lambda x: (x['score'], x['change_pct']),
        reverse=True
    )

@app.get('/api/news/{symbol}')
def news(symbol: str):
    symbol = symbol.upper()
    return {
        'symbol': symbol,
        'news': company_news(symbol),
        'kap': kap_notifications(symbol)
    }

# ==========================================================
# SİNYAL KAYDI + GEÇMİŞ + BAŞARI TAKİBİ
# ==========================================================

@app.post('/api/signals/{symbol}')
def save_signal(symbol: str, period: str = '1A', db: Session = Depends(get_db)):
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

    return {
        'count': len(rows),
        'items': [serialize_signal(x) for x in rows]
    }

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
        raise HTTPException(
            400,
            'horizon_days yalnızca 1, 3, 5 veya 10 olabilir'
        )

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
            errors.append({
                'signal_id': signal.id,
                'symbol': signal.symbol,
                'error': str(e)
            })

    return {
        'evaluated': evaluated,
        'waiting': waiting,
        'errors': errors
    }

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

    directional = [
        r for r in rows
        if r.successful is not None
    ]

    successful = sum(
        1 for r in directional
        if r.successful is True
    )

    failed = sum(
        1 for r in directional
        if r.successful is False
    )

    returns = [
        float(r.return_pct)
        for r in rows
        if r.return_pct is not None
    ]

    avg_return = (
        sum(returns) / len(returns)
        if returns else None
    )

    success_rate = (
        successful / len(directional) * 100
        if directional else None
    )

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


# ==========================================================
# TELEFON PUSH TOKEN + OTOMATIK ALARM MOTORU
# ==========================================================

class PushRegisterRequest(BaseModel):
    token: str
    platform: str = "web"


@app.post('/api/push/register')
def register_push_token(body: PushRegisterRequest, db: Session = Depends(get_db)):
    token = (body.token or '').strip()
    if len(token) < 20:
        raise HTTPException(400, 'Geçersiz FCM token')

    row = db.query(NotificationToken).filter(NotificationToken.token == token).first()
    if row:
        row.active = True
        row.platform = body.platform or 'web'
        row.updated_at = datetime.utcnow()
    else:
        row = NotificationToken(
            token=token,
            platform=body.platform or 'web',
            active=True,
        )
        db.add(row)
    db.commit()
    return {'ok': True}


@app.get('/api/push/status')
def push_status(db: Session = Depends(get_db)):
    active_count = db.query(NotificationToken).filter(NotificationToken.active == True).count()
    return {
        'ok': True,
        'firebase_ready': bool(os.getenv('FIREBASE_PROJECT_ID') and os.getenv('FIREBASE_CLIENT_EMAIL') and os.getenv('FIREBASE_PRIVATE_KEY')),
        'active_tokens': active_count,
    }


def _cooldown_exists(db: Session, symbol: str, rule_key: str, minutes: int = 60) -> bool:
    cutoff = datetime.utcnow() - pd.Timedelta(minutes=minutes).to_pytimedelta()
    return (
        db.query(NotificationEvent)
        .filter(
            NotificationEvent.symbol == symbol,
            NotificationEvent.rule_key == rule_key,
            NotificationEvent.sent_at >= cutoff,
        )
        .first()
        is not None
    )


def _record_alert(db: Session, symbol: str, rule_key: str, title: str, body: str):
    db.add(NotificationEvent(
        symbol=symbol,
        rule_key=rule_key,
        title=title,
        body=body,
        sent_at=datetime.utcnow(),
    ))
    db.commit()


def _batch_alert_scan_data():
    """BIST30 için 30 dakikalık veriyi tek istekte al."""
    tickers = [s + '.IS' for s in BIST30]
    return yf.download(
        tickers=tickers,
        period='1mo',
        interval='30m',
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by='ticker',
    )


@app.post('/api/alerts/scan')
def scan_and_notify(
    x_alert_key: str | None = None,
    db: Session = Depends(get_db),
):
    # GitHub Actions dışından rastgele tetiklenmeyi engelle.
    expected_key = os.getenv('ALERT_SCAN_KEY', '').strip()
    if expected_key and (x_alert_key or '').strip() != expected_key:
        raise HTTPException(403, 'Alarm anahtarı geçersiz')

    market = bist_market_status()
    if not market['market_open']:
        return {
            'ok': True,
            'skipped': True,
            'reason': market['reason'],
            'market_status': market['market_status'],
            'alerts_sent': 0,
        }

    tokens = [
        r.token for r in
        db.query(NotificationToken).filter(NotificationToken.active == True).all()
        if r.token
    ]
    if not tokens:
        return {'ok': True, 'skipped': True, 'reason': 'Kayıtlı telefon tokeni yok', 'alerts_sent': 0}

    try:
        data = _batch_alert_scan_data()
    except Exception as exc:
        raise HTTPException(503, f'Piyasa verisi alınamadı: {exc}')

    fired = []
    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.get_level_values(0):
                    continue
                d = data[ticker].dropna(how='all').copy()
            else:
                d = data.dropna(how='all').copy()

            if len(d) < 35:
                continue

            a = indicators(d)
            if len(a) < 3:
                continue

            t = technical_state(a)
            l = a.iloc[-1]
            p = a.iloc[-2]

            price = float(l['Close'])
            rsi = clean_num(l['RSI'])
            macd = clean_num(l['MACD'])
            macds = clean_num(l['MACDS'])
            prev_macd = clean_num(p['MACD'])
            prev_macds = clean_num(p['MACDS'])

            # Destek/direnç bugünkü son mumdan etkilenmesin diye son mumu dışarıda bırak.
            hist = a.iloc[:-1]
            support = float(hist['Low'].tail(min(50, len(hist))).min())
            resistance = float(hist['High'].tail(min(50, len(hist))).max())

            rules = []

            if t['score'] >= 8.0:
                rules.append((
                    'score_8',
                    f'{symbol} teknik skor yükseldi',
                    f'{symbol} teknik skoru {t["score"]:.1f}/10. Fiyat: {price:.2f} ₺'
                ))

            if support > 0 and price <= support * 1.015 and price >= support * 0.985:
                rules.append((
                    'near_support',
                    f'{symbol} destek bölgesinde',
                    f'Fiyat {price:.2f} ₺ • Destek yaklaşık {support:.2f} ₺'
                ))

            if resistance > 0 and price > resistance * 1.002:
                rules.append((
                    'resistance_break',
                    f'{symbol} direnç üstüne çıktı',
                    f'Fiyat {price:.2f} ₺ • Önceki direnç yaklaşık {resistance:.2f} ₺'
                ))

            if rsi is not None and rsi < 30:
                rules.append((
                    'rsi_oversold',
                    f'{symbol} RSI aşırı satım bölgesinde',
                    f'RSI {rsi:.1f} • Fiyat {price:.2f} ₺'
                ))

            if (
                prev_macd is not None and prev_macds is not None and
                macd is not None and macds is not None and
                prev_macd <= prev_macds and macd > macds
            ):
                rules.append((
                    'macd_bull_cross',
                    f'{symbol} MACD pozitif kesişim',
                    f'MACD yukarı kesişim oluştu • Fiyat {price:.2f} ₺'
                ))

            for rule_key, title, body in rules:
                if _cooldown_exists(db, symbol, rule_key, minutes=60):
                    continue

                result = send_push(
                    tokens=tokens,
                    title=title,
                    body=body,
                    data={'symbol': symbol, 'rule': rule_key},
                )

                # En az bir cihaza başarıyla gittiyse cooldown kaydı aç.
                if result.get('success_count', 0) > 0:
                    _record_alert(db, symbol, rule_key, title, body)
                    fired.append({
                        'symbol': symbol,
                        'rule': rule_key,
                        'title': title,
                        'success_count': result.get('success_count', 0),
                    })

                # Geçersiz tokenleri otomatik pasife al.
                for bad_token in result.get('invalid_tokens', []):
                    row = db.query(NotificationToken).filter(NotificationToken.token == bad_token).first()
                    if row:
                        row.active = False
                db.commit()

        except Exception:
            continue

    return {
        'ok': True,
        'skipped': False,
        'market_status': market['market_status'],
        'alerts_sent': len(fired),
        'alerts': fired,
    }
