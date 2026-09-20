'use client';
import {useEffect, useMemo, useState} from 'react';
import {PriceChart, AnalysisChart} from '../components/StockChart';
import {initializeApp, getApps} from 'firebase/app';
import {getMessaging, getToken, onMessage, isSupported} from 'firebase/messaging';

type Stock={symbol:string;price:number;change_pct:number};
type Scanner={symbol:string;price:number;change_pct:number;score:number;state:string;rsi:number|null;vol_ratio:number|null;support:number;resistance:number};
type SignalItem={id:number;symbol:string;signal_type:string;score:number;state:string;price:number;support:number|null;resistance:number|null;reasons:string[];created_at:string|null};
type SignalStats={horizon_days:number;evaluated_total:number;directional_total:number;successful:number;failed:number;success_rate_pct:number|null;average_return_pct:number|null;note:string};

const API=process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const periods=['1G','5G','1A','3A','6A','1Y','2Y'];
const analyses=['RSI','MACD','Hacim','RVOL','OBV','MFI','CMF','Bollinger','EMA'];
const horizons=[1,3,5,10];

export default function Home(){
  const [watch,setWatch]=useState<Stock[]>([]);
  const [scan,setScan]=useState<Scanner[]>([]);
  const [symbol,setSymbol]=useState('BIMAS');
  const [period,setPeriod]=useState('1A');
  const [analysis,setAnalysis]=useState('RSI');
  const [stock,setStock]=useState<any>(null);
  const [loading,setLoading]=useState(false);
  const [signals,setSignals]=useState<SignalItem[]>([]);
  const [stats,setStats]=useState<SignalStats|null>(null);
  const [horizon,setHorizon]=useState(5);
  const [signalBusy,setSignalBusy]=useState(false);
  const [signalMessage,setSignalMessage]=useState('');
  const [pushStatus,setPushStatus]=useState('Bildirim kapalı');
  const [pushToken,setPushToken]=useState('');
  const [tradeHistory,setTradeHistory]=useState<any[]>([]);
  const [tradeHistoryLoading,setTradeHistoryLoading]=useState(false);
  const [v5,setV5]=useState<any>(null);
  const [openPositions,setOpenPositions]=useState<any[]>([]);
  const [v9Status,setV9Status]=useState<any>(null);
  const [showExtraPanels,setShowExtraPanels]=useState(false);
  const [mobileMenuOpen,setMobileMenuOpen]=useState(false);

  const loadSignals=async()=>{
    try{
      const r=await fetch(`${API}/api/signals?limit=100`,{cache:'no-store'});
      if(r.ok){const d=await r.json();setSignals(d.items||[])}
      const s=await fetch(`${API}/api/signals/stats/summary?horizon_days=${horizon}`,{cache:'no-store'});
      if(s.ok)setStats(await s.json());
    }catch{}
  };

  const loadWatch=async()=>{
    try{
      const r=await fetch(`${API}/api/bist30`,{cache:'no-store'});
      if(r.ok)setWatch(await r.json());
    }catch{}
  };

  const loadScanner=async()=>{
    try{
      const r=await fetch(`${API}/api/scanner?min_score=6`,{cache:'no-store'});
      if(r.ok)setScan(await r.json());
    }catch{}
  };

  const loadStock=async(showLoading=false)=>{
    if(showLoading)setLoading(true);
    try{
      const r=await fetch(`${API}/api/stock/${symbol}?period=${period}`,{cache:'no-store'});
      if(r.ok)setStock(await r.json());
    }catch{}
    finally{
      if(showLoading)setLoading(false);
    }
  };

  const loadV5=async()=>{
    try{
      const r=await fetch(`${API}/api/analysis/v5/${symbol}`,{cache:'no-store'});
      if(r.ok)setV5(await r.json());
    }catch{}
  };

  const loadOpenPositions=async()=>{
    try{
      const r=await fetch(`${API}/api/positions/open`,{cache:'no-store'});
      if(r.ok){
        const j=await r.json();
        setOpenPositions(j?.items ?? []);
      }
    }catch{}
  };

  const loadV9Status=async()=>{
    try{
      const r=await fetch(`${API}/api/v9/live-status`,{cache:'no-store'});
      if(r.ok)setV9Status(await r.json());
    }catch{}
  };

  const loadExtraPanels=async()=>{
    setShowExtraPanels(true);
    await Promise.allSettled([
      loadScanner(),
      loadOpenPositions(),
      loadV9Status(),
    ]);
  };

  const loadTradeHistory=async()=>{
    setTradeHistoryLoading(true);
    try{
      const r=await fetch(`${API}/api/backtest/v4-trades?limit=40`,{cache:'no-store'});
      if(r.ok){
        const j=await r.json();
        setTradeHistory(j?.trades ?? []);
      }
    }catch{}
    finally{setTradeHistoryLoading(false);}
  };

  useEffect(()=>{
    loadWatch();
    loadSignals();
    const watchTimer=setInterval(loadWatch,60000);
    return()=>{clearInterval(watchTimer);};
  },[]);

  useEffect(()=>{
    loadStock(true);
    loadV5();

    const stockTimer=setInterval(()=>{
      if(document.visibilityState==='visible'){
        loadStock(false);
      }
    },15000);

    const analysisTimer=setInterval(()=>{
      if(document.visibilityState==='visible'){
        loadV5();
      }
    },120000);

    return()=>{
      clearInterval(stockTimer);
      clearInterval(analysisTimer);
    };
  },[symbol,period]);

  useEffect(()=>{loadSignals();},[horizon]);

  const saveCurrentSignal=async()=>{
    setSignalBusy(true);setSignalMessage('');
    try{
      const r=await fetch(`${API}/api/signals/${symbol}?period=${period}`,{method:'POST'});
      const d=await r.json();
      if(!r.ok) throw new Error(d?.detail||'Sinyal kaydedilemedi');
      setSignalMessage(`${symbol} sinyali kaydedildi.`);
      await loadSignals();
    }catch(e:any){setSignalMessage(e?.message||'Sinyal kaydedilemedi.')}finally{setSignalBusy(false)}
  };

  const evaluatePending=async()=>{
    setSignalBusy(true);setSignalMessage('');
    try{
      const r=await fetch(`${API}/api/signals/evaluate-pending/all?horizon_days=${horizon}&limit=100`,{method:'POST'});
      const d=await r.json();
      if(!r.ok) throw new Error(d?.detail||'Değerlendirme başarısız');
      setSignalMessage(`${d.evaluated||0} sinyal değerlendirildi, ${d.waiting||0} sinyal bekliyor.`);
      await loadSignals();
    }catch(e:any){setSignalMessage(e?.message||'Değerlendirme başarısız.')}finally{setSignalBusy(false)}
  };


  const enableNotifications=async()=>{
    try{
      if(!('Notification' in window)){
        setPushStatus('Bu tarayıcı bildirim desteklemiyor');
        return;
      }

      const supported=await isSupported();
      if(!supported){
        setPushStatus('Firebase Messaging desteklenmiyor');
        return;
      }

      const permission=await Notification.requestPermission();
      if(permission!=='granted'){
        setPushStatus('Bildirim izni verilmedi');
        return;
      }

      const firebaseConfig={
        apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
        authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
        projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
        storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
        messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
        appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
        measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
      };

      const app=getApps().length?getApps()[0]:initializeApp(firebaseConfig);
      const messaging=getMessaging(app);

      await navigator.serviceWorker.register('/firebase-messaging-sw.js');

      // Service worker ilk kayıtta hemen aktif olmayabilir.
      // Firebase token istemeden önce aktif hale gelmesini bekliyoruz.
      const registration=await navigator.serviceWorker.ready;

      const token=await getToken(messaging,{
        vapidKey: process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY,
        serviceWorkerRegistration: registration,
      });

      if(!token){
        setPushStatus('Bildirim tokeni alınamadı');
        return;
      }

      setPushToken(token);
      try{
        await fetch(`${API}/api/push/register`,{
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({token,platform:'web'})
        });
      }catch{}
      setPushStatus('Bildirim açık');

      onMessage(messaging,(payload)=>{
        const title=payload?.notification?.title || 'BIST Terminal';
        const body=payload?.notification?.body || 'Yeni bildirim';
        new Notification(title,{body});
      });
    }catch(e:any){
      console.error(e);
      setPushStatus(e?.message || 'Bildirim kurulamadı');
    }
  };

  const copyPushToken=async()=>{
    if(!pushToken)return;
    await navigator.clipboard.writeText(pushToken);
    setPushStatus('Token kopyalandı');
  };

  const last=stock?.candles?.[stock.candles.length-1];
  const prev=stock?.candles?.[stock.candles.length-2];
  const change=last&&prev?((last.close/prev.close)-1)*100:0;
  const score=stock?.technical?.score ?? 0;
  const state=stock?.technical?.state ?? '—';
  const stateColor=stock?.technical?.color || '#f8bd39';
  const selectedWatch=useMemo(()=>watch.find(x=>x.symbol===symbol),[watch,symbol]);

  const dataStatus=stock?.data_status ?? '—';
  const dataAge=stock?.data_age_minutes;
  const dataSource=stock?.data_source ?? '—';
  const dataTime=stock?.last_data_time ? formatDataTime(stock.last_data_time) : '—';
  const dataStatusColor=
    dataStatus==='GUNCEL' ? '#2ecc71' :
    dataStatus==='GECIKMELI' ? '#f8bd39' :
    dataStatus==='ESKI' ? '#ff5c5c' :
    '#9aa4b2';

  return <main className="appShell">
    <aside className={`sidebar ${mobileMenuOpen?'open':''}`}>
      <div className="sidebarTop"><div className="brand">▮▮▮ <b>BIST TERMINAL</b></div><button className="mobileCloseBtn" onClick={()=>setMobileMenuOpen(false)} aria-label="Menüyü kapat">✕</button></div><h3>BIST 30</h3>
      <div className="watchHead"><span>Hisse</span><span>Fiyat</span><span>Değişim</span></div>
      <div className="watchList">{watch.map(x=><button key={x.symbol} className={`watchRow ${x.change_pct>=0?'up':'down'} ${x.symbol===symbol?'active':''}`} onClick={()=>{setSymbol(x.symbol);setMobileMenuOpen(false)}}><span><i>{x.change_pct>=0?'▲':'▼'}</i>{x.symbol}</span><b>{x.price.toFixed(2)}</b><em>{x.change_pct>=0?'+':''}{x.change_pct.toFixed(2)}%</em></button>)}</div>
      <small>Veriler ücretsiz kaynaklardan gelir; gerçek zamanlı olduğu garanti edilmez.</small>
    </aside>
    {mobileMenuOpen?<button className="mobileBackdrop" onClick={()=>setMobileMenuOpen(false)} aria-label="Menüyü kapat"/>:null}

    <section className="mainArea">
      <header className="topnav"><button className="mobileMenuBtn" onClick={()=>setMobileMenuOpen(true)}>☰ BIST 30</button><div className="brand">▮▮▮ <b>BIST TERMINAL</b></div><nav><span>Ana Sayfa</span><span className="active">Hisse Analizi</span><span>BIST 30 Tarayıcı</span><span>Haberler (KAP)</span><span>Takip Listesi</span><span>Sinyal Geçmişi</span></nav><div style={{display:'flex',gap:'8px',alignItems:'center'}}>
          <button onClick={enableNotifications} style={{padding:'7px 10px',borderRadius:'7px',border:'1px solid #24445f',background:'#123451',color:'#fff',cursor:'pointer'}}>
            🔔 Bildirimleri Aç
          </button>
          {pushToken?<button onClick={copyPushToken} style={{padding:'7px 10px',borderRadius:'7px',border:'1px solid #24445f',background:'#0e2435',color:'#b8c7d4',cursor:'pointer'}}>Tokeni Kopyala</button>:null}
          <span style={{fontSize:'11px',color:pushStatus==='Bildirim açık'?'#32d296':'#9aa4b2'}}>{pushStatus}</span>
          <div className="market">● Piyasa Takip</div>
        </div></header>
      <div className="periods">{periods.map(p=><button className={period===p?'active':''} onClick={()=>setPeriod(p)} key={p}>{p}</button>)}</div>
      <section className="company">
        <div className="badge">{symbol.slice(0,3)}</div>
        <div>
          <h1>{symbol}</h1>
          <p>{symbol}.IS • Borsa İstanbul • Teknik Analiz</p>
          <div style={{display:'flex',gap:'8px',flexWrap:'wrap',alignItems:'center',marginTop:'6px',fontSize:'12px',color:'#9aa4b2'}}>
            <span>Veri: {dataSource}</span>
            <span>•</span>
            <span>Son veri: {dataTime}</span>
            <span>•</span>
            <span>{dataAge==null?'Gecikme: —':`Gecikme: ${Number(dataAge).toFixed(1)} dk`}</span>
            <span>•</span>
            <b style={{color:dataStatusColor}}>{dataStatus}</b><span>•</span><span>Otomatik yenileme: 15 sn</span>
          </div>
        </div>
      </section>

      <div className="workspace">
        <div className="charts">
          <div className="panel chartPanel"><div className="chartTitle"><b>{symbol}.IS • {period}</b><span>{loading?'Veri güncelleniyor...':`${stock?.candles?.length ?? 0} mum`}</span></div>{stock?.candles?.length?<PriceChart candles={stock.candles}/>:<div className="loading">Grafik verisi bekleniyor...</div>}</div>
          <div className="analysisTabs">{analyses.map(a=><button key={a} className={analysis===a?'active':''} onClick={()=>setAnalysis(a)}>{a}</button>)}</div>
          <div className="panel analysisPanel">{stock?.candles?.length?<AnalysisChart candles={stock.candles} mode={analysis}/>:null}</div>
        </div>

        <aside className="rightRail">
          <div className="panel heroCard"><div><span className="muted">{symbol}</span><div className="bigPrice">{stock?.price?.toFixed?.(2) ?? '—'} ₺</div><div className={change>=0?'green':'red'}>{change>=0?'+':''}{change.toFixed(2)}%</div></div><div className="stateBox"><span>Genel Durum</span><b style={{color:stateColor}}>{state}</b></div><div className="scoreBar"><i style={{width:`${score*10}%`,background:stateColor}}/></div><div className="scoreText"><span>Teknik Skor</span><b style={{color:stateColor}}>{score.toFixed?.(1) ?? score}/10</b></div><button className="saveSignalBtn" onClick={saveCurrentSignal} disabled={signalBusy}>{signalBusy?'İşleniyor...':'Bu analizi sinyal olarak kaydet'}</button></div>
          <div className="panel"><h3>Piyasa Verileri</h3><Row k="Açılış" v={stock?.open}/><Row k="Yüksek" v={stock?.high}/><Row k="Düşük" v={stock?.low}/><Row k="Kapanış" v={stock?.price}/><Row k="RSI (14)" v={last?.rsi}/><Row k="EMA 20" v={last?.ema20}/><Row k="EMA 50" v={last?.ema50}/><Row k="EMA 200" v={last?.ema200}/><Row k="ATR (14)" v={last?.atr}/></div>
          <div className="panel"><h3>Teknik Seviyeler</h3><Row k="● Destek" v={stock?.support} green/><Row k="● Direnç" v={stock?.resistance} red/></div>
          <div className="panel"><h3>Hacim Kalitesi</h3><Row k="Hacim Skoru" v={stock?.volume_analysis?.score}/><Row k="RVOL" v={stock?.volume_analysis?.rvol}/><Row k="MFI" v={stock?.volume_analysis?.mfi}/><Row k="CMF" v={stock?.volume_analysis?.cmf}/><p className="reason">• {stock?.volume_analysis?.state ?? '—'}</p>{stock?.volume_analysis?.reasons?.slice(0,3).map((r:string)=><p className="reason" key={r}>• {r}</p>)}</div>
          <div className="panel"><h3>Piyasa Rejimi</h3><div className="stateBox"><span>BIST yönü</span><b className={stock?.market_regime?.positive?'green':'red'}>{stock?.market_regime?.state ?? '—'}</b></div><p className="reason">{stock?.market_regime?.reason ?? 'Endeks verisi bekleniyor'}</p><div className="stateBox"><span>V4 teyit</span><b className={stock?.v4_signal==='GÜÇLÜ TEKNİK TEYİT'?'green':''}>{stock?.v4_signal ?? '—'}</b></div></div>
          <div className="panel"><h3>V5 Erken Hareket</h3><div className="stateBox"><span>Sinyal</span><b className={(v5?.v5?.signal==='BREAKOUT'||v5?.v5?.signal==='GUCLU_TEKNIK_TEYIT')?'green':''}>{v5?.v5?.signal ?? '—'}</b></div><Row k="Erken Hareket Skoru" v={v5?.v5?.early_move_score}/><Row k="RVOL" v={v5?.v5?.rvol}/>{v5?.v5?.reasons?.slice(0,4).map((r:string)=><p className="reason" key={r}>• {r}</p>)}</div>
          <div className="panel"><h3>Kısa Teknik Yorum</h3>{stock?.technical?.reasons?.slice(0,5).map((r:string)=><p className="reason" key={r}>• {r}</p>)}</div>
        </aside>
      </div>

      <div className="metricGrid"><Metric k="Teknik Skor" v={`${score.toFixed?.(1) ?? score}/10`}/><Metric k="Hacim Skoru" v={stock?.volume_analysis?.score==null?'—':`${Number(stock.volume_analysis.score).toFixed(1)}/10`}/><Metric k="RVOL" v={last?.rvol==null?'—':`${Number(last.rvol).toFixed(2)}x`}/><Metric k="MFI" v={fmt(last?.mfi)}/><Metric k="CMF" v={last?.cmf==null?'—':Number(last.cmf).toFixed(3)}/><Metric k="RSI" v={fmt(last?.rsi)}/><Metric k="ATR" v={fmt(last?.atr)}/><Metric k="Piyasa" v={stock?.market_regime?.state ?? '—'}/></div>

      <section className="panel scanner"><div className="sectionTitle"><div><h2>BIST 30 Fırsat Tarayıcı</h2><p>Teknik skoru yüksek hisseleri hızlıca görün.</p></div></div><div className="table"><div className="tr head"><span>Hisse</span><span>Fiyat</span><span>Değişim</span><span>Skor</span><span>RSI</span><span>Hacim</span><span>Destek</span><span>Direnç</span><span>Durum</span></div>{scan.map(x=><div className="tr" key={x.symbol} onClick={()=>{setSymbol(x.symbol);setMobileMenuOpen(false)}}><span><b>{x.symbol}</b></span><span>{x.price.toFixed(2)} ₺</span><span className={x.change_pct>=0?'green':'red'}>{x.change_pct>=0?'+':''}{x.change_pct.toFixed(2)}%</span><span>{x.score.toFixed(1)}</span><span>{x.rsi?.toFixed?.(1) ?? '—'}</span><span>{x.vol_ratio?.toFixed?.(2) ?? '—'}x</span><span>{x.support.toFixed(2)}</span><span>{x.resistance.toFixed(2)}</span><span>{x.state}</span></div>)}</div></section>

      <section className="panel lazyPanelToggle">
        <div>
          <b>Ek Paneller</b>
          <span>Tarayıcı, açık sinyaller ve geçmiş veriler yalnızca istediğinde yüklenir.</span>
        </div>
        <button onClick={showExtraPanels?()=>setShowExtraPanels(false):loadExtraPanels}>
          {showExtraPanels?"Panelleri Gizle":"Alt Panelleri Yükle"}
        </button>
      </section>
      {showExtraPanels && (<>
      <section className="panel v9PaperBanner">
        <div><b>V9 PAPER FORWARD TEST</b><span> Gerçek para emri yok — canlı sinyaller ve sonuçlar kaydediliyor.</span></div>
        <div className="v9StatusRow">
          <span>Piyasa: <b>{v9Status?.market_regime?.state ?? '—'}</b></span>
          <span>Breadth: <b>{v9Status?.market_regime?.breadth_pct==null?'—':`%${v9Status.market_regime.breadth_pct}`}</b></span>
          <span>Açık sinyal: <b>{v9Status?.open_positions ?? openPositions.length}</b></span>
        </div>
      </section>

      <section className="panel performanceBanner">
        <div><b>V10 Hız Modu</b><span> Ağır geçmiş testleri otomatik yüklenmez; günlük analizler seyrek, fiyat verisi hızlı yenilenir.</span></div>
      </section>

      <section className="panel openSignals">
        <div className="signalHeader">
          <div><h2>Açık V6 Sinyalleri</h2><p>BREAKOUT / güçlü teyit sonrası stop ve hedefleri otomatik takip eder.</p></div>
          <div className="signalActions"><button onClick={loadOpenPositions}>Yenile</button></div>
        </div>
        <div className="tradeTableWrap">
          <div className="v6Tr head"><span>Hisse</span><span>Sinyal</span><span>Giriş</span><span>Stop</span><span>Hedef 1</span><span>Hedef 2</span><span>Son</span><span>H1</span></div>
          {openPositions.length?openPositions.map((p:any)=><div className="v6Tr" key={p.id} onClick={()=>setSymbol(p.symbol)}>
            <b>{p.symbol}</b><span>{p.signal_type}</span><span>{fmt(p.entry_price)} ₺</span><span className="red">{fmt(p.stop_price)} ₺</span><span>{fmt(p.target1_price)} ₺</span><span className="green">{fmt(p.target2_price)} ₺</span><span>{p.last_price==null?'—':`${fmt(p.last_price)} ₺`}</span><span>{p.target1_hit?'✓':'—'}</span>
          </div>):<div className="emptySignals">Şu anda açık V6 sinyali yok.</div>}
        </div>
      </section>

      <section className="panel tradeHistory">
        <div className="signalHeader">
          <div><h2>Geçmiş V4 İşlemleri</h2><p>V4'ün geçmişte verdiği AL adayları ve stop/hedef/zaman çıkışları.</p></div>
          <div className="signalActions"><button onClick={loadTradeHistory}>{tradeHistoryLoading?"Yükleniyor...":"Geçmişi Yükle"}</button></div>
        </div>
        <div className="tradeTableWrap">
          <div className="tradeTr head"><span>Hisse</span><span>AL tarihi</span><span>Giriş</span><span>Çıkış tarihi</span><span>Çıkış</span><span>Neden</span><span>Getiri</span><span>Skor</span><span>Hacim</span></div>
          {tradeHistory.length?tradeHistory.map((t:any,i:number)=><div className="tradeTr" key={`${t.symbol}-${t.entry_date}-${i}`} onClick={()=>setSymbol(t.symbol)}>
            <b>{t.symbol}</b><span>{t.entry_date}</span><span>{fmt(t.entry_price)} ₺</span><span>{t.exit_date}</span><span>{fmt(t.exit_price)} ₺</span><span>{t.exit_reason==='TARGET'?'HEDEF':t.exit_reason==='STOP'?'STOP':'ZAMAN'}</span><b className={Number(t.net_return_pct)>=0?'green':'red'}>{Number(t.net_return_pct)>=0?'+':''}{Number(t.net_return_pct).toFixed(2)}%</b><span>{Number(t.quality_score).toFixed(2)}</span><span>{Number(t.volume_score).toFixed(2)}</span>
          </div>):<div className="emptySignals">{tradeHistoryLoading?'Geçmiş işlemler hesaplanıyor...':'Geçmiş işlem bulunamadı.'}</div>}
        </div>
      </section>

      </>)}

      <section className="panel signalHistory">
        <div className="signalHeader">
          <div><h2>Sinyal Geçmişi</h2><p>PostgreSQL'e kaydedilen teknik sinyaller ve geçmiş performans takibi.</p></div>
          <div className="signalActions">
            <label>Sonuç süresi<select value={horizon} onChange={e=>setHorizon(Number(e.target.value))}>{horizons.map(h=><option key={h} value={h}>{h} işlem günü</option>)}</select></label>
            <button onClick={evaluatePending} disabled={signalBusy}>Bekleyenleri değerlendir</button>
            <button onClick={loadSignals} disabled={signalBusy}>Yenile</button>
          </div>
        </div>
        {signalMessage?<div className="signalMessage">{signalMessage}</div>:null}
        <div className="signalStats">
          <Metric k={`${horizon} Gün Değerlendirilen`} v={String(stats?.evaluated_total ?? 0)}/>
          <Metric k="Başarılı" v={String(stats?.successful ?? 0)}/>
          <Metric k="Başarısız" v={String(stats?.failed ?? 0)}/>
          <Metric k="Başarı Oranı" v={stats?.success_rate_pct==null?'—':`%${stats.success_rate_pct.toFixed(1)}`}/>
          <Metric k="Ort. Getiri" v={stats?.average_return_pct==null?'—':`${stats.average_return_pct>=0?'+':''}${stats.average_return_pct.toFixed(2)}%`}/>
        </div>
        <div className="signalTableWrap">
          <div className="signalTr head"><span>Tarih</span><span>Hisse</span><span>Sinyal</span><span>Fiyat</span><span>Skor</span><span>Durum</span><span>Destek</span><span>Direnç</span></div>
          {signals.length?signals.map(s=><div className="signalTr" key={s.id} onClick={()=>setSymbol(s.symbol)}><span>{formatDate(s.created_at)}</span><span><b>{s.symbol}</b></span><span><i className={`signalBadge ${signalClass(s.signal_type)}`}>{s.signal_type}</i></span><span>{fmt(s.price)} ₺</span><span>{Number(s.score).toFixed(1)}</span><span>{s.state}</span><span>{fmt(s.support)}</span><span>{fmt(s.resistance)}</span></div>):<div className="emptySignals">Henüz kayıtlı sinyal yok. Sağdaki “Bu analizi sinyal olarak kaydet” düğmesini kullanabilirsin.</div>}
        </div>
      </section>
    </section>
  </main>
}

function fmt(v:any){return v==null?'—':Number(v).toFixed(2)}
function Row({k,v,green,red}:{k:string;v:any;green?:boolean;red?:boolean}){return <div className="row"><span className={green?'green':red?'red':''}>{k}</span><b>{fmt(v)}</b></div>}
function Metric({k,v}:{k:string;v:string}){return <div className="metric"><span>{k}</span><b>{v}</b></div>}
function signalClass(v:string){return v==='AL'?'buy':v==='SAT'?'sell':'wait'}
function formatDate(v:string|null){if(!v)return '—';try{return new Intl.DateTimeFormat('tr-TR',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(v))}catch{return v}}
function formatDataTime(v:string){try{return new Intl.DateTimeFormat('tr-TR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(v))}catch{return v}}
