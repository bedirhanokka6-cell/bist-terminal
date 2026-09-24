
from fastapi import FastAPI, Query
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import os
import requests
import threading


try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception:
    firebase_admin = None
    credentials = None
    messaging = None

load_dotenv()

app = FastAPI(
    title="BIST Katilim Terminal API",
    version="18.0.0",
    description="V7.2 frozen strategy + automatic paper scan + notification queue"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PAPER_SYMBOLS = [
    "ALKLC", "ALTNY", "ASELS", "BERA", "BIMAS", "BINHO", "BMSTL", "BSOKE",
    "CANTE", "CIMSA", "CVKMD", "CWENE", "DAPGM", "DOFRB", "EFOR", "EKGYO",
    "ENJSA", "EREGL", "EUPWR", "FORMT", "GENIL", "GESAN", "GLRMK", "GRSEL",
    "GRTHO", "GUBRF", "IHLAS", "IZFAS", "KARSN", "KATMR", "KCAER", "KRDMD",
    "KTLEV", "KZBGY", "MAGEN", "MAVI", "MPARK", "NETCD", "OBAMS", "PASEU",
    "PETKM", "QUAGR", "RALYH", "SARKY", "TKFEN", "TUKAS", "TUPRS", "TUREX",
    "USAK", "YEOTK"
]

PAPER_SCAN_BATCH_SIZE = 10

TIMEFRAMES = {
    "1h": {"period": "730d", "interval": "1h"},
    "1d": {"period": "5y", "interval": "1d"},
}

FILTERS = {
    "rsi_min": 42.0,
    "rsi_max": 62.0,
    "adx_min": 17.0,
    "vol_ratio_min": 0.80,
    "vol5_to_vol20_min": 0.90,
    "dist_ema20_atr_min": -0.50,
    "dist_ema20_atr_max": 1.00,
    "atr_pct_min": 0.15,
    "atr_pct_max": 4.50,
    "benchmark_rsi_soft_min": 42.0,
}

PAPER_CONFIG = {
    "fee_bps_each_side": 10.0,
    "slippage_bps_each_side": 5.0,
    "stop_atr": 1.25,
    "reward_risk": 2.0,
    "max_hold_bars": 14,
}

AUTO_SCAN_MINUTES = 5

STATE_PATH = Path(__file__).with_name("paper_state.json")
STATE_LOCK = threading.Lock()
scheduler = BackgroundScheduler(timezone="UTC")

NEWS_CACHE = {}
NEWS_CACHE_TTL_SECONDS = 300
KAP_CACHE = {}
KAP_CACHE_TTL_SECONDS = 180


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def default_state():
    return {
        "version": "18.0.0",
        "started_at": now_utc_iso(),
        "strategy": "V7.2_FROZEN",
        "symbols": PAPER_SYMBOLS,
        "open_positions": [],
        "closed_trades": [],
        "seen_signal_keys": [],
        "notifications": [],
        "last_auto_scan_at": None,
        "last_auto_scan_errors": [],
        "scan_cursor": 0,
        "last_scanned_symbols": [],
        "total_universe": len(PAPER_SYMBOLS),
        "alert_settings": {
            "enabled": True,
            "strong_candidate_enabled": True,
            "strong_candidate_min_score": 80,
            "exact_v72_enabled": True,
            "scan_every_minutes": 15
        },
        "alert_seen_keys": [],
        "last_alert_scan_at": None,
        "last_alert_scan_result": None,
    }


def load_state():
    if not STATE_PATH.exists():
        state = default_state()
        save_state(state)
        return state

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = default_state()

    # Eski V9 state dosyasini V10'a uyumlu hale getir.
    state.setdefault("notifications", [])
    state.setdefault("last_auto_scan_at", None)
    state.setdefault("last_auto_scan_errors", [])
    state.setdefault("seen_signal_keys", [])
    state.setdefault("open_positions", [])
    state.setdefault("closed_trades", [])
    state.setdefault("scan_cursor", 0)
    state.setdefault("last_scanned_symbols", [])
    state.setdefault("total_universe", len(PAPER_SYMBOLS))
    state.setdefault("alert_settings", {
        "enabled": True,
        "strong_candidate_enabled": True,
        "strong_candidate_min_score": 80,
        "exact_v72_enabled": True,
        "scan_every_minutes": 15
    })
    state.setdefault("alert_seen_keys", [])
    state.setdefault("last_alert_scan_at", None)
    state.setdefault("last_alert_scan_result", None)
    state["symbols"] = PAPER_SYMBOLS
    state["total_universe"] = len(PAPER_SYMBOLS)
    state.setdefault("strategy", "V7.2_FROZEN")
    state["version"] = "18.0.0"
    save_state(state)
    return state


def save_state(state):
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_notification(state, kind, title, message, payload=None):
    note = {
        "id": f"{datetime.now(timezone.utc).timestamp()}-{len(state['notifications'])}",
        "created_at": now_utc_iso(),
        "kind": kind,
        "title": title,
        "message": message,
        "read": False,
        "payload": payload or {},
    }
    state["notifications"].append(note)

    # Dosyanin sonsuza kadar buyumemesi icin son 200 bildirimi tut.
    state["notifications"] = state["notifications"][-200:]
    return note


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    return symbol if symbol.endswith(".IS") else f"{symbol}.IS"


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        level0 = list(map(str, df.columns.get_level_values(0)))
        level1 = list(map(str, df.columns.get_level_values(1)))
        ohlcv = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}

        if len(ohlcv.intersection(level0)) >= 4:
            df.columns = df.columns.get_level_values(0)
        elif len(ohlcv.intersection(level1)) >= 4:
            df.columns = df.columns.get_level_values(1)
        else:
            df.columns = ["_".join(map(str, x)) for x in df.columns]

    df = df.loc[:, ~pd.Index(df.columns).duplicated()].copy()
    return df


def make_index_naive(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    df.index = idx
    return df


def fetch_data(symbol: str, timeframe: str = "1h") -> pd.DataFrame:
    if timeframe not in TIMEFRAMES:
        raise ValueError("timeframe sadece 1h veya 1d olabilir")

    cfg = TIMEFRAMES[timeframe]
    df = yf.download(
        normalize_symbol(symbol),
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df.empty:
        raise ValueError(f"Veri bulunamadi: {symbol}")

    df = flatten_columns(df)
    df = make_index_naive(df).sort_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            raise ValueError(f"Eksik kolon: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    return line, signal, line - signal


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    up = high.diff()
    down = -low.diff()

    plus_dm = pd.Series(
        np.where((up > down) & (up > 0), up, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down > up) & (down > 0), down, 0.0),
        index=df.index,
    )

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr_s = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    plus_di = 100 * (
        plus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        / atr_s.replace(0, np.nan)
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        / atr_s.replace(0, np.nan)
    )

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]
    volume = df["Volume"]

    df["EMA20"] = close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()
    df["RSI"] = rsi(close)

    m, s, h = macd(close)
    df["MACD"] = m
    df["MACD_SIGNAL"] = s
    df["MACD_HIST"] = h

    df["ATR"] = atr(df)
    df["ADX"] = adx(df)

    df["VOL5"] = volume.rolling(5).mean()
    df["VOL20"] = volume.rolling(20).mean()
    df["VOL_RATIO"] = volume / df["VOL20"].replace(0, np.nan)
    df["VOL5_TO_VOL20"] = df["VOL5"] / df["VOL20"].replace(0, np.nan)

    df["EMA20_SLOPE"] = df["EMA20"] - df["EMA20"].shift(5)
    df["EMA50_SLOPE"] = df["EMA50"] - df["EMA50"].shift(10)
    df["DIST_EMA20_ATR"] = (
        (close - df["EMA20"]) / df["ATR"].replace(0, np.nan)
    )
    df["ATR_PCT"] = (df["ATR"] / close.replace(0, np.nan)) * 100.0

    return df.dropna().copy()


def fetch_benchmark_daily():
    for ticker in ["XU100.IS", "XU030.IS"]:
        df = yf.download(
            ticker,
            period="5y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df.empty:
            continue

        df = flatten_columns(df)
        df = make_index_naive(df).sort_index()
        close = pd.to_numeric(df["Close"], errors="coerce")

        df["EMA50_B"] = close.ewm(span=50, adjust=False).mean()
        df["EMA200_B"] = close.ewm(span=200, adjust=False).mean()
        df["RSI_B"] = rsi(close)

        score = (
            (close > df["EMA50_B"]).astype(int)
            + (df["EMA50_B"] > df["EMA200_B"]).astype(int)
            + (df["RSI_B"] >= FILTERS["benchmark_rsi_soft_min"]).astype(int)
        )

        # Gelecek veri sizintisini azaltmak icin onceki tamamlanmis gun.
        df["REGIME_SCORE"] = score.shift(1)
        return ticker, df[["REGIME_SCORE"]].dropna().copy()

    raise ValueError("Benchmark verisi bulunamadi")


def attach_market_regime(df: pd.DataFrame):
    benchmark, regime = fetch_benchmark_daily()

    left = make_index_naive(df).reset_index()
    right = make_index_naive(regime).reset_index()

    lt = left.columns[0]
    rt = right.columns[0]

    left[lt] = pd.to_datetime(left[lt], errors="coerce").dt.tz_localize(None)
    right[rt] = pd.to_datetime(right[rt], errors="coerce").dt.tz_localize(None)

    merged = pd.merge_asof(
        left.dropna(subset=[lt]).sort_values(lt),
        right.dropna(subset=[rt]).sort_values(rt),
        left_on=lt,
        right_on=rt,
        direction="backward",
    )

    merged = merged.set_index(lt)

    if rt != lt and rt in merged.columns:
        merged = merged.drop(columns=[rt])

    merged["REGIME_SCORE"] = merged["REGIME_SCORE"].fillna(0).astype(int)
    return benchmark, merged


def trend_is_up(row):
    return (
        row["Close"] > row["EMA20"]
        and row["EMA20"] > row["EMA50"]
        and row["EMA50"] > row["EMA200"]
        and row["EMA20_SLOPE"] > 0
        and row["EMA50_SLOPE"] > 0
    )


def pullback_signal(row, prev):
    return (
        row["REGIME_SCORE"] >= 1
        and trend_is_up(row)
        and FILTERS["rsi_min"] <= row["RSI"] <= FILTERS["rsi_max"]
        and row["ADX"] >= FILTERS["adx_min"]
        and row["VOL_RATIO"] >= FILTERS["vol_ratio_min"]
        and row["VOL5_TO_VOL20"] >= FILTERS["vol5_to_vol20_min"]
        and FILTERS["atr_pct_min"] <= row["ATR_PCT"] <= FILTERS["atr_pct_max"]
        and FILTERS["dist_ema20_atr_min"]
            <= row["DIST_EMA20_ATR"]
            <= FILTERS["dist_ema20_atr_max"]
        and row["MACD_HIST"] > prev["MACD_HIST"]
        and row["Close"] > row["Open"]
    )


def get_open_position(state, symbol):
    for p in state["open_positions"]:
        if p["symbol"] == symbol:
            return p
    return None


def update_open_positions(state, timeframe="1h"):
    still_open = []
    newly_closed = []

    for pos in state["open_positions"]:
        symbol = pos["symbol"]

        try:
            df = fetch_data(symbol, timeframe)
        except Exception:
            still_open.append(pos)
            continue

        entry_time = pd.Timestamp(pos["entry_time"])
        future = df[df.index >= entry_time].copy()

        if future.empty:
            still_open.append(pos)
            continue

        exit_info = None
        bars_held = 0

        for ts, bar in future.iterrows():
            bars_held += 1

            if float(bar["Low"]) <= pos["stop"]:
                exit_info = (ts, pos["stop"], "STOP")
                break

            if float(bar["High"]) >= pos["target"]:
                exit_info = (ts, pos["target"], "TARGET")
                break

            if bars_held >= PAPER_CONFIG["max_hold_bars"]:
                exit_info = (ts, float(bar["Close"]), "TIME")
                break

        if exit_info is None:
            pos["bars_held"] = bars_held
            pos["last_price"] = round(float(future.iloc[-1]["Close"]), 4)
            still_open.append(pos)
            continue

        exit_ts, raw_exit, reason = exit_info
        exit_price = raw_exit * (
            1 - PAPER_CONFIG["slippage_bps_each_side"] / 10000.0
        )

        gross = (exit_price - pos["entry"]) / pos["entry"]
        fees = 2 * PAPER_CONFIG["fee_bps_each_side"] / 10000.0
        net = gross - fees

        closed = {
            **pos,
            "status": "CLOSED",
            "exit_time": str(exit_ts),
            "exit": round(exit_price, 4),
            "exit_reason": reason,
            "net_return_pct": round(net * 100, 3),
            "result": "WIN" if net > 0 else "LOSS",
        }

        newly_closed.append(closed)

        add_notification(
            state,
            "TRADE_CLOSED",
            f"{symbol} paper islem kapandi",
            f"{reason} | Sonuc: {closed['net_return_pct']}%",
            closed,
        )

    state["open_positions"] = still_open
    state["closed_trades"].extend(newly_closed)
    return newly_closed


def try_open_new_trade(state, symbol, timeframe="1h"):
    if get_open_position(state, symbol):
        return None

    df = fetch_data(symbol, timeframe)
    _, df = attach_market_regime(enrich(df))

    if len(df) < 3:
        return None

    signal_i = len(df) - 2
    entry_i = len(df) - 1

    signal_row = df.iloc[signal_i]
    prev_row = df.iloc[signal_i - 1]

    if not pullback_signal(signal_row, prev_row):
        return None

    signal_time = df.index[signal_i]
    entry_time = df.index[entry_i]
    signal_key = f"{symbol}|{timeframe}|{signal_time}"

    if signal_key in state["seen_signal_keys"]:
        return None

    started_at = pd.Timestamp(state["started_at"]).tz_convert(None)
    if pd.Timestamp(signal_time) <= started_at:
        state["seen_signal_keys"].append(signal_key)
        return None

    raw_entry = float(df.iloc[entry_i]["Open"])
    entry = raw_entry * (
        1 + PAPER_CONFIG["slippage_bps_each_side"] / 10000.0
    )

    atr_v = float(signal_row["ATR"])
    stop = entry - PAPER_CONFIG["stop_atr"] * atr_v
    risk = max(entry - stop, entry * 0.001)
    target = entry + PAPER_CONFIG["reward_risk"] * risk

    pos = {
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "OPEN",
        "signal_time": str(signal_time),
        "entry_time": str(entry_time),
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "last_price": round(float(df.iloc[entry_i]["Close"]), 4),
        "bars_held": 1,
        "opened_at": now_utc_iso(),
    }

    state["seen_signal_keys"].append(signal_key)
    state["open_positions"].append(pos)

    add_notification(
        state,
        "NEW_SIGNAL",
        f"{symbol} yeni paper sinyali",
        f"Giris: {pos['entry']} | Stop: {pos['stop']} | Hedef: {pos['target']}",
        pos,
    )

    return pos


def paper_metrics(state):
    closed = state["closed_trades"]

    if not closed:
        return {
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "expectancy_pct_per_trade": 0.0,
            "profit_factor": None,
            "total_compounded_return_pct": 0.0,
        }

    returns = np.array(
        [t["net_return_pct"] / 100.0 for t in closed],
        dtype=float,
    )

    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    gp = float(wins.sum()) if len(wins) else 0.0
    gl = abs(float(losses.sum())) if len(losses) else 0.0
    pf = gp / gl if gl > 0 else None

    equity = 1.0
    for r in returns:
        equity *= 1 + r

    return {
        "closed_trades": len(closed),
        "wins": int((returns > 0).sum()),
        "losses": int((returns <= 0).sum()),
        "win_rate_pct": round(float((returns > 0).mean() * 100), 2),
        "expectancy_pct_per_trade": round(float(returns.mean() * 100), 3),
        "profit_factor": round(pf, 3) if pf is not None else None,
        "total_compounded_return_pct": round((equity - 1) * 100, 2),
    }


def next_paper_batch(state, full_scan=False):
    """
    Scheduler her 5 dakikada tum 50 hisseyi tek seferde cekmek yerine
    round-robin batch tarar. Boylece backend ve Yahoo uzerindeki yuk azalir.
    Acik pozisyonlar her taramada yine kontrol edilir.
    """
    if full_scan:
        return list(PAPER_SYMBOLS)

    size = min(PAPER_SCAN_BATCH_SIZE, len(PAPER_SYMBOLS))
    cursor = int(state.get("scan_cursor", 0)) % len(PAPER_SYMBOLS)

    batch = []
    for i in range(size):
        batch.append(PAPER_SYMBOLS[(cursor + i) % len(PAPER_SYMBOLS)])

    state["scan_cursor"] = (cursor + size) % len(PAPER_SYMBOLS)
    return batch


def run_scan(timeframe="1h", full_scan=False):
    with STATE_LOCK:
        state = load_state()

        newly_closed = update_open_positions(state, timeframe)
        newly_opened = []
        errors = []

        scan_symbols = next_paper_batch(state, full_scan=full_scan)

        for symbol in scan_symbols:
            try:
                opened = try_open_new_trade(state, symbol, timeframe)
                if opened:
                    newly_opened.append(opened)
            except Exception as e:
                errors.append({
                    "symbol": symbol,
                    "message": str(e),
                })

        state["last_auto_scan_at"] = now_utc_iso()
        state["last_auto_scan_errors"] = errors
        state["last_scanned_symbols"] = scan_symbols
        state["symbols"] = PAPER_SYMBOLS
        state["total_universe"] = len(PAPER_SYMBOLS)
        save_state(state)

        # Push yalnızca yeni paper olayı oluştuğunda gönderilir.
        for trade in newly_opened:
            try:
                send_push_to_registered(
                    f"{trade.get('symbol', '')} yeni paper pozisyon",
                    f"Giris {trade.get('entry', 0):.2f} | Stop {trade.get('stop', 0):.2f} | Hedef {trade.get('target', 0):.2f}",
                    {"kind": "NEW_SIGNAL", "url": "/", "symbol": trade.get("symbol", "")},
                )
            except Exception:
                pass

        for trade in newly_closed:
            try:
                send_push_to_registered(
                    f"{trade.get('symbol', '')} paper islem kapandi",
                    f"{trade.get('exit_reason', '')} | Getiri %{trade.get('net_return_pct', 0):.2f}",
                    {"kind": "TRADE_CLOSED", "url": "/", "symbol": trade.get("symbol", "")},
                )
            except Exception:
                pass

        return {
            "newly_opened": newly_opened,
            "newly_closed": newly_closed,
            "errors": errors,
            "scanned_symbols": scan_symbols,
            "scan_count": len(scan_symbols),
            "full_scan": full_scan,
            "open_positions": state["open_positions"],
            "metrics": paper_metrics(state),
        }


def scheduled_scan():
    try:
        run_scan("1h", full_scan=False)
    except Exception:
        # Scheduler thread'i hata nedeniyle tamamen durmasin.
        pass


@app.on_event("startup")
def start_scheduler():
    load_state()

    if not scheduler.running:
        scheduler.add_job(
            scheduled_scan,
            "interval",
            minutes=AUTO_SCAN_MINUTES,
            id="paper_auto_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            scheduled_candidate_alerts,
            "interval",
            minutes=15,
            id="candidate_alert_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)




def classify_news_impact(title: str):
    """
    Basit baslik-temelli siniflama. Yatirim tavsiyesi degildir.
    """
    t = (title or "").lower()

    positive = [
        "sözleşme", "ihale", "sipariş", "yatırım", "kapasite artışı",
        "geri alım", "temettü", "kar payı", "rekor", "artış", "büyüme",
        "iş birliği", "anlaşma", "onay", "lisans", "ihracat", "satış artışı",
    ]
    negative = [
        "ceza", "dava", "zarar", "iptal", "düşüş", "azalış", "temerrüt",
        "iflas", "konkordato", "soruşturma", "faaliyet durdurma",
        "üretim duruşu", "geri çağırma", "borç", "kaybı",
    ]

    pos = sum(1 for k in positive if k in t)
    neg = sum(1 for k in negative if k in t)

    if pos > neg:
        return "pozitif_aday"
    if neg > pos:
        return "negatif_aday"
    return "notr"


def _news_item_url(item):
    if not isinstance(item, dict):
        return None

    direct = item.get("link") or item.get("url")
    if direct:
        return direct

    content = item.get("content") or {}
    if isinstance(content, dict):
        canonical = content.get("canonicalUrl") or {}
        if isinstance(canonical, dict) and canonical.get("url"):
            return canonical.get("url")

        click = content.get("clickThroughUrl") or {}
        if isinstance(click, dict) and click.get("url"):
            return click.get("url")

    return None


def _news_item_title(item):
    if not isinstance(item, dict):
        return ""
    if item.get("title"):
        return str(item.get("title"))

    content = item.get("content") or {}
    if isinstance(content, dict):
        return str(content.get("title") or "")
    return ""


def _news_item_publisher(item):
    if not isinstance(item, dict):
        return "Yahoo Finance"
    if item.get("publisher"):
        return str(item.get("publisher"))

    content = item.get("content") or {}
    if isinstance(content, dict):
        provider = content.get("provider") or {}
        if isinstance(provider, dict):
            return str(provider.get("displayName") or "Yahoo Finance")
    return "Yahoo Finance"


def _news_item_time(item):
    if not isinstance(item, dict):
        return None

    raw = item.get("providerPublishTime")
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
        except Exception:
            pass

    content = item.get("content") or {}
    if isinstance(content, dict):
        value = content.get("pubDate") or content.get("displayTime")
        if value:
            return str(value)
    return None



def classify_kap_disclosure(subject: str, summary: str):
    text = f"{subject or ''} {summary or ''}".lower()

    categories = [
        ("finansal", ["finansal rapor", "finansal tablo", "faaliyet raporu", "kar veya zarar"]),
        ("yeni_is", ["yeni iş ilişkisi", "sözleşme", "ihale", "sipariş", "iş ilişkisi"]),
        ("sermaye", ["sermaye artır", "sermaye azalt", "bedelli", "bedelsiz"]),
        ("temettu", ["kar payı", "temettü"]),
        ("geri_alim", ["pay geri al", "geri alım"]),
        ("yonetim", ["yönetim kurulu", "genel kurul"]),
        ("ortaklik", ["pay alım satım", "ortaklık yapısı", "pay sahipliği"]),
        ("yatirim", ["yatırım", "kapasite artışı", "tesis"]),
        ("hukuki", ["dava", "ceza", "soruşturma"]),
        ("endeks_piyasa", ["devre kesici", "bist pay endeksleri", "hak kullanımı"]),
    ]

    for key, words in categories:
        if any(w in text for w in words):
            return key
    return "diger"


def kap_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "BIST-Katilim-Terminal/1.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.kap.org.tr/tr/bildirim-sorgu",
        "Content-Type": "application/json",
    })
    return s


def fetch_kap_company(symbol: str):
    s = kap_session()
    url = f"https://www.kap.org.tr/tr/api/member/filter/{symbol}"
    r = s.get(url, timeout=8)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, list):
        exact = next(
            (x for x in data if str(x.get("stockCode", "")).upper() == symbol.upper()),
            data[0] if data else None,
        )
        data = exact

    if not isinstance(data, dict) or not data.get("mkkMemberOid"):
        raise ValueError(f"KAP şirket kaydı bulunamadı: {symbol}")

    return data


def fetch_kap_disclosures(symbol: str, days: int = 30, limit: int = 20):
    symbol = symbol.upper().replace(".IS", "").strip()
    cache_key = f"{symbol}:{days}:{limit}"
    now_ts = datetime.now(timezone.utc).timestamp()

    cached = KAP_CACHE.get(cache_key)
    if cached and now_ts - cached["ts"] < KAP_CACHE_TTL_SECONDS:
        return cached["data"]

    company = fetch_kap_company(symbol)
    mkk_oid = company["mkkMemberOid"]

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    s = kap_session()

    # KAP tarafinda session cookie olusturmak bazı isteklerde stabiliteyi artırır.
    try:
        s.get("https://www.kap.org.tr/tr/bildirim-sorgu", timeout=6)
    except Exception:
        pass

    r = s.post(
        "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria",
        json={
            "fromDate": start_date.isoformat(),
            "toDate": end_date.isoformat(),
            "mkkMemberOidList": [mkk_oid],
            "subjectList": [],
        },
        timeout=12,
    )
    r.raise_for_status()

    rows = r.json()
    if not isinstance(rows, list):
        rows = []

    results = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue

        idx = row.get("disclosureIndex")
        if idx in seen:
            continue
        seen.add(idx)

        stock_codes = str(row.get("stockCodes") or "")
        related_stocks = str(row.get("relatedStocks") or "")

        # MKK member filtresi esas filtredir. İlgili hisse alanlarını da koruyoruz.
        subject = str(row.get("subject") or "")
        summary = str(row.get("summary") or "")
        publish_date = row.get("publishDate")

        results.append({
            "disclosure_index": idx,
            "publish_date": publish_date,
            "company": row.get("kapTitle"),
            "stock_codes": stock_codes,
            "related_stocks": related_stocks,
            "subject": subject,
            "summary": summary,
            "category": classify_kap_disclosure(subject, summary),
            "is_late": bool(row.get("isLate")),
            "is_correction": bool(row.get("modifyStatus")),
            "attachment_count": int(row.get("attachmentCount") or 0),
            "url": f"https://www.kap.org.tr/tr/Bildirim/{idx}" if idx else None,
        })

    # API genellikle yeniyi üstte verir; yine de tarih stringi + index ile ters sırala.
    results.sort(
        key=lambda x: (str(x.get("publish_date") or ""), int(x.get("disclosure_index") or 0)),
        reverse=True,
    )
    results = results[:limit]

    payload = {
        "status": "ok",
        "symbol": symbol,
        "official_source": "KAP",
        "company": {
            "title": company.get("title"),
            "company_code": company.get("companyCode"),
            "mkk_member_oid": mkk_oid,
            "permalink": company.get("permaLink"),
            "company_url": (
                f"https://www.kap.org.tr/tr/sirket-bilgileri/ozet/{company.get('permaLink')}"
                if company.get("permaLink") else None
            ),
        },
        "days": days,
        "results": results,
        "count": len(results),
        "retrieved_at": now_utc_iso(),
        "note": "Veriler KAP'ın kamuya açık sorgu servisinden alınır.",
    }

    KAP_CACHE[cache_key] = {"ts": now_ts, "data": payload}
    return payload


@app.get("/kap/{symbol}")
def kap_disclosures(
    symbol: str,
    days: int = Query(30, ge=1, le=90),
    limit: int = Query(20, ge=1, le=50),
):
    try:
        return fetch_kap_disclosures(symbol, days=days, limit=limit)
    except Exception as e:
        return {
            "status": "error",
            "symbol": symbol.upper().replace(".IS", ""),
            "official_source": "KAP",
            "results": [],
            "count": 0,
            "error": str(e),
            "fallback_url": f"https://www.kap.org.tr/tr/bildirim-sorgu?q={symbol.upper().replace('.IS', '')}",
        }


@app.get("/news/{symbol}")
def symbol_news(
    symbol: str,
    limit: int = Query(12, ge=1, le=30),
):
    base_symbol = symbol.upper().replace(".IS", "").strip()
    ticker_symbol = normalize_symbol(base_symbol)

    now_ts = datetime.now(timezone.utc).timestamp()
    cache_key = f"{ticker_symbol}:{limit}"
    cached = NEWS_CACHE.get(cache_key)
    if cached and now_ts - cached["ts"] < NEWS_CACHE_TTL_SECONDS:
        return cached["data"]

    raw_news = []
    errors = []

    try:
        ticker = yf.Ticker(ticker_symbol)
        raw_news = ticker.news or []
    except Exception as e:
        errors.append(str(e))

    if not raw_news:
        try:
            search = yf.Search(ticker_symbol, news_count=limit)
            raw_news = getattr(search, "news", None) or []
        except Exception as e:
            errors.append(str(e))

    results = []
    seen = set()

    for item in raw_news:
        title = _news_item_title(item).strip()
        if not title:
            continue

        url = _news_item_url(item)
        dedupe = (title, url)
        if dedupe in seen:
            continue
        seen.add(dedupe)

        results.append({
            "title": title,
            "publisher": _news_item_publisher(item),
            "published_at": _news_item_time(item),
            "url": url,
            "impact": classify_news_impact(title),
            "impact_method": "headline_keyword_heuristic",
        })

        if len(results) >= limit:
            break

    data = {
        "status": "ok",
        "symbol": base_symbol,
        "source": "Yahoo Finance",
        "realtime_guaranteed": False,
        "results": results,
        "errors": errors,
        "kap": {
            "source": "KAP",
            "official": True,
            "search_url": f"https://www.kap.org.tr/tr/bildirim-sorgu?q={base_symbol}",
            "note": "KAP bildirimleri resmi KAP sayfasinda acilir; terminal bu surumde KAP icerigini kopyalamaz.",
        },
        "classification_note": (
            "Pozitif/negatif/notr etiketi yalnizca basliktaki anahtar kelimelerden uretilen "
            "bir on siniflamadir; haberin gercek piyasa etkisini garanti etmez."
        ),
    }

    NEWS_CACHE[cache_key] = {"ts": now_ts, "data": data}
    return data


PUSH_TOKENS_FILE = "push_tokens.json"


class PushRegisterRequest(BaseModel):
    token: str
    user_agent: str | None = None
    platform: str | None = None


def load_push_tokens():
    try:
        with open(PUSH_TOKENS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_push_tokens(tokens):
    with open(PUSH_TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def firebase_public_config():
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", ""),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.getenv("FIREBASE_APP_ID", ""),
    }


def ensure_firebase_admin():
    if firebase_admin is None:
        return False, "firebase-admin paketi kurulu degil."

    if firebase_admin._apps:
        return True, None

    service_account_file = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE", "").strip()

    try:
        if service_account_file:
            if not os.path.isabs(service_account_file):
                service_account_file = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    service_account_file
                )

            if not os.path.exists(service_account_file):
                return False, f"Service account dosyasi bulunamadi: {service_account_file}"

            cred = credentials.Certificate(service_account_file)
            firebase_admin.initialize_app(cred)
            return True, None

        project_id = os.getenv("FIREBASE_PROJECT_ID", "")
        client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "")
        private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")

        if not project_id or not client_email or not private_key:
            return False, "Firebase service account ayarlari eksik."

        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
            "private_key": private_key,
            "client_email": client_email,
            "client_id": os.getenv("FIREBASE_CLIENT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL", ""),
            "universe_domain": "googleapis.com",
        })
        firebase_admin.initialize_app(cred)
        return True, None
    except Exception as e:
        return False, str(e)


def send_push_to_registered(title, body, data=None):
    ok, err = ensure_firebase_admin()
    if not ok:
        return {"success": 0, "failed": 0, "error": err}

    tokens = load_push_tokens()
    if not tokens:
        return {"success": 0, "failed": 0, "error": "Kayitli push token yok."}

    success = 0
    failed = 0
    dead_tokens = set()

    for item in tokens:
        token = item.get("token")
        if not token:
            continue
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=token,
            )
            messaging.send(msg)
            success += 1
        except Exception as e:
            failed += 1
            if "registration-token-not-registered" in str(e).lower():
                dead_tokens.add(token)

    if dead_tokens:
        save_push_tokens([x for x in tokens if x.get("token") not in dead_tokens])

    return {"success": success, "failed": failed}


@app.get("/push/public-config")
def push_public_config():
    cfg = firebase_public_config()
    vapid = os.getenv("FIREBASE_VAPID_KEY", "")
    enabled = bool(
        cfg["apiKey"]
        and cfg["projectId"]
        and cfg["messagingSenderId"]
        and cfg["appId"]
        and vapid
    )
    return {
        "status": "ok",
        "enabled": enabled,
        "firebase_config": cfg,
        "vapid_key": vapid,
    }


@app.post("/push/register")
def push_register(payload: PushRegisterRequest):
    tokens = load_push_tokens()
    existing = next((x for x in tokens if x.get("token") == payload.token), None)

    if existing:
        existing["user_agent"] = payload.user_agent
        existing["platform"] = payload.platform
        existing["updated_at"] = now_utc_iso()
    else:
        tokens.append({
            "token": payload.token,
            "user_agent": payload.user_agent,
            "platform": payload.platform,
            "created_at": now_utc_iso(),
            "updated_at": now_utc_iso(),
        })

    save_push_tokens(tokens)
    return {"status": "ok", "registered_tokens": len(tokens)}


@app.post("/push/test")
def push_test():
    from fastapi import HTTPException

    result = send_push_to_registered(
        "BIST Katilim Terminal",
        "Test bildirimi basariyla gonderildi.",
        {"kind": "TEST", "url": "/", "tag": "paper-test"},
    )
    if result.get("success", 0) == 0:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Bildirim gonderilemedi.")
        )
    return {"status": "ok", **result}


@app.get("/")
def root():
    return {
        "status": "ok",
        "name": "BIST Katilim Terminal",
        "version": "18.0.0",
        "strategy": "V7.2_FROZEN",
        "paper_symbols": PAPER_SYMBOLS,
        "paper_universe_count": len(PAPER_SYMBOLS),
        "paper_scan_batch_size": PAPER_SCAN_BATCH_SIZE,
        "auto_scan_every_minutes": AUTO_SCAN_MINUTES,
        "auto_scan_enabled": scheduler.running,
        "endpoints": [
            "/paper/scan?timeframe=1h",
            "/paper/status",
            "/paper/trades",
            "/paper/notifications",
            "/paper/notifications/unread",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": "18.0.0",
        "scheduler_running": scheduler.running,
    }


@app.get("/paper/scan")
def paper_scan(
    timeframe: str = Query("1h"),
    full: bool = Query(False),
):
    result = run_scan(timeframe, full_scan=full)
    return {
        "status": "ok",
        "timeframe": timeframe,
        "strategy": "V7.2_FROZEN",
        **result,
    }


@app.get("/paper/status")
def paper_status():
    with STATE_LOCK:
        state = load_state()

    return {
        "status": "ok",
        "started_at": state["started_at"],
        "strategy": state["strategy"],
        "symbols": state["symbols"],
        "universe_count": len(PAPER_SYMBOLS),
        "scan_batch_size": PAPER_SCAN_BATCH_SIZE,
        "estimated_full_cycle_minutes": int(
            np.ceil(len(PAPER_SYMBOLS) / PAPER_SCAN_BATCH_SIZE) * AUTO_SCAN_MINUTES
        ),
        "last_scanned_symbols": state.get("last_scanned_symbols", []),
        "scan_cursor": state.get("scan_cursor", 0),
        "auto_scan_every_minutes": AUTO_SCAN_MINUTES,
        "last_auto_scan_at": state["last_auto_scan_at"],
        "last_auto_scan_errors": state["last_auto_scan_errors"],
        "open_positions": state["open_positions"],
        "metrics": paper_metrics(state),
        "unread_notifications": sum(
            1 for n in state["notifications"] if not n.get("read", False)
        ),
    }


@app.get("/paper/scan-status")
def paper_scan_status():
    with STATE_LOCK:
        state = load_state()

    return {
        "status": "ok",
        "strategy": state["strategy"],
        "universe_count": len(PAPER_SYMBOLS),
        "scan_batch_size": PAPER_SCAN_BATCH_SIZE,
        "auto_scan_every_minutes": AUTO_SCAN_MINUTES,
        "estimated_full_cycle_minutes": int(
            np.ceil(len(PAPER_SYMBOLS) / PAPER_SCAN_BATCH_SIZE) * AUTO_SCAN_MINUTES
        ),
        "last_auto_scan_at": state.get("last_auto_scan_at"),
        "last_scanned_symbols": state.get("last_scanned_symbols", []),
        "next_cursor": state.get("scan_cursor", 0),
        "open_positions_count": len(state.get("open_positions", [])),
        "closed_trades_count": len(state.get("closed_trades", [])),
        "last_errors": state.get("last_auto_scan_errors", []),
    }


@app.get("/paper/trades")
def paper_trades():
    with STATE_LOCK:
        state = load_state()

    return {
        "status": "ok",
        "closed_trades": state["closed_trades"],
        "count": len(state["closed_trades"]),
    }


@app.get("/paper/notifications")
def paper_notifications(limit: int = Query(50, ge=1, le=200)):
    with STATE_LOCK:
        state = load_state()

    notes = list(reversed(state["notifications"][-limit:]))

    return {
        "status": "ok",
        "count": len(notes),
        "notifications": notes,
    }


@app.get("/paper/notifications/unread")
def paper_notifications_unread():
    with STATE_LOCK:
        state = load_state()

    notes = [
        n for n in reversed(state["notifications"])
        if not n.get("read", False)
    ]

    return {
        "status": "ok",
        "count": len(notes),
        "notifications": notes,
    }


@app.post("/paper/notifications/read-all")
def paper_notifications_read_all():
    with STATE_LOCK:
        state = load_state()

        for n in state["notifications"]:
            n["read"] = True

        save_state(state)

    return {
        "status": "ok",
        "message": "Tum bildirimler okundu olarak isaretlendi",
    }


# ============================================================
# V12 OPTIMIZED MARKET DATA LAYER
# - Watchlist: tek toplu Yahoo istegi
# - Secili hisse: daha hafif 120 gun / 1 saat veri
# - Cache: watchlist 120 sn, secili hisse 60 sn, endeksler 120 sn
# - Grafik icin sadece son 100 bar dondurulur
#
# NOT:
# Yahoo Finance resmi Borsa Istanbul lisansli real-time feed degildir.
# Veri gecikmeli, eksik veya bazi sembollerde kullanilamaz olabilir.
# ============================================================

KATILIM_50 = [
    "ALKLC", "ALTNY", "ASELS", "BERA", "BIMAS", "BINHO", "BMSTL", "BSOKE",
    "CANTE", "CIMSA", "CVKMD", "CWENE", "DAPGM", "DOFRB", "EFOR", "EKGYO",
    "ENJSA", "EREGL", "EUPWR", "FORMT", "GENIL", "GESAN", "GLRMK", "GRSEL",
    "GRTHO", "GUBRF", "IHLAS", "IZFAS", "KARSN", "KATMR", "KCAER", "KRDMD",
    "KTLEV", "KZBGY", "MAGEN", "MAVI", "MPARK", "NETCD", "OBAMS", "PASEU",
    "PETKM", "QUAGR", "RALYH", "SARKY", "TKFEN", "TUKAS", "TUPRS", "TUREX",
    "USAK", "YEOTK"
]

_MARKET_CACHE = {}


def _cache_get(key, ttl_seconds=60):
    item = _MARKET_CACHE.get(key)
    if not item:
        return None
    ts, value = item
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age <= ttl_seconds:
        return value
    return None


def _cache_set(key, value):
    _MARKET_CACHE[key] = (datetime.now(timezone.utc), value)


def _safe_num(value, digits=3):
    try:
        if pd.isna(value):
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _fetch_ui_intraday(symbol: str) -> pd.DataFrame:
    """UI icin hafif 1 saatlik veri: 120 gun."""
    df = yf.download(
        normalize_symbol(symbol),
        period="120d",
        interval="1h",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df.empty:
        raise ValueError(f"Intraday veri bulunamadi: {symbol}")

    df = flatten_columns(df)
    df = make_index_naive(df).sort_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            raise ValueError(f"Eksik kolon: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()


def _fetch_ui_daily(symbol: str) -> pd.DataFrame:
    df = yf.download(
        normalize_symbol(symbol),
        period="1y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df.empty:
        raise ValueError(f"Gunluk veri bulunamadi: {symbol}")

    df = flatten_columns(df)
    df = make_index_naive(df).sort_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["High", "Low", "Close"]).copy()


def _cached_benchmark_regime():
    cached = _cache_get("ui_benchmark_regime", ttl_seconds=300)
    if cached is not None:
        return cached

    last_error = None
    for ticker in ["XU100.IS", "XU030.IS"]:
        try:
            df = yf.download(
                ticker,
                period="2y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df.empty:
                continue

            df = flatten_columns(df)
            df = make_index_naive(df).sort_index()
            close = pd.to_numeric(df["Close"], errors="coerce")

            df["EMA50_B"] = close.ewm(span=50, adjust=False).mean()
            df["EMA200_B"] = close.ewm(span=200, adjust=False).mean()
            df["RSI_B"] = rsi(close)

            score = (
                (close > df["EMA50_B"]).astype(int)
                + (df["EMA50_B"] > df["EMA200_B"]).astype(int)
                + (df["RSI_B"] >= FILTERS["benchmark_rsi_soft_min"]).astype(int)
            )
            df["REGIME_SCORE"] = score.shift(1)
            result = (ticker, df[["REGIME_SCORE"]].dropna().copy())
            _cache_set("ui_benchmark_regime", result)
            return result
        except Exception as e:
            last_error = e

    raise ValueError(f"Benchmark verisi bulunamadi: {last_error}")


def _attach_ui_regime(df: pd.DataFrame):
    benchmark, regime = _cached_benchmark_regime()

    left = make_index_naive(df).reset_index()
    right = make_index_naive(regime).reset_index()

    lt = left.columns[0]
    rt = right.columns[0]

    left[lt] = pd.to_datetime(left[lt], errors="coerce").dt.tz_localize(None)
    right[rt] = pd.to_datetime(right[rt], errors="coerce").dt.tz_localize(None)

    merged = pd.merge_asof(
        left.dropna(subset=[lt]).sort_values(lt),
        right.dropna(subset=[rt]).sort_values(rt),
        left_on=lt,
        right_on=rt,
        direction="backward",
    )
    merged = merged.set_index(lt)

    if rt != lt and rt in merged.columns:
        merged = merged.drop(columns=[rt])

    merged["REGIME_SCORE"] = merged["REGIME_SCORE"].fillna(0).astype(int)
    return benchmark, merged


def _pivot_levels(daily_df):
    daily_df = daily_df.copy().sort_index().dropna(subset=["High", "Low", "Close"])

    if len(daily_df) < 2:
        return {
            "method": "classic_pivot_previous_completed_day",
            "pivot": None, "r1": None, "r2": None, "r3": None,
            "s1": None, "s2": None, "s3": None,
            "basis_time": None,
        }

    # Son satir bugunun tamamlanmamis bari olabilir.
    ref = daily_df.iloc[-2]
    h = float(ref["High"])
    l = float(ref["Low"])
    c = float(ref["Close"])

    p = (h + l + c) / 3.0
    r1 = 2 * p - l
    s1 = 2 * p - h
    r2 = p + (h - l)
    s2 = p - (h - l)
    r3 = h + 2 * (p - l)
    s3 = l - 2 * (h - p)

    return {
        "method": "classic_pivot_previous_completed_day",
        "pivot": round(p, 4),
        "r1": round(r1, 4),
        "r2": round(r2, 4),
        "r3": round(r3, 4),
        "s1": round(s1, 4),
        "s2": round(s2, 4),
        "s3": round(s3, 4),
        "basis_time": str(daily_df.index[-2]),
    }


def _istanbul_iso(ts):
    """
    Chart zamanlarini Europe/Istanbul offset'i ile gonder.
    Veri index'i UTC-naive ise UTC kabul edilir.
    """
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.tz_convert("Europe/Istanbul").isoformat()


def _chart_data_for_range(symbol: str, chart_range: str):
    """
    Sadece grafik icin kullanilir.
    1d: son islem gununun 15 dakikalik mumlari
    1w: son 7 takvim gununun 1 saatlik mumlari
    """
    chart_range = chart_range.lower().strip()

    if chart_range == "1d":
        df = yf.download(
            normalize_symbol(symbol),
            period="5d",
            interval="15m",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        interval_label = "15m"

    elif chart_range == "1w":
        df = yf.download(
            normalize_symbol(symbol),
            period="10d",
            interval="1h",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        interval_label = "1h"

    else:
        raise ValueError("chart_range sadece 1d veya 1w olabilir")

    if df.empty:
        raise ValueError(f"Grafik verisi bulunamadi: {symbol}")

    df = flatten_columns(df)
    df = make_index_naive(df).sort_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            raise ValueError(f"Grafik icin eksik kolon: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"]).copy()

    if chart_range == "1d":
        if len(df):
            last_date = df.index[-1].date()
            df = df[df.index.date == last_date].copy()
        df = df.tail(60)
    else:
        if len(df):
            cutoff = df.index[-1] - pd.Timedelta(days=7)
            df = df[df.index >= cutoff].copy()
        df = df.tail(100)

    chart = []
    for ts, row in df.iterrows():
        chart.append({
            "time": _istanbul_iso(ts),
            "open": _safe_num(row["Open"], 4),
            "high": _safe_num(row["High"], 4),
            "low": _safe_num(row["Low"], 4),
            "close": _safe_num(row["Close"], 4),
            "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
        })

    return interval_label, chart


def _market_symbol_payload(symbol, timeframe="1h", chart_range="1w"):
    if timeframe != "1h":
        raise ValueError("V12 UI market endpointi su an 1h destekler")

    symbol = symbol.upper().strip()
    cache_key = f"v12_2:symbol:{symbol}:{chart_range}"
    cached = _cache_get(cache_key, ttl_seconds=60)
    if cached is not None:
        return cached

    raw = _fetch_ui_intraday(symbol)
    enriched = enrich(raw)
    benchmark, merged = _attach_ui_regime(enriched)

    daily = _fetch_ui_daily(symbol)
    pivots = _pivot_levels(daily)

    if len(merged) < 3:
        raise ValueError("Gostergeler icin yeterli veri yok")

    # Sinyal hesaplamasinda kapanmis saat bari kullan.
    completed = merged.iloc[-2]
    previous = merged.iloc[-3]

    current_price = float(raw.iloc[-1]["Close"])

    daily_clean = daily.dropna(subset=["Close"])
    if len(daily_clean) >= 2:
        last_d = float(daily_clean.iloc[-1]["Close"])
        prev_d = float(daily_clean.iloc[-2]["Close"])
        day_change = ((last_d / prev_d) - 1) * 100 if prev_d else 0.0
    else:
        day_change = 0.0

    signal_active = pullback_signal(completed, previous)

    # Grafik araligi stratejiden bagimsizdir.
    chart_interval, chart = _chart_data_for_range(symbol, chart_range)

    payload = {
        "status": "ok",
        "symbol": symbol,
        "timeframe": "1h",
        "source": "Yahoo Finance",
        "realtime_guaranteed": False,
        "cache_seconds": 60,
        "chart_range": chart_range,
        "chart_interval": chart_interval,
        "benchmark": benchmark,
        "price": {
            "last": round(current_price, 4),
            "daily_change_pct": round(day_change, 3),
            "asof": _istanbul_iso(raw.index[-1]),
        },
        "signal": {
            "value": "AL" if signal_active else "BEKLE",
            "strategy": "V7.2_FROZEN",
            "signal_bar_time": str(merged.index[-2]),
        },
        "support_resistance": pivots,
        "indicators": {
            "rsi14": _safe_num(completed["RSI"], 2),
            "macd": _safe_num(completed["MACD"], 4),
            "macd_signal": _safe_num(completed["MACD_SIGNAL"], 4),
            "macd_hist": _safe_num(completed["MACD_HIST"], 4),
            "adx14": _safe_num(completed["ADX"], 2),
            "ema20": _safe_num(completed["EMA20"], 4),
            "ema50": _safe_num(completed["EMA50"], 4),
            "ema200": _safe_num(completed["EMA200"], 4),
            "atr14": _safe_num(completed["ATR"], 4),
            "volume_ratio": _safe_num(completed["VOL_RATIO"], 3),
            "regime_score": int(completed["REGIME_SCORE"]),
        },
        "chart": chart,
    }

    _cache_set(cache_key, payload)
    return payload


def _extract_bulk_symbol(raw: pd.DataFrame, ticker: str):
    """
    yfinance farkli surumlerde MultiIndex kolonlarini
    (ticker, field) veya (field, ticker) seklinde dondurebilir.
    Ikisini de destekle.
    """
    if not isinstance(raw.columns, pd.MultiIndex):
        return None

    level0 = list(map(str, raw.columns.get_level_values(0)))
    level1 = list(map(str, raw.columns.get_level_values(1)))

    if ticker in level0:
        sub = raw[ticker].copy()
        return sub

    if ticker in level1:
        try:
            sub = raw.xs(ticker, axis=1, level=1, drop_level=True).copy()
            return sub
        except Exception:
            return None

    return None


def _parse_watch_item(symbol: str, sub: pd.DataFrame):
    if sub is None or sub.empty:
        raise ValueError("Ticker toplu cevapta yok")

    sub = sub.copy()
    sub.index = pd.to_datetime(sub.index)
    sub = sub.sort_index()

    if isinstance(sub.columns, pd.MultiIndex):
        sub = flatten_columns(sub)

    if "Close" not in sub.columns:
        raise ValueError("Close kolonu yok")

    close = pd.to_numeric(sub["Close"], errors="coerce").dropna()
    if len(close) < 2:
        raise ValueError("Yeterli kapanis verisi yok")

    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = ((last / prev) - 1) * 100 if prev else 0.0

    volume = None
    if "Volume" in sub.columns:
        vol = pd.to_numeric(sub["Volume"], errors="coerce").dropna()
        if len(vol):
            volume = int(vol.iloc[-1])

    return {
        "symbol": symbol,
        "last_price": round(last, 4),
        "daily_change_pct": round(change, 3),
        "volume": volume,
        "asof": str(close.index[-1]),
    }


def _download_watchlist_chunk(symbols):
    tickers = [normalize_symbol(s) for s in symbols]

    raw = yf.download(
        tickers=tickers,
        period="7d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    results = []
    errors = []

    if raw.empty:
        return results, [{"symbol": s, "message": "Toplu veri bos"} for s in symbols]

    # Tek sembol chunk'inda yfinance MultiIndex vermeyebilir.
    if len(symbols) == 1 and not isinstance(raw.columns, pd.MultiIndex):
        try:
            results.append(_parse_watch_item(symbols[0], raw))
            return results, errors
        except Exception as e:
            return results, [{"symbol": symbols[0], "message": str(e)}]

    for symbol, ticker in zip(symbols, tickers):
        try:
            sub = _extract_bulk_symbol(raw, ticker)
            results.append(_parse_watch_item(symbol, sub))
        except Exception as e:
            errors.append({"symbol": symbol, "message": str(e)})

    return results, errors


def _bulk_watchlist():
    # 10'luk chunk, tek devasa istege gore daha stabil;
    # yine 50 ayri istekten cok daha hafif.
    all_results = []
    failed_symbols = []

    for i in range(0, len(KATILIM_50), 10):
        chunk = KATILIM_50[i:i+10]
        results, errors = _download_watchlist_chunk(chunk)
        all_results.extend(results)
        failed_symbols.extend([e["symbol"] for e in errors])

    # Sadece eksik kalanlari tek tek dene.
    recovered = []
    final_errors = []

    seen = {x["symbol"] for x in all_results}
    for symbol in KATILIM_50:
        if symbol in seen:
            continue
        try:
            df = yf.download(
                normalize_symbol(symbol),
                period="7d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df.empty:
                raise ValueError("Veri bulunamadi")

            df = flatten_columns(df)
            df = make_index_naive(df).sort_index()
            recovered.append(_parse_watch_item(symbol, df))
        except Exception as e:
            final_errors.append({"symbol": symbol, "message": str(e)})

    all_results.extend(recovered)

    # Orijinal Katilim 50 sirasini koru.
    order = {s: i for i, s in enumerate(KATILIM_50)}
    all_results.sort(key=lambda x: order.get(x["symbol"], 999))

    return all_results, final_errors


@app.get("/market/watchlist")
def market_watchlist():
    cache_key = "v12:watchlist"
    cached = _cache_get(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    try:
        results, errors = _bulk_watchlist()
    except Exception as e:
        results, errors = [], [{"symbol": "BULK", "message": str(e)}]

    payload = {
        "status": "ok",
        "index_code": "XK050",
        "source": "Yahoo Finance",
        "realtime_guaranteed": False,
        "cache_seconds": 120,
        "requested": len(KATILIM_50),
        "returned": len(results),
        "results": results,
        "errors": errors,
    }

    _cache_set(cache_key, payload)
    return payload


@app.get("/market/{symbol}")
def market_symbol(
    symbol: str,
    timeframe: str = Query("1h"),
    chart_range: str = Query("1w"),
):
    try:
        return _market_symbol_payload(symbol, timeframe, chart_range)
    except Exception as e:
        return {
            "status": "error",
            "symbol": symbol.upper(),
            "message": str(e),
        }


def _download_index_candidates(candidates):
    last_error = None

    for ticker in candidates:
        try:
            df = yf.download(
                ticker,
                period="7d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if df.empty:
                continue

            df = flatten_columns(df)
            df = make_index_naive(df).sort_index()
            close = pd.to_numeric(df["Close"], errors="coerce").dropna()

            if len(close) < 2:
                continue

            last = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            chg = ((last / prev) - 1) * 100 if prev else 0.0

            return {
                "ticker": ticker,
                "value": round(last, 4),
                "daily_change_pct": round(chg, 3),
                "asof": str(close.index[-1]),
                "proxy": False,
            }
        except Exception as e:
            last_error = e

    raise ValueError(str(last_error) if last_error else "veri bulunamadi")


@app.get("/market-indexes")
def market_indexes():
    cache_key = "v12:indexes"
    cached = _cache_get(cache_key, ttl_seconds=120)
    if cached is not None:
        return cached

    definitions = [
        ("BIST 100", ["XU100.IS", "XU100"]),
        ("BIST 30", ["XU030.IS", "XU030"]),
        ("BIST KATILIM 50", ["XK050.IS", "XK050"]),
    ]

    results = []
    errors = []

    for name, candidates in definitions:
        try:
            item = _download_index_candidates(candidates)
            item["name"] = name
            results.append(item)
        except Exception as e:
            errors.append({"name": name, "message": str(e)})

    # XK050 Yahoo'da yoksa endeks degeri UYDURMA.
    # Sadece watchlist'in esit agirlikli ortalama gunluk degisimini "proxy" olarak ver.
    if not any(x["name"] == "BIST KATILIM 50" for x in results):
        wl = _cache_get("v12:watchlist", ttl_seconds=180)
        if wl and wl.get("results"):
            changes = [
                x["daily_change_pct"]
                for x in wl["results"]
                if x.get("daily_change_pct") is not None
            ]
            if changes:
                results.append({
                    "name": "BIST KATILIM 50",
                    "ticker": None,
                    "value": None,
                    "daily_change_pct": round(sum(changes) / len(changes), 3),
                    "asof": wl["results"][0].get("asof"),
                    "proxy": True,
                })

    payload = {
        "status": "ok",
        "source": "Yahoo Finance",
        "realtime_guaranteed": False,
        "cache_seconds": 120,
        "results": results,
        "errors": errors,
    }

    _cache_set(cache_key, payload)
    return payload



class AlertSettingsRequest(BaseModel):
    enabled: bool = True
    strong_candidate_enabled: bool = True
    strong_candidate_min_score: int = 80
    exact_v72_enabled: bool = True


def _normalize_alert_settings(raw=None):
    raw = raw or {}
    score = int(raw.get("strong_candidate_min_score", 80))
    score = max(60, min(100, score))
    return {
        "enabled": bool(raw.get("enabled", True)),
        "strong_candidate_enabled": bool(raw.get("strong_candidate_enabled", True)),
        "strong_candidate_min_score": score,
        "exact_v72_enabled": bool(raw.get("exact_v72_enabled", True)),
        "scan_every_minutes": 15,
    }


def _emit_system_alert(state, kind, title, message, payload, dedupe_key):
    seen = state.setdefault("alert_seen_keys", [])
    if dedupe_key in seen:
        return False

    seen.append(dedupe_key)
    state["alert_seen_keys"] = seen[-1000:]

    add_notification(
        state,
        kind,
        title,
        message,
        payload,
    )

    try:
        send_push_to_registered(
            title,
            message,
            {
                "kind": kind,
                "url": "/",
                "symbol": payload.get("symbol", ""),
                "tag": f"alert-{kind.lower()}-{payload.get('symbol', '')}",
            },
        )
    except Exception:
        pass

    return True


def run_candidate_alert_scan(force=True):
    with STATE_LOCK:
        state = load_state()
        settings = _normalize_alert_settings(state.get("alert_settings"))

        if not settings["enabled"]:
            result = {
                "status": "disabled",
                "alerts_created": 0,
                "checked": 0,
                "generated_at": now_utc_iso(),
            }
            state["last_alert_scan_at"] = result["generated_at"]
            state["last_alert_scan_result"] = result
            save_state(state)
            return result

    # Scanner kendi 5 dakikalik cache'ini kullanabilir; scheduler'da yeni bar icin force=True.
    scan = scanner_candidates(
        limit=50,
        min_score=float(min(settings["strong_candidate_min_score"], 80)),
        refresh=bool(force),
    )

    candidates = scan.get("results", [])
    created = []
    skipped = []

    with STATE_LOCK:
        state = load_state()
        settings = _normalize_alert_settings(state.get("alert_settings"))

        for item in candidates:
            symbol = item.get("symbol", "")
            bar_time = item.get("bar_time", "")
            score = float(item.get("score") or 0)

            if settings["exact_v72_enabled"] and item.get("exact_v72_signal"):
                key = f"V72|{symbol}|{bar_time}"
                title = f"{symbol} V7.2 sinyal kosullari tamam"
                message = (
                    f"Uyum {score:.0f}/100 | RSI {item.get('rsi')} | "
                    f"ADX {item.get('adx')} | Hacim {item.get('volume_ratio')}x"
                )
                if _emit_system_alert(state, "V72_SIGNAL", title, message, item, key):
                    created.append({"kind": "V72_SIGNAL", "symbol": symbol, "score": score})
                else:
                    skipped.append(key)
                # Tam sinyal ayni barda ayrica guclu aday bildirimi uretmesin.
                continue

            if (
                settings["strong_candidate_enabled"]
                and score >= settings["strong_candidate_min_score"]
            ):
                key = f"STRONG|{symbol}|{bar_time}|{settings['strong_candidate_min_score']}"
                title = f"{symbol} teknik uyum adayi"
                message = (
                    f"V7.2 kosul uyumu {score:.0f}/100 | "
                    f"{item.get('passed_checks')}/{item.get('total_checks')} kosul"
                )
                if _emit_system_alert(state, "STRONG_CANDIDATE", title, message, item, key):
                    created.append({"kind": "STRONG_CANDIDATE", "symbol": symbol, "score": score})
                else:
                    skipped.append(key)

        result = {
            "status": "ok",
            "alerts_created": len(created),
            "created": created,
            "duplicates_skipped": len(skipped),
            "checked": scan.get("scored_symbols", 0),
            "regime_score": scan.get("regime_score"),
            "scanner_errors": len(scan.get("errors", [])),
            "generated_at": now_utc_iso(),
        }

        state["alert_settings"] = settings
        state["last_alert_scan_at"] = result["generated_at"]
        state["last_alert_scan_result"] = result
        save_state(state)

    return result


def scheduled_candidate_alerts():
    try:
        run_candidate_alert_scan(force=True)
    except Exception:
        pass


@app.get("/alerts/settings")
def get_alert_settings():
    with STATE_LOCK:
        state = load_state()
    return {
        "status": "ok",
        "settings": _normalize_alert_settings(state.get("alert_settings")),
        "last_alert_scan_at": state.get("last_alert_scan_at"),
        "last_alert_scan_result": state.get("last_alert_scan_result"),
        "registered_push_tokens": len(load_push_tokens()),
    }


@app.post("/alerts/settings")
def update_alert_settings(payload: AlertSettingsRequest):
    settings = _normalize_alert_settings(payload.model_dump())
    with STATE_LOCK:
        state = load_state()
        state["alert_settings"] = settings
        save_state(state)
    return {"status": "ok", "settings": settings}


@app.post("/alerts/check-now")
def alert_check_now():
    return run_candidate_alert_scan(force=True)


# ============================================================
# V17 - GUCLU ADAY TARAYICI
# Mevcut V7.2_FROZEN kosullarina "uyum" puani verir.
# Bu puan al/sat tavsiyesi veya tahmin degildir.
# ============================================================

_SCANNER_CACHE = {}


def _scanner_score_frame(symbol: str, df: pd.DataFrame, regime_score: int):
    if df is None or df.empty:
        raise ValueError("Veri bos")

    df = df.copy()
    df = flatten_columns(df)
    df = make_index_naive(df).sort_index()

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            raise ValueError(f"Eksik kolon: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    df = enrich(df)

    if len(df) < 3:
        raise ValueError("Yetersiz teknik veri")

    # Son bar tam kapanmamis olabilir; paper mantigi ile ayni sekilde
    # bir onceki tamamlanmis bari puanliyoruz.
    row = df.iloc[-2].copy()
    prev = df.iloc[-3].copy()
    row["REGIME_SCORE"] = int(regime_score)

    checks = {
        "piyasa_rejimi": bool(row["REGIME_SCORE"] >= 1),
        "trend": bool(trend_is_up(row)),
        "rsi": bool(FILTERS["rsi_min"] <= row["RSI"] <= FILTERS["rsi_max"]),
        "adx": bool(row["ADX"] >= FILTERS["adx_min"]),
        "hacim": bool(row["VOL_RATIO"] >= FILTERS["vol_ratio_min"]),
        "hacim_ortalamasi": bool(row["VOL5_TO_VOL20"] >= FILTERS["vol5_to_vol20_min"]),
        "ema20_mesafe": bool(
            FILTERS["dist_ema20_atr_min"]
            <= row["DIST_EMA20_ATR"]
            <= FILTERS["dist_ema20_atr_max"]
        ),
        "atr": bool(FILTERS["atr_pct_min"] <= row["ATR_PCT"] <= FILTERS["atr_pct_max"]),
        "macd_ivme": bool(row["MACD_HIST"] > prev["MACD_HIST"]),
        "pozitif_mum": bool(row["Close"] > row["Open"]),
    }

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    score = round((passed / total) * 100, 1)

    exact_signal = bool(
        checks["piyasa_rejimi"]
        and checks["trend"]
        and checks["rsi"]
        and checks["adx"]
        and checks["hacim"]
        and checks["hacim_ortalamasi"]
        and checks["ema20_mesafe"]
        and checks["atr"]
        and checks["macd_ivme"]
        and checks["pozitif_mum"]
    )

    if exact_signal:
        level = "V7.2_SINYAL"
    elif score >= 80:
        level = "GUCLU_ADAY"
    elif score >= 60:
        level = "IZLE"
    else:
        level = "ZAYIF"

    return {
        "symbol": symbol,
        "score": score,
        "passed_checks": passed,
        "total_checks": total,
        "level": level,
        "exact_v72_signal": exact_signal,
        "price": _safe_num(row["Close"], 4),
        "bar_time": str(df.index[-2]),
        "rsi": _safe_num(row["RSI"], 2),
        "adx": _safe_num(row["ADX"], 2),
        "macd_hist": _safe_num(row["MACD_HIST"], 4),
        "volume_ratio": _safe_num(row["VOL_RATIO"], 2),
        "vol5_to_vol20": _safe_num(row["VOL5_TO_VOL20"], 2),
        "atr_pct": _safe_num(row["ATR_PCT"], 2),
        "dist_ema20_atr": _safe_num(row["DIST_EMA20_ATR"], 2),
        "ema20": _safe_num(row["EMA20"], 4),
        "ema50": _safe_num(row["EMA50"], 4),
        "ema200": _safe_num(row["EMA200"], 4),
        "regime_score": int(regime_score),
        "checks": checks,
    }


def _scanner_bulk_chunk(symbols, regime_score):
    tickers = [normalize_symbol(s) for s in symbols]
    raw = yf.download(
        tickers=tickers,
        period="90d",
        interval="1h",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    results = []
    errors = []

    if raw.empty:
        return [], [{"symbol": s, "message": "Toplu 1h veri bos"} for s in symbols]

    if len(symbols) == 1 and not isinstance(raw.columns, pd.MultiIndex):
        try:
            results.append(_scanner_score_frame(symbols[0], raw, regime_score))
        except Exception as e:
            errors.append({"symbol": symbols[0], "message": str(e)})
        return results, errors

    for symbol, ticker in zip(symbols, tickers):
        try:
            sub = _extract_bulk_symbol(raw, ticker)
            if sub is None or sub.empty:
                raise ValueError("Toplu cevapta veri yok")
            results.append(_scanner_score_frame(symbol, sub, regime_score))
        except Exception as e:
            errors.append({"symbol": symbol, "message": str(e)})

    return results, errors


@app.get("/scanner/candidates")
def scanner_candidates(
    limit: int = Query(15, ge=1, le=50),
    min_score: float = Query(50.0, ge=0, le=100),
    refresh: bool = Query(False),
):
    cache_key = f"{limit}:{min_score}"
    now = datetime.now(timezone.utc)

    cached = _SCANNER_CACHE.get(cache_key)
    if cached and not refresh:
        age = (now - cached["ts"]).total_seconds()
        if age <= 300:
            return cached["data"]

    benchmark_symbol = None
    regime_score = 0
    benchmark_error = None

    try:
        benchmark_symbol, regime_df = fetch_benchmark_daily()
        if not regime_df.empty:
            regime_score = int(regime_df["REGIME_SCORE"].iloc[-1])
    except Exception as e:
        benchmark_error = str(e)

    all_results = []
    errors = []

    # 10'luk toplu 1h indirme: 50 tekil istege gore daha hafif.
    for i in range(0, len(KATILIM_50), 10):
        chunk = KATILIM_50[i:i+10]
        chunk_results, chunk_errors = _scanner_bulk_chunk(chunk, regime_score)
        all_results.extend(chunk_results)
        errors.extend(chunk_errors)

    filtered = [x for x in all_results if x["score"] >= min_score]
    filtered.sort(
        key=lambda x: (
            1 if x["exact_v72_signal"] else 0,
            x["score"],
            x["adx"] or 0,
        ),
        reverse=True,
    )

    payload = {
        "status": "ok",
        "strategy": "V7.2_FROZEN",
        "universe": "XK050_APP_UNIVERSE",
        "requested_symbols": len(KATILIM_50),
        "scored_symbols": len(all_results),
        "benchmark": benchmark_symbol,
        "regime_score": regime_score,
        "benchmark_error": benchmark_error,
        "min_score": min_score,
        "results": filtered[:limit],
        "errors": errors,
        "generated_at": now_utc_iso(),
        "cache_seconds": 300,
        "note": (
            "Uyum skoru V7.2_FROZEN teknik kosullarinin kacinin saglandigini gosterir. "
            "Kar olasiligi, hedef fiyat veya yatirim tavsiyesi degildir."
        ),
    }

    _SCANNER_CACHE[cache_key] = {"ts": now, "data": payload}
    return payload

