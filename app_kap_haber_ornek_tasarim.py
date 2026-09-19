import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import quote
import re
import html as html_lib

st.set_page_config(page_title='BIST Terminal Pro', page_icon='📊', layout='wide', initial_sidebar_state='expanded')

# ---------- GÜVENLİ GİRİŞ ----------
if 'APP_PASSWORD' in st.secrets:
    if not st.session_state.get('authenticated', False):
        st.markdown('## 📊 BIST TERMINAL')
        password = st.text_input('Şifre', type='password')
        if st.button('Giriş', use_container_width=True):
            if password == st.secrets['APP_PASSWORD']:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error('Şifre hatalı.')
        st.stop()

# ---------- TEMA ----------
st.markdown('''
<style>
:root{
 --bg:#06111d; --panel:#0a1a2a; --panel2:#0d2134; --line:#173149;
 --text:#eef6ff; --muted:#7f98b2; --green:#12d6a0; --red:#ff4d61;
 --yellow:#f8bd39; --blue:#2f7cff; --purple:#9b6cff;
}
html,body,[class*="css"]{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;}
.stApp{background:var(--bg);color:var(--text);}
.block-container{padding:.55rem .9rem 1.4rem .9rem;max-width:100% !important;width:100% !important;}
[data-testid="stAppViewContainer"] .main{width:100% !important;max-width:100% !important;}
[data-testid="stMainBlockContainer"]{max-width:100% !important;width:100% !important;}
[data-testid="stHorizontalBlock"]{gap:.7rem !important;}
[data-testid="stSidebar"]{background:#071522;border-right:1px solid var(--line);min-width:285px;max-width:285px;width:285px;}
[data-testid="stSidebar"] > div:first-child{padding-top:.45rem;}
[data-testid="stSidebar"] .stButton button{
 min-height:31px;border:0;border-radius:5px;background:transparent;color:#dce9f6;
 font-size:12px;text-align:left;padding:3px 8px;box-shadow:none;
}
[data-testid="stSidebar"] .stButton button:hover{background:#10345f;color:#fff;}
[data-testid="stSidebar"] hr{border-color:#12304a;margin:.5rem 0;}
[data-testid="stSidebar"] input{background:#0a1b2a !important;color:#fff !important;border:1px solid #173149 !important;}
[data-testid="stSidebar"] label{color:#8ba4be !important;}

.topnav{display:flex;align-items:center;gap:10px;background:#071522;border:1px solid #112c42;border-radius:8px;padding:8px 12px;margin-bottom:10px;}
.logo{font-size:22px;font-weight:900;color:#6e7dff;letter-spacing:.3px;white-space:nowrap;}
.logo b{color:#eef6ff;}
.navitem{font-size:12px;color:#a9bdd1;padding:7px 10px;border-radius:7px;white-space:nowrap;}
.navitem.active{background:#102b49;color:#fff;border:1px solid #174a7a;}
.navspacer{flex:1}.marketclosed{color:#ff4d61;font-weight:800;font-size:12px;}.marketopen{color:#12d6a0;font-weight:800;font-size:12px;}

.company-head{background:linear-gradient(180deg,#081a2a,#071725);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin-bottom:8px;}
.company-title{font-size:21px;font-weight:900;color:#f2f7fc;}.company-sub{font-size:12px;color:#8ca5bf;margin-top:3px;}
.badge{display:inline-flex;align-items:center;justify-content:center;width:48px;height:48px;background:#e61f35;color:white;border-radius:9px;font-size:20px;font-weight:900;margin-right:12px;}

.panel{background:linear-gradient(180deg,#0b1d2d,#091725);border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:8px;}
.panel-title{font-size:13px;font-weight:850;color:#f1f6fb;margin-bottom:8px;}.muted{font-size:11px;color:var(--muted);}
.big-price{font-size:31px;font-weight:900;line-height:1.05;}.state{font-size:21px;font-weight:900;}.rowline{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,.045);font-size:12px;}
.rowline:last-child{border-bottom:0}.label{color:#8ea6bf}.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;}
.comment{font-size:12px;line-height:1.6;color:#d6e2ed;}.scorebar{height:8px;background:#173149;border-radius:12px;overflow:hidden;margin:8px 0 4px;}.scorefill{height:100%;border-radius:12px;}
.metric-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:8px 0;}.mini{background:#0a1b2a;border:1px solid #173149;border-radius:7px;padding:10px 12px;}.mini .k{font-size:10px;color:#7e97af}.mini .v{font-size:15px;font-weight:800;margin-top:2px}

div[data-testid="stPlotlyChart"]{background:#071725;border:1px solid #173149;border-radius:8px;overflow:hidden;}
[data-testid="stDataFrame"]{border:1px solid #173149;border-radius:8px;overflow:hidden;}
.stTabs [data-baseweb="tab-list"]{gap:4px}.stTabs [data-baseweb="tab"]{height:32px;background:#0a1a29;border-radius:6px;padding:4px 11px;color:#a9bdd1}.stTabs [aria-selected="true"]{background:#10345f !important;color:#fff !important;}
button[kind="secondary"]{border:1px solid #173149 !important;background:#0a1b2a !important;color:#dbe8f5 !important;}

/* BIST 30 renkli izleme listesi */
.watch-head{display:grid;grid-template-columns:minmax(82px,1fr) 76px 82px;gap:6px;padding:2px 6px 7px;color:#7f98b2;font-size:11px;align-items:center;}
.watch-row{display:grid;grid-template-columns:minmax(82px,1fr) 76px 82px;gap:6px;align-items:center;text-decoration:none !important;padding:7px 7px;margin:3px 0;border:1px solid #12324b;border-radius:6px;background:#081827;transition:.12s ease;}
.watch-row:hover{background:#0d263b;border-color:#24557b;transform:translateX(1px);}
.watch-row .sym{font-weight:800;font-size:12px;display:flex;align-items:center;white-space:nowrap;overflow:hidden;min-width:0;}
.watch-row .price{text-align:right;font-weight:750;font-size:12px;white-space:nowrap;}
.watch-row .chg{text-align:right;font-weight:850;font-size:12px;border-radius:5px;padding:3px 5px;white-space:nowrap;}
.watch-row.up .sym,.watch-row.up .price,.watch-row.up .chg{color:#12d6a0 !important;}
.watch-row.down .sym,.watch-row.down .price,.watch-row.down .chg{color:#ff4d61 !important;}
.watch-row.flat .sym,.watch-row.flat .price,.watch-row.flat .chg{color:#f8bd39 !important;}
.watch-row.up .chg{background:rgba(18,214,160,.10);}
.watch-row.down .chg{background:rgba(255,77,97,.10);}
.watch-row.flat .chg{background:rgba(248,189,57,.10);}
.watch-arrow{display:inline-block;flex:0 0 12px;width:12px;margin-right:5px;font-size:10px;}

/* Haberler & KAP */
.news-wrap{margin-top:10px;background:linear-gradient(180deg,#0b1d2d,#091725);border:1px solid #173149;border-radius:8px;padding:12px;}
.news-title{font-size:14px;font-weight:850;color:#f1f6fb;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;}
.news-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.news-col{background:#081827;border:1px solid #14324b;border-radius:7px;padding:9px;min-height:170px;}
.news-col-title{font-size:12px;font-weight:850;color:#8fc7ff;margin-bottom:6px;}
.news-item{display:block;text-decoration:none !important;color:#dce8f3 !important;border-top:1px solid rgba(255,255,255,.055);padding:7px 2px;}
.news-item:first-of-type{border-top:0;}
.news-item:hover{color:#fff !important;}
.news-item .n-title{font-size:11px;font-weight:750;line-height:1.35;}
.news-item .n-meta{font-size:9px;color:#7f98b2;margin-top:3px;}
.kap-badge{display:inline-block;background:rgba(47,124,255,.14);color:#7fbbff;border:1px solid rgba(47,124,255,.3);border-radius:4px;padding:2px 5px;font-size:9px;font-weight:800;}
.news-empty{font-size:10px;color:#7f98b2;padding:12px 2px;line-height:1.5;}
.news-table-head{display:grid;grid-template-columns:84px 1fr 92px 78px;gap:7px;color:#7891aa;font-size:9px;padding:3px 2px 6px;border-bottom:1px solid #173149;}
.news-row{display:grid;grid-template-columns:84px 1fr 92px 78px;gap:7px;align-items:center;padding:8px 2px;border-bottom:1px solid rgba(255,255,255,.055);text-decoration:none!important;color:#dce8f3!important;}
.news-row:last-child{border-bottom:0}.news-row:hover{background:rgba(255,255,255,.018)}
.news-date{font-size:9px;color:#8ba4be;white-space:nowrap}.news-headline{font-size:10px;font-weight:750;line-height:1.35}.news-source{font-size:9px;color:#9fb2c5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.effect{display:inline-flex;align-items:center;justify-content:center;border-radius:5px;padding:3px 6px;font-size:9px;font-weight:850;white-space:nowrap}.effect.pos{color:#12d6a0;background:rgba(18,214,160,.12);border:1px solid rgba(18,214,160,.22)}.effect.neg{color:#ff4d61;background:rgba(255,77,97,.12);border:1px solid rgba(255,77,97,.22)}.effect.neu{color:#f8bd39;background:rgba(248,189,57,.12);border:1px solid rgba(248,189,57,.22)}
.news-note{font-size:9px;color:#718aa4;margin-top:7px;line-height:1.35}
@media(max-width:1000px){.news-grid{grid-template-columns:1fr;}}
</style>
''', unsafe_allow_html=True)

BIST30 = [
    'AKBNK','ASELS','ASTOR','BIMAS','DSTKF','EKGYO','ENKAI','EREGL','FROTO','GARAN',
    'GUBRF','ISCTR','KCHOL','KRDMD','MGROS','PETKM','PGSUS','SAHOL','SASA','SISE',
    'TAVHL','TCELL','THYAO','TOASO','TSKB','TUPRS','ULKER','VAKBN','YKBNK','ZOREN'
]

COMPANY_NAMES = {
 'BIMAS':'BİM BİRLEŞİK MAĞAZALAR A.Ş.','THYAO':'TÜRK HAVA YOLLARI A.O.','ASELS':'ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.',
 'TUPRS':'TÜPRAŞ TÜRKİYE PETROL RAFİNERİLERİ A.Ş.','KCHOL':'KOÇ HOLDİNG A.Ş.','AKBNK':'AKBANK T.A.Ş.',
 'GARAN':'TÜRKİYE GARANTİ BANKASI A.Ş.','ISCTR':'TÜRKİYE İŞ BANKASI A.Ş.','YKBNK':'YAPI VE KREDİ BANKASI A.Ş.',
 'TCELL':'TURKCELL İLETİŞİM HİZMETLERİ A.Ş.'
}

if 'hisse' not in st.session_state:
    st.session_state.hisse='BIMAS'

@st.cache_data(ttl=60, show_spinner=False)
def daily_watchlist():
    rows=[]
    for s in BIST30:
        try:
            d=yf.download(s+'.IS',period='5d',interval='1d',auto_adjust=False,progress=False,threads=False)
            if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
            d=d.dropna()
            if len(d):
                p=float(d['Close'].iloc[-1]); prev=float(d['Close'].iloc[-2]) if len(d)>1 else p
                ch=(p/prev-1)*100 if prev else 0
                rows.append((s,p,ch))
        except Exception:
            rows.append((s,np.nan,0.0))
    return rows

@st.cache_data(ttl=30, show_spinner=False)
def load_chart(symbol,period,interval):
    # 1G seçildiğinde son 24 saat/5 gün görünmesin; sadece son işlem günü (bugün/son seans) gelsin.
    req_period = '2d' if period == '1d' and interval in ['5m','15m','30m','60m','1h'] else period
    d=yf.download(symbol+'.IS',period=req_period,interval=interval,auto_adjust=False,progress=False,threads=False)
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    d=d.dropna()
    if d.empty:
        return d
    if period == '1d' and interval in ['5m','15m','30m','60m','1h']:
        idx = d.index
        try:
            dates = idx.tz_convert('Europe/Istanbul').date if getattr(idx, 'tz', None) is not None else idx.date
        except Exception:
            dates = idx.date
        last_date = max(dates)
        d = d[[x == last_date for x in dates]].copy()
    return d

def classify_news_effect(title):
    q=(title or '').lower()
    positive=['sözleşme','ihale','sipariş','yatırım','kapasite art','yeni mağaza','geri alım','temettü','kar payı','kâr payı','rekor','büyüme','artış','onay aldı','teşvik','ortaklık','anlaşma','ihracat','satışlar arttı','net kar arttı','net kâr arttı']
    negative=['ceza','dava','soruşturma','zarar','iptal','iflas','konkordato','düşüş','azalış','geriledi','faaliyet durdur','üretim durdur','temerrüt','borç yapılandır','net zarar','satışlar düştü']
    if any(k in q for k in negative): return 'Negatif','neg','↓'
    if any(k in q for k in positive): return 'Pozitif','pos','↑'
    return 'Nötr','neu','•'

@st.cache_data(ttl=180, show_spinner=False)
def load_company_news(symbol):
    """Yahoo/yfinance üzerinden seçili hisse için son haberleri döndürür."""
    items=[]
    try:
        raw=yf.Ticker(symbol+'.IS').news or []
        for n in raw[:12]:
            c=n.get('content', n) if isinstance(n,dict) else {}
            title=c.get('title') or n.get('title') or 'Haber'
            provider=(c.get('provider') or {}) if isinstance(c.get('provider'),dict) else {}
            publisher=provider.get('displayName') or n.get('publisher') or 'Haber kaynağı'
            url=''
            click=c.get('clickThroughUrl') if isinstance(c.get('clickThroughUrl'),dict) else None
            canonical=c.get('canonicalUrl') if isinstance(c.get('canonicalUrl'),dict) else None
            if click: url=click.get('url','')
            if not url and canonical: url=canonical.get('url','')
            if not url: url=n.get('link','')
            pub=c.get('pubDate') or c.get('displayTime') or n.get('providerPublishTime') or ''
            if isinstance(pub,(int,float)):
                try: pub=datetime.fromtimestamp(pub).strftime('%d.%m %H:%M')
                except Exception: pub=''
            elif isinstance(pub,str) and pub:
                pub=pub.replace('T',' ')[:16]
            items.append({'title':str(title),'publisher':str(publisher),'time':str(pub),'url':str(url)})
    except Exception:
        pass
    return items[:6]

@st.cache_data(ttl=180, show_spinner=False)
def load_kap_notifications(symbol):
    """KAP'ın herkese açık arama sayfasından seçili hisseye ait bildirim bağlantılarını okumayı dener.
    KAP sayfası yapısı değişirse uygulama otomatik olarak KAP arama bağlantısını göstermeye devam eder.
    """
    items=[]
    try:
        url=f'https://www.kap.org.tr/tr/search/{quote(symbol)}/1'
        req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept-Language':'tr-TR,tr;q=0.9'})
        raw=urlopen(req,timeout=6).read().decode('utf-8','ignore')
        # Bildirim sayfalarına giden bağlantıları ve yakınındaki başlık metnini yakala.
        patt=re.compile(r'<a[^>]+href=["\']([^"\']*(?:/tr/)?Bildirim/\d+[^"\']*)["\'][^>]*>(.*?)</a>',re.I|re.S)
        seen=set()
        for href,inner in patt.findall(raw):
            m=re.search(r'Bildirim/(\d+)',href,re.I)
            if not m or m.group(1) in seen: continue
            seen.add(m.group(1))
            title=re.sub(r'<[^>]+>',' ',inner)
            title=html_lib.unescape(re.sub(r'\s+',' ',title)).strip()
            if len(title)<4:
                pos=raw.find(href)
                snippet=raw[max(0,pos-500):pos+700]
                snippet=re.sub(r'<script.*?</script>|<style.*?</style>',' ',snippet,flags=re.I|re.S)
                snippet=html_lib.unescape(re.sub(r'<[^>]+>',' ',snippet))
                snippet=re.sub(r'\s+',' ',snippet).strip()
                title=snippet[-220:] if snippet else f'{symbol} KAP bildirimi'
            if href.startswith('/'):
                href='https://www.kap.org.tr'+href
            elif not href.startswith('http'):
                href='https://www.kap.org.tr/'+href.lstrip('/')
            items.append({'title':title[:180], 'url':href})
            if len(items)>=6: break
    except Exception:
        pass
    return items

def indicators(d):
    x=d.copy(); c=x['Close']
    x['EMA20']=c.ewm(span=20,adjust=False).mean(); x['EMA50']=c.ewm(span=50,adjust=False).mean(); x['EMA200']=c.ewm(span=200,adjust=False).mean()
    delta=c.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    ag=gain.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); al=loss.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    x['RSI']=100-(100/(1+(ag/al.replace(0,np.nan))))
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
    x['MACD']=e12-e26; x['MACDS']=x['MACD'].ewm(span=9,adjust=False).mean(); x['MACD_HIST']=x['MACD']-x['MACDS']
    x['BB_MID']=c.rolling(20).mean(); std=c.rolling(20).std(); x['BB_UPPER']=x['BB_MID']+2*std; x['BB_LOWER']=x['BB_MID']-2*std
    pc=c.shift(1); tr=pd.concat([(x['High']-x['Low']).abs(),(x['High']-pc).abs(),(x['Low']-pc).abs()],axis=1).max(axis=1)
    x['ATR']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean(); x['VOL_MA20']=x['Volume'].rolling(20,min_periods=1).mean(); x['VOL_RATIO']=x['Volume']/x['VOL_MA20'].replace(0,np.nan)
    return x

def technical_state(a):
    l=a.iloc[-1]; price=float(l['Close']); e20=float(l['EMA20']); e50=float(l['EMA50']); e200=float(l['EMA200']) if pd.notna(l['EMA200']) else np.nan
    rsi=float(l['RSI']) if pd.notna(l['RSI']) else 50; macd=float(l['MACD']) if pd.notna(l['MACD']) else 0; sig=float(l['MACDS']) if pd.notna(l['MACDS']) else 0; hist=float(l['MACD_HIST']) if pd.notna(l['MACD_HIST']) else 0
    vr=a.loc[a['Volume']>0,'VOL_RATIO'].dropna(); vol_ratio=float(vr.iloc[-1]) if len(vr) else 1.0; bb=float(l['BB_MID']) if pd.notna(l['BB_MID']) else np.nan
    pts=0.0; reasons=[]
    if price>e20: pts+=1.5; reasons.append('Fiyat EMA20 üzerinde')
    else: reasons.append('Fiyat EMA20 altında')
    if e20>e50: pts+=1.5; reasons.append('EMA20, EMA50 üzerinde')
    else: reasons.append('EMA20, EMA50 altında')
    if pd.notna(e200) and price>e200: pts+=1.5; reasons.append('Fiyat EMA200 üzerinde')
    elif pd.notna(e200): reasons.append('Fiyat EMA200 altında')
    else: pts+=.75; reasons.append('EMA200 için veri sınırlı')
    if macd>sig: pts+=1.5; reasons.append('MACD pozitif kesişimde')
    else: reasons.append('MACD sinyalin altında')
    if 45<=rsi<=65: pts+=1.5; reasons.append(f'RSI dengeli: {rsi:.1f}')
    elif 35<=rsi<=75: pts+=.75; reasons.append(f'RSI sınır bölgede: {rsi:.1f}')
    else: pts+=.25; reasons.append(f'RSI uç bölgede: {rsi:.1f}')
    if vol_ratio>=1.2: pts+=1.0; reasons.append(f'Hacim teyidi güçlü: {vol_ratio:.2f}x')
    elif vol_ratio>=.8: pts+=.5; reasons.append(f'Hacim normal: {vol_ratio:.2f}x')
    else: reasons.append(f'Hacim zayıf: {vol_ratio:.2f}x')
    if pd.notna(bb) and price>=bb: pts+=1.0; reasons.append('Bollinger orta bandı üzerinde')
    elif pd.notna(bb): pts+=.5; reasons.append('Bollinger orta bandı altında')
    else: pts+=.5
    if hist>0: pts+=.5; reasons.append('MACD histogramı pozitif')
    score=max(0,min(10,pts))
    if score>=7.5: return 'GÜÇLÜ POZİTİF','#12d6a0',reasons,score
    if score>=5.5: return 'POZİTİF','#58c7ff',reasons,score
    if score>=4.0: return 'NÖTR / İZLE','#f8bd39',reasons,score
    return 'ZAYIF','#ff4d61',reasons,score

@st.cache_data(ttl=300, show_spinner=False)
def scan_bist30():
    rows=[]
    for s in BIST30:
        try:
            d=yf.download(s+'.IS',period='1y',interval='1d',auto_adjust=False,progress=False,threads=False)
            if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
            d=d.dropna()
            if len(d)<30: continue
            a=indicators(d); l=a.iloc[-1]; p=a.iloc[-2]; price=float(l['Close']); prev=float(p['Close']); ch=(price/prev-1)*100 if prev else 0
            state,color,reasons,score=technical_state(a)
            vr=float(l['VOL_RATIO']) if pd.notna(l['VOL_RATIO']) else np.nan; rsi=float(l['RSI']) if pd.notna(l['RSI']) else np.nan
            e20=float(l['EMA20']); e50=float(l['EMA50']); e200=float(l['EMA200']); macd=float(l['MACD']); sig=float(l['MACDS'])
            trend='↑' if price>e20>e50 and price>e200 else ('↓' if price<e20<e50 and price<e200 else '→')
            support=float(a['Low'].tail(50).min()); resistance=float(a['High'].tail(50).max())
            rows.append({'Hisse':s,'Fiyat':round(price,2),'Değişim %':round(ch,2),'Teknik Skor':round(score,1),'RSI':round(rsi,1),'Hacim Oranı':round(vr,2) if pd.notna(vr) else np.nan,'EMA Trend':trend,'MACD':'Pozitif' if macd>sig else 'Negatif','Destek':round(support,2),'Direnç':round(resistance,2),'Durum':state})
        except Exception: pass
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(['Teknik Skor','Değişim %'],ascending=[False,False]).reset_index(drop=True)

# ---------- SIDEBAR ----------
# Renkli satıra tıklanınca hisseyi seç
try:
    qp_hisse = st.query_params.get('hisse')
    if qp_hisse in BIST30 and qp_hisse != st.session_state.hisse:
        st.session_state.hisse = qp_hisse
except Exception:
    pass

st.sidebar.markdown('<div class="logo">▮▮▮ <b>BIST TERMINAL</b></div>', unsafe_allow_html=True)
st.sidebar.markdown('### BIST 30')
search=st.sidebar.text_input('Ara',placeholder='Hisse ara...',label_visibility='collapsed')
watch=daily_watchlist()
st.sidebar.markdown('<div class="watch-head"><span>Hisse</span><span style="text-align:right">Fiyat</span><span style="text-align:right">Değişim</span></div>', unsafe_allow_html=True)
rows_html=[]
for s,p,ch in watch:
    if np.isnan(p):
        continue
    if search and search.upper() not in s:
        continue
    cls='up' if ch>0 else ('down' if ch<0 else 'flat')
    arrow='▲' if ch>0 else ('▼' if ch<0 else '•')
    rows_html.append(
        f'<a class="watch-row {cls}" href="?hisse={s}" target="_self">'
        f'<span class="sym"><span class="watch-arrow">{arrow}</span>{s}</span>'
        f'<span class="price">{p:,.2f}</span>'
        f'<span class="chg">{ch:+.2f}%</span>'
        f'</a>'
    )
st.sidebar.markdown(''.join(rows_html), unsafe_allow_html=True)
st.sidebar.divider()
st.sidebar.caption('Veriler yfinance üzerinden alınır. Gerçek zamanlı garanti edilmez.')

# ---------- ÜST NAV ----------
now=datetime.now().strftime('%d %B %Y  %H:%M')
st.markdown(f'''<div class="topnav"><div class="logo">▮▮▮ <b>BIST TERMINAL</b></div><div class="navitem">⌂ Ana Sayfa</div><div class="navitem active">⌁ Hisse Analizi</div><div class="navitem">⚑ BIST 30 Tarayıcı</div><div class="navitem">▤ Haberler (KAP)</div><div class="navitem">☆ Takip Listesi</div><div class="navitem">⚙ Ayarlar</div><div class="navspacer"></div><div class="muted">{now}</div><div class="marketclosed">● Piyasa Takip</div></div>''',unsafe_allow_html=True)

symbol=st.session_state.hisse
period_choice=st.segmented_control('Periyot',['1G','5G','1A','3A','6A','1Y','2Y'],default='1A',label_visibility='collapsed') if hasattr(st,'segmented_control') else st.radio('Periyot',['1G','5G','1A','3A','6A','1Y','2Y'],horizontal=True,label_visibility='collapsed')
settings={'1G':('1d','5m'),'5G':('5d','15m'),'1A':('1mo','30m'),'3A':('3mo','1h'),'6A':('6mo','1d'),'1Y':('1y','1d'),'2Y':('2y','1d')}
period,interval=settings[period_choice]
df=load_chart(symbol,period,interval)
if df.empty:
    st.error('Bu hisse için veri alınamadı.'); st.stop()
a=indicators(df); l=a.iloc[-1]; price=float(l['Close']); prev=float(a['Close'].iloc[-2]) if len(a)>1 else price; change=(price/prev-1)*100 if prev else 0
open_=float(l['Open']); high_=float(l['High']); low_=float(l['Low']); close_=price
rsi=float(l['RSI']) if pd.notna(l['RSI']) else 50; e20=float(l['EMA20']); e50=float(l['EMA50']); e200=float(l['EMA200']) if pd.notna(l['EMA200']) else np.nan
atr=float(l['ATR']) if pd.notna(l['ATR']) else np.nan; vol=float(a.loc[a['Volume']>0,'Volume'].iloc[-1]) if len(a.loc[a['Volume']>0]) else 0; vr=float(a.loc[a['Volume']>0,'VOL_RATIO'].dropna().iloc[-1]) if len(a.loc[a['Volume']>0,'VOL_RATIO'].dropna()) else 1.0
support=float(a['Low'].tail(min(50,len(a))).min()); resistance=float(a['High'].tail(min(50,len(a))).max()); high=float(a['High'].max()); low=float(a['Low'].min())
state,state_color,reasons,score=technical_state(a); cname=COMPANY_NAMES.get(symbol,f'{symbol} - Borsa İstanbul')

st.markdown(f'''<div class="company-head"><div style="display:flex;align-items:center"><div class="badge">{symbol[:3]}</div><div><div class="company-title">{cname} ({symbol})</div><div class="company-sub">{symbol}.IS &nbsp;◆&nbsp; Borsa İstanbul &nbsp;◆&nbsp; Teknik Analiz</div></div></div></div>''',unsafe_allow_html=True)

main,right=st.columns([4.65,1.55],gap='small')

with main:
    # ======================================================
    # ÜST: SADE MUM GRAFİK
    # ======================================================
    price_fig = go.Figure()

    price_fig.add_trace(
        go.Candlestick(
            x=a.index,
            open=a["Open"],
            high=a["High"],
            low=a["Low"],
            close=a["Close"],
            name=symbol,
            increasing_line_color="#18d596",
            increasing_fillcolor="#18d596",
            decreasing_line_color="#ff4d5f",
            decreasing_fillcolor="#ff4d5f",
            showlegend=False,
            hovertemplate=(
                "Tarih: %{x}<br>"
                "Açılış: %{open:.2f}<br>"
                "Yüksek: %{high:.2f}<br>"
                "Düşük: %{low:.2f}<br>"
                "Kapanış: %{close:.2f}<extra></extra>"
            )
        )
    )

    # Grafiği sade tutmak için sadece iki temel ortalama
    price_fig.add_trace(
        go.Scatter(
            x=a.index, y=a["EMA20"],
            name="EMA 20",
            line=dict(color="#2d8cff", width=1.5)
        )
    )
    price_fig.add_trace(
        go.Scatter(
            x=a.index, y=a["EMA50"],
            name="EMA 50",
            line=dict(color="#f5a623", width=1.5)
        )
    )

    price_fig.add_hline(
        y=price,
        line_dash="dot",
        line_color="#39b8ff",
        line_width=1.0
    )

    price_fig.update_layout(
        height=440,
        paper_bgcolor="#0c1a29",
        plot_bgcolor="#0c1a29",
        font=dict(color="#c8d4df", size=11),
        margin=dict(l=8, r=12, t=28, b=8),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        dragmode="pan",
        legend=dict(
            orientation="h",
            y=1.04,
            x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)"
        )
    )

    price_fig.update_xaxes(
        gridcolor="#172a3c",
        showgrid=True,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor="#3d5a73",
        spikethickness=1,
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(pattern="hour", bounds=[18, 10])
        ]
    )
    price_fig.update_yaxes(
        gridcolor="#172a3c",
        showgrid=True,
        side="right",
        zeroline=False
    )

    st.plotly_chart(
        price_fig,
        use_container_width=True,
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"]
        }
    )

    # ======================================================
    # ALT: SEÇİLEBİLİR ANALİZ GRAFİĞİ
    # ======================================================
    analysis_choice = st.segmented_control(
        "Analiz",
        ["RSI", "MACD", "Hacim", "Bollinger", "EMA"],
        default="RSI",
        label_visibility="collapsed",
        key="chart_analysis_choice"
    ) if hasattr(st, "segmented_control") else st.radio(
        "Analiz",
        ["RSI", "MACD", "Hacim", "Bollinger", "EMA"],
        horizontal=True,
        label_visibility="collapsed",
        key="chart_analysis_choice"
    )

    analysis_fig = go.Figure()

    if analysis_choice == "RSI":
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["RSI"], name="RSI (14)",
            line=dict(color="#9b6cff", width=1.8)
        ))
        analysis_fig.add_hline(y=70, line_dash="dash", line_color="#59697a")
        analysis_fig.add_hline(y=30, line_dash="dash", line_color="#59697a")
        analysis_fig.update_yaxes(range=[0, 100])

    elif analysis_choice == "MACD":
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["MACD"], name="MACD",
            line=dict(color="#2d8cff", width=1.6)
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["MACDS"], name="Sinyal",
            line=dict(color="#f5a623", width=1.6)
        ))
        if "MACD_HIST" in a.columns:
            macd_colors = np.where(a["MACD_HIST"] >= 0, "#159f82", "#c84b59")
            analysis_fig.add_trace(go.Bar(
                x=a.index, y=a["MACD_HIST"], name="Histogram",
                marker_color=macd_colors, opacity=0.65
            ))
        analysis_fig.add_hline(y=0, line_color="#59697a", line_width=1)

    elif analysis_choice == "Hacim":
        vol_colors = np.where(a["Close"] >= a["Open"], "#159f82", "#c84b59")
        analysis_fig.add_trace(go.Bar(
            x=a.index, y=a["Volume"], name="Hacim",
            marker_color=vol_colors, opacity=0.8
        ))
        if "VOL_MA20" in a.columns:
            analysis_fig.add_trace(go.Scatter(
                x=a.index, y=a["VOL_MA20"], name="20 Periyot Ort.",
                line=dict(color="#f5a623", width=1.4)
            ))

    elif analysis_choice == "Bollinger":
        analysis_fig.add_trace(go.Candlestick(
            x=a.index, open=a["Open"], high=a["High"], low=a["Low"], close=a["Close"],
            name=symbol,
            increasing_line_color="#18d596", increasing_fillcolor="#18d596",
            decreasing_line_color="#ff4d5f", decreasing_fillcolor="#ff4d5f",
            showlegend=False
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["BB_UPPER"], name="BB Üst",
            line=dict(color="#3d73c9", width=1)
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["BB_MID"], name="BB Orta",
            line=dict(color="#8fa3b8", width=1, dash="dot")
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["BB_LOWER"], name="BB Alt",
            line=dict(color="#3d73c9", width=1),
            fill="tonexty", fillcolor="rgba(61,115,201,0.07)"
        ))
        analysis_fig.update_layout(xaxis_rangeslider_visible=False)

    elif analysis_choice == "EMA":
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["Close"], name="Fiyat",
            line=dict(color="#dce8f3", width=1.2)
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["EMA20"], name="EMA 20",
            line=dict(color="#2d8cff", width=1.6)
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["EMA50"], name="EMA 50",
            line=dict(color="#f5a623", width=1.6)
        ))
        analysis_fig.add_trace(go.Scatter(
            x=a.index, y=a["EMA200"], name="EMA 200",
            line=dict(color="#9b59ff", width=1.5, dash="dot")
        ))

    analysis_fig.update_layout(
        height=280,
        paper_bgcolor="#0c1a29",
        plot_bgcolor="#0c1a29",
        font=dict(color="#c8d4df", size=11),
        margin=dict(l=8, r=12, t=20, b=8),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            y=1.05,
            x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)"
        )
    )
    analysis_fig.update_xaxes(
        gridcolor="#172a3c",
        showgrid=True,
        rangebreaks=[
            dict(bounds=["sat", "mon"]),
            dict(pattern="hour", bounds=[18, 10])
        ]
    )
    analysis_fig.update_yaxes(
        gridcolor="#172a3c",
        showgrid=True,
        side="right",
        zeroline=False
    )

    st.plotly_chart(
        analysis_fig,
        use_container_width=True,
        config={"displaylogo": False, "scrollZoom": True}
    )

    # ======================================================
    # HABERLER & KAP BİLDİRİMLERİ — yalnızca orta boş alan
    # ======================================================
    company_news=load_company_news(symbol)
    kap_items=load_kap_notifications(symbol)
    kap_search=f"https://www.kap.org.tr/tr/search/{symbol}/1"

    kap_rows=[]
    for item in kap_items[:5]:
        title=item.get("title","KAP bildirimi")
        eff,eff_cls,eff_icon=classify_news_effect(title)
        kap_rows.append(
            f'<a class="news-row" href="{html_lib.escape(item.get("url",kap_search), quote=True)}" target="_blank">'
            f'<span class="news-date">KAP</span>'
            f'<span class="news-headline">{html_lib.escape(title)}</span>'
            f'<span class="news-source">Resmî KAP</span>'
            f'<span class="effect {eff_cls}">{eff_icon} {eff}</span></a>'
        )
    if not kap_rows:
        kap_rows.append(f'<div class="news-empty">KAP bildirimleri otomatik okunamadı. <a href="{kap_search}" target="_blank" style="color:#7fbbff">{symbol} KAP sayfasını aç →</a></div>')

    news_rows=[]
    for item in company_news[:5]:
        safe_url=html_lib.escape(item.get("url","") or "#", quote=True)
        title=item.get("title","Haber")
        publisher=html_lib.escape(item.get("publisher","") or "Haber")
        tm=html_lib.escape(item.get("time","") or "—")
        eff,eff_cls,eff_icon=classify_news_effect(title)
        news_rows.append(
            f'<a class="news-row" href="{safe_url}" target="_blank">'
            f'<span class="news-date">{tm}</span>'
            f'<span class="news-headline">{html_lib.escape(title)}</span>'
            f'<span class="news-source">{publisher}</span>'
            f'<span class="effect {eff_cls}">{eff_icon} {eff}</span></a>'
        )
    if not news_rows:
        news_rows.append('<div class="news-empty">Bu hisse için şu anda haber bulunamadı veya haber kaynağına ulaşılamadı.</div>')

    head='<div class="news-table-head"><span>Zaman</span><span>Başlık</span><span>Kaynak</span><span>Etki</span></div>'
    st.markdown(
        f'<div class="news-wrap">'
        f'<div class="news-title"><span>📰 Haberler & KAP Bildirimleri</span><span class="muted">{symbol}</span></div>'
        f'<div class="news-grid">'
        f'<div class="news-col"><div class="news-col-title">📣 KAP Bildirimleri</div>{head}{"".join(kap_rows)}</div>'
        f'<div class="news-col"><div class="news-col-title">📰 Şirket Haberleri</div>{head}{"".join(news_rows)}</div>'
        f'</div><div class="news-note">Etki etiketi haber başlığındaki anahtar kelimelerden üretilen basit bir sınıflandırmadır; fiyat hareketi garantisi veya alım-satım sinyali değildir.</div></div>',
        unsafe_allow_html=True
    )

with right:
    st.markdown(f'''<div class="panel"><div class="panel-title">{symbol}</div><div class="muted">{cname}</div><div class="big-price" style="margin-top:8px">{price:,.2f} ₺</div><div style="font-size:16px;font-weight:800;color:{'#12d6a0' if change>=0 else '#ff4d61'}">{change:+.2f}%</div><div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px"><span class="muted">Genel Durum</span><span class="state" style="color:{state_color}">{state}</span></div><div class="scorebar"><div class="scorefill" style="width:{score*10:.0f}%;background:{state_color}"></div></div><div style="display:flex;justify-content:space-between;font-size:12px"><span class="muted">Teknik Skor</span><b style="color:{state_color}">{score:.1f} / 10</b></div></div>''',unsafe_allow_html=True)
    st.markdown(f'''<div class="panel"><div class="panel-title">Piyasa Verileri</div><div class="rowline"><span class="label">Açılış</span><b>{open_:.2f}</b></div><div class="rowline"><span class="label">Yüksek</span><b>{high_:.2f}</b></div><div class="rowline"><span class="label">Düşük</span><b>{low_:.2f}</b></div><div class="rowline"><span class="label">Kapanış</span><b>{close_:.2f}</b></div><div class="rowline"><span class="label">Hacim</span><b>{vol/1_000_000:.2f}M</b></div><div class="rowline"><span class="label">Hacim Ort.</span><b>{vr:.2f}x</b></div><div class="rowline"><span class="label">RSI (14)</span><b>{rsi:.1f}</b></div><div class="rowline"><span class="label">EMA 20</span><b>{e20:.2f}</b></div><div class="rowline"><span class="label">EMA 50</span><b>{e50:.2f}</b></div><div class="rowline"><span class="label">EMA 200</span><b>{'—' if np.isnan(e200) else f'{e200:.2f}'}</b></div><div class="rowline"><span class="label">ATR (14)</span><b>{'—' if np.isnan(atr) else f'{atr:.2f}'}</b></div></div>''',unsafe_allow_html=True)
    st.markdown(f'''<div class="panel"><div class="panel-title">Teknik Seviyeler</div><div class="rowline"><span><i class="dot" style="background:#12d6a0"></i><span class="label">Destek</span></span><b>{support:.2f}</b></div><div class="rowline"><span><i class="dot" style="background:#ff4d61"></i><span class="label">Direnç</span></span><b>{resistance:.2f}</b></div><div class="rowline"><span class="label">Dönem Yüksek</span><b>{high:.2f}</b></div><div class="rowline"><span class="label">Dönem Düşük</span><b>{low:.2f}</b></div></div>''',unsafe_allow_html=True)
    st.markdown(f'''<div class="panel"><div class="panel-title">Kısa Teknik Yorum</div><div class="comment">{symbol} için görünüm <b style="color:{state_color}">{state}</b>.<br>{'<br>'.join('• '+x for x in reasons[:4])}</div></div>''',unsafe_allow_html=True)
    up_level=max(resistance,price+(atr if pd.notna(atr) else 0)); down_level=min(support,price-(atr if pd.notna(atr) else 0))
    st.markdown(f'''<div class="panel"><div class="panel-title">Olası Senaryolar</div><div class="comment"><span style="color:#12d6a0">↗</span> {up_level:.2f} üzeri kalıcılıkta yukarı momentum güçlenebilir.<br><br><span style="color:#ff4d61">↘</span> {down_level:.2f} altı kapanışta satış baskısı artabilir.</div></div>''',unsafe_allow_html=True)

# Mini finansal kartlar (yfinance fundamental alanları çoğu zaman eksik olduğu için yalnızca fiyat/teknik ölçüler)
st.markdown(f'''<div class="metric-grid"><div class="mini"><div class="k">Teknik Skor</div><div class="v">{score:.1f}/10</div></div><div class="mini"><div class="k">RSI</div><div class="v">{rsi:.1f}</div></div><div class="mini"><div class="k">Hacim Oranı</div><div class="v">{vr:.2f}x</div></div><div class="mini"><div class="k">ATR</div><div class="v">{'—' if np.isnan(atr) else f'{atr:.2f}'}</div></div><div class="mini"><div class="k">Destek</div><div class="v">{support:.2f}</div></div><div class="mini"><div class="k">Direnç</div><div class="v">{resistance:.2f}</div></div></div>''',unsafe_allow_html=True)

st.markdown('### BIST 30 Fırsat Tarayıcı')
fc1,fc2,fc3=st.columns([1,1,5])
with fc1: min_score=st.selectbox('Minimum Skor',['4+','5+','6+','7+','8+'],index=2)
with fc2: only_volume=st.checkbox('Sadece hacimli',value=False)
with fc3:
    if st.button('Yenile'):
        scan_bist30.clear()
with st.spinner('BIST 30 taranıyor...'):
    scanner=scan_bist30()
if scanner.empty:
    st.warning('Tarayıcı verisi alınamadı.')
else:
    threshold=float(min_score.replace('+','')); out=scanner[scanner['Teknik Skor']>=threshold].copy()
    if only_volume: out=out[out['Hacim Oranı']>=1.0]
    st.dataframe(out,use_container_width=True,hide_index=True,column_config={
        'Fiyat':st.column_config.NumberColumn(format='%.2f ₺'),
        'Değişim %':st.column_config.NumberColumn(format='%+.2f%%'),
        'Teknik Skor':st.column_config.ProgressColumn(min_value=0,max_value=10,format='%.1f'),
        'Hacim Oranı':st.column_config.NumberColumn(format='%.2fx'),
        'Destek':st.column_config.NumberColumn(format='%.2f'),'Direnç':st.column_config.NumberColumn(format='%.2f')
    })

st.caption('Teknik analiz ve takip amaçlıdır. Veriler yfinance üzerinden gelir; Borsa İstanbul için gerçek zamanlı olduğu garanti edilmez. Teknik göstergeler tek başına alım-satım talimatı değildir.')
