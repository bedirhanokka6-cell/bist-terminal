import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="BIST Terminal", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

# ---------- GÜVENLİ GİRİŞ ----------
if "APP_PASSWORD" in st.secrets:
    if not st.session_state.get("authenticated", False):
        st.markdown("## 📊 BIST TERMINAL")
        password = st.text_input("Şifre", type="password")
        if st.button("Giriş", use_container_width=True):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Şifre hatalı.")
        st.stop()

# ---------- TASARIM ----------
st.markdown("""
<style>
:root{
 --bg:#07111d; --panel:#0c1a29; --panel2:#0f2031; --line:#1a3044;
 --text:#eef6ff; --muted:#8fa3b8; --green:#18d596; --red:#ff4d5f;
 --yellow:#f5b942; --blue:#2d8cff;
}
.stApp{background:var(--bg); color:var(--text);}
.block-container{padding:0.7rem 1rem 1.5rem 1rem; max-width:1900px;}
[data-testid="stSidebar"]{background:#081522; border-right:1px solid var(--line);}
[data-testid="stSidebar"] > div:first-child{padding-top:0.8rem;}
[data-testid="stSidebar"] .stButton button{
 min-height:35px; border:1px solid #173149; border-radius:7px;
 background:#0c1c2b; color:#e8f1fb; font-size:12px; text-align:left;
 padding:4px 8px;
}
[data-testid="stSidebar"] .stButton button:hover{border-color:#2d8cff;background:#10263a;}
div[data-testid="stMetric"]{
 background:var(--panel); border:1px solid var(--line); border-radius:9px;
 padding:10px 12px;
}
div[data-testid="stMetricLabel"]{font-size:12px;color:var(--muted);}
div[data-testid="stMetricValue"]{font-size:20px;}
div[data-testid="stMetricDelta"]{font-size:12px;}
h1,h2,h3{color:var(--text);}
hr{border-color:var(--line);}
.topbar{
 display:flex;align-items:center;justify-content:space-between;
 background:#091827;border:1px solid var(--line);border-radius:10px;
 padding:12px 16px;margin-bottom:10px;
}
.brand{font-size:24px;font-weight:800;letter-spacing:.2px}
.brand span{color:#2d8cff}
.sub{font-size:12px;color:var(--muted)}
.market-open{color:var(--green);font-weight:700}
.stock-head{
 background:var(--panel);border:1px solid var(--line);border-radius:10px;
 padding:14px 16px;margin-bottom:8px;
}
.stock-symbol{font-size:25px;font-weight:800}
.stock-price{font-size:31px;font-weight:800;margin-left:24px}
.small-muted{font-size:12px;color:var(--muted)}
.panel{
 background:var(--panel);border:1px solid var(--line);border-radius:10px;
 padding:14px;margin-bottom:10px;
}
.panel-title{font-size:16px;font-weight:750;margin-bottom:12px}
.big-state{font-size:30px;font-weight:850;margin:4px 0}
.rowline{
 display:flex;justify-content:space-between;gap:12px;
 padding:7px 0;border-bottom:1px solid rgba(255,255,255,.045);
 font-size:13px;
}
.rowline:last-child{border-bottom:none}
.label{color:var(--muted)}
.green{color:var(--green)} .red{color:var(--red)}
.yellow{color:var(--yellow)} .blue{color:var(--blue)}
.level{display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.comment{font-size:13px;line-height:1.65;color:#d8e3ee}
div[data-testid="stPlotlyChart"]{background:var(--panel);border:1px solid var(--line);border-radius:10px;}
.stTabs [data-baseweb="tab-list"]{gap:6px;}
.stTabs [data-baseweb="tab"]{background:#0c1a29;border-radius:7px;padding:7px 14px;}
</style>
""", unsafe_allow_html=True)

BIST30 = [
    "AKBNK","ASELS","ASTOR","BIMAS","DSTKF","EKGYO","ENKAI","EREGL","FROTO","GARAN",
    "GUBRF","ISCTR","KCHOL","KRDMD","MGROS","PETKM","PGSUS","SAHOL","SASA","SISE",
    "TAVHL","TCELL","THYAO","TOASO","TSKB","TUPRS","ULKER","VAKBN","YKBNK","ZOREN"
]

if "hisse" not in st.session_state:
    st.session_state.hisse = "THYAO"

@st.cache_data(ttl=60)
def daily_watchlist():
    rows=[]
    for s in BIST30:
        try:
            d=yf.download(s+".IS", period="5d", interval="1d",
                          auto_adjust=False, progress=False, threads=False)
            if isinstance(d.columns,pd.MultiIndex):
                d.columns=d.columns.get_level_values(0)
            d=d.dropna()
            if len(d):
                p=float(d["Close"].iloc[-1])
                prev=float(d["Close"].iloc[-2]) if len(d)>1 else p
                ch=(p/prev-1)*100 if prev else 0
                rows.append((s,p,ch))
        except Exception:
            rows.append((s,np.nan,0))
    return rows

@st.cache_data(ttl=30)
def load_chart(symbol, period, interval):
    d=yf.download(symbol+".IS", period=period, interval=interval,
                  auto_adjust=False, progress=False, threads=False)
    if isinstance(d.columns,pd.MultiIndex):
        d.columns=d.columns.get_level_values(0)
    return d.dropna()

def indicators(d):
    x=d.copy()
    c=x["Close"]
    x["EMA20"]=c.ewm(span=20,adjust=False).mean()
    x["EMA50"]=c.ewm(span=50,adjust=False).mean()
    delta=c.diff()
    gain=delta.clip(lower=0).rolling(14).mean()
    loss=(-delta.clip(upper=0)).rolling(14).mean()
    rs=gain/loss.replace(0,np.nan)
    x["RSI"]=100-(100/(1+rs))
    e12=c.ewm(span=12,adjust=False).mean()
    e26=c.ewm(span=26,adjust=False).mean()
    x["MACD"]=e12-e26
    x["MACDS"]=x["MACD"].ewm(span=9,adjust=False).mean()
    return x

def technical_state(a):
    last=a.iloc[-1]
    price=float(last["Close"])
    ema20=float(last["EMA20"]); ema50=float(last["EMA50"])
    rsi=float(last["RSI"]) if pd.notna(last["RSI"]) else 50
    macd=float(last["MACD"]); sig=float(last["MACDS"])
    score=0; reasons=[]
    if price>ema20: score+=1; reasons.append("Fiyat EMA20 üzerinde")
    else: score-=1; reasons.append("Fiyat EMA20 altında")
    if ema20>ema50: score+=1; reasons.append("EMA20, EMA50 üzerinde")
    else: score-=1; reasons.append("EMA20, EMA50 altında")
    if macd>sig: score+=1; reasons.append("MACD pozitif")
    else: score-=1; reasons.append("MACD zayıf")
    if 50<=rsi<=70: score+=1; reasons.append(f"RSI {rsi:.0f}")
    elif rsi>75: score-=1; reasons.append(f"RSI yüksek: {rsi:.0f}")
    elif rsi<40: score-=1; reasons.append(f"RSI düşük: {rsi:.0f}")
    if score>=3: return "GÜÇLENİYOR","#18d596",reasons
    if score<=-2: return "ZAYIFLIYOR","#ff4d5f",reasons
    return "İZLE","#f5b942",reasons

# ---------- ÜST BAR ----------
now=datetime.now().strftime("%d %B %Y %H:%M")
st.markdown(f"""
<div class="topbar">
 <div><div class="brand"><span>▮▮▮</span> BIST TERMINAL</div>
 <div class="sub">Basit • Hızlı • Anlaşılır teknik takip</div></div>
 <div style="text-align:right"><div class="small-muted">{now}</div>
 <div class="market-open">● Piyasa Takip Ekranı</div></div>
</div>
""", unsafe_allow_html=True)

# ---------- SOL BIST 30 ----------
watch=daily_watchlist()
st.sidebar.markdown("## BIST 30")
search=st.sidebar.text_input("Hisse ara", placeholder="THYAO")
st.sidebar.caption("Hisse   •   Fiyat   •   %   •   Durum")

# Sol listede hızlı teknik durum için günlük yön + değişim sade gösterilir.
for s,p,ch in watch:
    if search and search.upper() not in s:
        continue
    if np.isnan(p): continue
    if ch >= 1.0: state="GÜÇLÜ"
    elif ch <= -1.0: state="ZAYIF"
    else: state="İZLE"
    icon="🟢" if ch>0 else ("🔴" if ch<0 else "🟡")
    txt=f"{icon} {s:<5}  {p:,.2f} ₺  {ch:+.2f}%  {state}"
    if st.sidebar.button(txt, key="s_"+s, use_container_width=True):
        st.session_state.hisse=s
        st.rerun()

st.sidebar.divider()
st.sidebar.caption("Grafik dönemi")
period_choice=st.sidebar.radio("Dönem",["1G","5G","1A","3A","1Y"],
                               horizontal=True,label_visibility="collapsed")
settings={
 "1G":("5d","5m"), "5G":("5d","15m"), "1A":("1mo","30m"),
 "3A":("3mo","1h"), "1Y":("1y","1d")
}
period,interval=settings[period_choice]

# ---------- VERİ ----------
symbol=st.session_state.hisse
df=load_chart(symbol,period,interval)
if df.empty:
    st.error("Bu hisse için veri alınamadı.")
    st.stop()

a=indicators(df)
last=a.iloc[-1]
price=float(last["Close"])
prev=float(a["Close"].iloc[-2]) if len(a)>1 else price
change=(price/prev-1)*100 if prev else 0
high=float(a["High"].max()); low=float(a["Low"].min())
volume=float(last["Volume"])
rsi=float(last["RSI"]) if pd.notna(last["RSI"]) else 50
ema20=float(last["EMA20"]); ema50=float(last["EMA50"])
support=float(a["Low"].tail(min(50,len(a))).min())
resistance=float(a["High"].tail(min(50,len(a))).max())
state,state_color,reasons=technical_state(a)

# ---------- BAŞLIK ----------
st.markdown(f"""
<div class="stock-head">
 <span class="stock-symbol">{symbol}</span>
 <span class="stock-price">{price:,.2f} ₺</span>
 <span style="font-size:18px;font-weight:700;color:{'#18d596' if change>=0 else '#ff4d5f'}">
 {change:+.2f}%</span>
 <div class="small-muted">Borsa İstanbul • Teknik takip ekranı</div>
</div>
""", unsafe_allow_html=True)

# ---------- ORTA + SAĞ ----------
main,right=st.columns([4.5,1.35],gap="medium")

with main:
    # Grafik
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,
                      vertical_spacing=.025,row_heights=[.80,.20])
    fig.add_trace(go.Candlestick(
        x=a.index,open=a["Open"],high=a["High"],low=a["Low"],close=a["Close"],
        increasing_line_color="#18d596",increasing_fillcolor="#18d596",
        decreasing_line_color="#ff4d5f",decreasing_fillcolor="#ff4d5f",
        name=symbol,
        hovertemplate="Tarih: %{x}<br>Açılış: %{open:.2f}<br>Yüksek: %{high:.2f}<br>Düşük: %{low:.2f}<br>Kapanış: %{close:.2f}<extra></extra>"
    ),row=1,col=1)
    fig.add_trace(go.Scatter(x=a.index,y=a["EMA20"],name="EMA 20",
                             line=dict(color="#2d8cff",width=1.6)),row=1,col=1)
    fig.add_trace(go.Scatter(x=a.index,y=a["EMA50"],name="EMA 50",
                             line=dict(color="#f5a623",width=1.6)),row=1,col=1)
    colors=np.where(a["Close"]>=a["Open"],"#159f82","#c84b59")
    fig.add_trace(go.Bar(x=a.index,y=a["Volume"],marker_color=colors,
                         name="Hacim",opacity=.7),row=2,col=1)
    fig.add_hline(y=price,line_dash="dot",line_color=state_color,row=1,col=1)
    fig.update_layout(
        height=600,paper_bgcolor="#0c1a29",plot_bgcolor="#0c1a29",
        font=dict(color="#9eb1c5"),margin=dict(l=8,r=55,t=42,b=8),
        xaxis_rangeslider_visible=False,hovermode="x unified",
        legend=dict(orientation="h",y=1.04,x=0,bgcolor="rgba(0,0,0,0)")
    )
    fig.update_xaxes(gridcolor="#172a3c",showgrid=True)
    fig.update_yaxes(gridcolor="#172a3c",side="right",showgrid=True)
    st.plotly_chart(fig,use_container_width=True,
                    config={"displaylogo":False,"scrollZoom":True})

    tabs=st.tabs(["RSI","MACD"])
    with tabs[0]:
        rfig=go.Figure()
        rfig.add_trace(go.Scatter(x=a.index,y=a["RSI"],line=dict(color="#a875ff",width=1.5)))
        rfig.add_hline(y=70,line_dash="dash",line_color="#59697a")
        rfig.add_hline(y=30,line_dash="dash",line_color="#59697a")
        rfig.update_layout(height=180,paper_bgcolor="#0c1a29",plot_bgcolor="#0c1a29",
                           font=dict(color="#9eb1c5"),margin=dict(l=8,r=45,t=10,b=8),
                           showlegend=False)
        rfig.update_xaxes(gridcolor="#172a3c")
        rfig.update_yaxes(gridcolor="#172a3c",side="right",range=[0,100])
        st.plotly_chart(rfig,use_container_width=True,config={"displayModeBar":False})
    with tabs[1]:
        mfig=go.Figure()
        mfig.add_trace(go.Scatter(x=a.index,y=a["MACD"],name="MACD",
                                  line=dict(color="#2d8cff",width=1.4)))
        mfig.add_trace(go.Scatter(x=a.index,y=a["MACDS"],name="Sinyal",
                                  line=dict(color="#f5a623",width=1.4)))
        mfig.update_layout(height=180,paper_bgcolor="#0c1a29",plot_bgcolor="#0c1a29",
                           font=dict(color="#9eb1c5"),margin=dict(l=8,r=45,t=10,b=8),
                           legend=dict(orientation="h"))
        mfig.update_xaxes(gridcolor="#172a3c")
        mfig.update_yaxes(gridcolor="#172a3c",side="right")
        st.plotly_chart(mfig,use_container_width=True,config={"displayModeBar":False})

with right:
    st.markdown(f"""
    <div class="panel">
      <div class="panel-title">Genel Durum</div>
      <div class="big-state" style="color:{state_color}">{state}</div>
      <div class="small-muted">Teknik göstergelerin ortak görünümü</div>
      <br>
      <div class="rowline"><span class="label">Fiyat</span><b>{price:,.2f} ₺</b></div>
      <div class="rowline"><span class="label">Değişim</span><b style="color:{'#18d596' if change>=0 else '#ff4d5f'}">{change:+.2f}%</b></div>
      <div class="rowline"><span class="label">Hacim</span><b>{volume:,.0f}</b></div>
      <div class="rowline"><span class="label">RSI (14)</span><b>{rsi:.1f}</b></div>
      <div class="rowline"><span class="label">EMA 20</span><b>{ema20:.2f}</b></div>
      <div class="rowline"><span class="label">EMA 50</span><b>{ema50:.2f}</b></div>
    </div>

    <div class="panel">
      <div class="panel-title">Teknik Seviyeler</div>
      <div class="rowline"><span class="level"><i class="dot" style="background:#18d596"></i><span class="label">Destek</span></span><b>{support:.2f}</b></div>
      <div class="rowline"><span class="level"><i class="dot" style="background:#ff4d5f"></i><span class="label">Direnç</span></span><b>{resistance:.2f}</b></div>
      <div class="rowline"><span class="label">Dönem Yüksek</span><b>{high:.2f}</b></div>
      <div class="rowline"><span class="label">Dönem Düşük</span><b>{low:.2f}</b></div>
    </div>

    <div class="panel">
      <div class="panel-title">Kısa Teknik Yorum</div>
      <div class="comment">{symbol} için görünüm <b style="color:{state_color}">{state}</b>.
      Destek <b>{support:.2f}</b>, direnç <b>{resistance:.2f}</b>.
      RSI <b>{rsi:.1f}</b>. {"; ".join(reasons[:3])}.</div>
    </div>
    """,unsafe_allow_html=True)

# ---------- ALT ÖZET ----------
c1,c2=st.columns(2,gap="medium")
with c1:
    st.markdown(f"""
    <div class="panel">
      <div class="panel-title">Hızlı Özet</div>
      <div class="comment">
      • Son fiyat: <b>{price:.2f} ₺</b><br>
      • Teknik durum: <b style="color:{state_color}">{state}</b><br>
      • Destek / Direnç: <b>{support:.2f} / {resistance:.2f}</b><br>
      • RSI: <b>{rsi:.1f}</b>
      </div>
    </div>
    """,unsafe_allow_html=True)
with c2:
    st.markdown("""
    <div class="panel">
      <div class="panel-title">Bilgi</div>
      <div class="comment">
      Bu ekran teknik analiz ve takip amaçlıdır. Veriler yfinance üzerinden gelir ve
      Borsa İstanbul için gerçek zamanlı olduğu garanti edilmez. Teknik durum tek başına
      alım-satım talimatı değildir.
      </div>
    </div>
    """,unsafe_allow_html=True)
