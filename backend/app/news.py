from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import re
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed


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



_IMAGE_CACHE: dict[str, str | None] = {}

def _first_image_from_description(description: str | None) -> str | None:
    if not description:
        return None
    txt = html_lib.unescape(description)
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', txt, re.I)
    if m:
        return m.group(1)
    return None


def _extract_og_image(url: str) -> str | None:
    if not url:
        return None
    if url in _IMAGE_CACHE:
        return _IMAGE_CACHE[url]

    try:
        # Google News RSS linki çoğu zaman yayıncının gerçek haber sayfasına yönlenir.
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(req, timeout=7) as res:
            final_url = res.geturl()
            body = res.read(600_000).decode("utf-8", errors="ignore")

        def find_og(html_text: str):
            pats = [
                r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
                r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
            ]
            for p in pats:
                m = re.search(p, html_text, re.I)
                if m:
                    img = html_lib.unescape(m.group(1)).strip()
                    if img.startswith("//"):
                        img = "https:" + img
                    if img.startswith(("http://", "https://")):
                        return img
            return None

        img = find_og(body)
        if img:
            _IMAGE_CACHE[url] = img
            return img

        # Bazen yönlendirme sonrası HTML'de ilk büyük haber resmi bulunur.
        candidates = re.findall(r'<img[^>]+(?:src|data-src)=["\'](https?://[^"\']+)["\']', body, re.I)
        for img in candidates:
            low = img.lower()
            if any(x in low for x in ['logo', 'icon', 'avatar', 'sprite', 'favicon']):
                continue
            _IMAGE_CACHE[url] = html_lib.unescape(img)
            return _IMAGE_CACHE[url]

    except Exception:
        pass

    _IMAGE_CACHE[url] = None
    return None


def _fill_missing_images(rows: list[dict[str, Any]], max_items: int = 16) -> list[dict[str, Any]]:
    targets = [(i, x.get("url")) for i, x in enumerate(rows[:max_items]) if not x.get("image_url") and x.get("url")]
    if not targets:
        return rows

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_extract_og_image, url): i for i, url in targets}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                rows[i]["image_url"] = fut.result()
            except Exception:
                rows[i]["image_url"] = None
    return rows


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
        description = item.findtext("description")

        image_url = _first_image_from_description(description)

        if not image_url:
            for child in list(item):
                tag = child.tag.lower()
                if tag.endswith("content") or tag.endswith("thumbnail"):
                    candidate = child.attrib.get("url")
                    if candidate and candidate.startswith(("http://", "https://")):
                        image_url = candidate
                        break

        if not title or not link:
            continue

        out.append({
            "title": title,
            "url": link,
            "source": source or "Google News",
            "published_at": pub,
            "image_url": image_url,
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
                x.update(news_impact(x.get("title",""), "HABER"))
                rows.append(x)
        except Exception:
            continue

    rows.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    rows = rows[:limit]
    return rows


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
                x.update(news_impact(x.get("title",""), "KAP"))
                rows.append(x)
        except Exception:
            continue

    rows.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    rows = rows[:limit]
    return rows


POSITIVE_KEYWORDS = [
    "temettü", "temettu", "sözleşme", "sozlesme", "ihale", "yatırım", "yatirim",
    "kapasite art", "kar art", "kâr art", "rekor", "geri alım", "geri alim",
    "hedef fiyat yüksel", "hedef fiyat yuks", "not artır", "not artir",
    "yeni anlaşma", "yeni anlasma", "ihracat", "büyüme", "buyume"
]

NEGATIVE_KEYWORDS = [
    "zarar", "ceza", "soruşturma", "sorusturma", "dava", "iptal",
    "hedef fiyat düş", "hedef fiyat dus", "not düş", "not dus",
    "satış baskısı", "satis baskisi", "temerrüt", "temerrut",
    "üretim durdu", "uretim durdu", "kapatıldı", "kapatildi"
]


def news_impact(title: str, kind: str = "HABER") -> dict[str, Any]:
    t = (title or "").lower()
    score = 5.0
    reasons = []

    pos_hits = [k for k in POSITIVE_KEYWORDS if k in t]
    neg_hits = [k for k in NEGATIVE_KEYWORDS if k in t]

    if pos_hits:
        score += min(3.0, 0.9 * len(pos_hits))
        reasons.append("Olumlu anahtar kelime")
    if neg_hits:
        score -= min(3.0, 1.0 * len(neg_hits))
        reasons.append("Olumsuz anahtar kelime")

    if kind == "KAP":
        score += 0.3
        reasons.append("KAP kaynağı daha yüksek ağırlık")

    score = max(0.0, min(10.0, score))

    if score >= 7.5:
        label = "GÜÇLÜ OLUMLU"
    elif score >= 6.0:
        label = "OLUMLU"
    elif score <= 2.5:
        label = "GÜÇLÜ OLUMSUZ"
    elif score <= 4.0:
        label = "OLUMSUZ"
    else:
        label = "NÖTR"

    return {
        "impact_score": round(score, 1),
        "impact_label": label,
        "impact_reason": reasons[0] if reasons else "Başlıktan belirgin yön çıkarılamadı",
    }


def article_image(article_url: str) -> str | None:
    """Resolve a single article's real publisher image on demand."""
    return _extract_og_image(article_url)
