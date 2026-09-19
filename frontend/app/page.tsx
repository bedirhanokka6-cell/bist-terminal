'use client';
import {useEffect, useMemo, useState} from 'react';
import {PriceChart, AnalysisChart} from '../components/StockChart';

type Stock={symbol:string;price:number;change_pct:number};
type Scanner={symbol:string;price:number;change_pct:number;score:number;state:string;rsi:number|null;vol_ratio:number|null;support:number;resistance:number};
type SignalItem={id:number;symbol:string;signal_type:string;score:number;state:string;price:number;support:number|null;resistance:number|null;reasons:string[];created_at:string|null};
type SignalStats={horizon_days:number;evaluated_total:number;directional_total:number;successful:number;failed:number;success_rate_pct:number|null;average_return_pct:number|null;note:string};

const API=process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const periods=['1G','5G','1A','3A','6A','1Y','2Y'];
const analyses=['RSI','MACD','Hacim','Bollinger','EMA'];
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

  const loadSignals=async()=>{
    try{
      const r=await fetch(`${API}/api/signals?limit=100`,{cache:'no-store'});
      if(r.ok){const d=await r.json();setSignals(d.items||[])}
      const s=await fetch(`${API}/api/signals/stats/summary?horizon_days=${horizon}`,{cache:'no-store'});
      if(s.ok)setStats(await s.json());
    }catch{}
  };

  useEffect(()=>{
    fetch(`${API}/api/bist30`).then(r=>r.json()).then(setWatch).catch(()=>{});
    fetch(`${API}/api/scanner?min_score=6`).then(r=>r.json()).then(setScan).catch(()=>{});
    loadSignals();
  },[]);

  useEffect(()=>{
    setLoading(true);
    fetch(`${API}/api/stock/${symbol}?period=${period}`)
      .then(r=>r.json()).then(setStock).finally(()=>setLoading(false));
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
    <aside className="sidebar">
      <div className="brand">▮▮▮ <b>BIST TERMINAL</b></div><h3>BIST 30</h3>
      <div className="watchHead"><span>Hisse</span><span>Fiyat</span><span>Değişim</span></div>
      <div className="watchList">{watch.map(x=><button key={x.symbol} className={`watchRow ${x.change_pct>=0?'up':'down'} ${x.symbol===symbol?'active':''}`} onClick={()=>setSymbol(x.symbol)}><span><i>{x.change_pct>=0?'▲':'▼'}</i>{x.symbol}</span><b>{x.price.toFixed(2)}</b><em>{x.change_pct>=0?'+':''}{x.change_pct.toFixed(2)}%</em></button>)}</div>
      <small>Veriler ücretsiz kaynaklardan gelir; gerçek zamanlı olduğu garanti edilmez.</small>
    </aside>

    <section className="mainArea">
      <header className="topnav"><div className="brand">▮▮▮ <b>BIST TERMINAL</b></div><nav><span>Ana Sayfa</span><span className="active">Hisse Analizi</span><span>BIST 30 Tarayıcı</span><span>Haberler (KAP)</span><span>Takip Listesi</span><span>Sinyal Geçmişi</span></nav><div className="market">● Piyasa Takip</div></header>
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
            <b style={{color:dataStatusColor}}>{dataStatus}</b>
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
          <div className="panel"><h3>Kısa Teknik Yorum</h3>{stock?.technical?.reasons?.slice(0,5).map((r:string)=><p className="reason" key={r}>• {r}</p>)}</div>
        </aside>
      </div>

      <div className="metricGrid"><Metric k="Teknik Skor" v={`${score.toFixed?.(1) ?? score}/10`}/><Metric k="RSI" v={fmt(last?.rsi)}/><Metric k="Hacim Oranı" v={last?.vol_ratio==null?'—':`${Number(last.vol_ratio).toFixed(2)}x`}/><Metric k="ATR" v={fmt(last?.atr)}/><Metric k="Destek" v={fmt(stock?.support)}/><Metric k="Direnç" v={fmt(stock?.resistance)}/></div>

      <section className="panel scanner"><div className="sectionTitle"><div><h2>BIST 30 Fırsat Tarayıcı</h2><p>Teknik skoru yüksek hisseleri hızlıca görün.</p></div></div><div className="table"><div className="tr head"><span>Hisse</span><span>Fiyat</span><span>Değişim</span><span>Skor</span><span>RSI</span><span>Hacim</span><span>Destek</span><span>Direnç</span><span>Durum</span></div>{scan.map(x=><div className="tr" key={x.symbol} onClick={()=>setSymbol(x.symbol)}><span><b>{x.symbol}</b></span><span>{x.price.toFixed(2)} ₺</span><span className={x.change_pct>=0?'green':'red'}>{x.change_pct>=0?'+':''}{x.change_pct.toFixed(2)}%</span><span>{x.score.toFixed(1)}</span><span>{x.rsi?.toFixed?.(1) ?? '—'}</span><span>{x.vol_ratio?.toFixed?.(2) ?? '—'}x</span><span>{x.support.toFixed(2)}</span><span>{x.resistance.toFixed(2)}</span><span>{x.state}</span></div>)}</div></section>

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
