"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Metrics = {
  closed_trades: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  expectancy_pct_per_trade: number;
  profit_factor: number | null;
  total_compounded_return_pct: number;
};

type Position = {
  symbol: string;
  timeframe: string;
  status: string;
  signal_time: string;
  entry_time: string;
  entry: number;
  stop: number;
  target: number;
  last_price: number;
  bars_held: number;
};

type StatusData = {
  status: string;
  started_at: string;
  strategy: string;
  symbols: string[];
  auto_scan_every_minutes: number;
  last_auto_scan_at: string | null;
  last_auto_scan_errors: { symbol: string; message: string }[];
  open_positions: Position[];
  metrics: Metrics;
  unread_notifications: number;
};

type NotificationItem = {
  id: string;
  created_at: string;
  kind: string;
  title: string;
  message: string;
  read: boolean;
};

type ClosedTrade = {
  symbol: string;
  timeframe: string;
  status: string;
  signal_time: string;
  entry_time: string;
  entry: number;
  stop: number;
  target: number;
  last_price: number;
  bars_held: number;
  opened_at: string;
  exit_time: string;
  exit: number;
  exit_reason: string;
  net_return_pct: number;
  result: "WIN" | "LOSS";
};

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type AlertSettings = {
  enabled: boolean;
  strong_candidate_enabled: boolean;
  strong_candidate_min_score: number;
  exact_v72_enabled: boolean;
  scan_every_minutes: number;
};

type AlertSettingsData = {
  status: string;
  settings: AlertSettings;
  last_alert_scan_at: string | null;
  last_alert_scan_result: {
    status?: string;
    alerts_created?: number;
    checked?: number;
    regime_score?: number;
    scanner_errors?: number;
    generated_at?: string;
  } | null;
  registered_push_tokens: number;
};

type ScannerCandidate = {
  symbol: string;
  score: number;
  passed_checks: number;
  total_checks: number;
  level: "V7.2_SINYAL" | "GUCLU_ADAY" | "IZLE" | "ZAYIF";
  exact_v72_signal: boolean;
  price: number | null;
  bar_time: string;
  rsi: number | null;
  adx: number | null;
  macd_hist: number | null;
  volume_ratio: number | null;
  vol5_to_vol20: number | null;
  atr_pct: number | null;
  dist_ema20_atr: number | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  regime_score: number;
  checks: Record<string, boolean>;
};

type ScannerData = {
  status: string;
  strategy: string;
  requested_symbols: number;
  scored_symbols: number;
  benchmark: string | null;
  regime_score: number;
  min_score: number;
  results: ScannerCandidate[];
  errors: Array<{symbol:string; message:string}>;
  generated_at: string;
  note: string;
};

type NewsItem = {
  title: string;
  publisher: string;
  published_at: string | null;
  url: string | null;
  impact: "pozitif_aday" | "negatif_aday" | "notr";
  impact_method: string;
};

type NewsData = {
  status: string;
  symbol: string;
  source: string;
  realtime_guaranteed: boolean;
  results: NewsItem[];
  errors: string[];
  kap: {
    source: string;
    official: boolean;
    search_url: string;
    note: string;
  };
  classification_note: string;
};


type KapDisclosure = {
  disclosure_index: number | null;
  publish_date: string | null;
  company: string | null;
  stock_codes: string;
  related_stocks: string;
  subject: string;
  summary: string;
  category: string;
  is_late: boolean;
  is_correction: boolean;
  attachment_count: number;
  url: string | null;
};

type KapData = {
  status: string;
  symbol: string;
  official_source: string;
  company?: {
    title?: string | null;
    company_code?: string | null;
    mkk_member_oid?: string | null;
    permalink?: string | null;
    company_url?: string | null;
  };
  days?: number;
  results: KapDisclosure[];
  count: number;
  retrieved_at?: string;
  note?: string;
  error?: string;
  fallback_url?: string;
};

type WatchItem = {
  symbol: string;
  last_price: number;
  daily_change_pct: number;
  volume: number | null;
  asof: string;
};

type IndexItem = {
  name: string;
  ticker: string;
  value: number;
  daily_change_pct: number;
  asof: string;
};

type MarketDetail = {
  status: string;
  symbol: string;
  source: string;
  realtime_guaranteed: boolean;
  price: { last: number; daily_change_pct: number; asof: string };
  signal: { value: string; strategy: string; signal_bar_time: string };
  support_resistance: {
    method: string;
    pivot: number | null; r1: number | null; r2: number | null; r3: number | null;
    s1: number | null; s2: number | null; s3: number | null; basis_time: string | null;
  };
  indicators: {
    rsi14: number | null;
    macd: number | null;
    macd_signal: number | null;
    macd_hist: number | null;
    adx14: number | null;
    ema20: number | null;
    ema50: number | null;
    ema200: number | null;
    atr14: number | null;
    volume_ratio: number | null;
    regime_score: number;
  };
  chart: Array<{
    time: string; open: number; high: number; low: number; close: number; volume: number;
  }>;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

const quotePool = [
  ["Veri konuşur, disiplin kararı uygular.", "BIST Katılım Terminal"],
  ["Önce riski yönet, sonra getiriyi düşün.", "BIST Katılım Terminal"],
  ["İyi sistem, her fırsatı değil doğru fırsatı bekler.", "BIST Katılım Terminal"],
  ["Planlı işlem, duygusal karardan daha güçlüdür.", "BIST Katılım Terminal"],
];

function dailyQuote() {
  const d = new Date();
  const n = Math.floor(
    Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / 86400000
  );
  return quotePool[n % quotePool.length];
}

function fmtPct(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

function fmtDateTime(value: string | null | undefined) {
  if (!value) return "Henüz yok";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

export default function Home() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [notes, setNotes] = useState<NotificationItem[]>([]);
  const [backendOnline, setBackendOnline] = useState(false);
  const [clock, setClock] = useState(new Date());
  const [selected, setSelected] = useState("TUPRS");
  const [search, setSearch] = useState("");
  const [chartRange, setChartRange] = useState<"1d" | "1w">("1w");
  const [hoveredCandle, setHoveredCandle] = useState<number | null>(null);
  const [hoveredPrice, setHoveredPrice] = useState<number | null>(null);
  const [detailOverlay, setDetailOverlay] = useState<"none" | "sr">("none");
  const [analysisTab, setAnalysisTab] = useState<"chart" | "support" | "fibonacci" | "indicators" | "patterns">("chart");
  const [analysisMenuOpen, setAnalysisMenuOpen] = useState(false);
  const [mainView, setMainView] = useState<"home" | "candles" | "paper" | "performance" | "news" | "scanner" | "settings">("home");
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [paperNotes, setPaperNotes] = useState<NotificationItem[]>([]);
  const [paperLoading, setPaperLoading] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notificationItems, setNotificationItems] = useState<NotificationItem[]>([]);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [pushSupported, setPushSupported] = useState(false);
  const [pushPermission, setPushPermission] = useState<NotificationPermission>("default");
  const [pushStatus, setPushStatus] = useState<"idle" | "working" | "ready" | "error">("idle");
  const [pushMessage, setPushMessage] = useState("");
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [watchErrors, setWatchErrors] = useState(0);
  const [indexes, setIndexes] = useState<IndexItem[]>([]);
  const [market, setMarket] = useState<MarketDetail | null>(null);
  const [newsData, setNewsData] = useState<NewsData | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [kapData, setKapData] = useState<KapData | null>(null);
  const [kapLoading, setKapLoading] = useState(false);
  const [scannerData, setScannerData] = useState<ScannerData | null>(null);
  const [scannerLoading, setScannerLoading] = useState(false);
  const [alertData, setAlertData] = useState<AlertSettingsData | null>(null);
  const [alertLoading, setAlertLoading] = useState(false);
  const [alertSaving, setAlertSaving] = useState(false);
  const [alertMessage, setAlertMessage] = useState("");
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [pwaMessage, setPwaMessage] = useState("");

  const quote = useMemo(() => dailyQuote(), []);

  const filteredStocks = useMemo(() => {
    const q = search.trim().toUpperCase();
    if (!q) return watchlist;
    return watchlist.filter((x) => x.symbol.includes(q));
  }, [search, watchlist]);

  const loadData = useCallback(async () => {
    try {
      const [healthRes, statusRes, noteRes] = await Promise.all([
        fetch(`${API_BASE}/health`, { cache: "no-store" }),
        fetch(`${API_BASE}/paper/status`, { cache: "no-store" }),
        fetch(`${API_BASE}/paper/notifications/unread`, { cache: "no-store" }),
      ]);
      setBackendOnline(healthRes.ok);
      if (statusRes.ok) setStatus(await statusRes.json());
      if (noteRes.ok) {
        const data = await noteRes.json();
        setNotes(data.notifications || []);
      }
    } catch {
      setBackendOnline(false);
    }
  }, []);

  const loadMarketLists = useCallback(async () => {
    try {
      const [watchRes, indexRes] = await Promise.all([
        fetch(`${API_BASE}/market/watchlist`, { cache: "no-store" }),
        fetch(`${API_BASE}/market-indexes`, { cache: "no-store" }),
      ]);

      if (watchRes.ok) {
        const data = await watchRes.json();
        setWatchlist(data.results || []);
        setWatchErrors((data.errors || []).length);
      }

      if (indexRes.ok) {
        const data = await indexRes.json();
        setIndexes(data.results || []);
      }
    } catch {
      // Paper panel calismaya devam etsin; market liste hatasi sayfayi bozmasin.
    }
  }, []);


  const loadPaperDetails = useCallback(async () => {
    setPaperLoading(true);
    try {
      const [tradesRes, notesRes] = await Promise.all([
        fetch(`${API_BASE}/paper/trades`, { cache: "no-store" }),
        fetch(`${API_BASE}/paper/notifications?limit=100`, { cache: "no-store" }),
      ]);

      if (tradesRes.ok) {
        const data = await tradesRes.json();
        setClosedTrades(data.closed_trades || []);
      }

      if (notesRes.ok) {
        const data = await notesRes.json();
        setPaperNotes(data.notifications || []);
      }
    } catch {
      // Ana terminal calismaya devam etsin.
    } finally {
      setPaperLoading(false);
    }
  }, []);

  const loadAlertSettings = useCallback(async () => {
    setAlertLoading(true);
    try {
      const res = await fetch(`${API_BASE}/alerts/settings`, { cache: "no-store" });
      if (res.ok) {
        setAlertData(await res.json());
      } else {
        setAlertData(null);
      }
    } catch {
      setAlertData(null);
    } finally {
      setAlertLoading(false);
    }
  }, []);

  const saveAlertSettings = useCallback(async (settings: AlertSettings) => {
    setAlertSaving(true);
    setAlertMessage("");
    try {
      const res = await fetch(`${API_BASE}/alerts/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: settings.enabled,
          strong_candidate_enabled: settings.strong_candidate_enabled,
          strong_candidate_min_score: settings.strong_candidate_min_score,
          exact_v72_enabled: settings.exact_v72_enabled,
        }),
      });
      if (!res.ok) throw new Error("Alarm ayarlari kaydedilemedi.");
      const saved = await res.json();
      setAlertData(prev => prev ? {...prev, settings: saved.settings} : prev);
      setAlertMessage("Alarm ayarlari kaydedildi.");
    } catch (err) {
      setAlertMessage(err instanceof Error ? err.message : "Kaydetme hatasi.");
    } finally {
      setAlertSaving(false);
    }
  }, []);

  const checkAlertsNow = useCallback(async () => {
    setAlertLoading(true);
    setAlertMessage("");
    try {
      const res = await fetch(`${API_BASE}/alerts/check-now`, { method: "POST" });
      const result = await res.json();
      if (!res.ok) throw new Error("Alarm taramasi basarisiz.");
      setAlertMessage(
        `Tarama tamamlandi: ${result.checked ?? 0} hisse, ${result.alerts_created ?? 0} yeni bildirim.`
      );
      await loadAlertSettings();
      await loadData();
    } catch (err) {
      setAlertMessage(err instanceof Error ? err.message : "Alarm taramasi hatasi.");
    } finally {
      setAlertLoading(false);
    }
  }, [loadAlertSettings, loadData]);

  const loadScanner = useCallback(async (force = false) => {
    setScannerLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/scanner/candidates?limit=20&min_score=50&refresh=${force ? "true" : "false"}`,
        { cache: "no-store" }
      );
      if (res.ok) {
        setScannerData(await res.json());
      } else {
        setScannerData(null);
      }
    } catch {
      setScannerData(null);
    } finally {
      setScannerLoading(false);
    }
  }, []);

  const loadNews = useCallback(async (symbol: string) => {
    setNewsLoading(true);
    setKapLoading(true);

    try {
      const [newsRes, kapRes] = await Promise.all([
        fetch(`${API_BASE}/news/${symbol}?limit=12`, { cache: "no-store" }),
        fetch(`${API_BASE}/kap/${symbol}?days=30&limit=20`, { cache: "no-store" }),
      ]);

      if (newsRes.ok) {
        setNewsData(await newsRes.json());
      } else {
        setNewsData(null);
      }

      if (kapRes.ok) {
        setKapData(await kapRes.json());
      } else {
        setKapData(null);
      }
    } catch {
      setNewsData(null);
      setKapData(null);
    } finally {
      setNewsLoading(false);
      setKapLoading(false);
    }
  }, []);


  useEffect(() => {
    if (typeof window === "undefined") return;

    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as any).standalone === true;
    setIsStandalone(standalone);

    const handler = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };

    window.addEventListener("beforeinstallprompt", handler);

    navigator.serviceWorker?.register("/firebase-messaging-sw.js").catch(() => {});

    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  const installPwa = useCallback(async () => {
    setPwaMessage("");
    if (isStandalone) {
      setPwaMessage("Uygulama zaten kurulu.");
      return;
    }

    if (!installPrompt) {
      setPwaMessage("Kurulum düğmesi henüz tarayıcı tarafından hazır değil. HTTPS üzerinden açınca tekrar dene.");
      return;
    }

    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    if (choice.outcome === "accepted") {
      setPwaMessage("Uygulama kurulumu başlatıldı.");
      setInstallPrompt(null);
    } else {
      setPwaMessage("Kurulum iptal edildi.");
    }
  }, [installPrompt, isStandalone]);

  useEffect(() => {
    if (mainView !== "settings") return;
    loadAlertSettings();
  }, [mainView, loadAlertSettings]);

  useEffect(() => {
    if (mainView !== "scanner") return;
    loadScanner(false);
  }, [mainView, loadScanner]);

  useEffect(() => {
    if (mainView !== "news") return;
    loadNews(selected);
  }, [mainView, selected, loadNews]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const supported =
      "serviceWorker" in navigator &&
      "Notification" in window &&
      "PushManager" in window;
    setPushSupported(supported);
    if ("Notification" in window) {
      setPushPermission(Notification.permission);
    }
  }, []);

  const enablePushNotifications = useCallback(async () => {
    setPushMessage("");

    if (!pushSupported) {
      setPushStatus("error");
      setPushMessage("Bu tarayıcı web push bildirimini desteklemiyor.");
      return;
    }

    setPushStatus("working");
    try {
      const permission = await Notification.requestPermission();
      setPushPermission(permission);

      if (permission !== "granted") {
        throw new Error("Bildirim izni verilmedi.");
      }

      const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
      await navigator.serviceWorker.ready;

      const configRes = await fetch(`${API_BASE}/push/public-config`, { cache: "no-store" });
      if (!configRes.ok) throw new Error("Firebase ayarları backend'den alınamadı.");

      const cfg = await configRes.json();
      if (!cfg.enabled || !cfg.vapid_key) {
        throw new Error("Firebase ayarları henüz tamamlanmamış.");
      }

      // Next.js/Turbopack ile uzak URL import etmek yerine
      // proje içindeki resmi Firebase npm paketini kullan.
      const appMod = await import("firebase/app");
      const msgMod = await import("firebase/messaging");

      const apps = appMod.getApps();
      const firebaseApp = apps.length ? apps[0] : appMod.initializeApp(cfg.firebase_config);
      const messaging = msgMod.getMessaging(firebaseApp);

      const token = await msgMod.getToken(messaging, {
        vapidKey: cfg.vapid_key,
        serviceWorkerRegistration: registration,
      });

      if (!token) throw new Error("FCM token alınamadı.");

      const registerRes = await fetch(`${API_BASE}/push/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          user_agent: navigator.userAgent,
          platform: navigator.platform || "web",
        }),
      });

      if (!registerRes.ok) throw new Error("Push token backend'e kaydedilemedi.");

      setPushStatus("ready");
      setPushMessage("Push bildirimi aktif.");
    } catch (err) {
      setPushStatus("error");
      setPushMessage(err instanceof Error ? err.message : "Push kurulumu başarısız.");
    }
  }, [pushSupported]);

  const testPush = useCallback(async () => {
    setPushStatus("working");
    setPushMessage("");
    try {
      const res = await fetch(`${API_BASE}/push/test`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Test bildirimi gönderilemedi.");
      setPushStatus("ready");
      setPushMessage(`Test bildirimi gönderildi. Başarılı: ${data.success ?? 0}`);
    } catch (err) {
      setPushStatus("error");
      setPushMessage(err instanceof Error ? err.message : "Test bildirimi başarısız.");
    }
  }, []);

  const loadNotificationCenter = useCallback(async () => {
    setNotificationLoading(true);
    try {
      const res = await fetch(`${API_BASE}/paper/notifications/unread`, { cache: "no-store" });
      if (res.ok) {
        const data = await res.json();
        setNotificationItems(data.notifications || []);
      }
    } catch {
      // Bildirim kutusu hata verse de terminal calismaya devam etsin.
    } finally {
      setNotificationLoading(false);
    }
  }, []);

  const markAllNotificationsRead = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/paper/notifications/read-all`, {
        method: "POST",
      });
      setNotificationItems([]);
      await loadData();
    } catch {
      // Sessizce devam et.
    }
  }, [loadData]);

  useEffect(() => {
    loadData();
    loadMarketLists();

    const statusPoll = window.setInterval(loadData, 30000);
    const marketPoll = window.setInterval(loadMarketLists, 120000);
    const timer = window.setInterval(() => setClock(new Date()), 1000);

    return () => {
      window.clearInterval(statusPoll);
      window.clearInterval(marketPoll);
      window.clearInterval(timer);
    };
  }, [loadData, loadMarketLists]);

  useEffect(() => {
    if (!notificationOpen) return;
    loadNotificationCenter();
  }, [notificationOpen, loadNotificationCenter]);

  useEffect(() => {
    if (mainView !== "paper" && mainView !== "performance") return;

    loadPaperDetails();
    const id = window.setInterval(loadPaperDetails, 60000);
    return () => window.clearInterval(id);
  }, [mainView, loadPaperDetails]);

  useEffect(() => {
    let cancelled = false;
    async function loadSelected() {
      try {
        const res = await fetch(`${API_BASE}/market/${selected}?timeframe=1h&chart_range=${chartRange}`, { cache: "no-store" });
        const data = await res.json();
        if (!cancelled && data.status === "ok") setMarket(data);
        if (!cancelled && data.status !== "ok") setMarket(null);
      } catch {
        if (!cancelled) setMarket(null);
      }
    }
    loadSelected();
    const id = window.setInterval(loadSelected, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [selected, chartRange]);

  const metrics = status?.metrics;
  const openPositions = status?.open_positions || [];
  const selectedPosition = openPositions.find((p) => p.symbol === selected);

  return (
    <main className="terminal-shell">
      <aside className="left-rail">
        <div className="brand">
          <div className="brand-crown">♛</div>
          <div>
            <strong>BIST Katılım Terminal</strong>
            <span>Disiplin · Analiz · Strateji</span>
          </div>
        </div>

        <div className="rail-title">◎ BIST KATILIM 50 <em>Örnek</em></div>

        <div className="rail-search">
          <span>⌕</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Hisse ara..."
          />
        </div>

        <div className="stock-head">
          <span>Hisse</span><span>Son Fiyat</span><span>%Gün</span>
        </div>

        <div className="stock-scroll">
          {filteredStocks.map((item) => {
            const pos = item.daily_change_pct >= 0;
            return (
              <button
                className={`stock-row ${selected === item.symbol ? "selected" : ""}`}
                key={item.symbol}
                onClick={() => setSelected(item.symbol)}
              >
                <b>{item.symbol}</b>
                <span className="spark">⌁</span>
                <span>{item.last_price.toLocaleString("tr-TR", { maximumFractionDigits: 2 })}</span>
                <span className={pos ? "pos" : "neg"}>{fmtPct(item.daily_change_pct)}</span>
              </button>
            );
          })}
        </div>

        <div className="rail-bottom">
          <button>{watchlist.length} hisse yüklendi · {watchErrors} veri hatası</button>
          <div className="mini-system">
            <span className={`dot ${backendOnline ? "ok" : "bad"}`} />
            <div>
              <b>{backendOnline ? "Sistem çalışıyor" : "Backend kapalı"}</b>
              <small>{status ? `Tarama ${status.auto_scan_every_minutes} dk` : "Bağlantı bekleniyor"}</small>
            </div>
          </div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="search-wide">⌕ <span>Hisse ara... (örn. TUPRS)</span></div>
          <nav className="main-nav">
            <button
              className={mainView === "home" ? "active" : ""}
              onClick={() => {
                setMainView("home");
                setAnalysisTab("chart");
              }}
            >
              ⌂ Ana Sayfa
            </button>
            <button
              className={mainView === "scanner" ? "active" : ""}
              onClick={() => setMainView("scanner")}
            >
              ⚡ Güçlü Adaylar
            </button>

            <div className="nav-dropdown">
              <button
                className={analysisMenuOpen ? "nav-drop-active" : ""}
                onClick={() => setAnalysisMenuOpen((v) => !v)}
              >
                ◫ Analiz ▾
              </button>

              {analysisMenuOpen && (
                <div className="analysis-dropdown-menu">
                  <button onClick={() => {
                    setMainView("home");
                    setAnalysisTab("chart");
                    setAnalysisMenuOpen(false);
                  }}>
                    Grafik
                  </button>
                  <button onClick={() => {
                    setMainView("home");
                    setAnalysisTab("support");
                    setAnalysisMenuOpen(false);
                  }}>
                    Destek - Direnç
                  </button>
                  <button onClick={() => {
                    setMainView("home");
                    setAnalysisTab("fibonacci");
                    setAnalysisMenuOpen(false);
                  }}>
                    Fibonacci
                  </button>
                  <button onClick={() => {
                    setMainView("home");
                    setAnalysisTab("indicators");
                    setAnalysisMenuOpen(false);
                  }}>
                    Göstergeler
                  </button>
                  <button onClick={() => {
                    setMainView("home");
                    setAnalysisTab("patterns");
                    setAnalysisMenuOpen(false);
                  }}>
                    Formasyonlar
                  </button>
                </div>
              )}
            </div>

            <button
              className={mainView === "paper" ? "active" : ""}
              onClick={() => setMainView("paper")}
            >
              ⌁ Paper Trading
            </button>
            <button
              className={mainView === "performance" ? "active" : ""}
              onClick={() => setMainView("performance")}
            >
              ▤ Performans
            </button>
            <button
              className={mainView === "news" ? "active" : ""}
              onClick={() => setMainView("news")}
            >
              ▣ KAP / Haberler
            </button>
            <button
              className={`nav-candle ${mainView === "candles" ? "active" : ""}`}
              onClick={() => setMainView("candles")}
            >
              ▥ Mum Analizi
            </button>
            <button
              className={mainView === "settings" ? "active" : ""}
              onClick={() => setMainView("settings")}
            >
              ⚙ Ayarlar
            </button>
          </nav>
          <div className="top-status">
            <span className="market-pill"><i />Piyasa</span>
            <strong>{clock.toLocaleTimeString("tr-TR")}</strong>
            <button onClick={loadData}>↻</button>
            <div className="notify-wrap">
              <button
                className={`notify ${notificationOpen ? "notify-active" : ""}`}
                onClick={() => setNotificationOpen((v) => !v)}
                aria-label="Bildirimler"
              >
                ♢
                <b>{status?.unread_notifications || 0}</b>
              </button>

              {notificationOpen && (
                <div className="notification-center">
                  <div className="notification-center-head">
                    <div>
                      <strong>Bildirimler</strong>
                      <span>{status?.unread_notifications || 0} okunmamış</span>
                    </div>
                    <button
                      onClick={markAllNotificationsRead}
                      disabled={!notificationItems.length}
                    >
                      Tümünü okundu yap
                    </button>
                  </div>

                  <div className="notification-center-list">
                    {notificationLoading ? (
                      <div className="notification-empty">Yükleniyor…</div>
                    ) : notificationItems.length ? (
                      notificationItems.slice(0, 15).map((n) => (
                        <article className={`notification-entry notification-${n.kind.toLowerCase()}`} key={n.id}>
                          <div className="notification-entry-icon">
                            {n.kind === "NEW_SIGNAL" ? "↗" : n.kind === "TRADE_CLOSED" ? "✓" : "•"}
                          </div>
                          <div className="notification-entry-body">
                            <b>{n.title}</b>
                            <span>{n.message}</span>
                            <time>{fmtDateTime(n.created_at)}</time>
                          </div>
                        </article>
                      ))
                    ) : (
                      <div className="notification-empty">
                        <span>♢</span>
                        <b>Yeni bildirim yok</b>
                        <small>Yeni paper sinyali veya kapanış olduğunda burada görünecek.</small>
                      </div>
                    )}
                  </div>

                  <div className="push-setup">
                    <div className="push-setup-top">
                      <div>
                        <b>Telefon Bildirimi</b>
                        <span>
                          {!pushSupported
                            ? "Desteklenmiyor"
                            : pushPermission === "granted"
                              ? "Tarayıcı izni açık"
                              : "Henüz etkin değil"}
                        </span>
                      </div>
                      <i className={
                        pushStatus === "ready"
                          ? "push-dot ready"
                          : pushStatus === "error"
                            ? "push-dot error"
                            : "push-dot"
                      } />
                    </div>

                    <div className="push-actions">
                      <button
                        onClick={enablePushNotifications}
                        disabled={!pushSupported || pushStatus === "working"}
                      >
                        {pushStatus === "working" ? "Bekle…" : "Push'u Etkinleştir"}
                      </button>
                      <button
                        onClick={testPush}
                        disabled={pushPermission !== "granted" || pushStatus === "working"}
                      >
                        Test Gönder
                      </button>
                    </div>

                    {pushMessage && (
                      <small className={pushStatus === "error" ? "push-msg error" : "push-msg"}>
                        {pushMessage}
                      </small>
                    )}
                  </div>

                  <div className="notification-center-foot">
                    <button onClick={() => {
                      setMainView("paper");
                      setNotificationOpen(false);
                    }}>
                      Paper Trading ekranına git
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>

        {mainView === "home" && (
          <>
        <section className="summary-row">
          {["BIST 100", "BIST 30", "BIST KATILIM 50"].map((name) => {
            const idx = indexes.find((x) => x.name === name);
            return (
              <MarketCard
                key={name}
                name={name}
                value={idx?.value != null ? idx.value.toLocaleString("tr-TR", { maximumFractionDigits: 2 }) : "—"}
                sub={idx ? `${fmtPct(idx.daily_change_pct)}${(idx as any).proxy ? " · 50 hisse ort." : ""}` : "Veri yok"}
              />
            );
          })}
          <Metric name="Toplam Getiri (Paper)" value={fmtPct(metrics?.total_compounded_return_pct ?? 0)} />
          <Metric name="Açık İşlem" value={String(openPositions.length)} />
          <Metric name="Kazanma Oranı" value={fmtPct(metrics?.win_rate_pct ?? 0, 0)} />
        </section>

        <section className="core-grid">
          <section className="analysis-card">
            <div className="analysis-header">
              <div>
                <span className="eyebrow">Seçili Hisse Analizi</span>
                <h1>{selected}</h1>
                <small>
                  {market ? `Sinyal: ${market.signal.value} · ${market.signal.strategy}` : "Veri yükleniyor"}
                </small>
              </div>

            </div>

            <div className="price-line">
              <strong>{market ? market.price.last.toLocaleString("tr-TR", { maximumFractionDigits: 2 }) : "—"}</strong>
              <span className={market && market.price.daily_change_pct >= 0 ? "pos" : "neg"}>
                {market ? fmtPct(market.price.daily_change_pct) : "Veri bekleniyor"}
              </span>
              <span className="muted">{market ? `${market.source} · resmi real-time feed değil` : ""}</span>
            </div>

            <div className="technical-summary">
              <span className="summary-label">Teknik Özet</span>
              <span>
                <b>Sinyal</b>
                <em>{market?.signal.value ?? "—"}</em>
              </span>
              <span>
                <b>Trend</b>
                <em>
                  {market?.indicators.adx14 != null
                    ? market.indicators.adx14 >= 25
                      ? "Güçlü"
                      : "Zayıf"
                    : "—"}
                </em>
              </span>
              <span>
                <b>RSI</b>
                <em>{market?.indicators.rsi14?.toFixed(1) ?? "—"}</em>
              </span>
              <span>
                <b>MACD</b>
                <em>
                  {market?.indicators.macd_hist != null
                    ? market.indicators.macd_hist > 0
                      ? "Pozitif"
                      : "Negatif"
                    : "—"}
                </em>
              </span>
              <span>
                <b>Destek</b>
                <em>{market?.support_resistance.s1?.toFixed(2) ?? "—"}</em>
              </span>
              <span>
                <b>Direnç</b>
                <em>{market?.support_resistance.r1?.toFixed(2) ?? "—"}</em>
              </span>
            </div>

            {analysisTab === "support" && (
              <section className="support-detail-view">
                <div className="support-range-bar">
                  <span>Grafik Aralığı</span>
                  <div>
                    <button
                      className={chartRange === "1d" ? "active" : ""}
                      onClick={() => setChartRange("1d")}
                    >
                      1 Gün
                    </button>
                    <button
                      className={chartRange === "1w" ? "active" : ""}
                      onClick={() => setChartRange("1w")}
                    >
                      1 Hafta
                    </button>
                  </div>
                  <small>
                    {chartRange === "1d"
                      ? "Son işlem gününün 15 dk mumları"
                      : "Son 7 günün 1 saatlik mumları"}
                  </small>
                </div>
                {(() => {
                  const price = market?.price.last ?? null;
                  const sr = market?.support_resistance;
                  const supports = [sr?.s1, sr?.s2, sr?.s3]
                    .filter((v): v is number => v != null)
                    .sort((a,b) => b - a);
                  const resistances = [sr?.r1, sr?.r2, sr?.r3]
                    .filter((v): v is number => v != null)
                    .sort((a,b) => a - b);

                  const nearestSupport = price != null
                    ? supports.find((v) => v <= price) ?? supports[0] ?? null
                    : null;
                  const nearestResistance = price != null
                    ? resistances.find((v) => v >= price) ?? resistances[0] ?? null
                    : null;

                  const supportDistance = price != null && nearestSupport != null
                    ? ((price - nearestSupport) / price) * 100
                    : null;
                  const resistanceDistance = price != null && nearestResistance != null
                    ? ((nearestResistance - price) / price) * 100
                    : null;

                  let shortNote = "Seviye verisi bekleniyor.";
                  if (price != null && nearestSupport != null && nearestResistance != null) {
                    if (supportDistance != null && supportDistance <= 1.5) {
                      shortNote = "Fiyat en yakın desteğe oldukça yakın.";
                    } else if (resistanceDistance != null && resistanceDistance <= 1.5) {
                      shortNote = "Fiyat en yakın dirence yaklaşıyor.";
                    } else {
                      shortNote = "Fiyat destek ile direnç arasında orta bölgede.";
                    }
                  }

                  const chartBars = market?.chart?.slice(-80) ?? [];
                  const highs = chartBars.map((b) => b.high);
                  const lows = chartBars.map((b) => b.low);
                  const maxP = highs.length ? Math.max(...highs) : 1;
                  const minP = lows.length ? Math.min(...lows) : 0;
                  const pRange = Math.max(maxP - minP, 0.0001);
                  const yPrice = (v: number) => 15 + ((maxP - v) / pRange) * 210;

                  return (
                    <>
                      <div className="support-kpis">
                        <div>
                          <span>Güncel Fiyat</span>
                          <strong>{price != null ? price.toFixed(2) : "—"}</strong>
                        </div>
                        <div className="support-kpi-green">
                          <span>En Yakın Destek</span>
                          <strong>{nearestSupport != null ? nearestSupport.toFixed(2) : "—"}</strong>
                          <small>{supportDistance != null ? `Fiyata uzaklık %${supportDistance.toFixed(2)}` : ""}</small>
                        </div>
                        <div className="support-kpi-red">
                          <span>En Yakın Direnç</span>
                          <strong>{nearestResistance != null ? nearestResistance.toFixed(2) : "—"}</strong>
                          <small>{resistanceDistance != null ? `Fiyata uzaklık %${resistanceDistance.toFixed(2)}` : ""}</small>
                        </div>
                        <div>
                          <span>Pivot</span>
                          <strong>{sr?.pivot?.toFixed(2) ?? "—"}</strong>
                          <small>Classic Pivot · önceki tamamlanmış gün</small>
                        </div>
                      </div>

                      <div className="support-note">
                        <b>Kısa Yorum</b>
                        <span>{shortNote}</span>
                      </div>

                      <div className="support-detail-grid">
                        <div className="support-level-table">
                          <div className="support-level-head">
                            <span>Seviye</span><span>Fiyat</span><span>Tür</span>
                          </div>
                          {[
                            ["R3", sr?.r3, "Direnç"],
                            ["R2", sr?.r2, "Direnç"],
                            ["R1", sr?.r1, "Direnç"],
                            ["P", sr?.pivot, "Pivot"],
                            ["S1", sr?.s1, "Destek"],
                            ["S2", sr?.s2, "Destek"],
                            ["S3", sr?.s3, "Destek"],
                          ].map(([name, value, kind]) => (
                            <div className="support-level-row" key={String(name)}>
                              <b className={String(kind) === "Direnç" ? "sr-red" : String(kind) === "Destek" ? "sr-green" : "sr-gold"}>
                                {String(name)}
                              </b>
                              <span>{typeof value === "number" ? value.toFixed(2) : "—"}</span>
                              <em>{String(kind)}</em>
                            </div>
                          ))}
                        </div>

                        <div className="support-mini-chart candlestick-box">
                          {chartBars.length ? (
                            <svg viewBox="0 0 760 250" preserveAspectRatio="none">
                              <g className="gridlines">
                                <line x1="0" y1="50" x2="760" y2="50"/>
                                <line x1="0" y1="100" x2="760" y2="100"/>
                                <line x1="0" y1="150" x2="760" y2="150"/>
                                <line x1="0" y1="200" x2="760" y2="200"/>
                              </g>

                              {(() => {
                                const slot = 760 / chartBars.length;
                                const bodyW = Math.max(2.2, slot * 0.55);
                                return chartBars.map((b, i) => {
                                  const x = i * slot + slot / 2;
                                  const up = b.close >= b.open;
                                  const yO = yPrice(b.open);
                                  const yC = yPrice(b.close);
                                  const yH = yPrice(b.high);
                                  const yL = yPrice(b.low);
                                  const y = Math.min(yO, yC);
                                  const h = Math.max(Math.abs(yC - yO), 1.3);
                                  return (
                                    <g key={`sr-${b.time}-${i}`} className={up ? "candle-up" : "candle-down"}>
                                      <line x1={x} y1={yH} x2={x} y2={yL} className="wick" />
                                      <rect x={x-bodyW/2} y={y} width={bodyW} height={h} className="body" />
                                    </g>
                                  );
                                });
                              })()}

                              {[
                                {name:"R3", value:sr?.r3, cls:"sr-line-red"},
                                {name:"R2", value:sr?.r2, cls:"sr-line-red"},
                                {name:"R1", value:sr?.r1, cls:"sr-line-red"},
                                {name:"P", value:sr?.pivot, cls:"sr-line-gold"},
                                {name:"S1", value:sr?.s1, cls:"sr-line-green"},
                                {name:"S2", value:sr?.s2, cls:"sr-line-green"},
                                {name:"S3", value:sr?.s3, cls:"sr-line-green"},
                              ].filter((lv) => lv.value != null).map((lv) => {
                                const y = yPrice(Number(lv.value));
                                return (
                                  <g key={lv.name} className={lv.cls}>
                                    <line x1="0" y1={y} x2="760" y2={y} />
                                    <text x="748" y={y-3} textAnchor="end">{lv.name} {Number(lv.value).toFixed(2)}</text>
                                  </g>
                                );
                              })}
                            </svg>
                          ) : (
                            <div className="chart-loading">Grafik verisi bekleniyor…</div>
                          )}
                        </div>
                      </div>
                    </>
                  );
                })()}
              </section>
            )}

            {analysisTab === "fibonacci" && (
              <section className="fibonacci-detail-view">
                {(() => {
                  const bars = market?.chart?.slice(-80) ?? [];
                  if (!bars.length) {
                    return <div className="chart-loading">Fibonacci için grafik verisi bekleniyor…</div>;
                  }

                  const swingLowBar = bars.reduce((a, b) => b.low < a.low ? b : a, bars[0]);
                  const swingHighBar = bars.reduce((a, b) => b.high > a.high ? b : a, bars[0]);
                  const low = swingLowBar.low;
                  const high = swingHighBar.high;
                  const range = Math.max(high - low, 0.0001);

                  const fibs = [
                    { ratio: 0.000, label: "0.0%", price: high },
                    { ratio: 0.236, label: "23.6%", price: high - range * 0.236 },
                    { ratio: 0.382, label: "38.2%", price: high - range * 0.382 },
                    { ratio: 0.500, label: "50.0%", price: high - range * 0.500 },
                    { ratio: 0.618, label: "61.8%", price: high - range * 0.618 },
                    { ratio: 0.786, label: "78.6%", price: high - range * 0.786 },
                    { ratio: 1.000, label: "100%", price: low },
                  ];

                  const current = market?.price.last ?? null;
                  const nearest = current != null
                    ? fibs.reduce((best, x) =>
                        Math.abs(x.price - current) < Math.abs(best.price - current) ? x : best,
                        fibs[0]
                      )
                    : null;

                  const highs = bars.map((b) => b.high);
                  const lows = bars.map((b) => b.low);
                  const maxP = Math.max(...highs, ...fibs.map((x) => x.price));
                  const minP = Math.min(...lows, ...fibs.map((x) => x.price));
                  const pRange = Math.max(maxP - minP, 0.0001);
                  const yPrice = (v: number) => 15 + ((maxP - v) / pRange) * 210;

                  return (
                    <>
                      <div className="fib-range-bar">
                        <span>Grafik Aralığı</span>
                        <div>
                          <button
                            className={chartRange === "1d" ? "active" : ""}
                            onClick={() => setChartRange("1d")}
                          >
                            1 Gün
                          </button>
                          <button
                            className={chartRange === "1w" ? "active" : ""}
                            onClick={() => setChartRange("1w")}
                          >
                            1 Hafta
                          </button>
                        </div>
                        <small>
                          Otomatik dip/tepe: son {bars.length} mum
                        </small>
                      </div>

                      <div className="fib-kpis">
                        <div>
                          <span>Seçilen Dip</span>
                          <strong>{low.toFixed(2)}</strong>
                          <small>{new Intl.DateTimeFormat("tr-TR", {
                            day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit",
                            timeZone:"Europe/Istanbul"
                          }).format(new Date(swingLowBar.time))}</small>
                        </div>
                        <div>
                          <span>Seçilen Tepe</span>
                          <strong>{high.toFixed(2)}</strong>
                          <small>{new Intl.DateTimeFormat("tr-TR", {
                            day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit",
                            timeZone:"Europe/Istanbul"
                          }).format(new Date(swingHighBar.time))}</small>
                        </div>
                        <div>
                          <span>Güncel Fiyat</span>
                          <strong>{current != null ? current.toFixed(2) : "—"}</strong>
                        </div>
                        <div>
                          <span>En Yakın Fib</span>
                          <strong>{nearest ? `${nearest.label} · ${nearest.price.toFixed(2)}` : "—"}</strong>
                        </div>
                      </div>

                      <div className="fib-note">
                        <b>Nasıl seçildi?</b>
                        <span>
                          Seçili zaman aralığındaki en düşük dip ile en yüksek tepe otomatik alındı.
                          Bu seviye analizi destek/direnç adayıdır; tek başına al/sat kararı değildir.
                        </span>
                      </div>

                      <div className="fib-grid">
                        <div className="fib-table">
                          <div className="fib-head"><span>Seviye</span><span>Fiyat</span></div>
                          {fibs.map((f) => (
                            <div className="fib-row" key={f.label}>
                              <b>{f.label}</b>
                              <span>{f.price.toFixed(2)}</span>
                            </div>
                          ))}
                        </div>

                        <div className="fib-chart candlestick-box">
                          <svg viewBox="0 0 760 250" preserveAspectRatio="none">
                            <g className="gridlines">
                              <line x1="0" y1="50" x2="760" y2="50"/>
                              <line x1="0" y1="100" x2="760" y2="100"/>
                              <line x1="0" y1="150" x2="760" y2="150"/>
                              <line x1="0" y1="200" x2="760" y2="200"/>
                            </g>

                            {(() => {
                              const slot = 760 / bars.length;
                              const bodyW = Math.max(2.2, slot * 0.55);
                              return bars.map((b, i) => {
                                const x = i * slot + slot / 2;
                                const up = b.close >= b.open;
                                const yO = yPrice(b.open);
                                const yC = yPrice(b.close);
                                const yH = yPrice(b.high);
                                const yL = yPrice(b.low);
                                const y = Math.min(yO, yC);
                                const h = Math.max(Math.abs(yC - yO), 1.3);
                                return (
                                  <g key={`fib-${b.time}-${i}`} className={up ? "candle-up" : "candle-down"}>
                                    <line x1={x} y1={yH} x2={x} y2={yL} className="wick" />
                                    <rect x={x-bodyW/2} y={y} width={bodyW} height={h} className="body" />
                                  </g>
                                );
                              });
                            })()}

                            {fibs.map((f, i) => {
                              const y = yPrice(f.price);
                              return (
                                <g key={`fibline-${f.label}`} className={`fib-line fib-line-${i}`}>
                                  <line x1="0" y1={y} x2="760" y2={y} />
                                  <text x="748" y={y-3} textAnchor="end">
                                    {f.label} · {f.price.toFixed(2)}
                                  </text>
                                </g>
                              );
                            })}
                          </svg>
                        </div>
                      </div>
                    </>
                  );
                })()}
              </section>
            )}

            {analysisTab === "indicators" && (
              <section className="indicators-detail-view">
                {(() => {
                  const ind = market?.indicators;
                  const price = market?.price.last ?? null;

                  const rsiStatus =
                    ind?.rsi14 == null ? "Veri yok" :
                    ind.rsi14 >= 70 ? "Aşırı alım" :
                    ind.rsi14 <= 30 ? "Aşırı satım" : "Nötr";

                  const macdStatus =
                    ind?.macd_hist == null ? "Veri yok" :
                    ind.macd_hist > 0 ? "Pozitif" : "Negatif";

                  const adxStatus =
                    ind?.adx14 == null ? "Veri yok" :
                    ind.adx14 >= 25 ? "Trend güçlü" :
                    ind.adx14 >= 18 ? "Trend orta" : "Trend zayıf";

                  const emaTrend =
                    ind?.ema20 != null && ind?.ema50 != null && ind?.ema200 != null && price != null
                      ? price > ind.ema20 && ind.ema20 > ind.ema50 && ind.ema50 > ind.ema200
                        ? "Yükseliş eğilimi"
                        : price < ind.ema20 && ind.ema20 < ind.ema50 && ind.ema50 < ind.ema200
                          ? "Düşüş eğilimi"
                          : "Karışık / yatay"
                      : "Veri yok";

                  const atrStatus =
                    ind?.atr14 == null || price == null
                      ? "Veri yok"
                      : ((ind.atr14 / price) * 100) >= 3
                        ? "Volatilite yüksek"
                        : ((ind.atr14 / price) * 100) >= 1.5
                          ? "Volatilite orta"
                          : "Volatilite düşük";

                  const volumeStatus =
                    ind?.volume_ratio == null ? "Veri yok" :
                    ind.volume_ratio >= 1.2 ? "Hacim güçlü" :
                    ind.volume_ratio >= 0.8 ? "Hacim normal" : "Hacim zayıf";

                  let positive = 0;
                  let negative = 0;

                  if (ind?.rsi14 != null) {
                    if (ind.rsi14 >= 45 && ind.rsi14 <= 65) positive += 1;
                    if (ind.rsi14 >= 75 || ind.rsi14 <= 25) negative += 1;
                  }
                  if (ind?.macd_hist != null) {
                    if (ind.macd_hist > 0) positive += 1;
                    else negative += 1;
                  }
                  if (ind?.adx14 != null) {
                    if (ind.adx14 >= 25) positive += 1;
                    if (ind.adx14 < 17) negative += 1;
                  }
                  if (ind?.ema20 != null && ind?.ema50 != null && ind?.ema200 != null && price != null) {
                    if (price > ind.ema20 && ind.ema20 > ind.ema50 && ind.ema50 > ind.ema200) positive += 2;
                    if (price < ind.ema20 && ind.ema20 < ind.ema50 && ind.ema50 < ind.ema200) negative += 2;
                  }
                  if (ind?.volume_ratio != null) {
                    if (ind.volume_ratio >= 1.0) positive += 1;
                    if (ind.volume_ratio < 0.7) negative += 1;
                  }

                  const technicalState =
                    positive >= negative + 2 ? "Pozitif teknik görünüm" :
                    negative >= positive + 2 ? "Zayıf teknik görünüm" :
                    "Nötr / karışık görünüm";

                  const technicalClass =
                    positive >= negative + 2 ? "indicator-positive" :
                    negative >= positive + 2 ? "indicator-negative" :
                    "indicator-neutral";

                  const emaBars = [
                    { label:"Fiyat", value:price, cls:"price" },
                    { label:"EMA20", value:ind?.ema20 ?? null, cls:"ema20" },
                    { label:"EMA50", value:ind?.ema50 ?? null, cls:"ema50" },
                    { label:"EMA200", value:ind?.ema200 ?? null, cls:"ema200" },
                  ].filter((x): x is {label:string; value:number; cls:string} => x.value != null);

                  const emaMin = emaBars.length ? Math.min(...emaBars.map(x => x.value)) : 0;
                  const emaMax = emaBars.length ? Math.max(...emaBars.map(x => x.value)) : 1;
                  const emaRange = Math.max(emaMax - emaMin, 0.0001);

                  return (
                    <>
                      <div className={`general-indicator-summary ${technicalClass}`}>
                        <div>
                          <span>Genel Teknik Durum</span>
                          <strong>{technicalState}</strong>
                        </div>
                        <div className="indicator-score">
                          <span>Pozitif</span><b>{positive}</b>
                          <span>Zayıf</span><b>{negative}</b>
                        </div>
                      </div>

                      <div className="indicator-cards">
                        <IndicatorCard
                          title="RSI (14)"
                          value={ind?.rsi14?.toFixed(1) ?? "—"}
                          status={rsiStatus}
                          note="Momentum ve aşırı alım/satım bölgelerini gösterir."
                          tone={ind?.rsi14 != null && ind.rsi14 >= 70 ? "warn" : ind?.rsi14 != null && ind.rsi14 <= 30 ? "bad" : "neutral"}
                        />
                        <IndicatorCard
                          title="MACD"
                          value={ind?.macd_hist?.toFixed(4) ?? "—"}
                          status={macdStatus}
                          note="Trend yönü ile momentum değişimini izler."
                          tone={ind?.macd_hist != null && ind.macd_hist > 0 ? "good" : "bad"}
                        />
                        <IndicatorCard
                          title="ADX (14)"
                          value={ind?.adx14?.toFixed(1) ?? "—"}
                          status={adxStatus}
                          note="Trendin yönünü değil, gücünü ölçer."
                          tone={ind?.adx14 != null && ind.adx14 >= 25 ? "good" : "neutral"}
                        />
                        <IndicatorCard
                          title="ATR (14)"
                          value={ind?.atr14?.toFixed(3) ?? "—"}
                          status={atrStatus}
                          note="Fiyatın ortalama oynaklık seviyesini gösterir."
                          tone="neutral"
                        />
                        <IndicatorCard
                          title="Hacim Oranı"
                          value={ind?.volume_ratio?.toFixed(2) ?? "—"}
                          status={volumeStatus}
                          note="1.00 civarı normal, üzeri ortalamadan güçlü hacimdir."
                          tone={ind?.volume_ratio != null && ind.volume_ratio >= 1.2 ? "good" : ind?.volume_ratio != null && ind.volume_ratio < 0.7 ? "bad" : "neutral"}
                        />
                        <IndicatorCard
                          title="Piyasa Rejimi"
                          value={ind?.regime_score != null ? `${ind.regime_score}/3` : "—"}
                          status={ind?.regime_score != null && ind.regime_score >= 2 ? "Olumlu" : "Zayıf / nötr"}
                          note="Benchmark trend ve RSI koşullarının kısa özetidir."
                          tone={ind?.regime_score != null && ind.regime_score >= 2 ? "good" : "neutral"}
                        />
                      </div>

                      <div className="indicator-lower-grid">
                        <div className="ema-panel">
                          <div className="indicator-section-title">
                            <div>
                              <b>EMA Trend Yapısı</b>
                              <span>{emaTrend}</span>
                            </div>
                          </div>

                          <div className="ema-list">
                            <div><span>Fiyat</span><b>{price?.toFixed(2) ?? "—"}</b></div>
                            <div><span>EMA20</span><b>{ind?.ema20?.toFixed(2) ?? "—"}</b></div>
                            <div><span>EMA50</span><b>{ind?.ema50?.toFixed(2) ?? "—"}</b></div>
                            <div><span>EMA200</span><b>{ind?.ema200?.toFixed(2) ?? "—"}</b></div>
                          </div>

                          <div className="ema-position-chart">
                            {emaBars.map((item) => {
                              const left = ((item.value - emaMin) / emaRange) * 92 + 4;
                              return (
                                <div
                                  key={item.label}
                                  className={`ema-marker ema-marker-${item.cls}`}
                                  style={{left:`${left}%`}}
                                >
                                  <i />
                                  <span>{item.label}<small>{item.value.toFixed(2)}</small></span>
                                </div>
                              );
                            })}
                            <div className="ema-axis" />
                          </div>
                        </div>

                        <div className="indicator-explain-panel">
                          <div className="indicator-section-title">
                            <div>
                              <b>Göstergeler Nasıl Okunur?</b>
                              <span>Kısa rehber</span>
                            </div>
                          </div>
                          <div className="indicator-guide-list">
                            <div><b>RSI</b><span>30 altı aşırı satım, 70 üstü aşırı alım olarak izlenir.</span></div>
                            <div><b>MACD</b><span>Histogramın pozitif olması momentumun güçlendiğine işaret edebilir.</span></div>
                            <div><b>ADX</b><span>25 üzeri daha güçlü trend ortamını gösterebilir.</span></div>
                            <div><b>EMA</b><span>Fiyat ve kısa/uzun ortalamaların dizilimi trend yapısını gösterir.</span></div>
                            <div><b>ATR</b><span>Yön vermez; fiyat oynaklığını ölçer.</span></div>
                            <div><b>Hacim</b><span>Fiyat hareketinin katılım gücünü değerlendirmeye yardımcı olur.</span></div>
                          </div>
                        </div>
                      </div>

                      <div className="indicator-disclaimer">
                        Bu göstergeler tek başına al/sat kararı değildir. V7.2 stratejisinin tamamında trend, momentum, hacim ve risk filtreleri birlikte değerlendirilir.
                      </div>
                    </>
                  );
                })()}
              </section>
            )}

            {analysisTab === "patterns" && (
              <PatternAnalysisView
                market={market}
                selected={selected}
                chartRange={chartRange}
                setChartRange={setChartRange}
              />
            )}

            <div className={analysisTab === "chart" ? "chart-view-wrap" : "chart-view-wrap hidden-analysis"}>

            <div className="chart-range-bar simple-chart-range">
              <div className="simple-chart-title">
                <b>Genel Görünüm</b>
                <span>Basit fiyat grafiği</span>
              </div>
              <div>
                <button
                  className={chartRange === "1d" ? "active" : ""}
                  onClick={() => setChartRange("1d")}
                >
                  1 Gün
                </button>
                <button
                  className={chartRange === "1w" ? "active" : ""}
                  onClick={() => setChartRange("1w")}
                >
                  1 Hafta
                </button>
              </div>
              <small>
                {chartRange === "1d"
                  ? "Bugünün / son işlem gününün 15 dk mumları"
                  : "Son 7 günün 1 saatlik mumları"}
              </small>
            </div>

            <div className="chart-box simple-price-chart">
              {market?.chart?.length ? (
                (() => {
                  const bars = market.chart.slice(-80);
                  const closes = bars.map((b) => b.close);
                  const highs = bars.map((b) => b.high);
                  const lows = bars.map((b) => b.low);
                  const maxP = Math.max(...highs);
                  const minP = Math.min(...lows);
                  const pRange = Math.max(maxP - minP, 0.0001);
                  const xStep = bars.length > 1 ? 760 / (bars.length - 1) : 760;
                  const yPrice = (v: number) => 18 + ((maxP - v) / pRange) * 190;

                  const linePath = closes.map((value, i) => {
                    const x = i * xStep;
                    const y = yPrice(value);
                    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
                  }).join(" ");

                  const firstY = yPrice(closes[0]);
                  const lastY = yPrice(closes[closes.length - 1]);
                  const areaPath = `${linePath} L760,225 L0,225 Z`;
                  const last = closes[closes.length - 1];
                  const first = closes[0];
                  const change = first ? ((last / first) - 1) * 100 : 0;

                  return (
                    <>
                      <svg viewBox="0 0 760 250" preserveAspectRatio="none" role="img" aria-label={`${selected} basit fiyat grafiği`}>
                        <defs>
                          <linearGradient id="simpleAreaGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
                            <stop offset="100%" stopColor="currentColor" stopOpacity="0.02" />
                          </linearGradient>
                        </defs>

                        <g className="gridlines">
                          <line x1="0" y1="50" x2="760" y2="50"/>
                          <line x1="0" y1="95" x2="760" y2="95"/>
                          <line x1="0" y1="140" x2="760" y2="140"/>
                          <line x1="0" y1="185" x2="760" y2="185"/>
                          <line x1="0" y1="225" x2="760" y2="225"/>
                        </g>

                        <path d={areaPath} className={change >= 0 ? "simple-area up" : "simple-area down"} />
                        <path d={linePath} className={change >= 0 ? "simple-line up" : "simple-line down"} />

                        <line
                          x1="0"
                          y1={lastY}
                          x2="760"
                          y2={lastY}
                          className="simple-last-line"
                        />

                        <circle
                          cx="760"
                          cy={lastY}
                          r="4"
                          className={change >= 0 ? "simple-last-dot up" : "simple-last-dot down"}
                        />
                      </svg>

                      <div className="simple-chart-stats">
                        <span>Başlangıç <b>{first.toFixed(2)}</b></span>
                        <span>Son <b>{last.toFixed(2)}</b></span>
                        <span className={change >= 0 ? "paper-pos" : "paper-neg"}>
                          Değişim <b>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</b>
                        </span>
                      </div>
                    </>
                  );
                })()
              ) : (
                <div className="chart-loading">Grafik verisi bekleniyor…</div>
              )}
              <span className="chart-demo-badge">{chartRange === "1d" ? "1 GÜN · 15 DK" : "1 HAFTA · 1 SAAT"}</span>
            </div>

            <div className="detail-chart-section">
              <div className="detail-chart-head">
                <div>
                  <b>Detaylı Mum Analizi</b>
                  <span>Mumun üzerine gel: Saat / Açılış / Yüksek / Düşük / Kapanış / Hacim</span>
                </div>
                <div className="detail-chart-tools">
                  <div className="overlay-buttons">
                    <button
                      className={detailOverlay === "none" ? "active" : ""}
                      onClick={() => setDetailOverlay("none")}
                    >
                      Normal
                    </button>
                    <button
                      className={detailOverlay === "sr" ? "active" : ""}
                      onClick={() => setDetailOverlay("sr")}
                    >
                      Destek / Direnç
                    </button>
                  </div>
                  <small>{chartRange === "1d" ? "1 Gün · 15 dk" : "1 Hafta · 1 saat"}</small>
                </div>
              </div>

              <div
                className="chart-box candlestick-box interactive-chart"
                onPointerMove={(e) => {
                  if (!market?.chart?.length) return;
                  const bars = market.chart.slice(-80);
                  const rect = e.currentTarget.getBoundingClientRect();
                  const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
                  const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
                  const index = Math.min(
                    bars.length - 1,
                    Math.max(0, Math.floor((x / Math.max(rect.width, 1)) * bars.length))
                  );
                  setHoveredCandle(index);

                  const highs = bars.map((b) => b.high);
                  const lows = bars.map((b) => b.low);
                  const maxP = Math.max(...highs);
                  const minP = Math.min(...lows);
                  const priceAreaTop = 12;
                  const priceAreaHeight = 176;
                  const clampedY = Math.max(priceAreaTop, Math.min(priceAreaTop + priceAreaHeight, (y / Math.max(rect.height, 1)) * 250));
                  const ratio = (clampedY - priceAreaTop) / priceAreaHeight;
                  setHoveredPrice(maxP - ratio * (maxP - minP));
                }}
                onPointerLeave={() => {
                  setHoveredCandle(null);
                  setHoveredPrice(null);
                }}
              >
                {market?.chart?.length ? (() => {
                  const bars = market.chart.slice(-80);
                  const highs = bars.map((b) => b.high);
                  const lows = bars.map((b) => b.low);
                  const maxP = Math.max(...highs);
                  const minP = Math.min(...lows);
                  const pRange = Math.max(maxP - minP, 0.0001);
                  const maxV = Math.max(...bars.map((b) => b.volume), 1);
                  const slot = 760 / bars.length;
                  const bodyW = Math.max(2.2, slot * 0.55);
                  const yPrice = (v: number) => 12 + ((maxP - v) / pRange) * 176;
                  const selectedBar = hoveredCandle != null ? bars[hoveredCandle] : null;
                  const selectedX = hoveredCandle != null ? hoveredCandle * slot + slot / 2 : null;

                  return (
                    <>
                      <svg viewBox="0 0 760 250" preserveAspectRatio="none" role="img" aria-label={`${selected} detaylı mum grafiği`}>
                        <g className="gridlines">
                          <line x1="0" y1="40" x2="760" y2="40"/>
                          <line x1="0" y1="80" x2="760" y2="80"/>
                          <line x1="0" y1="120" x2="760" y2="120"/>
                          <line x1="0" y1="160" x2="760" y2="160"/>
                          <line x1="0" y1="205" x2="760" y2="205"/>
                        </g>

                        {detailOverlay === "sr" && (() => {
                          const levels = [
                            { key: "R3", value: market.support_resistance.r3, kind: "res" },
                            { key: "R2", value: market.support_resistance.r2, kind: "res" },
                            { key: "R1", value: market.support_resistance.r1, kind: "res" },
                            { key: "P", value: market.support_resistance.pivot, kind: "pivot" },
                            { key: "S1", value: market.support_resistance.s1, kind: "sup" },
                            { key: "S2", value: market.support_resistance.s2, kind: "sup" },
                            { key: "S3", value: market.support_resistance.s3, kind: "sup" },
                          ].filter((lv) => lv.value != null && lv.value <= maxP * 1.08 && lv.value >= minP * 0.92);

                          return levels.map((lv) => {
                            const y = yPrice(Number(lv.value));
                            return (
                              <g key={`overlay-${lv.key}`} className={`overlay-line overlay-${lv.kind}`}>
                                <line x1="0" y1={y} x2="760" y2={y} />
                                <rect x="708" y={y - 8} width="46" height="14" rx="4" className="overlay-tag-bg" />
                                <text x="731" y={y + 2} textAnchor="middle" className="overlay-tag-text">
                                  {lv.key} {Number(lv.value).toFixed(2)}
                                </text>
                              </g>
                            );
                          });
                        })()}

                        {bars.map((b, i) => {
                          const x = i * slot + slot / 2;
                          const up = b.close >= b.open;
                          const yO = yPrice(b.open);
                          const yC = yPrice(b.close);
                          const yH = yPrice(b.high);
                          const yL = yPrice(b.low);
                          const y = Math.min(yO, yC);
                          const h = Math.max(Math.abs(yC - yO), 1.3);
                          const volH = (b.volume / maxV) * 36;
                          const cls = up ? "candle-up" : "candle-down";

                          return (
                            <g key={`detail-${b.time}-${i}`} className={`${cls} ${hoveredCandle === i ? "candle-hovered" : ""}`}>
                              <line x1={x} y1={yH} x2={x} y2={yL} className="wick" />
                              <rect x={x - bodyW/2} y={y} width={bodyW} height={h} rx="0.6" className="body" />
                              <rect x={x - bodyW/2} y={240 - volH} width={bodyW} height={volH} className="volume" />
                            </g>
                          );
                        })}

                        {selectedX != null && (
                          <line
                            x1={selectedX}
                            y1="0"
                            x2={selectedX}
                            y2="250"
                            className="crosshair-line"
                          />
                        )}

                        {hoveredPrice != null && (() => {
                          const y = yPrice(hoveredPrice);
                          return (
                            <>
                              <line
                                x1="0"
                                y1={y}
                                x2="760"
                                y2={y}
                                className="crosshair-price-line"
                              />
                              <rect
                                x="688"
                                y={y - 9}
                                width="66"
                                height="16"
                                rx="4"
                                className="price-tag-bg"
                              />
                              <text
                                x="721"
                                y={y + 2}
                                textAnchor="middle"
                                className="price-tag-text"
                              >
                                {hoveredPrice.toFixed(2)}
                              </text>
                            </>
                          );
                        })()}
                      </svg>

                      <div className="ohlcv-panel">
                        {selectedBar ? (
                          <>
                            <span><small>Saat</small><b>{new Intl.DateTimeFormat("tr-TR", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Europe/Istanbul"
                            }).format(new Date(selectedBar.time))}</b></span>
                            <span><small>Açılış</small><b>{selectedBar.open.toFixed(2)}</b></span>
                            <span><small>Yüksek</small><b>{selectedBar.high.toFixed(2)}</b></span>
                            <span><small>Düşük</small><b>{selectedBar.low.toFixed(2)}</b></span>
                            <span><small>Kapanış</small><b>{selectedBar.close.toFixed(2)}</b></span>
                            <span><small>Hacim</small><b>{selectedBar.volume.toLocaleString("tr-TR")}</b></span>
                            <span className="cursor-price"><small>İmleç Fiyatı</small><b>{hoveredPrice != null ? hoveredPrice.toFixed(2) : "—"}</b></span>
                          </>
                        ) : (
                          <div className="hover-hint">
                            {detailOverlay === "sr"
                              ? "Destek / direnç çizgileri açık. Mumun üzerine gelince OHLCV detayları görünür."
                              : "Detayları görmek için mumun üzerine gel."}
                          </div>
                        )}
                      </div>
                    </>
                  );
                })() : (
                  <div className="chart-loading">Detaylı grafik verisi bekleniyor…</div>
                )}
              </div>
            </div>
            </div>
          </section>

          <section className="levels-card">
            <div className="card-title level-title">
              <span>Destek - Direnç Seviyeleri</span>
              <small>Classic Pivot · önceki tamamlanmış gün</small>
            </div>
            <div className="level-list">
              <Level name="R3" value={market?.support_resistance.r3?.toFixed(2) ?? "—"} red />
              <Level name="R2" value={market?.support_resistance.r2?.toFixed(2) ?? "—"} red />
              <Level name="R1" value={market?.support_resistance.r1?.toFixed(2) ?? "—"} red />
              <Level name="P (Pivot)" value={market?.support_resistance.pivot?.toFixed(2) ?? "—"} />
              <Level name="S1" value={market?.support_resistance.s1?.toFixed(2) ?? "—"} green />
              <Level name="S2" value={market?.support_resistance.s2?.toFixed(2) ?? "—"} green />
              <Level name="S3" value={market?.support_resistance.s3?.toFixed(2) ?? "—"} green />
            </div>
            <div className="indicator-title">Göstergeler (Kısa Özet)</div>
            <div className="indicator-list">
              <span><b>RSI (14)</b><em>{market?.indicators.rsi14 != null ? `${market.indicators.rsi14.toFixed(1)} · ${market.indicators.rsi14 >= 70 ? "Aşırı alım" : market.indicators.rsi14 <= 30 ? "Aşırı satım" : "Nötr"}` : "—"}</em></span>
              <span><b>MACD</b><em>{market?.indicators.macd_hist != null ? `${market.indicators.macd_hist.toFixed(3)} · ${market.indicators.macd_hist > 0 ? "Pozitif" : "Negatif"}` : "—"}</em></span>
              <span><b>ADX (14)</b><em>{market?.indicators.adx14 != null ? `${market.indicators.adx14.toFixed(1)} · ${market.indicators.adx14 >= 25 ? "Trend güçlü" : "Trend zayıf"}` : "—"}</em></span>
              <span><b>EMA 50</b><em>{market?.indicators.ema50?.toFixed(2) ?? "—"}</em></span>
              <span><b>EMA 200</b><em>{market?.indicators.ema200?.toFixed(2) ?? "—"}</em></span>
            </div>
          </section>

          <section className="right-guide">
            <div className="guide-card">
              <div className="card-title">▤ Destek - Direnç Nedir?</div>
              <p><b>Destek</b>, fiyat düşerken alıcıların güçlenebildiği bölgedir. <b>Direnç</b> ise yükselişte satış baskısının artabildiği bölgedir.</p>
              <div className="sr-visual">
                <div className="r-line">Direnç</div>
                <div className="bars">
                  {[36,52,45,64,58,74,49,43,61].map((h,i)=><i key={i} style={{height:`${h}%`}} />)}
                </div>
                <div className="s-line">Destek</div>
              </div>
            </div>

            <div className="guide-card tool-guide">
              <div className="card-title">▤ Diğer Analiz Türleri</div>
              <Tool title="Fibonacci Analizi" text="Olası destek ve direnç bölgelerini belirler." />
              <Tool title="Mum (Candlestick) Analizi" text="Fiyat hareketlerinin psikolojisini gösterir." />
              <Tool title="Formasyonlar" text="Fincan-kulp, omuz-baş-omuz vb." />
              <Tool title="Hacim Analizi" text="Hareketin gücünü doğrular." />
              <Tool title="Göstergeler" text="RSI, MACD, ADX ve trend özeti." />
            </div>
          </section>
        </section>

        <section className="bottom-grid">
          <div className="bottom-card">
            <div className="card-title">⚡ Son Sinyaller</div>
            {notes.length ? notes.slice(0,4).map((n) => (
              <div className="signal-row" key={n.id}>
                <span>{new Date(n.created_at).toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit"})}</span>
                <b>{n.title}</b>
                <em>{n.kind}</em>
              </div>
            )) : <Empty text="Henüz yeni sinyal yok" />}
          </div>

          <div className="bottom-card">
            <div className="card-title">▣ Açık İşlemler ({openPositions.length})</div>
            {openPositions.length ? openPositions.map((p)=>(
              <div className="signal-row" key={`${p.symbol}-${p.entry_time}`}>
                <b>{p.symbol}</b>
                <span>{p.entry.toFixed(2)}</span>
                <em>Hedef {p.target.toFixed(2)}</em>
              </div>
            )) : <Empty text="Açık işlem bulunmuyor" />}
          </div>

          <div className="bottom-card">
            <div className="card-title">▥ Paper Performans</div>
            <div className="perf-mini">
              <span><b>{metrics?.closed_trades ?? 0}</b><small>Kapalı İşlem</small></span>
              <span><b>{metrics?.wins ?? 0}</b><small>Kazanç</small></span>
              <span><b>{metrics?.losses ?? 0}</b><small>Kayıp</small></span>
              <span><b>{metrics?.profit_factor?.toFixed(2) ?? "—"}</b><small>PF</small></span>
            </div>
          </div>
        </section>

        <section className="quote-strip">
          <div>
            <span>❝ Günün Sözü</span>
            <blockquote>“{quote[0]}”</blockquote>
            <small>— {quote[1]}</small>
          </div>
          <time>{new Intl.DateTimeFormat("tr-TR",{dateStyle:"long"}).format(clock)}</time>
        </section>

        <footer>
          <span>♛ BIST Katılım Terminal V4</span>
          <span><i className={`dot ${backendOnline ? "ok" : "bad"}`} /> {backendOnline ? "Backend bağlı" : "Backend bağlantısı yok"}</span>
          <span>Son tarama: {fmtDateTime(status?.last_auto_scan_at)}</span>
        </footer>
          </>
        )}

        {mainView === "candles" && (
          <CandleAnalysisView
            market={market}
            selected={selected}
            chartRange={chartRange}
            setChartRange={setChartRange}
          />
        )}

        {mainView === "paper" && (
          <PaperTradingView
            status={status}
            closedTrades={closedTrades}
            notes={paperNotes}
            loading={paperLoading}
            refresh={loadPaperDetails}
          />
        )}

        {mainView === "performance" && (
          <PerformanceView
            status={status}
            closedTrades={closedTrades}
            loading={paperLoading}
            refresh={loadPaperDetails}
          />
        )}

        {mainView === "news" && (
          <NewsView
            selected={selected}
            data={newsData}
            kapData={kapData}
            loading={newsLoading}
            kapLoading={kapLoading}
            refresh={() => loadNews(selected)}
          />
        )}

        {mainView === "scanner" && (
          <ScannerView
            data={scannerData}
            loading={scannerLoading}
            refresh={() => loadScanner(true)}
            selectSymbol={(symbol) => {
              setSelected(symbol);
              setMainView("home");
              setAnalysisTab("chart");
            }}
          />
        )}

        {mainView === "settings" && (
          <AlertSettingsView
            data={alertData}
            loading={alertLoading}
            saving={alertSaving}
            message={alertMessage}
            save={saveAlertSettings}
            checkNow={checkAlertsNow}
            isStandalone={isStandalone}
            pwaMessage={pwaMessage}
            installPwa={installPwa}
          />
        )}
      </section>
    </main>
  );
}








function AlertSettingsView({
  data,
  loading,
  saving,
  message,
  save,
  checkNow,
  isStandalone,
  pwaMessage,
  installPwa,
}: {
  data: AlertSettingsData | null;
  loading: boolean;
  saving: boolean;
  message: string;
  save: (settings: AlertSettings) => void;
  checkNow: () => void;
  isStandalone: boolean;
  pwaMessage: string;
  installPwa: () => void;
}) {
  const [draft, setDraft] = useState<AlertSettings>({
    enabled: true,
    strong_candidate_enabled: true,
    strong_candidate_min_score: 80,
    exact_v72_enabled: true,
    scan_every_minutes: 15,
  });

  useEffect(() => {
    if (data?.settings) setDraft(data.settings);
  }, [data]);

  return (
    <section className="alert-settings-page">
      <div className="alert-settings-head">
        <div>
          <span className="eyebrow">Ayarlar</span>
          <h1>Alarm Sistemi</h1>
          <small>Teknik koşullar oluştuğunda site içi ve push bildirim</small>
        </div>
        <button className="paper-refresh" onClick={checkNow} disabled={loading}>
          {loading ? "Taranıyor…" : "⚡ Şimdi Kontrol Et"}
        </button>
      </div>

      <div className="alert-status-grid">
        <div>
          <span>Alarm Sistemi</span>
          <strong className={draft.enabled ? "paper-pos" : "paper-neg"}>
            {draft.enabled ? "AÇIK" : "KAPALI"}
          </strong>
        </div>
        <div>
          <span>Otomatik Kontrol</span>
          <strong>{draft.scan_every_minutes} dk</strong>
        </div>
        <div>
          <span>Push Cihazı</span>
          <strong>{data?.registered_push_tokens ?? 0}</strong>
        </div>
        <div>
          <span>Son Kontrol</span>
          <strong className="alert-small-value">
            {data?.last_alert_scan_at ? fmtDateTime(data.last_alert_scan_at) : "Henüz yok"}
          </strong>
        </div>
      </div>

      <div className="alert-settings-grid">
        <section className="alert-card">
          <div className="alert-card-head">
            <div>
              <b>Ana Alarm</b>
              <span>Tüm otomatik teknik alarmları açar/kapatır.</span>
            </div>
            <button
              className={`alert-toggle ${draft.enabled ? "on" : ""}`}
              onClick={() => setDraft({...draft, enabled: !draft.enabled})}
            >
              <i />
            </button>
          </div>
        </section>

        <section className="alert-card">
          <div className="alert-card-head">
            <div>
              <b>Tam V7.2 Sinyali</b>
              <span>Donmuş V7.2 koşullarının tamamı aynı barda oluşursa bildir.</span>
            </div>
            <button
              className={`alert-toggle ${draft.exact_v72_enabled ? "on" : ""}`}
              onClick={() => setDraft({...draft, exact_v72_enabled: !draft.exact_v72_enabled})}
            >
              <i />
            </button>
          </div>
        </section>

        <section className="alert-card alert-card-wide">
          <div className="alert-card-head">
            <div>
              <b>Güçlü Aday Alarmı</b>
              <span>V7.2 teknik koşullarına uyum puanı eşik değere ulaşınca bildir.</span>
            </div>
            <button
              className={`alert-toggle ${draft.strong_candidate_enabled ? "on" : ""}`}
              onClick={() => setDraft({...draft, strong_candidate_enabled: !draft.strong_candidate_enabled})}
            >
              <i />
            </button>
          </div>

          <div className="alert-threshold">
            <div>
              <span>Minimum uyum skoru</span>
              <b>{draft.strong_candidate_min_score}/100</b>
            </div>
            <input
              type="range"
              min="60"
              max="100"
              step="10"
              value={draft.strong_candidate_min_score}
              onChange={(e) => setDraft({
                ...draft,
                strong_candidate_min_score: Number(e.target.value)
              })}
            />
            <div className="alert-scale">
              <span>60</span><span>70</span><span>80</span><span>90</span><span>100</span>
            </div>
          </div>
        </section>
      </div>

      <section className="pwa-card">
        <div>
          <span className="eyebrow">Mobil / PWA</span>
          <b>Telefona veya bilgisayara uygulama gibi kur</b>
          <small>
            Kurulduğunda tarayıcı sekmesi yerine ayrı uygulama penceresinde açılır.
            Canlı tarama ve bildirimler için internet bağlantısı gerekir.
          </small>
        </div>
        <div className="pwa-actions">
          <span className={isStandalone ? "pwa-status ready" : "pwa-status"}>
            {isStandalone ? "Kurulu" : "Kurulabilir"}
          </span>
          <button onClick={installPwa} disabled={isStandalone}>
            {isStandalone ? "Uygulama Kurulu" : "Uygulamayı Kur"}
          </button>
        </div>
        {pwaMessage && <p>{pwaMessage}</p>}
      </section>

      <div className="alert-event-list">
        <div className="alert-event">
          <span>⚡</span>
          <div><b>Güçlü aday</b><small>Varsayılan eşik: 80/100</small></div>
        </div>
        <div className="alert-event">
          <span>✓</span>
          <div><b>Tam V7.2 koşulu</b><small>Tüm donmuş teknik şartlar tamamlanırsa</small></div>
        </div>
        <div className="alert-event">
          <span>↗</span>
          <div><b>Paper pozisyon açılışı</b><small>Mevcut push sistemi otomatik bildirir</small></div>
        </div>
        <div className="alert-event">
          <span>■</span>
          <div><b>Paper işlem kapanışı</b><small>Stop / hedef / süre kapanışı otomatik bildirir</small></div>
        </div>
      </div>

      <div className="alert-actions">
        <button
          className="alert-save"
          onClick={() => save(draft)}
          disabled={saving}
        >
          {saving ? "Kaydediliyor…" : "Ayarları Kaydet"}
        </button>
        {message && <span>{message}</span>}
      </div>

      <div className="alert-warning">
        <b>Not</b>
        <span>
          “Güçlü aday” alarmı kazanç tahmini değildir. Yalnızca V7.2 teknik koşullarına uyumu bildirir.
          Aynı tamamlanmış 1 saatlik bar için tekrar bildirim gönderilmez.
        </span>
      </div>
    </section>
  );
}

function ScannerView({
  data,
  loading,
  refresh,
  selectSymbol,
}: {
  data: ScannerData | null;
  loading: boolean;
  refresh: () => void;
  selectSymbol: (symbol:string) => void;
}) {
  const strong = data?.results.filter(x => x.level === "GUCLU_ADAY").length ?? 0;
  const exact = data?.results.filter(x => x.exact_v72_signal).length ?? 0;
  const watch = data?.results.filter(x => x.level === "IZLE").length ?? 0;

  const levelLabel = (level: ScannerCandidate["level"]) => {
    if (level === "V7.2_SINYAL") return "V7.2 Sinyal";
    if (level === "GUCLU_ADAY") return "Güçlü Aday";
    if (level === "IZLE") return "İzle";
    return "Zayıf";
  };

  const checkLabel: Record<string,string> = {
    piyasa_rejimi:"Piyasa",
    trend:"Trend",
    rsi:"RSI",
    adx:"ADX",
    hacim:"Hacim",
    hacim_ortalamasi:"Hacim Ort.",
    ema20_mesafe:"EMA20",
    atr:"ATR",
    macd_ivme:"MACD",
    pozitif_mum:"Mum",
  };

  return (
    <section className="scanner-page">
      <div className="scanner-head">
        <div>
          <span className="eyebrow">Katılım 50 Tarayıcı</span>
          <h1>Güçlü Adaylar</h1>
          <small>V7.2_FROZEN koşullarına uyum · 1 saatlik veri</small>
        </div>
        <button className="paper-refresh" onClick={refresh}>
          {loading ? "50 hisse taranıyor…" : "↻ Yeniden Tara"}
        </button>
      </div>

      <div className="scanner-summary">
        <div><span>Taranan</span><strong>{data?.scored_symbols ?? 0}/{data?.requested_symbols ?? 50}</strong></div>
        <div className="scanner-exact"><span>Tam V7.2 Sinyal</span><strong>{exact}</strong></div>
        <div className="scanner-strong"><span>Güçlü Aday</span><strong>{strong}</strong></div>
        <div><span>İzle</span><strong>{watch}</strong></div>
        <div><span>Piyasa Rejimi</span><strong>{data?.regime_score ?? "—"}/3</strong></div>
      </div>

      <div className="scanner-info">
        <b>Uyum skoru nedir?</b>
        <span>
          10 teknik koşulun kaçının sağlandığını gösterir. Örneğin 80 puan = 10 koşulun 8'i uygun.
          Bu skor kazanç olasılığı değildir ve tek başına işlem sinyali sayılmaz.
        </span>
      </div>

      <section className="scanner-table-card">
        <div className="scanner-table-head">
          <span>Sıra</span>
          <span>Hisse</span>
          <span>Uyum</span>
          <span>Durum</span>
          <span>Fiyat</span>
          <span>RSI</span>
          <span>ADX</span>
          <span>Hacim</span>
          <span>MACD Hist.</span>
          <span>Koşullar</span>
        </div>

        <div className="scanner-list">
          {loading && !data ? (
            <div className="paper-empty">
              <span>⌁</span>
              <b>Katılım 50 taranıyor</b>
              <small>İlk tarama birkaç saniye sürebilir.</small>
            </div>
          ) : data?.results.length ? (
            data.results.map((item, idx) => (
              <article
                className={`scanner-row scanner-${item.level.toLowerCase().replaceAll(".", "-")}`}
                key={item.symbol}
                onClick={() => selectSymbol(item.symbol)}
              >
                <span className="scanner-rank">{idx + 1}</span>
                <b>{item.symbol}</b>

                <div className="scanner-score">
                  <strong>{item.score.toFixed(0)}</strong>
                  <div><i style={{width:`${item.score}%`}} /></div>
                </div>

                <em className={`scanner-level level-${item.level.toLowerCase().replaceAll(".", "-")}`}>
                  {levelLabel(item.level)}
                </em>

                <span>{item.price?.toFixed(2) ?? "—"}</span>
                <span>{item.rsi?.toFixed(1) ?? "—"}</span>
                <span>{item.adx?.toFixed(1) ?? "—"}</span>
                <span>{item.volume_ratio?.toFixed(2) ?? "—"}x</span>
                <span className={(item.macd_hist ?? 0) >= 0 ? "paper-pos" : "paper-neg"}>
                  {item.macd_hist?.toFixed(3) ?? "—"}
                </span>

                <div className="scanner-checks">
                  {Object.entries(item.checks).map(([key, ok]) => (
                    <span
                      key={key}
                      className={ok ? "check-ok" : "check-no"}
                      title={`${checkLabel[key] || key}: ${ok ? "uygun" : "uygun değil"}`}
                    >
                      {checkLabel[key]?.slice(0,3) || key.slice(0,3)}
                    </span>
                  ))}
                </div>
              </article>
            ))
          ) : (
            <div className="paper-empty">
              <span>◇</span>
              <b>50 puan üzeri aday bulunamadı</b>
              <small>Yeniden tarama ile güncel 1 saatlik barlar kontrol edilebilir.</small>
            </div>
          )}
        </div>
      </section>

      <div className="scanner-footer">
        <span>Strateji: <b>{data?.strategy || "V7.2_FROZEN"}</b></span>
        <span>Kaynak: Yahoo Finance · lisanslı gerçek zamanlı BIST verisi değildir.</span>
        <span>{data?.errors?.length ? `${data.errors.length} sembolde veri hatası` : "Veri hatası yok"}</span>
      </div>
    </section>
  );
}

function NewsView({
  selected,
  data,
  kapData,
  loading,
  kapLoading,
  refresh,
}: {
  selected: string;
  data: NewsData | null;
  kapData: KapData | null;
  loading: boolean;
  kapLoading: boolean;
  refresh: () => void;
}) {
  const positive = data?.results.filter(x => x.impact === "pozitif_aday").length ?? 0;
  const negative = data?.results.filter(x => x.impact === "negatif_aday").length ?? 0;
  const neutral = data?.results.filter(x => x.impact === "notr").length ?? 0;

  const impactLabel = (impact: NewsItem["impact"]) => {
    if (impact === "pozitif_aday") return "Pozitif aday";
    if (impact === "negatif_aday") return "Negatif aday";
    return "Nötr";
  };

  const kapCategoryLabel = (c: string) => {
    const map: Record<string,string> = {
      finansal:"Finansal",
      yeni_is:"Yeni İş / Sözleşme",
      sermaye:"Sermaye",
      temettu:"Temettü",
      geri_alim:"Geri Alım",
      yonetim:"Yönetim",
      ortaklik:"Ortaklık / Pay",
      yatirim:"Yatırım",
      hukuki:"Hukuki",
      endeks_piyasa:"Piyasa / Endeks",
      diger:"Diğer",
    };
    return map[c] || "Diğer";
  };

  return (
    <section className="news-page">
      <div className="news-head">
        <div>
          <span className="eyebrow">KAP / Haberler</span>
          <h1>{selected}</h1>
          <small>Resmi KAP bildirimleri + Yahoo Finance haber akışı</small>
        </div>
        <button className="paper-refresh" onClick={refresh}>
          {loading || kapLoading ? "Yenileniyor…" : "↻ Yenile"}
        </button>
      </div>

      <div className="news-summary">
        <div className="news-kap-card">
          <span>Resmi Kaynak</span>
          <strong>KAP</strong>
          <small>
            {kapData?.company?.title || `${selected} resmi bildirimleri`}
          </small>
          <a
            href={
              kapData?.company?.company_url ||
              kapData?.fallback_url ||
              data?.kap.search_url ||
              `https://www.kap.org.tr/tr/bildirim-sorgu?q=${selected}`
            }
            target="_blank"
            rel="noreferrer"
          >
            KAP şirket sayfası ↗
          </a>
        </div>
        <div><span>KAP Bildirimi</span><strong>{kapData?.count ?? 0}</strong></div>
        <div><span>Haber</span><strong>{data?.results.length ?? 0}</strong></div>
        <div className="news-pos"><span>Pozitif Haber Adayı</span><strong>{positive}</strong></div>
        <div className="news-neg"><span>Negatif Haber Adayı</span><strong>{negative}</strong></div>
      </div>

      <div className="kap-news-grid">
        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Resmi KAP Bildirimleri</b>
              <span>Son {kapData?.days ?? 30} gün · resmi KAP kaynağı</span>
            </div>
          </div>

          <div className="kap-list">
            {kapLoading ? (
              <div className="paper-empty">
                <span>⌁</span>
                <b>KAP bildirimleri yükleniyor</b>
              </div>
            ) : kapData?.status === "ok" && kapData.results.length ? (
              kapData.results.map((item, idx) => (
                <article className="kap-item" key={`${item.disclosure_index}-${idx}`}>
                  <div className="kap-item-top">
                    <span className={`kap-category kap-${item.category}`}>
                      {kapCategoryLabel(item.category)}
                    </span>
                    <time>{item.publish_date || "—"}</time>
                  </div>

                  <b>{item.subject || "KAP Bildirimi"}</b>

                  {item.summary ? (
                    <p>{item.summary}</p>
                  ) : (
                    <p>Özet bilgi bulunmuyor.</p>
                  )}

                  <div className="kap-item-foot">
                    <div>
                      {item.is_correction && <em>Düzeltme</em>}
                      {item.is_late && <em>Geç bildirim</em>}
                      {item.attachment_count > 0 && <span>{item.attachment_count} ek</span>}
                    </div>
                    {item.url && (
                      <a href={item.url} target="_blank" rel="noreferrer">
                        KAP'ta aç ↗
                      </a>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <div className="paper-empty">
                <span>◇</span>
                <b>KAP bildirimi alınamadı</b>
                <small>{kapData?.error || "Son 30 günlük sonuç bulunamadı."}</small>
                {(kapData?.fallback_url || data?.kap.search_url) && (
                  <a
                    className="kap-fallback-link"
                    href={kapData?.fallback_url || data?.kap.search_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Resmi KAP sorgusunu aç ↗
                  </a>
                )}
              </div>
            )}
          </div>
        </section>

        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Son Haberler</b>
              <span>{data?.source || "Yahoo Finance"} · resmi gerçek zaman garantisi yok</span>
            </div>
          </div>

          <div className="news-list">
            {loading ? (
              <div className="paper-empty">
                <span>⌁</span>
                <b>Haberler yükleniyor</b>
              </div>
            ) : data?.results.length ? (
              data.results.map((item, idx) => (
                <article className="news-item" key={`${item.title}-${idx}`}>
                  <div className="news-item-main">
                    <div className="news-item-meta">
                      <span>{item.publisher || "Kaynak"}</span>
                      <time>{item.published_at ? fmtDateTime(item.published_at) : "Zaman yok"}</time>
                    </div>
                    <b>{item.title}</b>
                    <div className="news-item-bottom">
                      <em className={`impact impact-${item.impact}`}>
                        {impactLabel(item.impact)}
                      </em>
                      {item.url ? (
                        <a href={item.url} target="_blank" rel="noreferrer">Haberi aç ↗</a>
                      ) : (
                        <span>Bağlantı yok</span>
                      )}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="paper-empty">
                <span>◇</span>
                <b>Haber bulunamadı</b>
                <small>Kaynak bu hisse için sonuç döndürmemiş olabilir.</small>
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="kap-info-strip">
        <span>
          <b>KAP:</b> resmi şirket bildirimidir.
        </span>
        <span>
          <b>Haber etiketi:</b> yalnızca başlık anahtar kelimelerine göre ön sınıflamadır.
        </span>
        <span>
          Bildirim veya haber tek başına al/sat sinyali değildir.
        </span>
      </div>
    </section>
  );
}

function PerformanceView({
  status,
  closedTrades,
  loading,
  refresh,
}: {
  status: StatusData | null;
  closedTrades: ClosedTrade[];
  loading: boolean;
  refresh: () => void;
}) {
  const stats = useMemo(() => {
    const trades = closedTrades || [];
    if (!trades.length) {
      return {
        total: 0,
        wins: 0,
        losses: 0,
        winRate: 0,
        avgWin: 0,
        avgLoss: 0,
        expectancy: 0,
        profitFactor: 0,
        compounded: 0,
        maxDrawdown: 0,
        bestTrade: 0,
        worstTrade: 0,
        bySymbol: [] as Array<{
          symbol:string; trades:number; wins:number; winRate:number;
          avgReturn:number; totalReturn:number;
        }>,
        equity: [{x:0,y:100}],
      };
    }

    const wins = trades.filter(t => (t.net_return_pct || 0) > 0);
    const losses = trades.filter(t => (t.net_return_pct || 0) <= 0);

    const avgWin = wins.length
      ? wins.reduce((a,t)=>a+(t.net_return_pct||0),0)/wins.length
      : 0;
    const avgLoss = losses.length
      ? losses.reduce((a,t)=>a+(t.net_return_pct||0),0)/losses.length
      : 0;

    let equityValue = 100;
    let peak = 100;
    let maxDrawdown = 0;
    const equity = [{x:0,y:100}];

    trades.forEach((t,i)=>{
      equityValue *= 1 + (t.net_return_pct || 0)/100;
      peak = Math.max(peak, equityValue);
      const dd = ((equityValue - peak)/peak)*100;
      maxDrawdown = Math.min(maxDrawdown, dd);
      equity.push({x:i+1,y:equityValue});
    });

    const grossProfit = wins.reduce((a,t)=>a+(t.net_return_pct||0),0);
    const grossLoss = Math.abs(losses.reduce((a,t)=>a+(t.net_return_pct||0),0));
    const expectancy = trades.reduce((a,t)=>a+(t.net_return_pct||0),0)/trades.length;
    const profitFactor = grossLoss > 0 ? grossProfit/grossLoss : (grossProfit > 0 ? 999 : 0);

    const grouped = new Map<string, ClosedTrade[]>();
    trades.forEach(t => {
      if (!grouped.has(t.symbol)) grouped.set(t.symbol, []);
      grouped.get(t.symbol)!.push(t);
    });

    const bySymbol = [...grouped.entries()].map(([symbol, rows]) => {
      const symbolWins = rows.filter(r => (r.net_return_pct||0)>0).length;
      const sum = rows.reduce((a,r)=>a+(r.net_return_pct||0),0);
      return {
        symbol,
        trades: rows.length,
        wins: symbolWins,
        winRate: (symbolWins/rows.length)*100,
        avgReturn: sum/rows.length,
        totalReturn: sum,
      };
    }).sort((a,b)=>b.totalReturn-a.totalReturn);

    const values = trades.map(t=>t.net_return_pct||0);

    return {
      total: trades.length,
      wins: wins.length,
      losses: losses.length,
      winRate: (wins.length/trades.length)*100,
      avgWin,
      avgLoss,
      expectancy,
      profitFactor,
      compounded: equityValue-100,
      maxDrawdown,
      bestTrade: Math.max(...values),
      worstTrade: Math.min(...values),
      bySymbol,
      equity,
    };
  }, [closedTrades]);

  const equityPath = useMemo(() => {
    if (stats.equity.length < 2) return "";
    const ys = stats.equity.map(p=>p.y);
    const min = Math.min(...ys);
    const max = Math.max(...ys);
    const range = Math.max(max-min, .1);

    return stats.equity.map((p,i)=>{
      const x = (i/Math.max(stats.equity.length-1,1))*760;
      const y = 210 - ((p.y-min)/range)*170;
      return `${i===0?"M":"L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [stats.equity]);

  const recent = [...closedTrades].slice(-12).reverse();

  return (
    <section className="performance-page">
      <div className="performance-head">
        <div>
          <span className="eyebrow">Performans</span>
          <h1>V7.2_FROZEN</h1>
          <small>Paper Trading ileri dönem sonuçları · gerçek para değildir</small>
        </div>
        <button className="paper-refresh" onClick={refresh}>
          {loading ? "Yenileniyor…" : "↻ Yenile"}
        </button>
      </div>

      <div className="performance-kpis">
        <PaperMetric title="Toplam İşlem" value={String(stats.total)} />
        <PaperMetric title="Kazanma Oranı" value={`${stats.winRate.toFixed(1)}%`} />
        <PaperMetric title="Expectancy" value={`${stats.expectancy.toFixed(3)}%`} />
        <PaperMetric title="Profit Factor" value={stats.profitFactor >= 999 ? "∞" : stats.profitFactor.toFixed(2)} />
        <PaperMetric title="Bileşik Getiri" value={`${stats.compounded.toFixed(2)}%`} />
        <PaperMetric title="Maks. Drawdown" value={`${stats.maxDrawdown.toFixed(2)}%`} />
      </div>

      <div className="performance-grid">
        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Equity Eğrisi</b>
              <span>100 başlangıç değeri</span>
            </div>
          </div>
          <div className="performance-equity">
            {stats.total ? (
              <svg viewBox="0 0 760 240" preserveAspectRatio="none">
                <g className="gridlines">
                  <line x1="0" y1="50" x2="760" y2="50"/>
                  <line x1="0" y1="100" x2="760" y2="100"/>
                  <line x1="0" y1="150" x2="760" y2="150"/>
                  <line x1="0" y1="200" x2="760" y2="200"/>
                </g>
                <path d={equityPath} fill="none" stroke="#00d99a" strokeWidth="3"/>
              </svg>
            ) : (
              <div className="paper-empty">
                <span>⌁</span>
                <b>Henüz performans verisi yok</b>
                <small>İlk paper işlemler kapandığında grafik oluşacak.</small>
              </div>
            )}
          </div>
        </section>

        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Kalite Özeti</b>
              <span>İşlem dağılımı</span>
            </div>
          </div>

          <div className="quality-grid">
            <div><span>Kazançlı</span><b className="paper-pos">{stats.wins}</b></div>
            <div><span>Kayıplı</span><b className="paper-neg">{stats.losses}</b></div>
            <div><span>Ort. Kazanç</span><b className="paper-pos">{stats.avgWin.toFixed(2)}%</b></div>
            <div><span>Ort. Kayıp</span><b className="paper-neg">{stats.avgLoss.toFixed(2)}%</b></div>
            <div><span>En İyi İşlem</span><b>{stats.bestTrade.toFixed(2)}%</b></div>
            <div><span>En Kötü İşlem</span><b>{stats.worstTrade.toFixed(2)}%</b></div>
          </div>

          <div className="performance-note">
            <b>İleri dönem doğrulama</b>
            <span>
              Bu ekran backtest değil; Paper Trading ile bugünden sonra oluşan kapanmış işlemleri özetler.
              Az işlem varken sonuçlar yanıltıcı olabilir.
            </span>
          </div>
        </section>
      </div>

      <div className="performance-grid lower">
        <section className="paper-history-panel">
          <div className="paper-panel-head">
            <div>
              <b>Hisse Bazında Performans</b>
              <span>{stats.bySymbol.length} hisse</span>
            </div>
          </div>

          {stats.bySymbol.length ? (
            <div className="symbol-performance-table">
              <div className="symbol-performance-row head">
                <span>Hisse</span>
                <span>İşlem</span>
                <span>Win Rate</span>
                <span>Ort. Getiri</span>
                <span>Toplam</span>
              </div>
              {stats.bySymbol.map(row=>(
                <div className="symbol-performance-row" key={row.symbol}>
                  <b>{row.symbol}</b>
                  <span>{row.trades}</span>
                  <span>{row.winRate.toFixed(1)}%</span>
                  <span className={row.avgReturn>=0?"paper-pos":"paper-neg"}>
                    {row.avgReturn>=0?"+":""}{row.avgReturn.toFixed(2)}%
                  </span>
                  <strong className={row.totalReturn>=0?"paper-pos":"paper-neg"}>
                    {row.totalReturn>=0?"+":""}{row.totalReturn.toFixed(2)}%
                  </strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="paper-empty">
              <span>▤</span>
              <b>Hisse performansı henüz oluşmadı</b>
              <small>Kapanmış işlemler geldikçe otomatik hesaplanacak.</small>
            </div>
          )}
        </section>

        <section className="paper-history-panel">
          <div className="paper-panel-head">
            <div>
              <b>Son İşlemler</b>
              <span>En yeni 12 kapanış</span>
            </div>
          </div>

          {recent.length ? (
            <div className="recent-performance-list">
              {recent.map((t,i)=>(
                <article key={`${t.symbol}-${t.exit_time}-${i}`}>
                  <div>
                    <b>{t.symbol}</b>
                    <span>{t.exit_reason || "—"} · {fmtDateTime(t.exit_time)}</span>
                  </div>
                  <strong className={t.net_return_pct>=0?"paper-pos":"paper-neg"}>
                    {t.net_return_pct>=0?"+":""}{t.net_return_pct.toFixed(2)}%
                  </strong>
                </article>
              ))}
            </div>
          ) : (
            <div className="paper-empty">
              <span>◇</span>
              <b>Henüz kapanmış işlem yok</b>
              <small>İlk sonuçlar burada listelenecek.</small>
            </div>
          )}
        </section>
      </div>

      <div className="performance-footer">
        <span>Strateji: <b>{status?.strategy || "V7.2_FROZEN"}</b></span>
        <span>Açık pozisyon: <b>{status?.open_positions?.length ?? 0}</b></span>
        <span>Takip evreni: <b>{status?.symbols?.length ?? 0}</b></span>
      </div>
    </section>
  );
}

function PaperTradingView({
  status,
  closedTrades,
  notes,
  loading,
  refresh,
}: {
  status: StatusData | null;
  closedTrades: ClosedTrade[];
  notes: NotificationItem[];
  loading: boolean;
  refresh: () => void;
}) {
  const metrics = status?.metrics;
  const openPositions = status?.open_positions || [];

  const equity = useMemo(() => {
    let value = 100;
    const points = [{ x: 0, y: value }];

    closedTrades.forEach((t, i) => {
      value *= 1 + (t.net_return_pct || 0) / 100;
      points.push({ x: i + 1, y: value });
    });

    return points;
  }, [closedTrades]);

  const equityPath = useMemo(() => {
    if (equity.length < 2) return "";
    const ys = equity.map(p => p.y);
    const min = Math.min(...ys);
    const max = Math.max(...ys);
    const range = Math.max(max - min, 0.1);

    return equity.map((p, i) => {
      const x = (i / Math.max(equity.length - 1, 1)) * 760;
      const y = 210 - ((p.y - min) / range) * 170;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
  }, [equity]);

  const reasonLabel = (reason: string) => {
    if (reason === "TARGET") return "Hedef";
    if (reason === "STOP") return "Stop";
    if (reason === "TIME") return "Süre";
    return reason || "—";
  };

  return (
    <section className="paper-page">
      <div className="paper-page-head">
        <div>
          <span className="eyebrow">Paper Trading</span>
          <h1>V7.2_FROZEN</h1>
          <small>
            Sanal işlemler · otomatik tarama {status?.auto_scan_every_minutes ?? 5} dakikada bir
          </small>
        </div>

        <button className="paper-refresh" onClick={refresh}>
          {loading ? "Yenileniyor…" : "↻ Yenile"}
        </button>
      </div>

      <div className="paper-metrics">
        <PaperMetric title="Kapalı İşlem" value={String(metrics?.closed_trades ?? 0)} />
        <PaperMetric title="Kazanma Oranı" value={`${(metrics?.win_rate_pct ?? 0).toFixed(1)}%`} />
        <PaperMetric title="Expectancy" value={`${(metrics?.expectancy_pct_per_trade ?? 0).toFixed(3)}%`} />
        <PaperMetric title="Profit Factor" value={metrics?.profit_factor?.toFixed(2) ?? "—"} />
        <PaperMetric title="Toplam Getiri" value={`${(metrics?.total_compounded_return_pct ?? 0).toFixed(2)}%`} />
        <PaperMetric title="Açık İşlem" value={String(openPositions.length)} />
      </div>

      <div className="paper-main-grid">
        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Açık İşlemler</b>
              <span>{openPositions.length} pozisyon</span>
            </div>
          </div>

          {openPositions.length ? (
            <div className="paper-open-list">
              {openPositions.map((p) => {
                const currentPct = ((p.last_price / p.entry) - 1) * 100;
                const stopPct = ((p.stop / p.entry) - 1) * 100;
                const targetPct = ((p.target / p.entry) - 1) * 100;

                return (
                  <article className="paper-open-card" key={`${p.symbol}-${p.entry_time}`}>
                    <div className="paper-open-top">
                      <div>
                        <strong>{p.symbol}</strong>
                        <span>{p.timeframe}</span>
                      </div>
                      <em className={currentPct >= 0 ? "paper-pos" : "paper-neg"}>
                        {currentPct >= 0 ? "+" : ""}{currentPct.toFixed(2)}%
                      </em>
                    </div>

                    <div className="paper-price-grid">
                      <div><span>Giriş</span><b>{p.entry.toFixed(2)}</b></div>
                      <div><span>Son</span><b>{p.last_price.toFixed(2)}</b></div>
                      <div><span>Stop</span><b className="paper-neg">{p.stop.toFixed(2)}</b><small>{stopPct.toFixed(2)}%</small></div>
                      <div><span>Hedef</span><b className="paper-pos">{p.target.toFixed(2)}</b><small>+{targetPct.toFixed(2)}%</small></div>
                    </div>

                    <div className="paper-progress">
                      <span>Bar: {p.bars_held}/14</span>
                      <div><i style={{width:`${Math.min(100, (p.bars_held/14)*100)}%`}} /></div>
                    </div>

                    <small className="paper-time">
                      Açılış: {fmtDateTime(p.opened_at)}
                    </small>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="paper-empty">
              <span>◇</span>
              <b>Açık paper işlem yok</b>
              <small>Yeni V7.2 sinyali oluştuğunda burada görünecek.</small>
            </div>
          )}
        </section>

        <section className="paper-panel">
          <div className="paper-panel-head">
            <div>
              <b>Equity Eğrisi</b>
              <span>100 başlangıç değeri · bileşik sonuç</span>
            </div>
          </div>

          <div className="paper-equity">
            {closedTrades.length ? (
              <svg viewBox="0 0 760 240" preserveAspectRatio="none">
                <g className="gridlines">
                  <line x1="0" y1="50" x2="760" y2="50"/>
                  <line x1="0" y1="100" x2="760" y2="100"/>
                  <line x1="0" y1="150" x2="760" y2="150"/>
                  <line x1="0" y1="200" x2="760" y2="200"/>
                </g>
                <path d={equityPath} fill="none" stroke="#00d99a" strokeWidth="3" />
              </svg>
            ) : (
              <div className="paper-empty">
                <span>⌁</span>
                <b>Equity eğrisi için işlem bekleniyor</b>
                <small>İlk paper işlem kapandığında grafik oluşacak.</small>
              </div>
            )}
          </div>

          <div className="paper-system-info">
            <span><b>Başlangıç</b><em>{fmtDateTime(status?.started_at)}</em></span>
            <span><b>Son Tarama</b><em>{fmtDateTime(status?.last_auto_scan_at)}</em></span>
            <span><b>Takip</b><em>{status?.symbols?.join(", ") || "—"}</em></span>
            <span><b>Hata</b><em>{status?.last_auto_scan_errors?.length ? `${status.last_auto_scan_errors.length} hata` : "Yok"}</em></span>
          </div>
        </section>
      </div>

      <section className="paper-history-panel">
        <div className="paper-panel-head">
          <div>
            <b>İşlem Geçmişi</b>
            <span>{closedTrades.length} kapanmış işlem</span>
          </div>
        </div>

        {closedTrades.length ? (
          <div className="paper-table-wrap">
            <div className="paper-trade-row paper-trade-head">
              <span>Hisse</span>
              <span>Giriş</span>
              <span>Çıkış</span>
              <span>Stop</span>
              <span>Hedef</span>
              <span>Kapanış</span>
              <span>Sonuç</span>
              <span>Getiri</span>
              <span>Çıkış Zamanı</span>
            </div>

            {[...closedTrades].reverse().map((t, i) => (
              <div className="paper-trade-row" key={`${t.symbol}-${t.exit_time}-${i}`}>
                <b>{t.symbol}</b>
                <span>{t.entry.toFixed(2)}</span>
                <span>{t.exit.toFixed(2)}</span>
                <span>{t.stop.toFixed(2)}</span>
                <span>{t.target.toFixed(2)}</span>
                <span>{reasonLabel(t.exit_reason)}</span>
                <span className={t.result === "WIN" ? "paper-pos" : "paper-neg"}>
                  {t.result === "WIN" ? "Kazanç" : "Kayıp"}
                </span>
                <strong className={t.net_return_pct >= 0 ? "paper-pos" : "paper-neg"}>
                  {t.net_return_pct >= 0 ? "+" : ""}{t.net_return_pct.toFixed(2)}%
                </strong>
                <span>{fmtDateTime(t.exit_time)}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="paper-empty paper-history-empty">
            <span>▤</span>
            <b>Henüz kapanmış işlem yok</b>
            <small>İşlemler kapandıkça giriş, çıkış ve kapanış nedeni burada tutulacak.</small>
          </div>
        )}
      </section>

      <section className="paper-history-panel">
        <div className="paper-panel-head">
          <div>
            <b>Paper Bildirimleri</b>
            <span>Son {Math.min(notes.length, 100)} kayıt</span>
          </div>
        </div>

        <div className="paper-notes">
          {notes.length ? notes.slice(0, 20).map((n) => (
            <article className="paper-note" key={n.id}>
              <div>
                <b>{n.title}</b>
                <span>{n.message}</span>
              </div>
              <time>{fmtDateTime(n.created_at)}</time>
            </article>
          )) : (
            <div className="paper-empty">
              <span>♢</span>
              <b>Bildirim yok</b>
              <small>Yeni sinyal veya işlem kapanışı burada görünecek.</small>
            </div>
          )}
        </div>
      </section>

      <div className="paper-warning">
        <b>Paper Trading</b>
        <span>
          Bu ekran gerçek para emri göndermez. Amaç V7.2 stratejisinin ileri dönem davranışını ölçmek ve backtest sonuçlarıyla karşılaştırmaktır.
        </span>
      </div>
    </section>
  );
}

function PaperMetric({title, value}:{title:string; value:string}) {
  return (
    <div className="paper-metric">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PatternAnalysisView({
  market,
  selected,
  chartRange,
  setChartRange,
}: {
  market: MarketDetail | null;
  selected: string;
  chartRange: "1d" | "1w";
  setChartRange: (v: "1d" | "1w") => void;
}) {
  const bars = market?.chart?.slice(-80) ?? [];

  const analysis = useMemo(() => {
    type Swing = { i:number; price:number; type:"high"|"low"; time:string };
    type Result = {
      name:string;
      status:"aday"|"zayıf";
      direction:"pozitif"|"negatif"|"nötr";
      confidence:number;
      reason:string;
      points:number[];
    };

    if (bars.length < 12) {
      return { swings: [] as Swing[], results: [] as Result[] };
    }

    const swings: Swing[] = [];
    for (let i = 2; i < bars.length - 2; i++) {
      const h = bars[i].high;
      const l = bars[i].low;
      const isHigh =
        h >= bars[i-1].high && h >= bars[i-2].high &&
        h >= bars[i+1].high && h >= bars[i+2].high;
      const isLow =
        l <= bars[i-1].low && l <= bars[i-2].low &&
        l <= bars[i+1].low && l <= bars[i+2].low;

      if (isHigh) swings.push({ i, price:h, type:"high", time:bars[i].time });
      if (isLow) swings.push({ i, price:l, type:"low", time:bars[i].time });
    }

    const results: Result[] = [];
    const tol = 0.025; // 2.5%

    // Double top / bottom
    const highs = swings.filter(s => s.type === "high");
    const lows = swings.filter(s => s.type === "low");

    for (let a = 0; a < highs.length - 1; a++) {
      for (let b = a + 1; b < highs.length; b++) {
        const p1 = highs[a], p2 = highs[b];
        if (p2.i - p1.i < 5 || p2.i - p1.i > 35) continue;
        const diff = Math.abs(p1.price - p2.price) / ((p1.price+p2.price)/2);
        const betweenLows = lows.filter(x => x.i > p1.i && x.i < p2.i);
        if (diff <= tol && betweenLows.length) {
          const neck = Math.min(...betweenLows.map(x => x.price));
          const depth = ((Math.min(p1.price,p2.price)-neck)/neck)*100;
          if (depth >= 2) {
            results.push({
              name:"Çift Tepe Adayı",
              status:"aday",
              direction:"negatif",
              confidence: Math.min(90, Math.round(70 + (tol-diff)*400)),
              reason:`İki tepe birbirine yakın ve arada yaklaşık %${depth.toFixed(1)} geri çekilme var.`,
              points:[p1.i,p2.i]
            });
            a = highs.length; break;
          }
        }
      }
    }

    for (let a = 0; a < lows.length - 1; a++) {
      for (let b = a + 1; b < lows.length; b++) {
        const p1 = lows[a], p2 = lows[b];
        if (p2.i - p1.i < 5 || p2.i - p1.i > 35) continue;
        const diff = Math.abs(p1.price - p2.price) / ((p1.price+p2.price)/2);
        const betweenHighs = highs.filter(x => x.i > p1.i && x.i < p2.i);
        if (diff <= tol && betweenHighs.length) {
          const neck = Math.max(...betweenHighs.map(x => x.price));
          const height = ((neck-Math.max(p1.price,p2.price))/Math.max(p1.price,p2.price))*100;
          if (height >= 2) {
            results.push({
              name:"Çift Dip Adayı",
              status:"aday",
              direction:"pozitif",
              confidence: Math.min(90, Math.round(70 + (tol-diff)*400)),
              reason:`İki dip birbirine yakın ve arada yaklaşık %${height.toFixed(1)} tepki yükselişi var.`,
              points:[p1.i,p2.i]
            });
            a = lows.length; break;
          }
        }
      }
    }

    // Head & shoulders / inverse: use last 5 alternating swing points
    const ordered = swings.sort((a,b)=>a.i-b.i);
    for (let i=0;i<=ordered.length-5;i++) {
      const s = ordered.slice(i,i+5);

      if (
        s[0].type==="high" && s[1].type==="low" && s[2].type==="high" &&
        s[3].type==="low" && s[4].type==="high"
      ) {
        const shouldersClose = Math.abs(s[0].price-s[4].price)/((s[0].price+s[4].price)/2) <= 0.04;
        const headHigher = s[2].price > s[0].price*1.02 && s[2].price > s[4].price*1.02;
        if (shouldersClose && headHigher) {
          results.push({
            name:"Omuz-Baş-Omuz Adayı",
            status:"aday",
            direction:"negatif",
            confidence:76,
            reason:"Ortadaki tepe daha yüksek, iki omuz birbirine yakın görünüyor.",
            points:[s[0].i,s[2].i,s[4].i]
          });
          break;
        }
      }

      if (
        s[0].type==="low" && s[1].type==="high" && s[2].type==="low" &&
        s[3].type==="high" && s[4].type==="low"
      ) {
        const shouldersClose = Math.abs(s[0].price-s[4].price)/((s[0].price+s[4].price)/2) <= 0.04;
        const headLower = s[2].price < s[0].price*0.98 && s[2].price < s[4].price*0.98;
        if (shouldersClose && headLower) {
          results.push({
            name:"Ters Omuz-Baş-Omuz Adayı",
            status:"aday",
            direction:"pozitif",
            confidence:76,
            reason:"Ortadaki dip daha düşük, iki omuz birbirine yakın görünüyor.",
            points:[s[0].i,s[2].i,s[4].i]
          });
          break;
        }
      }
    }

    // Triangle / squeeze proxy: recent 24 bars, lower highs + higher lows
    const recent = bars.slice(-24);
    if (recent.length >= 18) {
      const half = Math.floor(recent.length/2);
      const firstHigh = Math.max(...recent.slice(0,half).map(b=>b.high));
      const secondHigh = Math.max(...recent.slice(half).map(b=>b.high));
      const firstLow = Math.min(...recent.slice(0,half).map(b=>b.low));
      const secondLow = Math.min(...recent.slice(half).map(b=>b.low));
      const narrowing = secondHigh < firstHigh && secondLow > firstLow;
      const firstRange = firstHigh-firstLow;
      const secondRange = secondHigh-secondLow;
      if (narrowing && secondRange < firstRange*0.8) {
        results.push({
          name:"Üçgen / Sıkışma Adayı",
          status:"aday",
          direction:"nötr",
          confidence:72,
          reason:"Son bölümde daha düşük tepeler ve daha yüksek diplerle fiyat aralığı daralıyor.",
          points:[bars.length-24,bars.length-1]
        });
      }
    }

    // Cup & handle heuristic, intentionally labelled candidate
    if (bars.length >= 40) {
      const w = bars.slice(-50);
      const leftHigh = Math.max(...w.slice(0,12).map(b=>b.high));
      const midLow = Math.min(...w.slice(12,34).map(b=>b.low));
      const rightHigh = Math.max(...w.slice(28,42).map(b=>b.high));
      const handleLow = Math.min(...w.slice(40).map(b=>b.low));
      const rimDiff = Math.abs(leftHigh-rightHigh)/((leftHigh+rightHigh)/2);
      const cupDepth = (Math.min(leftHigh,rightHigh)-midLow)/Math.min(leftHigh,rightHigh);
      const handleDepth = (rightHigh-handleLow)/rightHigh;
      if (rimDiff <= 0.05 && cupDepth >= 0.05 && cupDepth <= 0.28 && handleDepth <= cupDepth*0.55) {
        results.push({
          name:"Fincan-Kulp Adayı",
          status:"aday",
          direction:"pozitif",
          confidence:68,
          reason:"Sol ve sağ kenarlar yakın, orta bölüm daha düşük ve son geri çekilme görece sığ.",
          points:[bars.length-50,bars.length-22,bars.length-8]
        });
      }
    }

    // de-dupe by name
    const unique: Result[] = [];
    for (const r of results) {
      if (!unique.some(x=>x.name===r.name)) unique.push(r);
    }

    return { swings, results: unique.slice(0,6) };
  }, [bars]);

  const best = analysis.results.length
    ? [...analysis.results].sort((a,b)=>b.confidence-a.confidence)[0]
    : null;

  const positives = analysis.results.filter(x=>x.direction==="pozitif").length;
  const negatives = analysis.results.filter(x=>x.direction==="negatif").length;
  const neutrals = analysis.results.filter(x=>x.direction==="nötr").length;

  return (
    <section className="patterns-page">
      <div className="patterns-head">
        <div>
          <span className="eyebrow">Formasyon Analizi</span>
          <h2>{selected}</h2>
          <small>Hafif istemci tarafı tarama · yalnızca bu görünüm açıkken</small>
        </div>
        <div className="patterns-range">
          <button className={chartRange==="1d"?"active":""} onClick={()=>setChartRange("1d")}>1 Gün</button>
          <button className={chartRange==="1w"?"active":""} onClick={()=>setChartRange("1w")}>1 Hafta</button>
        </div>
      </div>

      <div className="patterns-summary">
        <div>
          <span>En Belirgin Aday</span>
          <strong>{best?.name ?? "Belirgin aday yok"}</strong>
          <small>{best ? `Güven skoru: ${best.confidence}/100` : "Son 80 mum tarandı"}</small>
        </div>
        <div className="pattern-pos"><span>Pozitif</span><strong>{positives}</strong></div>
        <div className="pattern-neg"><span>Negatif</span><strong>{negatives}</strong></div>
        <div><span>Nötr</span><strong>{neutrals}</strong></div>
      </div>

      <div className="patterns-grid">
        <div className="patterns-chart candlestick-box">
          <div className="card-title">Fiyat Yapısı ve Swing Noktaları</div>
          <div className="patterns-svg-wrap">
            {bars.length ? (() => {
              const highs = bars.map(b=>b.high);
              const lows = bars.map(b=>b.low);
              const maxP = Math.max(...highs);
              const minP = Math.min(...lows);
              const pRange = Math.max(maxP-minP,0.0001);
              const slot = 760/bars.length;
              const bodyW = Math.max(2.2,slot*.5);
              const yPrice=(v:number)=>15+((maxP-v)/pRange)*205;

              return (
                <svg viewBox="0 0 760 250" preserveAspectRatio="none">
                  <g className="gridlines">
                    <line x1="0" y1="50" x2="760" y2="50"/>
                    <line x1="0" y1="100" x2="760" y2="100"/>
                    <line x1="0" y1="150" x2="760" y2="150"/>
                    <line x1="0" y1="200" x2="760" y2="200"/>
                  </g>
                  {bars.map((b,i)=>{
                    const x=i*slot+slot/2;
                    const yO=yPrice(b.open), yC=yPrice(b.close), yH=yPrice(b.high), yL=yPrice(b.low);
                    return (
                      <g key={`${b.time}-${i}`} className={b.close>=b.open?"candle-up":"candle-down"}>
                        <line x1={x} y1={yH} x2={x} y2={yL} className="wick"/>
                        <rect x={x-bodyW/2} y={Math.min(yO,yC)} width={bodyW} height={Math.max(Math.abs(yC-yO),1.2)} className="body"/>
                      </g>
                    )
                  })}
                  {analysis.swings.map((s,idx)=>{
                    const x=s.i*slot+slot/2;
                    const y=yPrice(s.price);
                    return <circle key={`${s.i}-${idx}`} cx={x} cy={y} r="3.2" className={s.type==="high"?"swing-high":"swing-low"}/>
                  })}
                  {best?.points?.map((pi,idx)=>{
                    const b=bars[pi];
                    if(!b) return null;
                    const x=pi*slot+slot/2;
                    const y=yPrice((b.high+b.low)/2);
                    return <circle key={`best-${pi}-${idx}`} cx={x} cy={y} r="7" className="pattern-focus"/>
                  })}
                </svg>
              );
            })() : <div className="chart-loading">Formasyon verisi bekleniyor…</div>}
          </div>
          <div className="patterns-legend">
            <span><i className="swing-high-dot"/> Swing tepe</span>
            <span><i className="swing-low-dot"/> Swing dip</span>
            <span><i className="pattern-focus-dot"/> En belirgin formasyon noktaları</span>
          </div>
        </div>

        <div className="patterns-list-card">
          <div className="card-title">Tespit Edilen Adaylar</div>
          <div className="patterns-list">
            {analysis.results.length ? analysis.results.map((r,idx)=>(
              <div className={`formation-item formation-${r.direction}`} key={`${r.name}-${idx}`}>
                <div className="formation-top">
                  <b>{r.name}</b>
                  <span>{r.confidence}/100</span>
                </div>
                <p>{r.reason}</p>
                <small>
                  {r.direction==="pozitif" ? "Pozitif yönlü aday" :
                   r.direction==="negatif" ? "Negatif yönlü aday" : "Yön teyidi beklenir"}
                </small>
              </div>
            )) : (
              <div className="empty-small">
                <span>◇</span>
                <b>Belirgin formasyon adayı yok</b>
                <small>Son 80 mumda temel fiyat yapıları tarandı.</small>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="patterns-info">
        <b>Önemli</b>
        <span>
          Bunlar otomatik “aday” tespitleridir. Formasyonun tamamlandığı veya kırılımın gerçekleştiği anlamına gelmez.
          Hacim, destek/direnç, trend ve risk filtreleriyle teyit edilmelidir.
        </span>
      </div>
    </section>
  );
}

function CandleAnalysisView({
  market,
  selected,
  chartRange,
  setChartRange,
}: {
  market: MarketDetail | null;
  selected: string;
  chartRange: "1d" | "1w";
  setChartRange: (v: "1d" | "1w") => void;
}) {
  const bars = market?.chart?.slice(-30) ?? [];

  const detected = useMemo(() => {
    type P = {
      name: string;
      tone: "good" | "bad" | "neutral";
      index: number;
      time: string;
      reason: string;
    };

    const out: P[] = [];
    const body = (b: MarketDetail["chart"][number]) => Math.abs(b.close - b.open);
    const range = (b: MarketDetail["chart"][number]) => Math.max(b.high - b.low, 0.0001);
    const upper = (b: MarketDetail["chart"][number]) => b.high - Math.max(b.open, b.close);
    const lower = (b: MarketDetail["chart"][number]) => Math.min(b.open, b.close) - b.low;

    bars.forEach((b, i) => {
      const bd = body(b);
      const rg = range(b);
      const up = upper(b);
      const lo = lower(b);
      const bullish = b.close > b.open;

      if (bd / rg <= 0.12) {
        out.push({
          name: "Doji",
          tone: "neutral",
          index: i,
          time: b.time,
          reason: "Açılış ve kapanış birbirine çok yakın; kararsızlık göstergesi olabilir.",
        });
      }

      if (lo >= bd * 2 && up <= Math.max(bd * 0.8, rg * 0.15) && bd / rg <= 0.45) {
        out.push({
          name: "Hammer",
          tone: "good",
          index: i,
          time: b.time,
          reason: "Uzun alt gölge ve küçük gövde; aşağı yönlü baskının reddedildiğini gösterebilir.",
        });
      }

      if (up >= bd * 2 && lo <= Math.max(bd * 0.8, rg * 0.15) && bd / rg <= 0.45) {
        out.push({
          name: "Shooting Star",
          tone: "bad",
          index: i,
          time: b.time,
          reason: "Uzun üst gölge; yukarı hareketin satışla karşılandığını gösterebilir.",
        });
      }

      if (i > 0) {
        const p = bars[i - 1];
        const prevBear = p.close < p.open;
        const prevBull = p.close > p.open;

        if (
          bullish &&
          prevBear &&
          b.open <= p.close &&
          b.close >= p.open
        ) {
          out.push({
            name: "Bullish Engulfing",
            tone: "good",
            index: i,
            time: b.time,
            reason: "Yükseliş mumu önceki düşüş gövdesini kapsıyor; pozitif dönüş sinyali olabilir.",
          });
        }

        if (
          !bullish &&
          prevBull &&
          b.open >= p.close &&
          b.close <= p.open
        ) {
          out.push({
            name: "Bearish Engulfing",
            tone: "bad",
            index: i,
            time: b.time,
            reason: "Düşüş mumu önceki yükseliş gövdesini kapsıyor; negatif dönüş sinyali olabilir.",
          });
        }
      }
    });

    return out.slice(-12).reverse();
  }, [bars]);

  const latest = detected[0] ?? null;
  const positiveCount = detected.filter((x) => x.tone === "good").length;
  const negativeCount = detected.filter((x) => x.tone === "bad").length;
  const neutralCount = detected.filter((x) => x.tone === "neutral").length;

  const overall =
    positiveCount > negativeCount ? "Pozitif ağırlıklı" :
    negativeCount > positiveCount ? "Negatif ağırlıklı" :
    "Nötr / karışık";

  return (
    <section className="candle-page">
      <div className="candle-page-head">
        <div>
          <span className="eyebrow">Mum Analizi</span>
          <h1>{selected}</h1>
          <small>Hesaplama yalnızca bu görünüm açıkken tarayıcıda yapılır.</small>
        </div>

        <div className="candle-range">
          <button className={chartRange === "1d" ? "active" : ""} onClick={() => setChartRange("1d")}>1 Gün</button>
          <button className={chartRange === "1w" ? "active" : ""} onClick={() => setChartRange("1w")}>1 Hafta</button>
        </div>
      </div>

      <div className="candle-summary-grid">
        <div>
          <span>Son Formasyon</span>
          <strong>{latest?.name ?? "Tespit yok"}</strong>
          <small>{latest ? new Intl.DateTimeFormat("tr-TR", {
            day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit",
            timeZone:"Europe/Istanbul"
          }).format(new Date(latest.time)) : "Son 30 mum tarandı"}</small>
        </div>
        <div className="candle-good"><span>Pozitif</span><strong>{positiveCount}</strong></div>
        <div className="candle-bad"><span>Negatif</span><strong>{negativeCount}</strong></div>
        <div><span>Nötr</span><strong>{neutralCount}</strong></div>
        <div><span>Genel Durum</span><strong>{overall}</strong></div>
      </div>

      <div className="candle-content-grid">
        <div className="candle-chart-card candlestick-box">
          <div className="card-title">Son Mumlar</div>
          <div className="candle-analysis-chart">
            {bars.length ? (() => {
              const highs = bars.map((b) => b.high);
              const lows = bars.map((b) => b.low);
              const maxP = Math.max(...highs);
              const minP = Math.min(...lows);
              const pRange = Math.max(maxP - minP, 0.0001);
              const slot = 760 / bars.length;
              const bodyW = Math.max(5, slot * 0.48);
              const yPrice = (v:number) => 18 + ((maxP - v) / pRange) * 190;

              return (
                <svg viewBox="0 0 760 240" preserveAspectRatio="none">
                  <g className="gridlines">
                    <line x1="0" y1="45" x2="760" y2="45"/>
                    <line x1="0" y1="90" x2="760" y2="90"/>
                    <line x1="0" y1="135" x2="760" y2="135"/>
                    <line x1="0" y1="180" x2="760" y2="180"/>
                  </g>

                  {bars.map((b, i) => {
                    const x = i * slot + slot / 2;
                    const yO = yPrice(b.open);
                    const yC = yPrice(b.close);
                    const yH = yPrice(b.high);
                    const yL = yPrice(b.low);
                    const y = Math.min(yO, yC);
                    const h = Math.max(Math.abs(yC-yO), 1.5);
                    const matches = detected.filter((d) => d.index === i);
                    return (
                      <g key={`${b.time}-${i}`} className={b.close >= b.open ? "candle-up" : "candle-down"}>
                        <line x1={x} y1={yH} x2={x} y2={yL} className="wick"/>
                        <rect x={x-bodyW/2} y={y} width={bodyW} height={h} className="body"/>
                        {matches.length > 0 && (
                          <>
                            <circle cx={x} cy={Math.max(9, yH - 8)} r="4" className={`pattern-dot pattern-${matches[0].tone}`}/>
                            <text x={x} y={Math.max(7, yH - 13)} textAnchor="middle" className="pattern-label">
                              {matches[0].name === "Bullish Engulfing" ? "BE" :
                               matches[0].name === "Bearish Engulfing" ? "SE" :
                               matches[0].name === "Shooting Star" ? "SS" :
                               matches[0].name === "Hammer" ? "H" : "D"}
                            </text>
                          </>
                        )}
                      </g>
                    );
                  })}
                </svg>
              );
            })() : <div className="chart-loading">Mum verisi bekleniyor…</div>}
          </div>
          <div className="pattern-legend">
            <span><i className="good-dot"/> Pozitif</span>
            <span><i className="bad-dot2"/> Negatif</span>
            <span><i className="neutral-dot"/> Nötr</span>
            <small>H: Hammer · D: Doji · SS: Shooting Star · BE/SE: Engulfing</small>
          </div>
        </div>

        <div className="pattern-list-card">
          <div className="card-title">Son Tespitler</div>
          <div className="pattern-list">
            {detected.length ? detected.map((p, idx) => (
              <div className={`pattern-item tone-${p.tone}`} key={`${p.time}-${p.name}-${idx}`}>
                <div>
                  <b>{p.name}</b>
                  <span>{new Intl.DateTimeFormat("tr-TR", {
                    day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit",
                    timeZone:"Europe/Istanbul"
                  }).format(new Date(p.time))}</span>
                </div>
                <p>{p.reason}</p>
              </div>
            )) : (
              <div className="empty-small">
                <span>◇</span>
                <b>Belirgin formasyon tespit edilmedi</b>
                <small>Son 30 mum içinde temel kalıplar aranmıştır.</small>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="candle-guide">
        <b>Nasıl kullanılır?</b>
        <span>
          Mum formasyonları tek başına işlem sinyali değildir. Destek/direnç, trend, hacim ve V7.2 filtreleriyle birlikte değerlendirilmelidir.
        </span>
      </div>
    </section>
  );
}

function IndicatorCard({
  title,
  value,
  status,
  note,
  tone,
}: {
  title: string;
  value: string;
  status: string;
  note: string;
  tone: "good" | "bad" | "warn" | "neutral";
}) {
  return (
    <article className={`indicator-card tone-${tone}`}>
      <span className="indicator-card-title">{title}</span>
      <strong>{value}</strong>
      <b>{status}</b>
      <small>{note}</small>
    </article>
  );
}

function MarketCard({name,value,sub}:{name:string;value:string;sub:string}) {
  return <div className="summary-card market-card">
    <span>{name}</span><strong>{value}</strong><small>{sub}</small>
  </div>;
}

function Metric({name,value}:{name:string;value:string}) {
  return <div className="summary-card metric-card2">
    <span>{name}</span><strong>{value}</strong>
  </div>;
}

function Level({name,value,red,green}:{name:string;value:string;red?:boolean;green?:boolean}) {
  return <div className="level-row">
    <b className={red ? "red" : green ? "green" : ""}>{name}</b><span>{value}</span>
  </div>;
}

function Tool({title,text}:{title:string;text:string}) {
  return <div className="tool-row"><b>{title}</b><span>{text}</span></div>;
}

function Empty({text}:{text:string}) {
  return <div className="empty-small"><span>◇</span><b>{text}</b><small>Yeni veri geldiğinde burada görünecek.</small></div>;
}
