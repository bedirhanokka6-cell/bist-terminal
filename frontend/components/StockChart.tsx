'use client';

import {useEffect, useRef} from 'react';
import {
  ColorType,
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
} from 'lightweight-charts';

type Candle = {
  time: string;
  open: number; high: number; low: number; close: number;
  volume?: number | null;
  ema20?: number | null; ema50?: number | null; ema200?: number | null;
  rsi?: number | null; macd?: number | null; macd_signal?: number | null; macd_hist?: number | null;
  bb_upper?: number | null; bb_mid?: number | null; bb_lower?: number | null;
};

const toTime = (iso:string) => Math.floor(new Date(iso).getTime()/1000) as any;
const points = (data:Candle[], key:keyof Candle) => data.filter(x=>typeof x[key]==='number').map(x=>({time:toTime(x.time), value:Number(x[key])}));

export function PriceChart({candles}:{candles:Candle[]}){
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!ref.current || !candles.length) return;
    const chart=createChart(ref.current,{height:430,layout:{background:{type:ColorType.Solid,color:'#071725'},textColor:'#9fb3c8'},grid:{vertLines:{color:'#12283a'},horzLines:{color:'#12283a'}},rightPriceScale:{borderColor:'#173149'},timeScale:{borderColor:'#173149',timeVisible:true,secondsVisible:false},crosshair:{vertLine:{color:'#3b5d76'},horzLine:{color:'#3b5d76'}}});
    const cs=chart.addSeries(CandlestickSeries,{upColor:'#12d6a0',downColor:'#ff4d61',borderVisible:false,wickUpColor:'#12d6a0',wickDownColor:'#ff4d61'});
    cs.setData(candles.map(x=>({time:toTime(x.time),open:x.open,high:x.high,low:x.low,close:x.close})));
    const e20=chart.addSeries(LineSeries,{color:'#2f7cff',lineWidth:2,title:'EMA 20'}); e20.setData(points(candles,'ema20'));
    const e50=chart.addSeries(LineSeries,{color:'#f8a923',lineWidth:2,title:'EMA 50'}); e50.setData(points(candles,'ema50'));
    chart.timeScale().fitContent();
    const ro=new ResizeObserver(entries=>{for(const e of entries) chart.applyOptions({width:e.contentRect.width});}); ro.observe(ref.current);
    return()=>{ro.disconnect();chart.remove();};
  },[candles]);
  return <div ref={ref} className="chartBox"/>;
}

export function AnalysisChart({candles,mode}:{candles:Candle[];mode:string}){
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!ref.current || !candles.length) return;
    const chart=createChart(ref.current,{height:255,layout:{background:{type:ColorType.Solid,color:'#071725'},textColor:'#9fb3c8'},grid:{vertLines:{color:'#12283a'},horzLines:{color:'#12283a'}},rightPriceScale:{borderColor:'#173149'},timeScale:{borderColor:'#173149',timeVisible:true,secondsVisible:false}});
    if(mode==='RSI'){
      const s=chart.addSeries(LineSeries,{color:'#9b6cff',lineWidth:2,title:'RSI (14)'}); s.setData(points(candles,'rsi'));
      s.createPriceLine({price:70,color:'#59697a',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'70'});
      s.createPriceLine({price:30,color:'#59697a',lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'30'});
    } else if(mode==='MACD'){
      const m=chart.addSeries(LineSeries,{color:'#2f7cff',lineWidth:2,title:'MACD'}); m.setData(points(candles,'macd'));
      const sig=chart.addSeries(LineSeries,{color:'#f8a923',lineWidth:2,title:'Sinyal'}); sig.setData(points(candles,'macd_signal'));
      const h=chart.addSeries(HistogramSeries,{priceFormat:{type:'price',precision:3,minMove:0.001},title:'Histogram'});
      h.setData(candles.filter(x=>typeof x.macd_hist==='number').map(x=>({time:toTime(x.time),value:Number(x.macd_hist),color:Number(x.macd_hist)>=0?'rgba(18,214,160,.65)':'rgba(255,77,97,.65)'})));
    } else if(mode==='Hacim'){
      const h=chart.addSeries(HistogramSeries,{priceFormat:{type:'volume'},title:'Hacim'});
      h.setData(candles.filter(x=>typeof x.volume==='number').map(x=>({time:toTime(x.time),value:Number(x.volume),color:x.close>=x.open?'rgba(18,214,160,.7)':'rgba(255,77,97,.7)'})));
    } else if(mode==='Bollinger'){
      const close=chart.addSeries(LineSeries,{color:'#d7e4ef',lineWidth:1,title:'Fiyat'}); close.setData(candles.map(x=>({time:toTime(x.time),value:x.close})));
      const up=chart.addSeries(LineSeries,{color:'#3d73c9',lineWidth:1,title:'BB Üst'}); up.setData(points(candles,'bb_upper'));
      const mid=chart.addSeries(LineSeries,{color:'#8fa3b8',lineWidth:1,title:'BB Orta'}); mid.setData(points(candles,'bb_mid'));
      const low=chart.addSeries(LineSeries,{color:'#3d73c9',lineWidth:1,title:'BB Alt'}); low.setData(points(candles,'bb_lower'));
    } else {
      const close=chart.addSeries(LineSeries,{color:'#d7e4ef',lineWidth:1,title:'Fiyat'}); close.setData(candles.map(x=>({time:toTime(x.time),value:x.close})));
      const e20=chart.addSeries(LineSeries,{color:'#2f7cff',lineWidth:2,title:'EMA 20'}); e20.setData(points(candles,'ema20'));
      const e50=chart.addSeries(LineSeries,{color:'#f8a923',lineWidth:2,title:'EMA 50'}); e50.setData(points(candles,'ema50'));
      const e200=chart.addSeries(LineSeries,{color:'#9b6cff',lineWidth:2,title:'EMA 200'}); e200.setData(points(candles,'ema200'));
    }
    chart.timeScale().fitContent();
    const ro=new ResizeObserver(entries=>{for(const e of entries) chart.applyOptions({width:e.contentRect.width});}); ro.observe(ref.current);
    return()=>{ro.disconnect();chart.remove();};
  },[candles,mode]);
  return <div ref={ref} className="chartBox small"/>;
}
