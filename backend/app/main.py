from fastapi import FastAPI, HTTPException, Depends, Query, Header
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
from .models import Signal, SignalResult, NotificationToken, NotificationEvent, OpenSignalPosition
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
    from .analysis_v2 import indicators_v2
    from .analysis_v4 import volume_score_series, volume_latest_summary, market_regime_from_index

    symbol = symbol.upper()
    if symbol not in BIST30:
        raise HTTPException(404, 'BIST30 hissesi bulunamadı')

    d = load_chart(symbol, period)
    if d.empty:
        raise HTTPException(503, 'Fiyat verisi alınamadı')

    a = indicators(d)
    t = technical_state(a)
    l = a.iloc[-1]

    # V4 volume indicators on the same chart data.
    v4 = volume_score_series(indicators_v2(d))
    vol_summary = volume_latest_summary(indicators_v2(d))

    # Market regime: try BIST100, then BIST30 index. If unavailable, do not crash stock page.
    market_regime = {
        'state': 'BİLİNMİYOR',
        'score': 0,
        'positive': False,
        'reason': 'Endeks verisi alınamadı',
    }
    try:
        idx = yf.download(
            'XU100.IS',
            period='1y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if idx is None or len(idx) < 60:
            idx = yf.download(
                'XU030.IS',
                period='1y',
                interval='1d',
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        if idx is not None and len(idx):
            # yfinance can return MultiIndex even for one ticker.
            if isinstance(idx.columns, pd.MultiIndex):
                idx.columns = idx.columns.get_level_values(0)
            market_regime = market_regime_from_index(idx)
    except Exception:
        pass

    support = float(a['Low'].tail(min(50, len(a))).min())
    resistance = float(a['High'].tail(min(50, len(a))).max())

    candles = []
    for idx, row in a.iterrows():
        vr = v4.loc[idx] if idx in v4.index else None
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
            'vol_ma20': clean_num(vr['VOL_MA20_V4']) if vr is not None else None,
            'rvol': clean_num(vr['RVOL20']) if vr is not None else None,
            'vol_z': clean_num(vr['VOL_Z20']) if vr is not None else None,
            'obv': clean_num(vr['OBV']) if vr is not None else None,
            'obv_ema10': clean_num(vr['OBV_EMA10']) if vr is not None else None,
            'mfi': clean_num(vr['MFI14']) if vr is not None else None,
            'cmf': clean_num(vr['CMF20']) if vr is not None else None,
            'volume_score': clean_num(vr['VOLUME_SCORE']) if vr is not None else None,
            'prior_high20': clean_num(vr['PRIOR_HIGH20_V4']) if vr is not None else None,
            'prior_low20': clean_num(vr['PRIOR_LOW20_V4']) if vr is not None else None,
        })

    freshness = data_freshness(a.index[-1])

    # V4 live decision is an analysis label, not an order instruction.
    v4_signal = (
        'GÜÇLÜ TEKNİK TEYİT'
        if t['score'] >= 8.25 and vol_summary['gate_passed'] and market_regime.get('positive')
        else 'İZLE'
    )

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
        'volume_analysis': vol_summary,
        'market_regime': market_regime,
        'v4_signal': v4_signal,
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



def _v6_trade_levels(a, entry_price: float):
    """
    Support/ATR based levels.
    Risk is clamped between 1% and 7% to avoid unrealistically tight/wide stops.
    """
    try:
        from .analysis_v5 import prepare_v5
        x = prepare_v5(a)
        l = x.iloc[-1]
        atr = float(l['ATR']) if pd.notna(l.get('ATR')) else None
        prior_low = float(l['PRIOR_LOW20_V4']) if pd.notna(l.get('PRIOR_LOW20_V4')) else None
    except Exception:
        atr = None
        prior_low = None

    if atr is None or atr <= 0:
        risk_pct = 3.0
    elif prior_low is None or prior_low >= entry_price:
        risk_pct = (1.75 * atr / entry_price) * 100.0
    else:
        raw_stop = prior_low - 0.25 * atr
        risk_pct = ((entry_price - raw_stop) / entry_price) * 100.0

    risk_pct = min(max(float(risk_pct), 1.0), 7.0)
    stop = entry_price * (1.0 - risk_pct / 100.0)
    one_r = entry_price - stop
    target1 = entry_price + one_r
    target2 = entry_price + 2.0 * one_r

    return {
        'risk_pct': round(risk_pct, 2),
        'stop_price': round(stop, 2),
        'target1_price': round(target1, 2),
        'target2_price': round(target2, 2),
    }


def _serialize_open_signal(x):
    return {
        'id': x.id,
        'symbol': x.symbol,
        'signal_type': x.signal_type,
        'entry_price': x.entry_price,
        'stop_price': x.stop_price,
        'target1_price': x.target1_price,
        'target2_price': x.target2_price,
        'risk_pct': x.risk_pct,
        'quality_score': x.quality_score,
        'volume_score': x.volume_score,
        'early_move_score': x.early_move_score,
        'status': x.status,
        'target1_hit': bool(x.target1_hit),
        'last_price': x.last_price,
        'exit_price': x.exit_price,
        'exit_reason': x.exit_reason,
        'opened_at': x.opened_at.isoformat() if x.opened_at else None,
        'closed_at': x.closed_at.isoformat() if x.closed_at else None,
    }


def _v6_trading_days_open(symbol: str, opened_at) -> int:
    try:
        d = yf.download(
            symbol + '.IS',
            period='2mo',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if d is None or len(d) == 0:
            return 0
        dates = pd.DatetimeIndex(d.index)
        opened_date = pd.Timestamp(opened_at).date()
        return int(sum(1 for x in dates if pd.Timestamp(x).date() > opened_date))
    except Exception:
        return 0


@app.get('/api/positions/open')
def v6_open_positions(db: Session = Depends(get_db)):
    rows = (
        db.query(OpenSignalPosition)
        .filter(OpenSignalPosition.status == 'OPEN')
        .order_by(OpenSignalPosition.opened_at.desc())
        .all()
    )
    return {
        'count': len(rows),
        'items': [_serialize_open_signal(x) for x in rows],
    }


@app.get('/api/positions/history')
def v6_position_history(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(OpenSignalPosition)
        .order_by(OpenSignalPosition.opened_at.desc())
        .limit(limit)
        .all()
    )
    return {
        'count': len(rows),
        'items': [_serialize_open_signal(x) for x in rows],
    }




# ==========================================================
# V9 FINAL — BACKTEST İLE CANLI SİNYALİN AYNI ZAMAN DİLİMİ
# ==========================================================

def _batch_daily_signal_data():
    """BIST30 için sinyal üretiminde kullanılan günlük veriyi tek istekte al."""
    tickers = [s + '.IS' for s in BIST30]
    return yf.download(
        tickers=tickers,
        period='18mo',
        interval='1d',
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by='ticker',
    )


def _extract_ticker_frame(batch, symbol: str):
    ticker = symbol + '.IS'
    if isinstance(batch.columns, pd.MultiIndex):
        if ticker not in batch.columns.get_level_values(0):
            return pd.DataFrame()
        d = batch[ticker].copy()
    else:
        d = batch.copy()
    return d.dropna(subset=['Open','High','Low','Close'])


def _v9_completed_daily_frame(d: pd.DataFrame) -> pd.DataFrame:
    """
    Piyasa açıkken bugünkü günlük mum tamamlanmamıştır.
    Sinyal için yalnızca kapanmış günlük mumları kullan.
    """
    if d is None or len(d) == 0:
        return d

    x = d.copy()
    try:
        today = pd.Timestamp.now(tz='Europe/Istanbul').date()
    except Exception:
        today = pd.Timestamp.now().date()

    last_date = pd.Timestamp(x.index[-1]).date()
    if last_date >= today and len(x) >= 2:
        x = x.iloc[:-1]
    return x


def _v9_daily_market_regime(daily_batch):
    """
    Backtest ile aynı mantık:
    equal-weight BIST30 proxy + EMA20/50 + EMA20 slope + breadth.
    STRONG = trend pozitif ve breadth >= %65.
    POSITIVE = trend pozitif ve breadth >= %55.
    """
    from .analysis_v5 import prepare_v5

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        try:
            d = _v9_completed_daily_frame(_extract_ticker_frame(daily_batch, symbol))
            if d is None or len(d) < 220:
                continue
            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not close_map:
        return {
            'state': 'UNKNOWN',
            'strong': False,
            'positive': False,
            'breadth_pct': None,
            'proxy_slope5_pct': None,
            'date': None,
        }, prepared

    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    ema20 = proxy.ewm(span=20, adjust=False).mean()
    ema50 = proxy.ewm(span=50, adjust=False).mean()
    slope5 = (ema20 / ema20.shift(5) - 1) * 100

    above = {}
    for symbol, a in prepared.items():
        above[symbol] = a['Close'] > a['EMA50']
    breadth_df = pd.DataFrame(above).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100

    trend_ok = bool((ema20.iloc[-1] > ema50.iloc[-1]) and (slope5.iloc[-1] > 0))
    b = float(breadth.iloc[-1])
    strong = bool(trend_ok and b >= 65)
    positive = bool(trend_ok and b >= 55)

    state = 'STRONG' if strong else ('POSITIVE' if positive else 'WEAK')
    return {
        'state': state,
        'strong': strong,
        'positive': positive,
        'breadth_pct': round(b, 2),
        'proxy_slope5_pct': round(float(slope5.iloc[-1]), 3),
        'date': pd.Timestamp(close_df.index[-1]).date().isoformat(),
    }, prepared


def _v9_trade_levels(a, entry_price: float):
    """
    Final ileri-test profili:
    destek/ATR stop, en fazla %6; Hedef1=1R, Hedef2=2R.
    """
    try:
        l = a.iloc[-1]
        atr = float(l['ATR']) if pd.notna(l.get('ATR')) else None
        prior_low = float(l['PRIOR_LOW20_V4']) if pd.notna(l.get('PRIOR_LOW20_V4')) else None
    except Exception:
        atr = None
        prior_low = None

    if atr is None or atr <= 0:
        risk_pct = 3.0
    elif prior_low is None or prior_low >= entry_price:
        risk_pct = (1.75 * atr / entry_price) * 100.0
    else:
        raw_stop = prior_low - 0.25 * atr
        risk_pct = ((entry_price - raw_stop) / entry_price) * 100.0

    risk_pct = min(max(float(risk_pct), 1.0), 6.0)
    stop = entry_price * (1.0 - risk_pct / 100.0)
    one_r = entry_price - stop

    return {
        'risk_pct': round(risk_pct, 2),
        'stop_price': round(stop, 2),
        'target1_price': round(entry_price + one_r, 2),
        'target2_price': round(entry_price + 2.0 * one_r, 2),
    }


@app.get('/api/v9/live-status')
def v9_live_status(db: Session = Depends(get_db)):
    open_count = (
        db.query(OpenSignalPosition)
        .filter(OpenSignalPosition.status == 'OPEN')
        .count()
    )
    try:
        daily = _batch_daily_signal_data()
        regime, _ = _v9_daily_market_regime(daily)
    except Exception as exc:
        regime = {'state': 'UNKNOWN', 'error': str(exc)}

    return {
        'ok': True,
        'model': 'v9_final_forward_test',
        'mode': 'PAPER_FORWARD_TEST',
        'real_money_orders': False,
        'signal_timeframe': 'completed_daily_candle',
        'entry_execution': 'next live scan/current market price after completed signal',
        'entry_rule': 'STRONG_CONFIRMATION_BASE + STRONG market regime',
        'watch_only': ['BREAKOUT', 'ERKEN_TREND', 'KIRILIM_YAKIN'],
        'risk': 'support/ATR, max %6',
        'target1': '1R alert',
        'target2': '2R close',
        'max_hold': '10 trading days',
        'open_positions': open_count,
        'market_regime': regime,
    }

@app.post('/api/alerts/scan')
def scan_and_notify(
    x_alert_key: str | None = Header(default=None, alias='x-alert-key'),
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

    # V9: teknik sinyal günlük kapanmış mumdan; intraday veri yalnız fiyat/stop takibi için.
    try:
        daily_signal_data = _batch_daily_signal_data()
        v9_market, v9_prepared = _v9_daily_market_regime(daily_signal_data)
    except Exception as exc:
        daily_signal_data = None
        v9_prepared = {}
        v9_market = {
            'state': 'UNKNOWN',
            'strong': False,
            'positive': False,
            'error': str(exc),
        }

    fired = []

    # ------------------------------------------------------
    # V6: önce mevcut açık teknik sinyalleri yönet.
    # STOP / Hedef 1 / Hedef 2 / 10 işlem günü çıkışı.
    # ------------------------------------------------------
    open_positions = (
        db.query(OpenSignalPosition)
        .filter(OpenSignalPosition.status == 'OPEN')
        .all()
    )

    for pos in open_positions:
        ticker = pos.symbol + '.IS'
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if ticker not in data.columns.get_level_values(0):
                    continue
                od = data[ticker].dropna(how='all').copy()
            else:
                od = data.dropna(how='all').copy()

            if od is None or len(od) == 0:
                continue

            current_price = float(pd.to_numeric(od['Close'], errors='coerce').dropna().iloc[-1])
            pos.last_price = current_price

            rule_key = None
            title = None
            body = None
            close_now = False

            if current_price <= float(pos.stop_price):
                rule_key = f'v6_stop_{pos.id}'
                title = f'{pos.symbol} — STOP / ÇIKIŞ UYARISI'
                body = (
                    f'Fiyat {current_price:.2f} ₺ • Stop {pos.stop_price:.2f} ₺ kırıldı '
                    f'• Giriş {pos.entry_price:.2f} ₺'
                )
                pos.exit_price = current_price
                pos.exit_reason = 'STOP'
                close_now = True

            elif current_price >= float(pos.target2_price):
                rule_key = f'v6_target2_{pos.id}'
                title = f'{pos.symbol} — HEDEF 2 UYARISI'
                body = (
                    f'Fiyat {current_price:.2f} ₺ • Hedef 2 {pos.target2_price:.2f} ₺ görüldü '
                    f'• Giriş {pos.entry_price:.2f} ₺'
                )
                pos.exit_price = current_price
                pos.exit_reason = 'TARGET2'
                close_now = True

            elif (not pos.target1_hit) and current_price >= float(pos.target1_price):
                rule_key = f'v6_target1_{pos.id}'
                title = f'{pos.symbol} — HEDEF 1 UYARISI'
                body = (
                    f'Fiyat {current_price:.2f} ₺ • Hedef 1 {pos.target1_price:.2f} ₺ görüldü '
                    f'• Hedef 2 {pos.target2_price:.2f} ₺'
                )
                pos.target1_hit = True

            else:
                trading_days = _v6_trading_days_open(pos.symbol, pos.opened_at)
                if trading_days >= 10:
                    rule_key = f'v6_time_{pos.id}'
                    title = f'{pos.symbol} — 10 GÜN / ÇIKIŞ DEĞERLENDİRMESİ'
                    body = (
                        f'10 işlem günü doldu • Güncel {current_price:.2f} ₺ '
                        f'• Giriş {pos.entry_price:.2f} ₺'
                    )
                    pos.exit_price = current_price
                    pos.exit_reason = 'TIME'
                    close_now = True

            if rule_key:
                result = send_push(
                    tokens=tokens,
                    title=title,
                    body=body,
                    data={'symbol': pos.symbol, 'rule': rule_key, 'position_id': str(pos.id)},
                )
                if result.get('success_count', 0) > 0:
                    _record_alert(db, pos.symbol, rule_key, title, body)
                    fired.append({
                        'symbol': pos.symbol,
                        'rule': rule_key,
                        'title': title,
                        'success_count': result.get('success_count', 0),
                    })

            if close_now:
                pos.status = 'CLOSED'
                pos.closed_at = datetime.utcnow()

            db.add(pos)
            db.commit()

        except Exception:
            db.rollback()
            continue

    # ------------------------------------------------------
    # Sonra yeni BIST30 fırsatlarını tara.
    # ------------------------------------------------------
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

            # --------------------------------------------------
            # V9 FINAL: günlük kapanmış mumlarla izleme + paper forward giriş.
            # 30 dakikalık veri sadece güncel fiyat ve açık pozisyon yönetiminde kullanılır.
            # --------------------------------------------------
            try:
                from .analysis_v5 import latest_v5

                daily_a = v9_prepared.get(symbol)
                if daily_a is not None and len(daily_a) >= 220:
                    v9_watch = latest_v5(
                        _v9_completed_daily_frame(_extract_ticker_frame(daily_signal_data, symbol)),
                        market_positive=v9_market.get('positive', False),
                    )

                    watch_sig = v9_watch.get('signal')
                    if watch_sig == 'BREAKOUT':
                        rules.append((
                            'v9_watch_breakout',
                            f'{symbol} — BREAKOUT / İZLE',
                            f'Günlük direnç kırılımı • Fiyat {price:.2f} ₺ • '
                            f'RVOL {v9_watch.get("rvol") or 0:.2f}x • '
                            f'Piyasa {v9_market.get("state","UNKNOWN")}'
                        ))
                    elif watch_sig == 'ERKEN_TREND':
                        rules.append((
                            'v9_watch_early',
                            f'{symbol} — ERKEN TREND / İZLE',
                            f'Günlük trend güçleniyor • Fiyat {price:.2f} ₺ • '
                            f'Piyasa {v9_market.get("state","UNKNOWN")}'
                        ))
                    elif watch_sig == 'KIRILIM_YAKIN':
                        rules.append((
                            'v9_watch_near',
                            f'{symbol} — KIRILIMA YAKIN / İZLE',
                            f'Dirence yakın • Fiyat {price:.2f} ₺ • '
                            f'Piyasa {v9_market.get("state","UNKNOWN")}'
                        ))

                    # Final paper-forward giriş:
                    # yalnız güçlü teknik teyit + STRONG piyasa.
                    last_daily = daily_a.iloc[-1]
                    final_entry = bool(
                        last_daily.get('STRONG_CONFIRMATION_BASE', False)
                        and v9_market.get('strong', False)
                    )

                    if final_entry:
                        existing = (
                            db.query(OpenSignalPosition)
                            .filter(
                                OpenSignalPosition.symbol == symbol,
                                OpenSignalPosition.status == 'OPEN',
                            )
                            .first()
                        )

                        if existing is None:
                            levels = _v9_trade_levels(daily_a, price)
                            new_pos = OpenSignalPosition(
                                symbol=symbol,
                                signal_type='V9_STRONG_PAPER',
                                entry_price=price,
                                stop_price=levels['stop_price'],
                                target1_price=levels['target1_price'],
                                target2_price=levels['target2_price'],
                                risk_pct=levels['risk_pct'],
                                quality_score=float(last_daily.get('QUALITY_SCORE', 0) or 0),
                                volume_score=float(last_daily.get('VOLUME_SCORE', 0) or 0),
                                early_move_score=float(last_daily.get('EARLY_MOVE_SCORE', 0) or 0),
                                status='OPEN',
                                target1_hit=False,
                                last_price=price,
                            )
                            db.add(new_pos)
                            db.commit()
                            db.refresh(new_pos)

                            entry_title = f'{symbol} — V9 GÜÇLÜ TEYİT / PAPER'
                            entry_body = (
                                f'Giriş {price:.2f} ₺ • Stop {levels["stop_price"]:.2f} ₺ '
                                f'• H1 {levels["target1_price"]:.2f} ₺ '
                                f'• H2 {levels["target2_price"]:.2f} ₺ '
                                f'• Teknik {float(last_daily.get("QUALITY_SCORE",0) or 0):.1f}/10 '
                                f'• Hacim {float(last_daily.get("VOLUME_SCORE",0) or 0):.1f}/10 '
                                f'• Piyasa STRONG'
                            )

                            push_result = send_push(
                                tokens=tokens,
                                title=entry_title,
                                body=entry_body,
                                data={
                                    'symbol': symbol,
                                    'rule': 'v9_paper_entry',
                                    'position_id': str(new_pos.id),
                                    'signal_type': 'V9_STRONG_PAPER',
                                },
                            )
                            if push_result.get('success_count', 0) > 0:
                                _record_alert(
                                    db, symbol, f'v9_paper_entry_{new_pos.id}',
                                    entry_title, entry_body
                                )
                                fired.append({
                                    'symbol': symbol,
                                    'rule': 'v9_paper_entry',
                                    'title': entry_title,
                                    'success_count': push_result.get('success_count', 0),
                                })
            except Exception:
                db.rollback()

            for rule_key, title, body in rules:
                cooldown_minutes = 360 if (rule_key.startswith('v5_') or rule_key.startswith('v9_watch_')) else 60
                if _cooldown_exists(db, symbol, rule_key, minutes=cooldown_minutes):
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


# ==========================================================
# BIST30 GECMIS VERI BACKTEST
# ==========================================================

def _score_series(a: pd.DataFrame) -> pd.Series:
    """
    Mevcut technical_state() ile aynı puanlama mantığını satır bazında uygular.
    Gelecek veriyi kullanmaz; her gün yalnızca o güne kadar oluşmuş indikatörleri kullanır.
    """
    score = pd.Series(0.0, index=a.index)

    price = a['Close']
    e20 = a['EMA20']
    e50 = a['EMA50']
    e200 = a['EMA200']
    rsi = a['RSI'].fillna(50)
    macd = a['MACD'].fillna(0)
    macds = a['MACDS'].fillna(0)
    hist = a['MACD_HIST'].fillna(0)
    vr = a['VOL_RATIO'].fillna(1.0)
    bb = a['BB_MID']

    score += (price > e20).astype(float) * 1.5
    score += (e20 > e50).astype(float) * 1.5

    # Mevcut teknik skor mantığı: EMA200 varsa fiyat üzerindeyse +1.5,
    # henüz EMA200 yoksa +0.75.
    score += ((e200.notna()) & (price > e200)).astype(float) * 1.5
    score += (e200.isna()).astype(float) * 0.75

    score += (macd > macds).astype(float) * 1.5

    balanced = (rsi >= 45) & (rsi <= 65)
    border = (~balanced) & (rsi >= 35) & (rsi <= 75)
    extreme = ~(balanced | border)
    score += balanced.astype(float) * 1.5
    score += border.astype(float) * 0.75
    score += extreme.astype(float) * 0.25

    score += (vr >= 1.2).astype(float) * 1.0
    score += ((vr >= 0.8) & (vr < 1.2)).astype(float) * 0.5

    score += ((bb.notna()) & (price >= bb)).astype(float) * 1.0
    score += ((bb.notna()) & (price < bb)).astype(float) * 0.5
    score += (bb.isna()).astype(float) * 0.5

    score += (hist > 0).astype(float) * 0.5
    return score.clip(lower=0, upper=10).round(2)


def _signal_from_score(score: pd.Series) -> pd.Series:
    out = pd.Series('BEKLE', index=score.index, dtype='object')
    out.loc[score >= 7.5] = 'AL'
    out.loc[score < 4.0] = 'SAT'
    return out


def _safe_pct(v):
    if v is None or pd.isna(v):
        return None
    return round(float(v), 3)


@app.get('/api/backtest/bist30')
def backtest_bist30(
    test_days: int = Query(default=252, ge=60, le=504),
):
    """
    BIST30 için günlük mumlarda geçmiş test.
    - 3 yıllık veri indirir; ilk bölüm indikatör ısınması içindir.
    - Son test_days işlem günü değerlendirilir.
    - AL: gelecekte fiyat yükselirse başarılı.
    - SAT: gelecekte fiyat düşerse başarılı.
    - BEKLE başarı oranına dahil edilmez.
    - 1/3/5/10 işlem günü ufukları ölçülür.
    """
    horizons = [1, 3, 5, 10]
    tickers = [s + '.IS' for s in BIST30]

    try:
        raw = yf.download(
            tickers=tickers,
            period='3y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'Backtest verisi alınamadı: {exc}')

    all_rows = []
    symbol_summary = []

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open', 'High', 'Low', 'Close'])
            if len(d) < 260:
                continue

            a = indicators(d)
            a['score'] = _score_series(a)
            a['signal'] = _signal_from_score(a['score'])

            # Sadece son test_days işlem gününü test et.
            start_pos = max(0, len(a) - test_days)
            tested = a.iloc[start_pos:].copy()

            per_symbol_counts = {'AL': 0, 'SAT': 0, 'BEKLE': 0}
            for h in horizons:
                tested[f'ret_{h}'] = (a['Close'].shift(-h).reindex(tested.index) / tested['Close'] - 1.0) * 100.0

            for dt, row in tested.iterrows():
                sig = row['signal']
                per_symbol_counts[sig] = per_symbol_counts.get(sig, 0) + 1

                for h in horizons:
                    ret = row[f'ret_{h}']
                    if pd.isna(ret):
                        continue

                    success = None
                    if sig == 'AL':
                        success = bool(ret > 0)
                    elif sig == 'SAT':
                        success = bool(ret < 0)

                    all_rows.append({
                        'symbol': symbol,
                        'date': pd.Timestamp(dt).date().isoformat(),
                        'signal': sig,
                        'score': float(row['score']),
                        'horizon': h,
                        'future_return_pct': float(ret),
                        'success': success,
                    })

            symbol_summary.append({
                'symbol': symbol,
                'tested_days': int(len(tested)),
                'al_days': int(per_symbol_counts.get('AL', 0)),
                'sat_days': int(per_symbol_counts.get('SAT', 0)),
                'wait_days': int(per_symbol_counts.get('BEKLE', 0)),
            })

        except Exception:
            continue

    if not all_rows:
        raise HTTPException(503, 'Backtest için yeterli veri üretilemedi.')

    df = pd.DataFrame(all_rows)
    actionable = df[df['signal'].isin(['AL', 'SAT'])].copy()

    horizon_summary = []
    for h in horizons:
        g = actionable[actionable['horizon'] == h].copy()
        if len(g) == 0:
            horizon_summary.append({
                'horizon_days': h,
                'signals': 0,
                'success_rate_pct': None,
                'avg_directional_return_pct': None,
                'median_directional_return_pct': None,
            })
            continue

        # AL için getiri pozitif, SAT için fiyat düşüşü pozitif performans kabul edilir.
        directional = g['future_return_pct'].where(g['signal'] == 'AL', -g['future_return_pct'])
        horizon_summary.append({
            'horizon_days': h,
            'signals': int(len(g)),
            'successes': int(g['success'].sum()),
            'failures': int((~g['success']).sum()),
            'success_rate_pct': round(float(g['success'].mean() * 100), 2),
            'avg_directional_return_pct': round(float(directional.mean()), 3),
            'median_directional_return_pct': round(float(directional.median()), 3),
        })

    # Hisse bazında 5 günlük performans: yeterli sinyal olanları göster.
    h5 = actionable[actionable['horizon'] == 5].copy()
    by_symbol = []
    if len(h5):
        for symbol, g in h5.groupby('symbol'):
            directional = g['future_return_pct'].where(g['signal'] == 'AL', -g['future_return_pct'])
            by_symbol.append({
                'symbol': symbol,
                'signals': int(len(g)),
                'success_rate_pct': round(float(g['success'].mean() * 100), 2),
                'avg_directional_return_pct': round(float(directional.mean()), 3),
            })
        by_symbol.sort(key=lambda x: (x['signals'] >= 10, x['success_rate_pct'], x['avg_directional_return_pct']), reverse=True)

    # AL ve SAT'ı ayrı göster.
    signal_type_summary = []
    for sig in ['AL', 'SAT']:
        for h in horizons:
            g = actionable[(actionable['signal'] == sig) & (actionable['horizon'] == h)].copy()
            if not len(g):
                continue
            directional = g['future_return_pct'] if sig == 'AL' else -g['future_return_pct']
            signal_type_summary.append({
                'signal': sig,
                'horizon_days': h,
                'signals': int(len(g)),
                'success_rate_pct': round(float(g['success'].mean() * 100), 2),
                'avg_directional_return_pct': round(float(directional.mean()), 3),
            })

    return {
        'ok': True,
        'method': {
            'universe': 'BIST30',
            'data_interval': '1d',
            'download_period': '3y',
            'tested_last_trading_days': test_days,
            'signal_rules': {
                'AL': 'technical_score >= 7.5',
                'SAT': 'technical_score < 4.0',
                'BEKLE': '4.0 <= technical_score < 7.5',
            },
            'success_definition': 'AL sonrası fiyat yükselmesi; SAT sonrası fiyat düşmesi',
            'horizons_trading_days': horizons,
            'note': 'BEKLE başarı oranına dahil edilmez. İşlem maliyeti, vergi, kayma ve gerçek zamanlı veri farkı dahil değildir.',
        },
        'tested_symbols': int(len(symbol_summary)),
        'total_actionable_signal_observations': int(len(actionable[actionable['horizon'] == 1])),
        'horizon_summary': horizon_summary,
        'signal_type_summary': signal_type_summary,
        'best_symbols_5d': by_symbol[:10],
        'symbol_coverage': symbol_summary,
    }


# ==========================================================
# V2 SECICI TEKNIK MODEL + WALK-FORWARD BACKTEST
# ==========================================================

@app.get('/api/analysis/v2/{symbol}')
def stock_analysis_v2(symbol: str):
    from .analysis_v2 import explain_latest_v2

    symbol = symbol.upper().replace('.IS', '')
    if symbol not in BIST30:
        raise HTTPException(404, 'BIST30 içinde hisse bulunamadı')

    d = load_chart(symbol, '1Y')
    if d is None or len(d) < 220:
        raise HTTPException(503, 'V2 analiz için yeterli veri yok')

    return {
        'symbol': symbol,
        'model': 'quality_v2',
        **explain_latest_v2(d),
        'note': 'Bu teknik koşul analizidir; yatırım tavsiyesi değildir.'
    }


@app.get('/api/backtest/v2')
def backtest_v2(
    test_days: int = Query(default=504, ge=252, le=756),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
):
    """
    Daha gerçekçi event-based long-only test:
    - Current BIST30 universe
    - Günlük veri
    - Sadece yeni AL oluştuğu gün event sayılır
    - Aynı hissede cooldown boyunca tekrar sayılmaz
    - Maliyet net getiriden düşülür
    - Dönem ikiye ayrılır: development / validation
    """
    from .analysis_v2 import indicators_v2, quality_score_series

    horizons = [1, 3, 5, 10]
    tickers = [s + '.IS' for s in BIST30]
    roundtrip_cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V2 backtest verisi alınamadı: {exc}')

    events = []

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            a = quality_score_series(indicators_v2(d))

            # Son test_days + gelecek horizonlar.
            start_pos = max(220, len(a) - test_days)
            end_pos = len(a) - max(horizons)

            last_event_pos = -10_000
            prev_buy = False

            for pos in range(start_pos, end_pos):
                row = a.iloc[pos]
                is_buy = bool(row['QUALITY_BUY'])

                # Sadece yeni sinyal oluşumu + cooldown.
                new_event = is_buy and (not prev_buy) and (pos - last_event_pos >= cooldown_days)
                prev_buy = is_buy

                if not new_event:
                    continue

                entry = float(row['Close'])
                event = {
                    'symbol': symbol,
                    'date': pd.Timestamp(a.index[pos]).date().isoformat(),
                    'score': float(row['QUALITY_SCORE']),
                    'entry': entry,
                    'returns': {},
                }

                for h in horizons:
                    exit_price = float(a['Close'].iloc[pos+h])
                    gross = ((exit_price / entry) - 1.0) * 100.0
                    net = gross - roundtrip_cost_pct
                    event['returns'][h] = net

                events.append(event)
                last_event_pos = pos

        except Exception:
            continue

    if not events:
        raise HTTPException(503, 'V2 model hiç sinyal üretemedi')

    edf = pd.DataFrame([{
        'symbol': e['symbol'],
        'date': e['date'],
        'score': e['score'],
        **{f'ret_{h}': e['returns'][h] for h in horizons}
    } for e in events])

    edf['date'] = pd.to_datetime(edf['date'])
    edf = edf.sort_values('date').reset_index(drop=True)

    # Tarihe göre %50 / %50 ayır. Aynı günkü tüm hisseler aynı tarafta kalsın.
    unique_dates = sorted(edf['date'].dt.date.unique())
    split_i = max(1, len(unique_dates)//2)
    split_date = pd.Timestamp(unique_dates[split_i])

    edf['segment'] = np.where(edf['date'] < split_date, 'development', 'validation')

    def summarize(frame):
        out = []
        for h in horizons:
            s = frame[f'ret_{h}'].dropna()
            if not len(s):
                continue
            out.append({
                'horizon_days': h,
                'events': int(len(s)),
                'wins': int((s > 0).sum()),
                'losses': int((s <= 0).sum()),
                'success_rate_pct': round(float((s > 0).mean()*100), 2),
                'avg_net_return_pct': round(float(s.mean()), 3),
                'median_net_return_pct': round(float(s.median()), 3),
            })
        return out

    # Skor bandı analizi: daha yüksek skor gerçekten daha kaliteli mi?
    score_buckets = []
    temp = edf.copy()
    temp['score_bucket'] = pd.cut(
        temp['score'],
        bins=[7.24, 7.74, 8.24, 8.74, 10.01],
        labels=['7.25-7.74','7.75-8.24','8.25-8.74','8.75+'],
        include_lowest=True,
    )
    for bucket, g in temp[temp['segment']=='validation'].groupby('score_bucket', observed=True):
        if not len(g):
            continue
        s = g['ret_5'].dropna()
        score_buckets.append({
            'score_bucket': str(bucket),
            'events': int(len(s)),
            'success_rate_5d_pct': round(float((s > 0).mean()*100), 2) if len(s) else None,
            'avg_net_return_5d_pct': round(float(s.mean()), 3) if len(s) else None,
        })

    # Validation tarafında hisse bazlı 5 günlük görünüm.
    by_symbol = []
    vg = edf[edf['segment']=='validation']
    for symbol, g in vg.groupby('symbol'):
        s = g['ret_5'].dropna()
        if len(s) < 3:
            continue
        by_symbol.append({
            'symbol': symbol,
            'events': int(len(s)),
            'success_rate_5d_pct': round(float((s > 0).mean()*100), 2),
            'avg_net_return_5d_pct': round(float(s.mean()), 3),
        })
    by_symbol.sort(key=lambda x: (x['events'] >= 5, x['success_rate_5d_pct'], x['avg_net_return_5d_pct']), reverse=True)

    return {
        'ok': True,
        'model': 'quality_v2_long_only',
        'tested_current_bist30_symbols': int(edf['symbol'].nunique()),
        'event_count': int(len(edf)),
        'split_date': split_date.date().isoformat(),
        'settings': {
            'test_days': test_days,
            'roundtrip_cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'signal': 'QUALITY_SCORE >= 7.25 + trend hard-gate',
            'event_rule': 'yalnızca yeni AL oluştuğunda event; ardışık AL günleri ayrı sinyal sayılmaz',
        },
        'development': summarize(edf[edf['segment']=='development']),
        'validation': summarize(edf[edf['segment']=='validation']),
        'validation_score_buckets': score_buckets,
        'validation_best_symbols_5d': by_symbol[:10],
        'caveats': [
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance verisi kullanılır; resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
            'Haber/KAP faktörü bu testte henüz yoktur; önce teknik çekirdek ayrı doğrulanır.',
        ],
    }


# ==========================================================
# V3 RISK YONETIMI BACKTEST
# ==========================================================

def _simulate_trade_path(
    a: pd.DataFrame,
    pos: int,
    stop_price: float,
    target_price: float,
    max_hold_days: int,
    cost_pct: float,
):
    """
    Günlük OHLC ile muhafazakâr trade simülasyonu.
    Giriş sinyal gününün kapanış fiyatıdır.
    Stop/target kontrolü bir sonraki işlem gününden başlar.
    Aynı gün hem stop hem hedef görülürse sıralama bilinmediği için STOP önce kabul edilir.
    """
    entry = float(a['Close'].iloc[pos])

    exit_price = None
    exit_day = None
    exit_reason = None

    last_pos = min(len(a) - 1, pos + max_hold_days)
    for j in range(pos + 1, last_pos + 1):
        low = float(a['Low'].iloc[j])
        high = float(a['High'].iloc[j])

        stop_hit = low <= stop_price
        target_hit = high >= target_price

        if stop_hit and target_hit:
            exit_price = stop_price
            exit_day = j - pos
            exit_reason = 'STOP_SAME_DAY'
            break
        if stop_hit:
            exit_price = stop_price
            exit_day = j - pos
            exit_reason = 'STOP'
            break
        if target_hit:
            exit_price = target_price
            exit_day = j - pos
            exit_reason = 'TARGET'
            break

    if exit_price is None:
        exit_price = float(a['Close'].iloc[last_pos])
        exit_day = last_pos - pos
        exit_reason = 'TIME'

    gross = ((exit_price / entry) - 1.0) * 100.0
    net = gross - cost_pct
    risk_pct = ((entry - stop_price) / entry) * 100.0
    r_multiple = net / risk_pct if risk_pct > 0 else None

    return {
        'net_return_pct': float(net),
        'exit_day': int(exit_day),
        'exit_reason': exit_reason,
        'risk_pct': float(risk_pct),
        'r_multiple': float(r_multiple) if r_multiple is not None else None,
    }


@app.get('/api/backtest/v3-risk')
def backtest_v3_risk(
    test_days: int = Query(default=504, ge=252, le=756),
    min_score: float = Query(default=8.25, ge=7.25, le=10.0),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
    fixed_stop_pct: float = Query(default=3.0, ge=1.0, le=10.0),
    atr_mult: float = Query(default=1.75, ge=0.75, le=4.0),
    reward_r: float = Query(default=2.0, ge=1.0, le=4.0),
):
    """
    V3 risk yönetimi karşılaştırması.
    Sadece seçici AL eventleri kullanılır.

    Karşılaştırılan yöntemler:
    - baseline_time: stop/target yok, max_hold sonunda çıkış
    - fixed_stop_2r: sabit yüzde stop + 2R hedef
    - atr_stop_2r: ATR tabanlı stop + 2R hedef
    - support_stop_2r: önceki 20 günlük destek altı stop + 2R hedef

    Veriyi development/validation olarak tarihe göre ikiye böler.
    """
    from .analysis_v2 import indicators_v2, quality_score_series

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V3 backtest verisi alınamadı: {exc}')

    rows = []

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 320:
                continue

            a = quality_score_series(indicators_v2(d))

            # Yüksek kalite eşiğini ayrıca uygula.
            selected = a['QUALITY_GATE'] & (a['QUALITY_SCORE'] >= min_score)

            start_pos = max(220, len(a) - test_days)
            end_pos = len(a) - max_hold_days - 1

            last_event_pos = -10000
            prev_selected = False

            for pos in range(start_pos, end_pos + 1):
                is_selected = bool(selected.iloc[pos])
                new_event = is_selected and (not prev_selected) and (pos - last_event_pos >= cooldown_days)
                prev_selected = is_selected

                if not new_event:
                    continue

                entry = float(a['Close'].iloc[pos])
                atr = float(a['ATR'].iloc[pos]) if pd.notna(a['ATR'].iloc[pos]) else None
                prior_low = float(a['PRIOR_LOW20'].iloc[pos]) if pd.notna(a['PRIOR_LOW20'].iloc[pos]) else None

                if atr is None or atr <= 0:
                    continue

                # 1) baseline time-exit
                baseline_exit = float(a['Close'].iloc[pos + max_hold_days])
                baseline_net = ((baseline_exit / entry) - 1.0) * 100.0 - cost_pct

                # 2) fixed stop
                fixed_stop = entry * (1.0 - fixed_stop_pct / 100.0)
                fixed_risk = entry - fixed_stop
                fixed_target = entry + reward_r * fixed_risk

                # 3) ATR stop
                atr_stop = entry - atr_mult * atr
                # Mantıksız aşırı dar/geniş riskleri clamp et.
                atr_risk_pct = ((entry - atr_stop) / entry) * 100.0
                atr_risk_pct = min(max(atr_risk_pct, 1.0), 7.0)
                atr_stop = entry * (1.0 - atr_risk_pct / 100.0)
                atr_target = entry + reward_r * (entry - atr_stop)

                # 4) destek altı stop
                if prior_low is None or prior_low >= entry:
                    support_risk_pct = atr_risk_pct
                else:
                    raw_support_stop = prior_low - 0.25 * atr
                    support_risk_pct = ((entry - raw_support_stop) / entry) * 100.0
                    support_risk_pct = min(max(support_risk_pct, 1.0), 7.0)

                support_stop = entry * (1.0 - support_risk_pct / 100.0)
                support_target = entry + reward_r * (entry - support_stop)

                fixed_res = _simulate_trade_path(
                    a, pos, fixed_stop, fixed_target, max_hold_days, cost_pct
                )
                atr_res = _simulate_trade_path(
                    a, pos, atr_stop, atr_target, max_hold_days, cost_pct
                )
                support_res = _simulate_trade_path(
                    a, pos, support_stop, support_target, max_hold_days, cost_pct
                )

                rows.append({
                    'symbol': symbol,
                    'date': pd.Timestamp(a.index[pos]),
                    'score': float(a['QUALITY_SCORE'].iloc[pos]),
                    'entry': entry,
                    'baseline_time': {
                        'net_return_pct': float(baseline_net),
                        'exit_day': int(max_hold_days),
                        'exit_reason': 'TIME',
                        'risk_pct': None,
                        'r_multiple': None,
                    },
                    'fixed_stop_2r': fixed_res,
                    'atr_stop_2r': atr_res,
                    'support_stop_2r': support_res,
                })

                last_event_pos = pos

        except Exception:
            continue

    if not rows:
        raise HTTPException(503, 'V3 risk modeli için event üretilemedi')

    dates = sorted({r['date'].date() for r in rows})
    split_idx = max(1, len(dates) // 2)
    split_date = pd.Timestamp(dates[split_idx])

    strategies = ['baseline_time','fixed_stop_2r','atr_stop_2r','support_stop_2r']

    def summarize(segment_rows):
        out = []
        for strategy in strategies:
            vals = [r[strategy] for r in segment_rows]
            rets = pd.Series([v['net_return_pct'] for v in vals], dtype='float64')

            reasons = {}
            for v in vals:
                reasons[v['exit_reason']] = reasons.get(v['exit_reason'], 0) + 1

            risks = [v['risk_pct'] for v in vals if v['risk_pct'] is not None]
            rs = [v['r_multiple'] for v in vals if v['r_multiple'] is not None]

            out.append({
                'strategy': strategy,
                'events': int(len(rets)),
                'wins': int((rets > 0).sum()),
                'losses': int((rets <= 0).sum()),
                'success_rate_pct': round(float((rets > 0).mean()*100), 2),
                'avg_net_return_pct': round(float(rets.mean()), 3),
                'median_net_return_pct': round(float(rets.median()), 3),
                'total_compounded_return_pct': round(
                    float(((1 + rets/100.0).prod() - 1.0) * 100.0), 3
                ),
                'avg_risk_pct': round(float(pd.Series(risks).mean()), 3) if risks else None,
                'avg_r_multiple': round(float(pd.Series(rs).mean()), 3) if rs else None,
                'exit_reasons': reasons,
            })
        return out

    dev_rows = [r for r in rows if r['date'] < split_date]
    val_rows = [r for r in rows if r['date'] >= split_date]

    # Validation'da hisse bazında ATR-stop performansı; küçük örnekleri ayır.
    by_symbol = []
    symbols = sorted({r['symbol'] for r in val_rows})
    for symbol in symbols:
        sr = [r for r in val_rows if r['symbol'] == symbol]
        if len(sr) < 3:
            continue
        rets = pd.Series([r['atr_stop_2r']['net_return_pct'] for r in sr], dtype='float64')
        by_symbol.append({
            'symbol': symbol,
            'events': int(len(sr)),
            'success_rate_pct': round(float((rets > 0).mean()*100), 2),
            'avg_net_return_pct': round(float(rets.mean()), 3),
        })
    by_symbol.sort(
        key=lambda x: (x['events'] >= 5, x['avg_net_return_pct'], x['success_rate_pct']),
        reverse=True
    )

    return {
        'ok': True,
        'model': 'quality_v3_risk_management',
        'tested_current_bist30_symbols': len({r['symbol'] for r in rows}),
        'event_count': len(rows),
        'split_date': split_date.date().isoformat(),
        'settings': {
            'test_days': test_days,
            'min_score': min_score,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'fixed_stop_pct': fixed_stop_pct,
            'atr_mult': atr_mult,
            'reward_r': reward_r,
            'same_day_stop_and_target_rule': 'muhafazakar: stop önce kabul edilir',
        },
        'development': summarize(dev_rows),
        'validation': summarize(val_rows),
        'validation_atr_best_symbols': by_symbol[:10],
        'interpretation_note': (
            'Asıl karar validation sonuçlarına göre verilmelidir. '
            'Başarı oranı tek başına yeterli değildir; ortalama/medyan net getiri ve R multiple birlikte değerlendirilmelidir.'
        ),
        'caveats': [
            'Günlük OHLC verisi aynı gün stop/target sırasını göstermez; ikisi de görülürse stop önce varsayılır.',
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance verisi kullanılır; resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
            'Haber/KAP katmanı bu V3 risk testinden sonra ayrı doğrulanacaktır.',
        ],
    }


# ==========================================================
# V4 GELISMIS HACIM + PIYASA REJIMI
# ==========================================================

@app.get('/api/analysis/v4/{symbol}')
def analysis_v4_live(symbol: str):
    from .analysis_v2 import indicators_v2, quality_score_series
    from .analysis_v4 import volume_latest_summary, market_regime_from_index

    symbol = symbol.upper().replace('.IS', '')
    if symbol not in BIST30:
        raise HTTPException(404, 'BIST30 içinde hisse bulunamadı')

    d = load_chart(symbol, '1Y')
    if d is None or len(d) < 220:
        raise HTTPException(503, 'V4 analiz için yeterli veri yok')

    q = quality_score_series(indicators_v2(d))
    vol = volume_latest_summary(indicators_v2(d))
    l = q.iloc[-1]

    market = {
        'state': 'BİLİNMİYOR',
        'score': 0,
        'positive': False,
        'reason': 'Endeks verisi alınamadı',
    }
    try:
        idx = yf.download('XU100.IS', period='1y', interval='1d', auto_adjust=False, progress=False, threads=False)
        if idx is None or len(idx) < 60:
            idx = yf.download('XU030.IS', period='1y', interval='1d', auto_adjust=False, progress=False, threads=False)
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        market = market_regime_from_index(idx)
    except Exception:
        pass

    quality_score = float(l['QUALITY_SCORE'])
    technical_gate = bool(l['QUALITY_GATE'])
    signal = (
        'GÜÇLÜ TEKNİK TEYİT'
        if quality_score >= 8.25 and technical_gate and vol['gate_passed'] and market.get('positive')
        else 'İZLE'
    )

    return {
        'symbol': symbol,
        'model': 'v4_volume_market',
        'quality_score': round(quality_score, 2),
        'technical_gate': technical_gate,
        'volume': vol,
        'market_regime': market,
        'signal': signal,
        'note': 'Bu teknik/hacim teyididir; yatırım tavsiyesi veya otomatik işlem emri değildir.',
    }


@app.get('/api/scanner/v4')
def scanner_v4(min_quality: float = 8.25, min_volume: float = 6.0):
    from .analysis_v2 import indicators_v2, quality_score_series
    from .analysis_v4 import volume_latest_summary

    rows = []
    for s in BIST30:
        try:
            d = load_chart(s, '1Y')
            if len(d) < 220:
                continue
            q = quality_score_series(indicators_v2(d))
            vol = volume_latest_summary(indicators_v2(d))
            l = q.iloc[-1]
            price = float(l['Close'])
            prev = float(q['Close'].iloc[-2])

            if float(l['QUALITY_SCORE']) < min_quality:
                continue
            if vol['score'] < min_volume:
                continue

            rows.append({
                'symbol': s,
                'price': price,
                'change_pct': ((price / prev) - 1) * 100 if prev else 0,
                'quality_score': float(l['QUALITY_SCORE']),
                'volume_score': vol['score'],
                'rvol': vol['rvol'],
                'cmf': vol['cmf'],
                'mfi': vol['mfi'],
                'volume_state': vol['state'],
            })
        except Exception:
            continue

    return sorted(rows, key=lambda x: (x['quality_score'], x['volume_score']), reverse=True)


@app.get('/api/backtest/v4-volume')
def backtest_v4_volume(
    test_days: int = Query(default=504, ge=252, le=756),
    min_quality: float = Query(default=8.25, ge=7.25, le=10.0),
    min_volume: float = Query(default=6.0, ge=0.0, le=10.0),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
):
    """
    V4 giriş filtresi testi.
    Aynı veri üzerinde üç katmanı ayrı ayrı karşılaştırır:
    1) quality_only
    2) quality_plus_volume
    3) quality_plus_volume_plus_market

    Böylece hacim ve piyasa rejiminin gerçekten katkı sağlayıp sağlamadığı ölçülür.
    """
    from .analysis_v2 import indicators_v2, quality_score_series
    from .analysis_v4 import volume_score_series

    horizons = [5, 10]
    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V4 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()
            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            q = quality_score_series(indicators_v2(d))
            v = volume_score_series(q)
            prepared[symbol] = v
            close_map[symbol] = v['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V4 için yeterli hisse verisi hazırlanamadı')

    # Equal-weight market proxy + breadth, only using information available on each date.
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {}
    for symbol, a in prepared.items():
        above_ema50[symbol] = a['Close'] > a['EMA50']
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100

    market_positive = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 55)
    )

    all_dates = close_df.index
    if len(all_dates) < test_days:
        start_date = all_dates[0]
    else:
        start_date = all_dates[-test_days]
    test_dates = all_dates[all_dates >= start_date]
    split_date = test_dates[len(test_dates)//2]

    strategies = {
        'quality_only': [],
        'quality_plus_volume': [],
        'quality_plus_volume_plus_market': [],
    }

    for symbol, a in prepared.items():
        a = a.reindex(a.index)
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max(horizons) - 1

        conditions = {
            'quality_only': (
                a['QUALITY_GATE']
                & (a['QUALITY_SCORE'] >= min_quality)
            ),
            'quality_plus_volume': (
                a['QUALITY_GATE']
                & (a['QUALITY_SCORE'] >= min_quality)
                & (a['VOLUME_SCORE'] >= min_volume)
                & a['VOLUME_GATE']
            ),
        }

        market_on_symbol_dates = market_positive.reindex(a.index).fillna(False)
        conditions['quality_plus_volume_plus_market'] = (
            conditions['quality_plus_volume']
            & market_on_symbol_dates
        )

        for name, cond in conditions.items():
            last_event_pos = -10000
            prev = False

            for pos in range(start_pos, end_pos + 1):
                is_on = bool(cond.iloc[pos])
                new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
                prev = is_on
                if not new_event:
                    continue

                entry = float(a['Close'].iloc[pos])
                row = {
                    'symbol': symbol,
                    'date': pd.Timestamp(a.index[pos]),
                    'quality_score': float(a['QUALITY_SCORE'].iloc[pos]),
                    'volume_score': float(a['VOLUME_SCORE'].iloc[pos]),
                    'rvol': clean_num(a['RVOL20'].iloc[pos]),
                    'cmf': clean_num(a['CMF20'].iloc[pos]),
                }

                for h in horizons:
                    exit_price = float(a['Close'].iloc[pos+h])
                    row[f'ret_{h}'] = ((exit_price / entry) - 1.0) * 100.0 - cost_pct

                strategies[name].append(row)
                last_event_pos = pos

    def summarize(rows):
        out = []
        df = pd.DataFrame(rows)
        if df.empty:
            return out
        for segment_name, segment_mask in [
            ('development', df['date'] < split_date),
            ('validation', df['date'] >= split_date),
        ]:
            seg = df[segment_mask]
            for h in horizons:
                s = seg[f'ret_{h}'].dropna()
                if not len(s):
                    continue
                out.append({
                    'segment': segment_name,
                    'horizon_days': h,
                    'events': int(len(s)),
                    'wins': int((s > 0).sum()),
                    'losses': int((s <= 0).sum()),
                    'success_rate_pct': round(float((s > 0).mean() * 100), 2),
                    'avg_net_return_pct': round(float(s.mean()), 3),
                    'median_net_return_pct': round(float(s.median()), 3),
                })
        return out

    return {
        'ok': True,
        'model': 'v4_volume_market_filter',
        'tested_symbols': len(prepared),
        'split_date': pd.Timestamp(split_date).date().isoformat(),
        'settings': {
            'test_days': test_days,
            'min_quality': min_quality,
            'min_volume': min_volume,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'market_rule': 'equal-weight BIST30 proxy EMA20>EMA50, EMA20 slope>0, breadth>=55%',
        },
        'results': {
            name: summarize(rows)
            for name, rows in strategies.items()
        },
        'event_counts': {
            name: len(rows)
            for name, rows in strategies.items()
        },
        'interpretation': (
            'Validation bölümünde quality_plus_volume ve quality_plus_volume_plus_market '
            'quality_only modelinden daha iyi ise hacim/piyasa filtresi katkı sağlıyor demektir.'
        ),
        'caveats': [
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Piyasa filtresi current BIST30 hisselerinden oluşturulan eşit ağırlıklı proxy ve breadth kullanır.',
            'Yahoo Finance verisi kullanılır; resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
        ],
    }


@app.get('/api/backtest/v4-trades')
def backtest_v4_trades(
    test_days: int = Query(default=504, ge=120, le=756),
    min_quality: float = Query(default=8.25, ge=7.25, le=10.0),
    min_volume: float = Query(default=6.0, ge=0.0, le=10.0),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
    reward_r: float = Query(default=2.0, ge=1.0, le=4.0),
    limit: int = Query(default=100, ge=10, le=500),
):
    """
    V4 geçmiş işlem listesi.
    Her satır gerçek backtest olayıdır:
    - entry_date / entry_price
    - exit_date / exit_price
    - exit_reason: TARGET / STOP / TIME
    - net_return_pct
    - kalite/hacim skorları
    """
    from .analysis_v2 import indicators_v2, quality_score_series
    from .analysis_v4 import volume_score_series

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V4 trade listesi verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            q = quality_score_series(indicators_v2(d))
            v = volume_score_series(q)
            prepared[symbol] = v
            close_map[symbol] = v['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V4 trade listesi için veri hazırlanamadı')

    # Aynı V4 market proxy/breadth mantığı.
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {symbol: a['Close'] > a['EMA50'] for symbol, a in prepared.items()}
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100
    market_positive = (proxy_ema20 > proxy_ema50) & (proxy_slope5 > 0) & (breadth >= 55)

    trades = []

    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max_hold_days - 1

        cond = (
            a['QUALITY_GATE']
            & (a['QUALITY_SCORE'] >= min_quality)
            & (a['VOLUME_SCORE'] >= min_volume)
            & a['VOLUME_GATE']
            & market_positive.reindex(a.index).fillna(False)
        )

        last_event_pos = -10000
        prev = False

        for pos in range(start_pos, end_pos + 1):
            is_on = bool(cond.iloc[pos])
            new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
            prev = is_on

            if not new_event:
                continue

            entry = float(a['Close'].iloc[pos])
            atr = float(a['ATR'].iloc[pos]) if pd.notna(a['ATR'].iloc[pos]) else None
            prior_low = float(a['PRIOR_LOW20_V4'].iloc[pos]) if pd.notna(a['PRIOR_LOW20_V4'].iloc[pos]) else None
            if atr is None or atr <= 0:
                continue

            # Destek altı stop. Risk çok dar/geniş olmasın.
            if prior_low is None or prior_low >= entry:
                risk_pct = min(max((1.75 * atr / entry) * 100.0, 1.0), 7.0)
            else:
                raw_stop = prior_low - 0.25 * atr
                risk_pct = ((entry - raw_stop) / entry) * 100.0
                risk_pct = min(max(risk_pct, 1.0), 7.0)

            stop_price = entry * (1.0 - risk_pct / 100.0)
            target_price = entry + reward_r * (entry - stop_price)

            exit_price = None
            exit_reason = None
            exit_pos = None

            last_pos = min(len(a)-1, pos + max_hold_days)
            for j in range(pos + 1, last_pos + 1):
                low = float(a['Low'].iloc[j])
                high = float(a['High'].iloc[j])

                stop_hit = low <= stop_price
                target_hit = high >= target_price

                # Günlük OHLC sıralaması bilinmediği için muhafazakâr: aynı gün ikisi de varsa stop.
                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = 'STOP'
                    exit_pos = j
                    break
                if stop_hit:
                    exit_price = stop_price
                    exit_reason = 'STOP'
                    exit_pos = j
                    break
                if target_hit:
                    exit_price = target_price
                    exit_reason = 'TARGET'
                    exit_pos = j
                    break

            if exit_price is None:
                exit_pos = last_pos
                exit_price = float(a['Close'].iloc[exit_pos])
                exit_reason = 'TIME'

            gross = ((exit_price / entry) - 1.0) * 100.0
            net = gross - cost_pct

            trades.append({
                'symbol': symbol,
                'entry_date': pd.Timestamp(a.index[pos]).date().isoformat(),
                'entry_price': round(entry, 2),
                'exit_date': pd.Timestamp(a.index[exit_pos]).date().isoformat(),
                'exit_price': round(float(exit_price), 2),
                'exit_reason': exit_reason,
                'net_return_pct': round(float(net), 2),
                'quality_score': round(float(a['QUALITY_SCORE'].iloc[pos]), 2),
                'volume_score': round(float(a['VOLUME_SCORE'].iloc[pos]), 2),
                'rvol': round(float(a['RVOL20'].iloc[pos]), 2) if pd.notna(a['RVOL20'].iloc[pos]) else None,
                'cmf': round(float(a['CMF20'].iloc[pos]), 3) if pd.notna(a['CMF20'].iloc[pos]) else None,
                'stop_price': round(stop_price, 2),
                'target_price': round(target_price, 2),
                'hold_days': int(exit_pos - pos),
                'status': 'KÂR' if net > 0 else 'ZARAR',
            })

            last_event_pos = pos

    trades.sort(key=lambda x: x['entry_date'], reverse=True)

    return {
        'ok': True,
        'model': 'v4_trade_history',
        'count': len(trades),
        'settings': {
            'test_days': test_days,
            'min_quality': min_quality,
            'min_volume': min_volume,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'reward_r': reward_r,
            'exit_rules': 'destek altı stop + 2R hedef + maksimum bekleme',
        },
        'trades': trades[:limit],
    }


# ==========================================================
# V5 GENEL ERKEN TREND + BREAKOUT SINYAL MOTORU
# ==========================================================

@app.get('/api/analysis/v5/{symbol}')
def analysis_v5_live(symbol: str):
    from .analysis_v4 import market_regime_from_index
    from .analysis_v5 import latest_v5

    symbol = symbol.upper().replace('.IS', '')
    if symbol not in BIST30:
        raise HTTPException(404, 'BIST30 içinde hisse bulunamadı')

    d = load_chart(symbol, '1Y')
    if d is None or len(d) < 80:
        raise HTTPException(503, 'V5 analiz için yeterli veri yok')

    market = {
        'state': 'BİLİNMİYOR',
        'score': 0,
        'positive': False,
        'reason': 'Endeks verisi alınamadı',
    }
    try:
        idx = yf.download(
            'XU100.IS',
            period='1y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if idx is None or len(idx) < 60:
            idx = yf.download(
                'XU030.IS',
                period='1y',
                interval='1d',
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        market = market_regime_from_index(idx)
    except Exception:
        pass

    v5 = latest_v5(d, market_positive=market.get('positive'))
    return {
        'symbol': symbol,
        'model': 'v5_early_trend_breakout',
        'v5': v5,
        'market_regime': market,
        'signal_meanings': {
            'ERKEN_TREND': 'Trend yeni güçlenmeye başlıyor; erken uyarıdır.',
            'KIRILIM_YAKIN': 'Fiyat önemli kısa vadeli dirence yaklaşmıştır.',
            'BREAKOUT': '20 dönem zirvesi hacim/para akışı teyidiyle kırılmıştır.',
            'GUCLU_TEKNIK_TEYIT': 'V4 kalite + hacim + piyasa rejimi birlikte olumludur.',
            'TREND_DEVAM': 'Erken trend şartları devam etmektedir.',
            'IZLE': 'V5 için yeni güçlü olay oluşmamıştır.',
        },
        'note': 'Bunlar teknik analiz uyarılarıdır; otomatik işlem emri veya garanti değildir.',
    }


@app.get('/api/scanner/v5')
def scanner_v5():
    from .analysis_v4 import market_regime_from_index
    from .analysis_v5 import latest_v5

    market = {'positive': False, 'state': 'BİLİNMİYOR'}
    try:
        idx = yf.download('XU100.IS', period='1y', interval='1d', auto_adjust=False, progress=False, threads=False)
        if idx is None or len(idx) < 60:
            idx = yf.download('XU030.IS', period='1y', interval='1d', auto_adjust=False, progress=False, threads=False)
        if isinstance(idx.columns, pd.MultiIndex):
            idx.columns = idx.columns.get_level_values(0)
        market = market_regime_from_index(idx)
    except Exception:
        pass

    rows = []
    rank = {
        'GUCLU_TEKNIK_TEYIT': 5,
        'BREAKOUT': 4,
        'ERKEN_TREND': 3,
        'KIRILIM_YAKIN': 2,
        'TREND_DEVAM': 1,
        'IZLE': 0,
    }

    for s in BIST30:
        try:
            d = load_chart(s, '1Y')
            if d is None or len(d) < 80:
                continue
            v5 = latest_v5(d, market_positive=market.get('positive'))
            if v5['signal'] == 'IZLE':
                continue
            rows.append({
                'symbol': s,
                **v5,
            })
        except Exception:
            continue

    rows.sort(
        key=lambda x: (
            rank.get(x.get('signal'), 0),
            x.get('early_move_score', 0),
            x.get('quality_score', 0),
        ),
        reverse=True,
    )

    return {
        'market_regime': market,
        'count': len(rows),
        'signals': rows,
    }


@app.get('/api/backtest/v5-signals')
def backtest_v5_signals(
    test_days: int = Query(default=504, ge=252, le=756),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
):
    """
    V5 sinyal tiplerini ayrı ayrı test eder:
    - early_trend
    - breakout
    - strong_confirmation + market

    5 ve 10 işlem günü sonrası getirileri ölçer.
    """
    from .analysis_v5 import prepare_v5

    tickers = [s + '.IS' for s in BIST30]
    horizons = [5, 10]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V5 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()
            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue
            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V5 için yeterli veri hazırlanamadı')

    # Same general market filter as V4 backtest.
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {
        symbol: a['Close'] > a['EMA50']
        for symbol, a in prepared.items()
    }
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100
    market_positive = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 55)
    )

    all_dates = close_df.index
    start_date = all_dates[-test_days] if len(all_dates) >= test_days else all_dates[0]
    test_dates = all_dates[all_dates >= start_date]
    split_date = test_dates[len(test_dates)//2]

    strategies = {
        'early_trend': [],
        'breakout': [],
        'strong_confirmation_market': [],
    }

    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max(horizons) - 1

        conds = {
            'early_trend': a['EARLY_TREND'],
            'breakout': a['BREAKOUT_V5'],
            'strong_confirmation_market': (
                a['STRONG_CONFIRMATION_BASE']
                & market_positive.reindex(a.index).fillna(False)
            ),
        }

        for name, cond in conds.items():
            last_event_pos = -10000
            prev = False

            for pos in range(start_pos, end_pos + 1):
                is_on = bool(cond.iloc[pos])
                new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
                prev = is_on
                if not new_event:
                    continue

                entry = float(a['Close'].iloc[pos])
                row = {
                    'symbol': symbol,
                    'date': pd.Timestamp(a.index[pos]),
                    'early_move_score': float(a['EARLY_MOVE_SCORE'].iloc[pos]),
                    'quality_score': float(a['QUALITY_SCORE'].iloc[pos]),
                    'volume_score': float(a['VOLUME_SCORE'].iloc[pos]),
                    'rvol': clean_num(a['RVOL20'].iloc[pos]),
                }
                for h in horizons:
                    exit_price = float(a['Close'].iloc[pos+h])
                    row[f'ret_{h}'] = ((exit_price / entry) - 1) * 100 - cost_pct

                strategies[name].append(row)
                last_event_pos = pos

    def summary(rows):
        df = pd.DataFrame(rows)
        result = []
        if df.empty:
            return result

        for seg_name, mask in [
            ('development', df['date'] < split_date),
            ('validation', df['date'] >= split_date),
        ]:
            seg = df[mask]
            for h in horizons:
                s = seg[f'ret_{h}'].dropna()
                if not len(s):
                    continue
                result.append({
                    'segment': seg_name,
                    'horizon_days': h,
                    'events': int(len(s)),
                    'wins': int((s > 0).sum()),
                    'losses': int((s <= 0).sum()),
                    'success_rate_pct': round(float((s > 0).mean() * 100), 2),
                    'avg_net_return_pct': round(float(s.mean()), 3),
                    'median_net_return_pct': round(float(s.median()), 3),
                })
        return result

    return {
        'ok': True,
        'model': 'v5_early_trend_breakout',
        'tested_symbols': len(prepared),
        'split_date': pd.Timestamp(split_date).date().isoformat(),
        'settings': {
            'test_days': test_days,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
        },
        'results': {name: summary(rows) for name, rows in strategies.items()},
        'event_counts': {name: len(rows) for name, rows in strategies.items()},
        'interpretation': (
            'Validation bölümünde erken trend ve breakout sinyallerinin 5/10 günlük '
            'ortalama ve medyan getirileri ile başarı oranlarını strong_confirmation_market ile karşılaştır.'
        ),
        'caveats': [
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance verisi resmi gerçek zamanlı BIST verisi değildir.',
            'Erken sinyal daha fazla fırsat yakalayabilir ama yanlış sinyal sayısı da artabilir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
        ],
    }


@app.get('/api/v6/status')
def v6_status(db: Session = Depends(get_db)):
    open_count = (
        db.query(OpenSignalPosition)
        .filter(OpenSignalPosition.status == 'OPEN')
        .count()
    )
    closed_count = (
        db.query(OpenSignalPosition)
        .filter(OpenSignalPosition.status == 'CLOSED')
        .count()
    )
    return {
        'ok': True,
        'model': 'v6_alert_position_manager',
        'open_positions': open_count,
        'closed_positions': closed_count,
        'entry_signals': ['BREAKOUT', 'GUCLU_TEKNIK_TEYIT'],
        'watch_only': ['ERKEN_TREND', 'KIRILIM_YAKIN', 'TREND_DEVAM'],
        'exit_rules': ['STOP', 'TARGET1_ALERT', 'TARGET2_CLOSE', '10_TRADING_DAYS'],
        'note': 'Teknik uyarı sistemidir; otomatik gerçek para işlemi yapmaz.',
    }


@app.get('/api/backtest/v6-risk')
def backtest_v6_risk(
    test_days: int = Query(default=504, ge=252, le=756),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
):
    """
    V6 geçmiş test:
    - BREAKOUT
    - GUCLU_TEKNIK_TEYIT
    - COMBINED (ikisi birlikte)

    Çıkış:
    - destek/ATR tabanlı stop
    - Hedef 1 = 1R (sadece bilgi/ara hedef)
    - Hedef 2 = 2R (kapanış)
    - maksimum 10 işlem günü

    Günlük OHLC'de aynı gün stop ve hedef2 görülürse muhafazakâr olarak STOP kabul edilir.
    """
    from .analysis_v5 import prepare_v5

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V6 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V6 backtest için veri hazırlanamadı')

    # V4/V5 ile aynı piyasa filtresi.
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {
        symbol: a['Close'] > a['EMA50']
        for symbol, a in prepared.items()
    }
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100

    market_positive = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 55)
    )

    all_dates = close_df.index
    start_date = all_dates[-test_days] if len(all_dates) >= test_days else all_dates[0]
    test_dates = all_dates[all_dates >= start_date]
    split_date = test_dates[len(test_dates)//2]

    strategies = {
        'breakout': [],
        'strong_confirmation_market': [],
        'combined': [],
    }

    def levels_for_row(a, pos):
        entry = float(a['Close'].iloc[pos])
        atr = float(a['ATR'].iloc[pos]) if pd.notna(a['ATR'].iloc[pos]) else None
        prior_low = float(a['PRIOR_LOW20_V4'].iloc[pos]) if pd.notna(a['PRIOR_LOW20_V4'].iloc[pos]) else None

        if atr is None or atr <= 0:
            risk_pct = 3.0
        elif prior_low is None or prior_low >= entry:
            risk_pct = (1.75 * atr / entry) * 100.0
        else:
            raw_stop = prior_low - 0.25 * atr
            risk_pct = ((entry - raw_stop) / entry) * 100.0

        risk_pct = min(max(float(risk_pct), 1.0), 7.0)
        stop = entry * (1 - risk_pct / 100.0)
        one_r = entry - stop
        target1 = entry + one_r
        target2 = entry + 2 * one_r
        return entry, risk_pct, stop, target1, target2

    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max_hold_days - 1

        breakout_cond = a['BREAKOUT_V5']
        strong_cond = (
            a['STRONG_CONFIRMATION_BASE']
            & market_positive.reindex(a.index).fillna(False)
        )
        combined_cond = breakout_cond | strong_cond

        conds = {
            'breakout': breakout_cond,
            'strong_confirmation_market': strong_cond,
            'combined': combined_cond,
        }

        for strat_name, cond in conds.items():
            last_event_pos = -10000
            prev = False

            for pos in range(start_pos, end_pos + 1):
                is_on = bool(cond.iloc[pos])
                new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
                prev = is_on

                if not new_event:
                    continue

                entry, risk_pct, stop, target1, target2 = levels_for_row(a, pos)

                exit_price = None
                exit_reason = None
                exit_pos = None
                target1_hit = False

                last_pos = min(len(a)-1, pos + max_hold_days)

                for j in range(pos+1, last_pos+1):
                    low = float(a['Low'].iloc[j])
                    high = float(a['High'].iloc[j])

                    stop_hit = low <= stop
                    target2_hit = high >= target2
                    target1_today = high >= target1

                    if target1_today:
                        target1_hit = True

                    # conservative same-day ordering
                    if stop_hit and target2_hit:
                        exit_price = stop
                        exit_reason = 'STOP'
                        exit_pos = j
                        break
                    if stop_hit:
                        exit_price = stop
                        exit_reason = 'STOP'
                        exit_pos = j
                        break
                    if target2_hit:
                        exit_price = target2
                        exit_reason = 'TARGET2'
                        exit_pos = j
                        break

                if exit_price is None:
                    exit_pos = last_pos
                    exit_price = float(a['Close'].iloc[exit_pos])
                    exit_reason = 'TIME'

                gross = ((exit_price / entry) - 1.0) * 100.0
                net = gross - cost_pct
                r_multiple = net / risk_pct if risk_pct else None

                strategies[strat_name].append({
                    'symbol': symbol,
                    'date': pd.Timestamp(a.index[pos]),
                    'entry': entry,
                    'exit_date': pd.Timestamp(a.index[exit_pos]),
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'target1_hit': bool(target1_hit),
                    'net_return_pct': net,
                    'risk_pct': risk_pct,
                    'r_multiple': r_multiple,
                    'quality_score': float(a['QUALITY_SCORE'].iloc[pos]),
                    'volume_score': float(a['VOLUME_SCORE'].iloc[pos]),
                    'early_move_score': float(a['EARLY_MOVE_SCORE'].iloc[pos]),
                })

                last_event_pos = pos

    def summarize(rows):
        df = pd.DataFrame(rows)
        out = []
        if df.empty:
            return out

        for seg_name, mask in [
            ('development', df['date'] < split_date),
            ('validation', df['date'] >= split_date),
        ]:
            seg = df[mask].copy()
            if seg.empty:
                continue

            wins = int((seg['net_return_pct'] > 0).sum())
            losses = int((seg['net_return_pct'] <= 0).sum())
            reasons = seg['exit_reason'].value_counts().to_dict()

            out.append({
                'segment': seg_name,
                'events': int(len(seg)),
                'wins': wins,
                'losses': losses,
                'success_rate_pct': round(float(wins / len(seg) * 100), 2),
                'avg_net_return_pct': round(float(seg['net_return_pct'].mean()), 3),
                'median_net_return_pct': round(float(seg['net_return_pct'].median()), 3),
                'avg_r_multiple': round(float(seg['r_multiple'].dropna().mean()), 3) if seg['r_multiple'].notna().any() else None,
                'median_r_multiple': round(float(seg['r_multiple'].dropna().median()), 3) if seg['r_multiple'].notna().any() else None,
                'target1_hit_rate_pct': round(float(seg['target1_hit'].mean() * 100), 2),
                'avg_risk_pct': round(float(seg['risk_pct'].mean()), 3),
                'exit_reasons': {str(k): int(v) for k, v in reasons.items()},
            })
        return out

    # best recent examples for quick inspection
    examples = []
    combined_df = pd.DataFrame(strategies['combined'])
    if not combined_df.empty:
        validation = combined_df[combined_df['date'] >= split_date].copy()
        validation = validation.sort_values('net_return_pct', ascending=False).head(15)
        for _, r in validation.iterrows():
            examples.append({
                'symbol': r['symbol'],
                'entry_date': pd.Timestamp(r['date']).date().isoformat(),
                'exit_date': pd.Timestamp(r['exit_date']).date().isoformat(),
                'exit_reason': r['exit_reason'],
                'net_return_pct': round(float(r['net_return_pct']), 2),
                'risk_pct': round(float(r['risk_pct']), 2),
                'r_multiple': round(float(r['r_multiple']), 2) if pd.notna(r['r_multiple']) else None,
                'target1_hit': bool(r['target1_hit']),
            })

    return {
        'ok': True,
        'model': 'v6_signal_risk_manager',
        'tested_symbols': len(prepared),
        'split_date': pd.Timestamp(split_date).date().isoformat(),
        'settings': {
            'test_days': test_days,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'entry_signals': ['BREAKOUT', 'GUCLU_TEKNIK_TEYIT'],
            'risk_logic': 'destek/ATR tabanlı, %1-%7 risk clamp',
            'target1': '1R bilgilendirme',
            'target2': '2R kapanış',
            'same_day_rule': 'stop ve target2 aynı gün görülürse STOP',
        },
        'results': {
            name: summarize(rows)
            for name, rows in strategies.items()
        },
        'event_counts': {
            name: len(rows)
            for name, rows in strategies.items()
        },
        'validation_best_examples_combined': examples,
        'interpretation': (
            'Validation bölümünde avg/median net return, R multiple, success rate, '
            'target1 hit rate ve exit_reasons birlikte değerlendirilmelidir.'
        ),
        'caveats': [
            'Günlük OHLC verisi gün içi stop/hedef sırasını göstermez.',
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
        ],
    }


@app.get('/api/backtest/v7-exit-grid')
def backtest_v7_exit_grid(
    test_days: int = Query(default=504, ge=252, le=756),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
):
    """
    V7: GÜÇLÜ TEKNİK TEYİT + piyasa filtresi girişleri üzerinde
    stop üst sınırı / hedef R / 1R sonrası breakeven kombinasyonlarını test eder.

    Grid:
    stop_cap_pct = 3,4,5,6,7
    reward_r = 1.0, 1.5, 2.0
    breakeven_after_1r = False / True

    Toplam 30 kombinasyon.
    """
    from .analysis_v5 import prepare_v5

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V7 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V7 için veri hazırlanamadı')

    # V4/V5 ile aynı genel piyasa rejimi.
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {
        symbol: a['Close'] > a['EMA50']
        for symbol, a in prepared.items()
    }
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100
    market_positive = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 55)
    )

    all_dates = close_df.index
    start_date = all_dates[-test_days] if len(all_dates) >= test_days else all_dates[0]
    test_dates = all_dates[all_dates >= start_date]
    split_date = test_dates[len(test_dates)//2]

    # First collect the same strong-confirmation entry events once.
    events = []

    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max_hold_days - 1

        cond = (
            a['STRONG_CONFIRMATION_BASE']
            & market_positive.reindex(a.index).fillna(False)
        )

        last_event_pos = -10000
        prev = False

        for pos in range(start_pos, end_pos + 1):
            is_on = bool(cond.iloc[pos])
            new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
            prev = is_on
            if not new_event:
                continue

            events.append({
                'symbol': symbol,
                'a': a,
                'pos': pos,
                'date': pd.Timestamp(a.index[pos]),
            })
            last_event_pos = pos

    def base_risk(a, pos, entry, stop_cap):
        atr = float(a['ATR'].iloc[pos]) if pd.notna(a['ATR'].iloc[pos]) else None
        prior_low = float(a['PRIOR_LOW20_V4'].iloc[pos]) if pd.notna(a['PRIOR_LOW20_V4'].iloc[pos]) else None

        if atr is None or atr <= 0:
            risk_pct = 3.0
        elif prior_low is None or prior_low >= entry:
            risk_pct = (1.75 * atr / entry) * 100.0
        else:
            raw_stop = prior_low - 0.25 * atr
            risk_pct = ((entry - raw_stop) / entry) * 100.0

        risk_pct = min(max(float(risk_pct), 1.0), float(stop_cap))
        return risk_pct

    def simulate(event, stop_cap, reward_r, breakeven):
        a = event['a']
        pos = event['pos']
        entry = float(a['Close'].iloc[pos])

        risk_pct = base_risk(a, pos, entry, stop_cap)
        stop = entry * (1.0 - risk_pct / 100.0)
        one_r = entry - stop
        target1 = entry + one_r
        target = entry + reward_r * one_r

        current_stop = stop
        hit_1r = False
        exit_price = None
        exit_reason = None
        exit_pos = None

        last_pos = min(len(a)-1, pos + max_hold_days)

        for j in range(pos + 1, last_pos + 1):
            low = float(a['Low'].iloc[j])
            high = float(a['High'].iloc[j])

            # If both stop and target are visible in one daily candle,
            # use conservative ordering: stop first.
            stop_hit = low <= current_stop
            target_hit = high >= target

            if stop_hit and target_hit:
                exit_price = current_stop
                exit_reason = 'STOP' if not hit_1r else 'BREAKEVEN_STOP'
                exit_pos = j
                break

            if stop_hit:
                exit_price = current_stop
                exit_reason = 'STOP' if not hit_1r else 'BREAKEVEN_STOP'
                exit_pos = j
                break

            if target_hit:
                exit_price = target
                exit_reason = 'TARGET'
                exit_pos = j
                break

            # Move stop to entry only after candle survives without stop/target.
            if (not hit_1r) and high >= target1:
                hit_1r = True
                if breakeven:
                    current_stop = entry

        if exit_price is None:
            exit_pos = last_pos
            exit_price = float(a['Close'].iloc[exit_pos])
            exit_reason = 'TIME'

        gross = ((exit_price / entry) - 1.0) * 100.0
        net = gross - cost_pct
        r_mult = net / risk_pct if risk_pct else None

        return {
            'symbol': event['symbol'],
            'date': event['date'],
            'exit_date': pd.Timestamp(a.index[exit_pos]),
            'net_return_pct': net,
            'risk_pct': risk_pct,
            'r_multiple': r_mult,
            'exit_reason': exit_reason,
            'hit_1r': hit_1r,
        }

    stop_caps = [3, 4, 5, 6, 7]
    rewards = [1.0, 1.5, 2.0]
    be_options = [False, True]

    combos = []

    for stop_cap in stop_caps:
        for reward_r in rewards:
            for breakeven in be_options:
                rows = [simulate(ev, stop_cap, reward_r, breakeven) for ev in events]
                df = pd.DataFrame(rows)
                if df.empty:
                    continue

                combo_result = {
                    'stop_cap_pct': stop_cap,
                    'reward_r': reward_r,
                    'breakeven_after_1r': breakeven,
                    'development': None,
                    'validation': None,
                }

                for seg_name, mask in [
                    ('development', df['date'] < split_date),
                    ('validation', df['date'] >= split_date),
                ]:
                    seg = df[mask].copy()
                    if seg.empty:
                        continue

                    wins = int((seg['net_return_pct'] > 0).sum())
                    losses = int((seg['net_return_pct'] <= 0).sum())
                    reasons = seg['exit_reason'].value_counts().to_dict()

                    combo_result[seg_name] = {
                        'events': int(len(seg)),
                        'wins': wins,
                        'losses': losses,
                        'success_rate_pct': round(float(wins / len(seg) * 100), 2),
                        'avg_net_return_pct': round(float(seg['net_return_pct'].mean()), 3),
                        'median_net_return_pct': round(float(seg['net_return_pct'].median()), 3),
                        'avg_r_multiple': round(float(seg['r_multiple'].dropna().mean()), 3) if seg['r_multiple'].notna().any() else None,
                        'median_r_multiple': round(float(seg['r_multiple'].dropna().median()), 3) if seg['r_multiple'].notna().any() else None,
                        'hit_1r_rate_pct': round(float(seg['hit_1r'].mean() * 100), 2),
                        'avg_risk_pct': round(float(seg['risk_pct'].mean()), 3),
                        'exit_reasons': {str(k): int(v) for k, v in reasons.items()},
                    }

                combos.append(combo_result)

    # Do not declare a "winner"; return neutral sortable candidate views.
    validation_positive = [
        c for c in combos
        if c.get('validation')
        and c['validation']['avg_net_return_pct'] > 0
        and c['validation']['median_net_return_pct'] > 0
    ]

    by_avg_return = sorted(
        validation_positive,
        key=lambda c: c['validation']['avg_net_return_pct'],
        reverse=True
    )[:10]

    by_avg_r = sorted(
        validation_positive,
        key=lambda c: c['validation']['avg_r_multiple'],
        reverse=True
    )[:10]

    by_success = sorted(
        validation_positive,
        key=lambda c: c['validation']['success_rate_pct'],
        reverse=True
    )[:10]

    return {
        'ok': True,
        'model': 'v7_exit_grid',
        'tested_symbols': len(prepared),
        'entry_event_count': len(events),
        'split_date': pd.Timestamp(split_date).date().isoformat(),
        'settings': {
            'test_days': test_days,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'entry_signal': 'GUCLU_TEKNIK_TEYIT + piyasa filtresi',
            'stop_caps_tested_pct': stop_caps,
            'reward_r_tested': rewards,
            'breakeven_options': be_options,
            'same_day_rule': 'stop ve hedef aynı gün görülürse stop önce',
        },
        'all_combinations': combos,
        'validation_candidate_views': {
            'top_by_avg_net_return': by_avg_return,
            'top_by_avg_r_multiple': by_avg_r,
            'top_by_success_rate': by_success,
        },
        'interpretation': (
            'Validation sonuçlarını development ile birlikte incele. '
            'Tek bir metrik yerine ortalama/medyan getiri, R multiple, başarı oranı ve exit_reasons birlikte değerlendirilmelidir.'
        ),
        'caveats': [
            'Günlük OHLC gün içi stop/hedef sırasını göstermez; muhafazakâr stop-first kuralı kullanılır.',
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
        ],
    }


@app.get('/api/backtest/v8-adaptive-risk')
def backtest_v8_adaptive_risk(
    test_days: int = Query(default=504, ge=252, le=756),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
):
    """
    V8: Güçlü teknik teyit girişlerinde piyasa rejimine göre adaptif stop/hedef testi.

    Rejim:
    STRONG:
      proxy EMA20 > EMA50
      EMA20 slope5 > 0
      breadth >= 65%

    POSITIVE:
      proxy EMA20 > EMA50
      EMA20 slope5 > 0
      breadth >= 55%

    WEAK:
      diğer durumlar

    Politikalar:
    fixed_6_2r:
      tüm uygun girişlerde %6 stop cap, 2R hedef

    adaptive_balanced:
      STRONG -> %6 stop cap, 2R
      POSITIVE -> %5 stop cap, 1.5R
      WEAK -> işlem yok

    adaptive_conservative:
      STRONG -> %5 stop cap, 1.5R
      POSITIVE -> %4 stop cap, 1.5R
      WEAK -> işlem yok

    adaptive_selective:
      STRONG -> %6 stop cap, 2R
      POSITIVE -> işlem yok
      WEAK -> işlem yok
    """
    from .analysis_v5 import prepare_v5

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V8 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}

    for symbol in BIST30:
        ticker = symbol + '.IS'
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                d = raw[ticker].copy()
            else:
                d = raw.copy()

            d = d.dropna(subset=['Open','High','Low','Close'])
            if len(d) < 300:
                continue

            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V8 için veri hazırlanamadı')

    # Market proxy + breadth
    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    proxy_ema20 = proxy.ewm(span=20, adjust=False).mean()
    proxy_ema50 = proxy.ewm(span=50, adjust=False).mean()
    proxy_slope5 = (proxy_ema20 / proxy_ema20.shift(5) - 1) * 100

    above_ema50 = {
        symbol: a['Close'] > a['EMA50']
        for symbol, a in prepared.items()
    }
    breadth_df = pd.DataFrame(above_ema50).reindex(close_df.index)
    breadth = breadth_df.mean(axis=1, skipna=True) * 100

    strong_market = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 65)
    )
    positive_market = (
        (proxy_ema20 > proxy_ema50)
        & (proxy_slope5 > 0)
        & (breadth >= 55)
    )

    def regime_on(date):
        if bool(strong_market.reindex([date]).fillna(False).iloc[0]):
            return 'STRONG'
        if bool(positive_market.reindex([date]).fillna(False).iloc[0]):
            return 'POSITIVE'
        return 'WEAK'

    all_dates = close_df.index
    start_date = all_dates[-test_days] if len(all_dates) >= test_days else all_dates[0]
    test_dates = all_dates[all_dates >= start_date]
    split_date = test_dates[len(test_dates)//2]

    # Same entry signal: strong technical confirmation base.
    events = []
    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max_hold_days - 1

        # entry generation still requires at least POSITIVE market as in V7
        cond = (
            a['STRONG_CONFIRMATION_BASE']
            & positive_market.reindex(a.index).fillna(False)
        )

        last_event_pos = -10000
        prev = False

        for pos in range(start_pos, end_pos + 1):
            is_on = bool(cond.iloc[pos])
            new_event = is_on and (not prev) and (pos - last_event_pos >= cooldown_days)
            prev = is_on
            if not new_event:
                continue

            date = pd.Timestamp(a.index[pos])
            events.append({
                'symbol': symbol,
                'a': a,
                'pos': pos,
                'date': date,
                'regime': regime_on(date),
            })
            last_event_pos = pos

    policies = {
        'fixed_6_2r': {
            'STRONG': (6.0, 2.0),
            'POSITIVE': (6.0, 2.0),
            'WEAK': None,
        },
        'adaptive_balanced': {
            'STRONG': (6.0, 2.0),
            'POSITIVE': (5.0, 1.5),
            'WEAK': None,
        },
        'adaptive_conservative': {
            'STRONG': (5.0, 1.5),
            'POSITIVE': (4.0, 1.5),
            'WEAK': None,
        },
        'adaptive_selective': {
            'STRONG': (6.0, 2.0),
            'POSITIVE': None,
            'WEAK': None,
        },
    }

    def calc_base_risk(a, pos, entry, stop_cap):
        atr = float(a['ATR'].iloc[pos]) if pd.notna(a['ATR'].iloc[pos]) else None
        prior_low = float(a['PRIOR_LOW20_V4'].iloc[pos]) if pd.notna(a['PRIOR_LOW20_V4'].iloc[pos]) else None

        if atr is None or atr <= 0:
            risk_pct = 3.0
        elif prior_low is None or prior_low >= entry:
            risk_pct = (1.75 * atr / entry) * 100.0
        else:
            raw_stop = prior_low - 0.25 * atr
            risk_pct = ((entry - raw_stop) / entry) * 100.0

        risk_pct = min(max(float(risk_pct), 1.0), float(stop_cap))
        return risk_pct

    def simulate(event, stop_cap, reward_r):
        a = event['a']
        pos = event['pos']
        entry = float(a['Close'].iloc[pos])

        risk_pct = calc_base_risk(a, pos, entry, stop_cap)
        stop = entry * (1.0 - risk_pct / 100.0)
        one_r = entry - stop
        target = entry + reward_r * one_r

        exit_price = None
        exit_reason = None
        exit_pos = None
        last_pos = min(len(a)-1, pos + max_hold_days)

        for j in range(pos+1, last_pos+1):
            low = float(a['Low'].iloc[j])
            high = float(a['High'].iloc[j])

            stop_hit = low <= stop
            target_hit = high >= target

            if stop_hit and target_hit:
                exit_price = stop
                exit_reason = 'STOP'
                exit_pos = j
                break
            if stop_hit:
                exit_price = stop
                exit_reason = 'STOP'
                exit_pos = j
                break
            if target_hit:
                exit_price = target
                exit_reason = 'TARGET'
                exit_pos = j
                break

        if exit_price is None:
            exit_pos = last_pos
            exit_price = float(a['Close'].iloc[exit_pos])
            exit_reason = 'TIME'

        gross = ((exit_price / entry) - 1.0) * 100.0
        net = gross - cost_pct
        r_multiple = net / risk_pct if risk_pct else None

        return {
            'symbol': event['symbol'],
            'date': event['date'],
            'regime': event['regime'],
            'exit_date': pd.Timestamp(a.index[exit_pos]),
            'exit_reason': exit_reason,
            'net_return_pct': net,
            'risk_pct': risk_pct,
            'reward_r': reward_r,
            'r_multiple': r_multiple,
        }

    results = {}

    for policy_name, policy in policies.items():
        rows = []
        skipped = 0

        for ev in events:
            params = policy.get(ev['regime'])
            if params is None:
                skipped += 1
                continue
            stop_cap, reward_r = params
            rows.append(simulate(ev, stop_cap, reward_r))

        df = pd.DataFrame(rows)

        def summarize_segment(seg):
            if seg.empty:
                return None
            wins = int((seg['net_return_pct'] > 0).sum())
            losses = int((seg['net_return_pct'] <= 0).sum())
            reasons = seg['exit_reason'].value_counts().to_dict()
            regime_counts = seg['regime'].value_counts().to_dict()
            return {
                'events': int(len(seg)),
                'wins': wins,
                'losses': losses,
                'success_rate_pct': round(float(wins / len(seg) * 100), 2),
                'avg_net_return_pct': round(float(seg['net_return_pct'].mean()), 3),
                'median_net_return_pct': round(float(seg['net_return_pct'].median()), 3),
                'avg_r_multiple': round(float(seg['r_multiple'].dropna().mean()), 3) if seg['r_multiple'].notna().any() else None,
                'median_r_multiple': round(float(seg['r_multiple'].dropna().median()), 3) if seg['r_multiple'].notna().any() else None,
                'avg_risk_pct': round(float(seg['risk_pct'].mean()), 3),
                'exit_reasons': {str(k): int(v) for k, v in reasons.items()},
                'regime_counts': {str(k): int(v) for k, v in regime_counts.items()},
            }

        if df.empty:
            results[policy_name] = {
                'skipped_events': skipped,
                'development': None,
                'validation': None,
            }
            continue

        dev = df[df['date'] < split_date].copy()
        val = df[df['date'] >= split_date].copy()

        results[policy_name] = {
            'skipped_events': skipped,
            'development': summarize_segment(dev),
            'validation': summarize_segment(val),
        }

    # Regime diagnostics independent of policy
    regime_diag = {}
    events_df = pd.DataFrame([{
        'date': e['date'],
        'regime': e['regime'],
    } for e in events])
    if not events_df.empty:
        for seg_name, mask in [
            ('development', events_df['date'] < split_date),
            ('validation', events_df['date'] >= split_date),
        ]:
            seg = events_df[mask]
            regime_diag[seg_name] = {
                str(k): int(v)
                for k, v in seg['regime'].value_counts().to_dict().items()
            }

    return {
        'ok': True,
        'model': 'v8_adaptive_risk',
        'tested_symbols': len(prepared),
        'entry_event_count': len(events),
        'split_date': pd.Timestamp(split_date).date().isoformat(),
        'settings': {
            'test_days': test_days,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'entry_signal': 'GUCLU_TEKNIK_TEYIT + en az POSITIVE piyasa',
            'strong_regime': 'EMA20>EMA50, slope5>0, breadth>=65%',
            'positive_regime': 'EMA20>EMA50, slope5>0, breadth>=55%',
            'weak_regime': 'diğer',
        },
        'policies': {
            'fixed_6_2r': 'STRONG/POSITIVE -> %6 stop cap + 2R',
            'adaptive_balanced': 'STRONG -> %6 + 2R, POSITIVE -> %5 + 1.5R',
            'adaptive_conservative': 'STRONG -> %5 + 1.5R, POSITIVE -> %4 + 1.5R',
            'adaptive_selective': 'yalnız STRONG -> %6 + 2R',
        },
        'regime_diagnostics': regime_diag,
        'results': results,
        'interpretation': (
            'Validation ile development birlikte incelenmeli. '
            'Amaç sadece validation ortalamasını yükseltmek değil, iki dönemde de daha tutarlı sonuç elde etmektir.'
        ),
        'caveats': [
            'Günlük OHLC stop/hedef sırasını göstermez; aynı gün ikisi görülürse STOP önce kabul edilir.',
            'Current BIST30 composition geçmişe uygulanır; survivorship bias olabilir.',
            'Yahoo Finance resmi gerçek zamanlı BIST verisi değildir.',
            'Backtest geçmiş performanstır; geleceği garanti etmez.',
        ],
    }


@app.get('/api/backtest/v9-forward')
def backtest_v9_forward(
    test_days: int = Query(default=756, ge=504, le=1008),
    cost_bps: int = Query(default=20, ge=0, le=100),
    cooldown_days: int = Query(default=5, ge=1, le=20),
    max_hold_days: int = Query(default=10, ge=3, le=20),
    folds: int = Query(default=6, ge=4, le=8),
):
    """
    Final forward-like validation:
    - sinyal t günü kapanmış günlük mumda hesaplanır
    - işlem t+1 gün OPEN fiyatından başlatılır
    - yalnız STRONG market + STRONG_CONFIRMATION_BASE
    - stop cap %6, hedef 2R, max 10 gün
    - dönemi kronolojik fold'lara böler; optimizasyon yapmaz
    """
    from .analysis_v5 import prepare_v5

    tickers = [s + '.IS' for s in BIST30]
    cost_pct = cost_bps / 100.0

    try:
        raw = yf.download(
            tickers=tickers,
            period='5y',
            interval='1d',
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by='ticker',
        )
    except Exception as exc:
        raise HTTPException(503, f'V9 backtest verisi alınamadı: {exc}')

    prepared = {}
    close_map = {}
    for symbol in BIST30:
        try:
            d = _extract_ticker_frame(raw, symbol)
            if len(d) < 300:
                continue
            a = prepare_v5(d)
            prepared[symbol] = a
            close_map[symbol] = a['Close']
        except Exception:
            continue

    if not prepared:
        raise HTTPException(503, 'V9 için yeterli veri yok')

    close_df = pd.DataFrame(close_map).sort_index()
    returns = close_df.pct_change(fill_method=None)
    proxy = (1 + returns.mean(axis=1, skipna=True).fillna(0)).cumprod() * 100
    ema20 = proxy.ewm(span=20, adjust=False).mean()
    ema50 = proxy.ewm(span=50, adjust=False).mean()
    slope5 = (ema20 / ema20.shift(5) - 1) * 100

    above = {
        symbol: a['Close'] > a['EMA50']
        for symbol, a in prepared.items()
    }
    breadth = pd.DataFrame(above).reindex(close_df.index).mean(axis=1, skipna=True) * 100
    strong_market = (
        (ema20 > ema50)
        & (slope5 > 0)
        & (breadth >= 65)
    )

    all_dates = close_df.index
    start_date = all_dates[-test_days] if len(all_dates) >= test_days else all_dates[0]
    eval_dates = all_dates[all_dates >= start_date]

    events = []

    for symbol, a in prepared.items():
        start_pos = max(220, len(a) - test_days)
        end_pos = len(a) - max_hold_days - 2
        cond = (
            a['STRONG_CONFIRMATION_BASE']
            & strong_market.reindex(a.index).fillna(False)
        )

        last_event_pos = -10000
        prev = False

        for signal_pos in range(start_pos, end_pos + 1):
            is_on = bool(cond.iloc[signal_pos])
            new_event = is_on and (not prev) and (signal_pos - last_event_pos >= cooldown_days)
            prev = is_on
            if not new_event:
                continue

            entry_pos = signal_pos + 1
            entry = float(a['Open'].iloc[entry_pos])

            # Risk levels are based only on information available on signal day.
            l = a.iloc[signal_pos]
            atr = float(l['ATR']) if pd.notna(l.get('ATR')) else None
            prior_low = float(l['PRIOR_LOW20_V4']) if pd.notna(l.get('PRIOR_LOW20_V4')) else None

            if atr is None or atr <= 0:
                risk_pct = 3.0
            elif prior_low is None or prior_low >= entry:
                risk_pct = (1.75 * atr / entry) * 100.0
            else:
                raw_stop = prior_low - 0.25 * atr
                risk_pct = ((entry - raw_stop) / entry) * 100.0

            risk_pct = min(max(float(risk_pct), 1.0), 6.0)
            stop = entry * (1 - risk_pct / 100.0)
            one_r = entry - stop
            target = entry + 2.0 * one_r

            exit_price = None
            exit_reason = None
            exit_pos = None
            last_pos = min(len(a)-1, entry_pos + max_hold_days - 1)

            for j in range(entry_pos, last_pos + 1):
                low = float(a['Low'].iloc[j])
                high = float(a['High'].iloc[j])

                stop_hit = low <= stop
                target_hit = high >= target

                if stop_hit and target_hit:
                    exit_price = stop
                    exit_reason = 'STOP'
                    exit_pos = j
                    break
                if stop_hit:
                    exit_price = stop
                    exit_reason = 'STOP'
                    exit_pos = j
                    break
                if target_hit:
                    exit_price = target
                    exit_reason = 'TARGET'
                    exit_pos = j
                    break

            if exit_price is None:
                exit_pos = last_pos
                exit_price = float(a['Close'].iloc[exit_pos])
                exit_reason = 'TIME'

            net = ((exit_price / entry) - 1.0) * 100.0 - cost_pct
            r_multiple = net / risk_pct if risk_pct else None

            events.append({
                'symbol': symbol,
                'signal_date': pd.Timestamp(a.index[signal_pos]),
                'entry_date': pd.Timestamp(a.index[entry_pos]),
                'exit_date': pd.Timestamp(a.index[exit_pos]),
                'entry': entry,
                'exit': exit_price,
                'net_return_pct': net,
                'r_multiple': r_multiple,
                'risk_pct': risk_pct,
                'exit_reason': exit_reason,
            })
            last_event_pos = signal_pos

    df = pd.DataFrame(events)
    if df.empty:
        return {'ok': True, 'model': 'v9_forward', 'events': 0, 'folds': []}

    df = df.sort_values('entry_date').reset_index(drop=True)

    # Fixed chronological folds across the evaluation window.
    date_bins = [eval_dates[int(i * len(eval_dates) / folds)] for i in range(folds)]
    date_bins.append(eval_dates[-1] + pd.Timedelta(days=1))

    fold_rows = []
    for i in range(folds):
        lo, hi = date_bins[i], date_bins[i+1]
        seg = df[(df['entry_date'] >= lo) & (df['entry_date'] < hi)].copy()
        if seg.empty:
            fold_rows.append({
                'fold': i+1,
                'start': pd.Timestamp(lo).date().isoformat(),
                'end': (pd.Timestamp(hi)-pd.Timedelta(days=1)).date().isoformat(),
                'events': 0,
            })
            continue

        wins = int((seg['net_return_pct'] > 0).sum())
        reasons = seg['exit_reason'].value_counts().to_dict()
        fold_rows.append({
            'fold': i+1,
            'start': pd.Timestamp(lo).date().isoformat(),
            'end': (pd.Timestamp(hi)-pd.Timedelta(days=1)).date().isoformat(),
            'events': int(len(seg)),
            'wins': wins,
            'losses': int(len(seg)-wins),
            'success_rate_pct': round(float(wins/len(seg)*100), 2),
            'avg_net_return_pct': round(float(seg['net_return_pct'].mean()), 3),
            'median_net_return_pct': round(float(seg['net_return_pct'].median()), 3),
            'avg_r_multiple': round(float(seg['r_multiple'].mean()), 3),
            'median_r_multiple': round(float(seg['r_multiple'].median()), 3),
            'exit_reasons': {str(k): int(v) for k,v in reasons.items()},
        })

    wins = int((df['net_return_pct'] > 0).sum())
    overall = {
        'events': int(len(df)),
        'wins': wins,
        'losses': int(len(df)-wins),
        'success_rate_pct': round(float(wins/len(df)*100), 2),
        'avg_net_return_pct': round(float(df['net_return_pct'].mean()), 3),
        'median_net_return_pct': round(float(df['net_return_pct'].median()), 3),
        'avg_r_multiple': round(float(df['r_multiple'].mean()), 3),
        'median_r_multiple': round(float(df['r_multiple'].median()), 3),
        'positive_folds': int(sum(1 for x in fold_rows if x.get('avg_net_return_pct', 0) > 0)),
        'total_nonempty_folds': int(sum(1 for x in fold_rows if x.get('events',0) > 0)),
    }

    return {
        'ok': True,
        'model': 'v9_forward_next_day_open',
        'tested_symbols': len(prepared),
        'settings': {
            'test_days': test_days,
            'cost_bps': cost_bps,
            'cooldown_days': cooldown_days,
            'max_hold_days': max_hold_days,
            'folds': folds,
            'signal': 'completed daily STRONG_CONFIRMATION_BASE + STRONG market',
            'entry': 'next trading day OPEN',
            'stop_cap_pct': 6,
            'target_r': 2,
            'same_day_rule': 'STOP first if target and stop both appear',
        },
        'overall': overall,
        'folds': fold_rows,
        'caveats': [
            'This is still historical simulation, not a live fill record.',
            'Current BIST30 composition is applied historically; survivorship bias may exist.',
            'Yahoo Finance is not official real-time BIST data.',
            'Daily OHLC cannot reveal intraday stop/target order; STOP-first is used conservatively.',
        ],
    }

