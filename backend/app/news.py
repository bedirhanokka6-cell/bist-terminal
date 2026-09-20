from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


COMPANY_NAMES = {
    "AKBNK": "Akbank",
    "ASELS": "Aselsan",
    "ASTOR": "Astor Enerji",
    "BIMAS": "BİM Birleşik Mağazalar",
    "DSTKF": "Destek Finans Faktoring",
    "EKGYO": "Emlak Konut GYO",
    "ENKAI": "Enka İnşaat",
    "EREGL": "Ereğli Demir Çelik",
    "FROTO": "Ford Otosan",
    "GARAN": "Garanti BBVA",
    "GUBRF": "Gübre Fabrikaları",
    "ISCTR": "İş Bankası C",
    "KCHOL": "Koç Holding",
    "KRDMD": "Kardemir D",
    "MGROS": "Migros",
    "PETKM": "Petkim",
    "PGSUS": "Pegasus",
    "SAHOL": "Sabancı Holding",
    "SASA": "Sasa Polyester",
    "SISE": "Şişecam",
    "TAVHL": "TAV Havalimanları",
    "TCELL": "Turkcell",
    "THYAO": "Türk Hava Yolları",
    "TOASO": "Tofaş",
    "TSKB": "TSKB",
    "TUPRS": "Tüpraş",
    "ULKER": "Ülker",
    "VAKBN": "VakıfBank",
    "YKBNK": "Yapı Kredi",
    "ZOREN": "Zorlu Enerji",
}


def _clean_text(v: str | None) -> str:
    if not v:
        return ""
    return " ".join(v.replace("\n", " ").replace("\t", " ").split())


def _published_iso(v: str | None) -> str | None:
    if not v:
        return None
    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return v


def _rss(query: str, limit: int = 20) -> list[dict[str, Any]]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"
    )
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 BIST-Terminal/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )

    with urlopen(req, timeout=8) as res:
        body = res.read()

    root = ET.fromstring(body)
    out: list[dict[str, Any]] = []

    for item in root.findall(".//item")[:limit]:
        title = _clean_text(item.findtext("title"))
        link = _clean_text(item.findtext("link"))
        pub = _published_iso(item.findtext("pubDate"))
        source_el = item.find("source")
        source = _clean_text(source_el.text if source_el is not None else "")

        if not title or not link:
            continue

        out.append({
            "title": title,
            "url": link,
            "source": source or "Google News",
            "published_at": pub,
        })

    return out


def company_news(symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    symbol = symbol.upper().replace(".IS", "")
    name = COMPANY_NAMES.get(symbol, symbol)
    queries = [
        f'"{name}" Borsa İstanbul',
        f'{symbol} hisse',
    ]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for q in queries:
        try:
            for x in _rss(q, limit=max(8, limit)):
                key = x["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                x["kind"] = "HABER"
                rows.append(x)
        except Exception:
            continue

    rows.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return rows[:limit]


def kap_notifications(symbol: str, limit: int = 15) -> list[dict[str, Any]]:
    """
    Ücretsiz ve anahtarsız KAP görünümü.
    Google News RSS içinde kap.org.tr alanına indekslenmiş sonuçları arar.
    KAP'ın resmi bildirim ekranının yerine geçmez.
    """
    symbol = symbol.upper().replace(".IS", "")
    name = COMPANY_NAMES.get(symbol, symbol)
    queries = [
        f'site:kap.org.tr {symbol}',
        f'site:kap.org.tr "{name}"',
    ]

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for q in queries:
        try:
            for x in _rss(q, limit=max(8, limit)):
                key = x["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                x["kind"] = "KAP"
                rows.append(x)
        except Exception:
            continue

    rows.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return rows[:limit]
