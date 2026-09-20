from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from .db import Base


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(16), index=True, nullable=False)
    signal_type = Column(String(16), nullable=False, default="IZLE")
    score = Column(Float, nullable=False)
    state = Column(String(32), nullable=False)
    price = Column(Float, nullable=False)
    support = Column(Float, nullable=True)
    resistance = Column(Float, nullable=True)
    reasons = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(16), unique=True, index=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class VirtualPortfolio(Base):
    __tablename__ = "virtual_portfolio"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(16), index=True, nullable=False)
    side = Column(String(8), nullable=False, default="BUY")
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    status = Column(String(16), nullable=False, default="OPEN")
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class SignalResult(Base):
    __tablename__ = "signal_results"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, index=True, nullable=False)
    horizon_days = Column(Integer, nullable=False, default=5)
    start_price = Column(Float, nullable=False)
    end_price = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    successful = Column(Boolean, nullable=True)
    evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationToken(Base):
    __tablename__ = "notification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(Text, unique=True, nullable=False)
    platform = Column(String(32), nullable=False, default="web")
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(16), index=True, nullable=False)
    rule_key = Column(String(64), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


class OpenSignalPosition(Base):
    __tablename__ = "open_signal_positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(16), index=True, nullable=False)
    signal_type = Column(String(64), index=True, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    target1_price = Column(Float, nullable=False)
    target2_price = Column(Float, nullable=False)
    risk_pct = Column(Float, nullable=False)
    quality_score = Column(Float, nullable=True)
    volume_score = Column(Float, nullable=True)
    early_move_score = Column(Float, nullable=True)
    status = Column(String(16), index=True, nullable=False, default="OPEN")
    target1_hit = Column(Boolean, nullable=False, default=False)
    last_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String(32), nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    closed_at = Column(DateTime, nullable=True)
