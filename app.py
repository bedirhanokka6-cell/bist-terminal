import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
import feedparser
import urllib.parse


# =========================================================
# SAYFA
# =========================================================

st.set_page_config(
    page_title="BIST Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 15 saniyede bir yenile
st_autorefresh(
    interval=15000,
    key="bist_refresh"
)


# =========================================================
# TASARIM
# =========================================================

st.markdown("""
<style>

.stApp {
    background-color: #0b111c;
}

.block-container {
    padding-top: 1rem;
    max-width: 1900px;
}

[data-testid="stSidebar"] {
    background-color: #0d1623;
    border-right: 1px solid #1e2938;
}

div[data-testid="stMetric"] {
    background-color: #101a28;
    border: 1px solid #223044;
    border-radius: 8px;
    padding: 12px;
}

.stButton button {
    border-radius: 6px;
    border: 1px solid #223044;
    background-color: #101a28;
    color: white;
}

.stButton button:hover {
    border-color: #2962ff;
}

</style>
""", unsafe_allow_html=True)


# =========================================================
# HİSSELER
# =========================================================

HISSELER = [
    "ASELS",
    "THYAO",
    "TUPRS",
    "KCHOL",
    "SAHOL",
    "BIMAS",
    "AKBNK",
    "GARAN",
    "YKBNK",
    "ISCTR",
    "SISE",
    "FROTO",
    "TOASO",
    "TCELL",
    "PGSUS",
    "PETKM",
    "ENKAI",
    "EKGYO",
    "ARCLK",
    "HEKTS"
]


# =========================================================
# SEÇİLİ HİSSE
# =========================================================

if "hisse" not in st.session_state:
    st.session_state.hisse = "SAHOL"


# =========================================================
# WATCHLIST VERİLERİ
# =========================================================

@st.cache_data(ttl=30)
def watchlist_al():

    tickers = " ".join(
        [x + ".IS" for x in HISSELER]
    )

    try:

        data = yf.download(
            tickers,
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True
        )

        sonuc = []

        for hisse in HISSELER:

            ticker = hisse + ".IS"

            try:

                d = data[ticker].dropna()

                if len(d) == 0:
                    continue

                fiyat = float(
                    d["Close"].iloc[-1]
                )

                if len(d) >= 2:

                    onceki = float(
                        d["Close"].iloc[-2]
                    )

                else:

                    onceki = fiyat

                degisim = (
                    ((fiyat - onceki) / onceki) * 100
                    if onceki != 0
                    else 0
                )

                sonuc.append({
                    "symbol": hisse,
                    "price": fiyat,
                    "change": degisim
                })

            except:
                pass

        return sonuc

    except:
        return []


watchlist = watchlist_al()


# =========================================================
# SOL PANEL
# =========================================================

st.sidebar.markdown("## 📊 BIST Terminal")

st.sidebar.caption(
    "Borsa İstanbul Takip Ekranı"
)


arama = st.sidebar.text_input(
    "🔎 Hisse ara",
    placeholder="ASELS, THYAO..."
)


st.sidebar.markdown(
    "**Sembol &nbsp;&nbsp;&nbsp;&nbsp; Fiyat / Değişim**"
)


for item in watchlist:

    symbol = item["symbol"]

    if arama and arama.upper() not in symbol:
        continue

    price = item["price"]
    change = item["change"]

    if change >= 0:

        simge = "🟢"

        change_text = (
            f"+%{change:.2f}"
        )

    else:

        simge = "🔴"

        change_text = (
            f"%{change:.2f}"
        )

    button_text = (
        f"{simge} {symbol}   "
        f"{price:.2f} ₺   "
        f"{change_text}"
    )

    if st.sidebar.button(
        button_text,
        key="btn_" + symbol,
        use_container_width=True
    ):

        st.session_state.hisse = symbol
        st.rerun()


hisse = st.session_state.hisse


# =========================================================
# DÖNEM
# =========================================================

st.sidebar.divider()

st.sidebar.markdown("### Grafik Dönemi")

donem = st.sidebar.radio(
    "Dönem seç",
    [
        "1G",
        "1H",
        "1A",
        "1Y"
    ],
    horizontal=True,
    label_visibility="collapsed"
)


# =========================================================
# DÖNEM AYARLARI
# =========================================================

DONEM = {

    "1G": {
        "period": "5d",
        "interval": "5m"
    },

    "1H": {
        "period": "1mo",
        "interval": "30m"
    },

    "1A": {
        "period": "3mo",
        "interval": "1h"
    },

    "1Y": {
        "period": "1y",
        "interval": "1d"
    }
}


ayar = DONEM[donem]


# =========================================================
# GRAFİK VERİSİ
# =========================================================

@st.cache_data(ttl=10)
def veri_al(symbol, period, interval):

    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False
    )

    if isinstance(
        df.columns,
        pd.MultiIndex
    ):

        df.columns = (
            df.columns
            .get_level_values(0)
        )

    return df.dropna()


try:

    df = veri_al(
        hisse + ".IS",
        ayar["period"],
        ayar["interval"]
    )

except Exception as e:

    st.error(
        f"Veri alınamadı: {e}"
    )

    st.stop()


if df.empty:

    st.error(
        "Bu hisse için veri bulunamadı."
    )

    st.stop()


# =========================================================
# 1 GÜN
# =========================================================

if donem == "1G":

    son_gun = df.index[-1].date()

    df = df[
        df.index.date == son_gun
    ].copy()


# =========================================================
# 1 HAFTA
# =========================================================

elif donem == "1H":

    df = df.tail(100).copy()


# =========================================================
# 1 AY
# =========================================================

elif donem == "1A":

    df = df.tail(180).copy()


# =========================================================
# 1 YIL
# =========================================================

else:

    df = df.tail(260).copy()


# =========================================================
# FİYATLAR
# =========================================================

fiyat = float(
    df["Close"].iloc[-1]
)

onceki = (
    float(df["Close"].iloc[-2])
    if len(df) > 1
    else fiyat
)

degisim_tl = (
    fiyat - onceki
)

degisim = (
    (degisim_tl / onceki) * 100
    if onceki != 0
    else 0
)


yuksek = float(
    df["High"].max()
)

dusuk = float(
    df["Low"].min()
)

hacim = float(
    df["Volume"].sum()
)


# =========================================================
# HACİM FORMAT
# =========================================================

def hacim_yaz(value):

    if value >= 1_000_000_000:

        return (
            f"{value / 1_000_000_000:.2f} Mr"
        )

    elif value >= 1_000_000:

        return (
            f"{value / 1_000_000:.2f} Mn"
        )

    elif value >= 1_000:

        return (
            f"{value / 1_000:.1f} B"
        )

    return str(int(value))


# =========================================================
# BAŞLIK
# =========================================================

c1, c2 = st.columns(
    [4, 1]
)


with c1:

    st.markdown(
        f"# {hisse} / TRY"
    )

    renk = (
        "#00c896"
        if degisim >= 0
        else "#ff4655"
    )

    st.markdown(
        f"""
        <div style="
            font-size:30px;
            font-weight:700;
        ">
            {fiyat:.2f} ₺
        </div>

        <div style="
            color:{renk};
            font-size:17px;
        ">
            {degisim_tl:+.2f} ₺
            ({degisim:+.2f}%)
        </div>
        """,
        unsafe_allow_html=True
    )


with c2:

    st.caption(
        "🟡 SON ALINAN VERİ"
    )

    try:

        st.write(
            df.index[-1]
            .strftime(
                "%d.%m.%Y %H:%M"
            )
        )

    except:

        pass


# =========================================================
# METRİKLER
# =========================================================

m1, m2, m3, m4 = st.columns(4)


m1.metric(
    "Son Fiyat",
    f"{fiyat:.2f} ₺"
)


m2.metric(
    "En Yüksek",
    f"{yuksek:.2f} ₺"
)


m3.metric(
    "En Düşük",
    f"{dusuk:.2f} ₺"
)


m4.metric(
    "Hacim",
    hacim_yaz(hacim)
)


# =========================================================
# BOŞLUKSUZ X EKSENİ
# =========================================================

grafik = df.copy()

grafik["x"] = np.arange(
    len(grafik)
)


# =========================================================
# TARİH / SAAT
# =========================================================

if donem == "1Y":

    grafik["tarih"] = [
        x.strftime("%d.%m.%Y")
        for x in grafik.index
    ]

else:

    grafik["tarih"] = [
        x.strftime(
            "%d.%m.%Y %H:%M"
        )
        for x in grafik.index
    ]


# =========================================================
# GRAFİK
# =========================================================

fig = make_subplots(

    rows=2,

    cols=1,

    shared_xaxes=True,

    vertical_spacing=0.02,

    row_heights=[
        0.80,
        0.20
    ]
)


# =========================================================
# HOVER METİNLERİ
# =========================================================

hover_text = []


for i, row in grafik.iterrows():

    hover_text.append(

        "<b>"
        + row["tarih"]
        + "</b>"

        + "<br><br>"

        + "Açılış: "
        + f"{row['Open']:.2f} ₺"

        + "<br>"

        + "Yüksek: "
        + f"{row['High']:.2f} ₺"

        + "<br>"

        + "Düşük: "
        + f"{row['Low']:.2f} ₺"

        + "<br>"

        + "Kapanış: "
        + f"{row['Close']:.2f} ₺"

        + "<br>"

        + "Hacim: "
        + f"{int(row['Volume']):,}"
    )


# =========================================================
# MUMLAR
# =========================================================

fig.add_trace(

    go.Candlestick(

        x=grafik["x"],

        open=grafik["Open"],

        high=grafik["High"],

        low=grafik["Low"],

        close=grafik["Close"],

        increasing_line_color=
            "#00c896",

        increasing_fillcolor=
            "#00c896",

        decreasing_line_color=
            "#ff4655",

        decreasing_fillcolor=
            "#ff4655",

        hovertext=hover_text,

        hoverinfo="text",

        name=hisse
    ),

    row=1,
    col=1
)


# =========================================================
# HACİM
# =========================================================

hacim_renkleri = np.where(

    grafik["Close"]
    >=
    grafik["Open"],

    "#00a887",

    "#d84a55"
)


fig.add_trace(

    go.Bar(

        x=grafik["x"],

        y=grafik["Volume"],

        marker_color=
            hacim_renkleri,

        opacity=0.65,

        customdata=
            grafik["tarih"],

        hovertemplate=
            "<b>%{customdata}</b>"
            "<br>"
            "İşlem Hacmi: %{y:,.0f}"
            "<extra></extra>",

        name="Hacim"
    ),

    row=2,
    col=1
)


# =========================================================
# SON FİYAT ÇİZGİSİ
# =========================================================

fiyat_rengi = (
    "#00c896"
    if degisim >= 0
    else "#ff4655"
)


fig.add_hline(

    y=fiyat,

    line_width=1,

    line_dash="dot",

    line_color=fiyat_rengi,

    annotation_text=
        f" {fiyat:.2f} ₺ ",

    annotation_position=
        "right",

    row=1,
    col=1
)


# =========================================================
# X EKSENİ TARİHLER
# =========================================================

n = len(grafik)

adet = min(
    9,
    n
)


if n > 1:

    pozisyonlar = np.linspace(
        0,
        n - 1,
        adet,
        dtype=int
    )

else:

    pozisyonlar = [0]


etiketler = []


for pos in pozisyonlar:

    tarih = grafik.index[pos]

    if donem == "1G":

        etiket = tarih.strftime(
            "%H:%M"
        )

    elif donem in [
        "1H",
        "1A"
    ]:

        etiket = tarih.strftime(
            "%d %b"
        )

    else:

        etiket = tarih.strftime(
            "%b %Y"
        )

    etiketler.append(
        etiket
    )


fig.update_xaxes(

    tickmode="array",

    tickvals=
        pozisyonlar,

    ticktext=
        etiketler,

    gridcolor=
        "#1b2938",

    zeroline=False
)


# =========================================================
# Y EKSENİ
# =========================================================

fig.update_yaxes(

    side="right",

    gridcolor="#1b2938",

    zeroline=False,

    row=1,
    col=1
)


fig.update_yaxes(

    side="right",

    gridcolor="#1b2938",

    zeroline=False,

    row=2,
    col=1
)


# =========================================================
# GÖRÜNÜM
# =========================================================

fig.update_layout(

    height=650,

    paper_bgcolor=
        "#0b111c",

    plot_bgcolor=
        "#0b111c",

    font=dict(
        color="#aebdce"
    ),

    margin=dict(
        l=10,
        r=80,
        t=25,
        b=10
    ),

    showlegend=False,

    xaxis_rangeslider_visible=False,

    hovermode="x",

    dragmode="pan"
)


st.plotly_chart(

    fig,

    use_container_width=True,

    config={

        "scrollZoom": True,

        "displaylogo": False,

        "responsive": True

    }
)


# =========================================================
# DÖNEM AÇIKLAMASI
# =========================================================

aciklamalar = {

    "1G":
        "1 Gün • 5 dakikalık mum",

    "1H":
        "1 Hafta • 30 dakikalık mum",

    "1A":
        "1 Ay • saatlik mum",

    "1Y":
        "1 Yıl • günlük mum"
}


st.caption(
    aciklamalar[donem]
)


# =========================================================
# HABERLER
# =========================================================

@st.cache_data(ttl=300)
def haber_al(query):

    q = urllib.parse.quote(
        query
    )

    url = (
        "https://news.google.com/rss/search?"
        f"q={q}"
        "&hl=tr"
        "&gl=TR"
        "&ceid=TR:tr"
    )

    return feedparser.parse(
        url
    )


def haber_goster(feed, adet=5):

    if not feed.entries:

        st.caption(
            "İçerik bulunamadı."
        )

        return

    for haber in feed.entries[:adet]:

        baslik = haber.get(
            "title",
            "Başlık yok"
        )

        link = haber.get(
            "link",
            ""
        )

        tarih = haber.get(
            "published",
            ""
        )

        st.markdown(
            f"**{baslik}**"
        )

        if tarih:

            st.caption(
                tarih
            )

        if link:

            st.link_button(
                "Aç ↗",
                link
            )

        st.divider()


# =========================================================
# ALT PANELLER
# =========================================================

st.divider()


h1, h2, h3 = st.columns(3)


with h1:

    st.markdown(
        f"### 📰 {hisse} Haberleri"
    )

    haberler = haber_al(
        f"{hisse} Borsa İstanbul"
    )

    haber_goster(
        haberler
    )


with h2:

    st.markdown(
        "### 🔔 KAP Bildirimleri"
    )

    kap = haber_al(
        f"{hisse} KAP açıklaması"
    )

    haber_goster(
        kap
    )

    st.link_button(
        "Resmî KAP ↗",
        "https://www.kap.org.tr/"
    )


with h3:

    st.markdown(
        "### 🌍 Borsa Gündemi"
    )

    bist = haber_al(
        "BIST 100 Borsa İstanbul"
    )

    haber_goster(
        bist
    )


# =========================================================
# ALT NOT
# =========================================================

st.divider()

st.caption(
    "🟡 Fiyat/mum/hacim verileri yfinance üzerinden alınmaktadır. "
    "BIST için gerçek zamanlı veri garantisi yoktur."
)

st.caption(
    "Grafik bilgilendirme amaçlıdır."
)