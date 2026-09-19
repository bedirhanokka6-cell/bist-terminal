from functools import lru_cache
import pandas as pd
import yfinance as yf

BIST30 = [
    'AKBNK','ASELS','ASTOR','BIMAS','DSTKF','EKGYO','ENKAI','EREGL','FROTO','GARAN',
    'GUBRF','ISCTR','KCHOL','KRDMD','MGROS','PETKM','PGSUS','SAHOL','SASA','SISE',
    'TAVHL','TCELL','THYAO','TOASO','TSKB','TUPRS','ULKER','VAKBN','YKBNK','ZOREN'
]

PERIODS = {
    '1G': ('2d', '5m'),
    '5G': ('5d', '15m'),
    '1A': ('1mo', '30m'),
    '3A': ('3mo', '1h'),
    '6A': ('6mo', '1d'),
    '1Y': ('1y', '1d'),
    '2Y': ('2y', '1d'),
}

def load_chart(symbol: str, period_key: str = '1A') -> pd.DataFrame:
    period, interval = PERIODS.get(period_key, PERIODS['1A'])
    d = yf.download(symbol + '.IS', period=period, interval=interval,
                    auto_adjust=False, progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d.dropna()
    if d.empty:
        return d
    if period_key == '1G':
        idx = d.index
        try:
            dates = idx.tz_convert('Europe/Istanbul').date if getattr(idx, 'tz', None) is not None else idx.date
        except Exception:
            dates = idx.date
        last_date = max(dates)
        d = d[[x == last_date for x in dates]].copy()
    return d
