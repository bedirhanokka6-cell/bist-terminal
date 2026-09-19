from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import quote
import html as html_lib
import re
import yfinance as yf


def classify_news_effect(title: str):
    q = (title or '').lower()
    positive = ['sözleşme','ihale','sipariş','yatırım','kapasite art','yeni mağaza','geri alım','temettü','kar payı','kâr payı','rekor','büyüme','artış','onay aldı','teşvik','ortaklık','anlaşma','ihracat','satışlar arttı','net kar arttı','net kâr arttı']
    negative = ['ceza','dava','soruşturma','zarar','iptal','iflas','konkordato','düşüş','azalış','geriledi','faaliyet durdur','üretim durdur','temerrüt','borç yapılandır','net zarar','satışlar düştü']
    if any(k in q for k in negative): return 'Negatif'
    if any(k in q for k in positive): return 'Pozitif'
    return 'Nötr'


def company_news(symbol: str):
    items = []
    try:
        raw = yf.Ticker(symbol + '.IS').news or []
        for n in raw[:10]:
            c = n.get('content', n) if isinstance(n, dict) else {}
            title = c.get('title') or n.get('title') or 'Haber'
            provider = (c.get('provider') or {}) if isinstance(c.get('provider'), dict) else {}
            publisher = provider.get('displayName') or n.get('publisher') or 'Haber kaynağı'
            url = ''
            click = c.get('clickThroughUrl') if isinstance(c.get('clickThroughUrl'), dict) else None
            canonical = c.get('canonicalUrl') if isinstance(c.get('canonicalUrl'), dict) else None
            if click: url = click.get('url', '')
            if not url and canonical: url = canonical.get('url', '')
            if not url: url = n.get('link', '')
            pub = c.get('pubDate') or c.get('displayTime') or n.get('providerPublishTime') or ''
            if isinstance(pub, (int, float)):
                pub = datetime.fromtimestamp(pub).strftime('%d.%m %H:%M')
            elif isinstance(pub, str) and pub:
                pub = pub.replace('T', ' ')[:16]
            items.append({'title': str(title), 'publisher': str(publisher), 'time': str(pub), 'url': str(url), 'effect': classify_news_effect(title)})
    except Exception:
        pass
    return items[:6]


def kap_notifications(symbol: str):
    items = []
    try:
        url = f'https://www.kap.org.tr/tr/search/{quote(symbol)}/1'
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'tr-TR,tr;q=0.9'})
        raw = urlopen(req, timeout=6).read().decode('utf-8', 'ignore')
        patt = re.compile(r'<a[^>]+href=["\']([^"\']*(?:/tr/)?Bildirim/\d+[^"\']*)["\'][^>]*>(.*?)</a>', re.I | re.S)
        seen = set()
        for href, inner in patt.findall(raw):
            m = re.search(r'Bildirim/(\d+)', href, re.I)
            if not m or m.group(1) in seen: continue
            seen.add(m.group(1))
            title = re.sub(r'<[^>]+>', ' ', inner)
            title = html_lib.unescape(re.sub(r'\s+', ' ', title)).strip() or f'{symbol} KAP bildirimi'
            if href.startswith('/'):
                href = 'https://www.kap.org.tr' + href
            elif not href.startswith('http'):
                href = 'https://www.kap.org.tr/' + href.lstrip('/')
            items.append({'title': title[:180], 'url': href, 'effect': classify_news_effect(title)})
            if len(items) >= 6: break
    except Exception:
        pass
    return items
