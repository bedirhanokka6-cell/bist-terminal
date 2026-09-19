from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from .analysis import indicators, technical_state
from .data import BIST30, load_chart
from .models import Signal, SignalResult


def score_to_signal_type(score: float) -> str:
    """Teknik skoru sade AL/BEKLE/SAT etiketine dönüştürür."""
    if score >= 7.5:
        return "AL"
    if score < 4.0:
        return "SAT"
    return "BEKLE"


def serialize_signal(s: Signal) -> dict:
    return {
        "id": s.id,
        "symbol": s.symbol,
        "signal_type": s.signal_type,
        "score": s.score,
        "state": s.state,
        "price": s.price,
        "support": s.support,
        "resistance": s.resistance,
        "reasons": s.reasons.split(" || ") if s.reasons else [],
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def serialize_result(r: SignalResult) -> dict:
    return {
        "id": r.id,
        "signal_id": r.signal_id,
        "horizon_days": r.horizon_days,
        "start_price": r.start_price,
        "end_price": r.end_price,
        "return_pct": r.return_pct,
        "successful": r.successful,
        "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def create_signal_from_analysis(db: Session, symbol: str, period: str = "1A") -> Signal:
    symbol = symbol.upper()
    if symbol not in BIST30:
        raise ValueError("BIST30 hissesi bulunamadı")

    d = load_chart(symbol, period)
    if d.empty:
        raise RuntimeError("Fiyat verisi alınamadı")

    a = indicators(d)
    t = technical_state(a)
    last = a.iloc[-1]
    support = float(a["Low"].tail(min(50, len(a))).min())
    resistance = float(a["High"].tail(min(50, len(a))).max())

    signal = Signal(
        symbol=symbol,
        signal_type=score_to_signal_type(float(t["score"])),
        score=float(t["score"]),
        state=str(t["state"]),
        price=float(last["Close"]),
        support=support,
        resistance=resistance,
        reasons=" || ".join(t.get("reasons", [])),
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def _download_daily(symbol: str, start: datetime, days_ahead: int) -> pd.DataFrame:
    # Hafta sonu/tatil payı için hedefin epey sonrasını indiriyoruz.
    end = datetime.utcnow() + timedelta(days=2)
    earliest_end = start + timedelta(days=max(days_ahead * 3, 14))
    if end < earliest_end:
        end = earliest_end

    d = yf.download(
        symbol + ".IS",
        start=(start - timedelta(days=5)).strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    return d.dropna()


def evaluate_signal(db: Session, signal: Signal, horizon_days: int = 5) -> tuple[SignalResult, bool]:
    if horizon_days not in {1, 3, 5, 10}:
        raise ValueError("horizon_days yalnızca 1, 3, 5 veya 10 olabilir")

    existing = (
        db.query(SignalResult)
        .filter(SignalResult.signal_id == signal.id, SignalResult.horizon_days == horizon_days)
        .first()
    )
    if existing and existing.evaluated_at is not None:
        return existing, True

    d = _download_daily(signal.symbol, signal.created_at, horizon_days)
    if d.empty:
        raise RuntimeError("Değerlendirme için fiyat verisi alınamadı")

    # Sinyalin oluştuğu günün SONRASINDAKİ işlem seanslarını say.
    idx_dates = pd.to_datetime(d.index).date
    signal_date = signal.created_at.date()
    after_positions = [i for i, dt in enumerate(idx_dates) if dt > signal_date]

    if len(after_positions) < horizon_days:
        # Henüz yeterli işlem seansı geçmedi. Sonuç kaydı oluştur ama beklemede kalsın.
        if existing is None:
            existing = SignalResult(
                signal_id=signal.id,
                horizon_days=horizon_days,
                start_price=signal.price,
                end_price=None,
                return_pct=None,
                successful=None,
                evaluated_at=None,
            )
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return existing, False

    pos = after_positions[horizon_days - 1]
    end_price = float(d["Close"].iloc[pos])
    return_pct = ((end_price / signal.price) - 1) * 100 if signal.price else None

    if signal.signal_type == "AL":
        successful: Optional[bool] = return_pct is not None and return_pct > 0
    elif signal.signal_type == "SAT":
        successful = return_pct is not None and return_pct < 0
    else:
        # BEKLE sinyali için başarı/başarısızlık yönü tanımlamıyoruz.
        successful = None

    if existing is None:
        existing = SignalResult(
            signal_id=signal.id,
            horizon_days=horizon_days,
            start_price=signal.price,
        )
        db.add(existing)

    existing.end_price = end_price
    existing.return_pct = return_pct
    existing.successful = successful
    existing.evaluated_at = datetime.utcnow()
    db.commit()
    db.refresh(existing)
    return existing, True
