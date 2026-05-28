"""
Edge Agent — Hayatta Kalma Motoru
────────────────────────────────────────
Geleneksel indikatör YOK.

Piyasayı kim hareket ettirir?
  1. MM, bilinen stop clusterlarını süpürür → sweep sonrası dön
  2. Funding aşırı negatifse shortlar sıkışacak → long aç
  3. OI artarken fiyat sabitsa birikim var → patlama yakın
  4. Haberler fiyatı indikatörden önce hareket ettirir
  5. NY açılışı gerçek likidite getirir, Asia sahte hareket
  6. CVD: fiyat yukarı ama gerçekte satış mı var?

Bunlar RSI değil. Bunlar piyasanın gerçek mekaniği.
"""

import time, datetime, threading, json, os, math, requests
from collections import deque
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, load_trades, get_price,
                 send_telegram, get_usdt_balance)

# ─── Sabitler ────────────────────────────────────────────────────────────────
STATE_FILE   = 'edge_state.json'
PERF_FILE    = 'edge_performance.json'
FUTURES_BASE = 'https://fapi.binance.com'
NEWS_URL     = 'https://cryptopanic.com/api/v1/posts/'

FUNDING_SQUEEZE      = -0.0005   # < -0.05%: shortlar sıkışıyor → bull
FUNDING_STRONG_SQ    = -0.0010   # < -0.10%: güçlü sıkışma
FUNDING_AVOID        = +0.0008   # > +0.08%: longlar aşırı yüklenmiş → kaçın

MAX_POSITIONS  = 6
SCAN_INTERVAL  = 60    # saniye
MONITOR_SEC    = 5
MIN_SCORE      = 4.5   # 0-10 — trend modda daha düşük eşik

STABLECOINS = {
    'USDCUSDT','BUSDUSDT','TUSDUSDT','FDUSDUSDT','EURUSDT',
    'GBPUSDT','DAIUSDT','FRAXUSDT','USDPUSDT','PYUSDUSDT','USDTUSDT',
    'UUSDT','USDEUSDT','SUSDEUSDT','CRVUSDUSDT','GHOUSDT','USDTBUSDT',
    'AEURUSDT','EURSUSDT','IDRTUSDT','BIDRUSDT','BRLAUSDT','USDSBUSDT',
}

DEFAULT_WEIGHTS = {
    'funding':   2.0,
    'sweep':     2.0,
    'oi':        1.5,
    'cvd':       1.0,
    'news':      1.5,
    'session':   0.5,
    'struct':    1.0,
    'btc_trend': 1.5,   # BTC yükseliyorsa tüm coinlere bonus
}

# ─── Public Futures API ───────────────────────────────────────────────────────

def _pub(path, params=None):
    try:
        r = requests.get(f'{FUTURES_BASE}{path}', params=params, timeout=8)
        return r.json() if r.ok else None
    except Exception:
        return None

def _all_funding() -> dict:
    """Tüm USDT-M perp funding rateleri. Auth gerektirmez."""
    data = _pub('/fapi/v1/premiumIndex')
    if not data:
        return {}
    return {
        d['symbol']: float(d.get('lastFundingRate', 0))
        for d in data
        if isinstance(d, dict) and d.get('symbol', '').endswith('USDT')
    }

def _oi_hist(symbol, period='5m', limit=12):
    return _pub('/futures/data/openInterestHist',
                {'symbol': symbol, 'period': period, 'limit': limit}) or []

def _liquidations(symbol):
    """Son saatin zorunlu tasfiyeler — public endpoint, auth gerekmez."""
    return _pub('/fapi/v1/allForceOrders', {'symbol': symbol, 'limit': 200}) or []

def _futures_symbols(min_vol=30_000_000) -> list:
    """Son 24 saatte quoteVolume > $30M olan futures semboller."""
    data = _pub('/fapi/v1/ticker/24hr')
    if not data:
        return []
    out = []
    for d in data:
        sym = d.get('symbol', '')
        if not sym.endswith('USDT') or sym in STABLECOINS:
            continue
        price = float(d.get('lastPrice', 0))
        if 0.90 <= price <= 1.10:  # stablecoin fiyat aralığı
            continue
        if float(d.get('quoteVolume', 0)) > min_vol:
            out.append((sym, float(d.get('quoteVolume', 0))))
    out.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in out[:60]]

# ─── Haber Motoru ─────────────────────────────────────────────────────────────

BULL_KW = ['etf','approval','listing','partnership','upgrade','mainnet',
           'adoption','institutional','halving','rally','surge','bullish',
           'billion','record','launch','integration','acquire']
BEAR_KW = ['hack','exploit','ban','regulation','fraud','bankrupt','arrest',
           'investigation','delist','scam','crash','lawsuit','stolen','breach',
           'rug','death','shutdown','suspended']

_news_cache = {'ts': 0.0, 'data': []}

def _fetch_news(api_key=''):
    if time.time() - _news_cache['ts'] < 180:
        return _news_cache['data']
    try:
        params = {'public': 'true', 'kind': 'news', 'filter': 'hot'}
        if api_key:
            params['auth_token'] = api_key
        r = requests.get(NEWS_URL, params=params, timeout=10)
        if r.ok:
            items = r.json().get('results', [])
            _news_cache.update({'ts': time.time(), 'data': items})
            return items
    except Exception:
        pass
    return _news_cache['data']

def _news_signal(symbol, api_key=''):
    coin = symbol.replace('USDT', '').lower()
    score = 0.0
    reason = ''
    for art in _fetch_news(api_key)[:40]:
        title = (art.get('title', '') + ' ' + art.get('domain', '')).lower()
        coins = [c.get('code', '').lower() for c in art.get('currencies', [])]
        if coin not in coins and coin not in title:
            continue
        try:
            dt  = datetime.datetime.fromisoformat(
                      art.get('created_at','').replace('Z','+00:00'))
            age = (datetime.datetime.now(datetime.timezone.utc) - dt).seconds / 3600
        except Exception:
            age = 3
        decay = max(0.2, 1.0 - age / 3)
        b = sum(1 for w in BULL_KW if w in title)
        be = sum(1 for w in BEAR_KW if w in title)
        if b > be:
            s = min(b * 0.6, 2.0) * decay
            if s > score:
                score = s
                reason = f"Bullish haber: {art.get('title','')[:70]}"
        elif be > b:
            s = -min(be * 0.6, 2.0) * decay
            if s < score:
                score = s
                reason = f"Bearish haber: {art.get('title','')[:70]}"
    return round(max(-2.0, min(2.0, score)), 2), reason

# ─── Session Timing ───────────────────────────────────────────────────────────

def _session():
    h = datetime.datetime.utcnow().hour + datetime.datetime.utcnow().minute / 60
    if 13.5 <= h < 20:    return 'NY',     1.15, 'Wall St aktif, ETF akışları'
    elif 8.0 <= h < 13.5: return 'LONDON', 1.0,  'Londra-NY örtüşmesi yakın'
    elif 0.0 <= h < 8.0:  return 'ASIA',   0.82, 'Asya sessiz, sahte hareket riski'
    else:                  return 'LATE',   0.9,  'Geç US sessizliği'

# ─── OI Sinyali ───────────────────────────────────────────────────────────────

_oi_price: dict = {}

def _oi_signal(symbol, price):
    hist = _oi_hist(symbol)
    if len(hist) < 4:
        return 0.0, 'OI verisi yok'
    try:
        vals  = [float(h['sumOpenInterest']) for h in hist]
        delta = (vals[-1] - vals[0]) / vals[0] * 100 if vals[0] else 0
        prev  = _oi_price.get(symbol, price)
        pdelta = (price - prev) / prev * 100 if prev else 0
        _oi_price[symbol] = price

        if delta > 5 and abs(pdelta) < 1.5:
            return 1.5, f'Gizli birikim: OI +{delta:.1f}% fiyat sabit'
        elif delta > 4 and pdelta < -1:
            return 1.2, f'Short squeeze kurulumu: OI↑ fiyat↓'
        elif delta > 5 and pdelta > 4:
            return -1.0, f'Kaldıraçlı balon: OI +{delta:.1f}% + fiyat ↑'
        elif delta < -6:
            return -0.8, f'Pozisyon kapatma: OI {delta:.1f}%'
        return 0.2, f'OI nötr ({delta:.1f}%)'
    except Exception as e:
        return 0.0, f'OI hata: {e}'

# ─── Likidite Sweep ───────────────────────────────────────────────────────────

def _sweep_signal(symbol, price):
    """
    MM bir stop clusterını süpürdüyse ve fiyat geri döndüyse → en güçlü sinyal.
    Son 1 saat içinde büyük LONG likidasyonu ALTI'mızda = sweep oldu = dön.
    """
    liqs = _liquidations(symbol)
    if not liqs:
        return 0.0, 'Son 1 saatte tasfiye yok'
    now_ms   = int(time.time() * 1000)
    hour_ago = now_ms - 3_600_000
    long_usd = sum(
        float(l.get('origQty', 0)) * float(l.get('price', 0))
        for l in liqs
        if l.get('side') == 'SELL'
        and int(l.get('time', 0)) > hour_ago
        and float(l.get('price', 0)) < price * 0.995
    )
    short_usd = sum(
        float(l.get('origQty', 0)) * float(l.get('price', 0))
        for l in liqs
        if l.get('side') == 'BUY'
        and int(l.get('time', 0)) > hour_ago
        and float(l.get('price', 0)) > price * 1.005
    )
    if long_usd > 1_000_000:
        return 2.5, f'BÜYÜK stop avı: ${long_usd/1e6:.1f}M long tasfiye (altımızda)'
    elif long_usd > 200_000:
        return 1.5, f'Stop avı: ${long_usd/1e3:.0f}K long tasfiye altımızda'
    elif short_usd > 500_000:
        return -1.5, f'Short sweep: ${short_usd/1e6:.1f}M üstümüzde'
    return 0.0, 'Anlamlı sweep yok'

# ─── CVD (Gerçek Alım/Satış Baskısı) ─────────────────────────────────────────

def _cvd_signal(client, symbol):
    """
    500 son işlem: taker buy vs taker sell.
    Fiyat yukarı gidip CVD negatifse → dağıtım, sahte pump.
    CVD pozitif ama fiyat düzse → gizli birikim.
    """
    try:
        trades   = client.get_recent_trades(symbol=symbol, limit=500)
        buy_vol  = sum(float(t['qty']) for t in trades if not t['isBuyerMaker'])
        sell_vol = sum(float(t['qty']) for t in trades if t['isBuyerMaker'])
        total    = buy_vol + sell_vol
        if total == 0:
            return 0.0, 'CVD veri yok'
        ratio     = buy_vol / total
        imbalance = (ratio - 0.5) * 2   # -1..+1
        if imbalance > 0.35:
            return min(imbalance * 1.5, 1.5), f'Alım baskısı: %{ratio*100:.0f} taker buy'
        elif imbalance < -0.35:
            return max(imbalance * 1.5, -1.5), f'Satış baskısı: %{(1-ratio)*100:.0f} taker sell'
        return imbalance * 0.4, f'CVD nötr (%{ratio*100:.0f} buy)'
    except Exception as e:
        return 0.0, f'CVD hata: {e}'

# ─── Piyasa Yapısı (indikatörsüz) ────────────────────────────────────────────

def _structure_signal(client, symbol):
    """
    4H chart: Higher High / Higher Low = uptrend (HH/HL).
    Lower High / Lower Low = downtrend (LH/LL).
    RSI değil — sadece fiyatın nereye gittiği.
    """
    try:
        from signal_engine import get_klines
        _, highs, lows, _ = get_klines(client, symbol, '4h', limit=16)
        if len(highs) < 6:
            return 0.0, 'Yetersiz veri'
        hh = sum(1 for i in range(1, 6) if highs[-i] > highs[-i-1])
        ll = sum(1 for i in range(1, 6) if lows[-i]  < lows[-i-1])
        if hh >= 4:
            return 1.0, f'Yapısal yukarı trend (4H HH/HL: {hh}/5)'
        elif ll >= 4:
            return -1.0, f'Yapısal aşağı trend (4H LH/LL: {ll}/5)'
        return 0.0, 'Yapısal konsolidasyon'
    except Exception:
        return 0.0, ''

# ─── BTC Trend (tüm piyasanın yönü) ─────────────────────────────────────────

_btc_trend_cache = {'ts': 0.0, 'val': (0.0, 'BTC verisi yok')}

def _btc_trend_signal(client):
    """
    BTC 4H'de yükseliyorsa tüm coinlere +1.5 bonus.
    Düşüyorsa -1.0. Piyasa trend değiştirdiğinde hızlı tepki.
    """
    global _btc_trend_cache
    if time.time() - _btc_trend_cache['ts'] < 300:
        return _btc_trend_cache['val']
    try:
        from signal_engine import get_klines
        closes, highs, lows, _ = get_klines(client, 'BTCUSDT', '4h', limit=22)
        sma20 = sum(closes[-20:]) / 20
        price = closes[-1]
        hh = sum(1 for i in range(1, 5) if highs[-i] > highs[-i-1])
        ll = sum(1 for i in range(1, 5) if lows[-i]  < lows[-i-1])

        if price > sma20 * 1.01 and hh >= 3:
            result = (1.5, f'BTC yukarı trend (HH:{hh}/4, fiyat SMA üstünde)')
        elif price > sma20:
            result = (0.8, f'BTC SMA üstünde, nötr yapı')
        elif price < sma20 * 0.99 and ll >= 3:
            result = (-1.2, f'BTC aşağı trend (LL:{ll}/4)')
        else:
            result = (-0.3, f'BTC SMA altında, zayıf')
        _btc_trend_cache = {'ts': time.time(), 'val': result}
        return result
    except Exception:
        return 0.0, 'BTC trend alınamadı'

# ─── Ana Skor ────────────────────────────────────────────────────────────────

def _score(client, symbol, funding, weights, cfg):
    try:
        price = get_price(client, symbol)
    except Exception as e:
        return {'score': 0, 'signal': None, 'reason': str(e), 'details': {}, 'price': 0}
    if not price or price <= 0:
        return {'score': 0, 'signal': None, 'reason': 'Spot fiyat alınamadı', 'details': {}, 'price': 0, 'session': '', 'funding': 0}

    news_key = cfg.get('cryptopanic_key', '')
    sess, sess_mult, sess_note = _session()

    parts = {
        'funding':   _funding_part(funding),
        'sweep':     _sweep_signal(symbol, price),
        'oi':        _oi_signal(symbol, price),
        'cvd':       _cvd_signal(client, symbol),
        'news':      _news_signal(symbol, news_key),
        'struct':    _structure_signal(client, symbol),
        'session':   ((sess_mult - 1.0) * 1.5, f'{sess}: {sess_note}'),
        'btc_trend': _btc_trend_signal(client),
    }

    raw = sum(v[0] * weights.get(k, 1.0) for k, v in parts.items())

    # Teorik max (hepsinin olumlu maksimumu)
    max_raw = (
        3.0 * weights.get('funding', 2.0) +
        2.5 * weights.get('sweep', 2.0) +
        1.5 * weights.get('oi', 1.5) +
        1.5 * weights.get('cvd', 1.0) +
        2.0 * weights.get('news', 1.5) +
        1.0 * weights.get('struct', 1.0) +
        0.3 * weights.get('session', 0.5) +
        1.5 * weights.get('btc_trend', 1.5)
    )

    # 0-10 normalize
    score = round(max(0.0, min(10.0,
        (raw + max_raw * 0.35) / (max_raw * 1.35) * 10
    )), 2)

    signal = 'buy' if score >= MIN_SCORE else None

    reason_parts = [v[1] for k, v in parts.items() if abs(v[0]) > 0.4 and v[1]]
    reason = ' | '.join(reason_parts)[:350]

    return {
        'score':   score,
        'signal':  signal,
        'price':   price,
        'reason':  reason,
        'details': {k: {'score': round(v[0],2), 'reason': v[1]}
                    for k, v in parts.items()},
        'funding': funding,
        'session': sess,
    }

def _funding_part(funding):
    if funding <= FUNDING_STRONG_SQ:
        return 3.0, f'Güçlü short squeeze: funding {funding*100:.3f}%'
    elif funding <= FUNDING_SQUEEZE:
        return 1.8, f'Short squeeze zone: funding {funding*100:.3f}%'
    elif funding >= FUNDING_AVOID:
        return -2.5, f'Long overloaded: {funding*100:.3f}% → KAÇIN'
    elif funding > 0.0003:
        return -0.5, f'Hafif long ağır: {funding*100:.3f}%'
    return 0.0, f'Funding nötr: {funding*100:.3f}%'

# ─── ATR-tabanlı TP/SL ───────────────────────────────────────────────────────

def _atr(highs, lows, closes, n=14):
    trs = [max(highs[i]-lows[i],
               abs(highs[i]-closes[i-1]),
               abs(lows[i]-closes[i-1]))
           for i in range(1, len(closes))]
    return sum(trs[-n:]) / n if len(trs) >= n else closes[-1] * 0.02

# ─── Ajan ────────────────────────────────────────────────────────────────────

class EdgeAgent:
    def __init__(self):
        self._running   = False
        self._lock      = threading.Lock()
        self.state      = self._load_state()
        self.perf       = self._load_perf()
        # Kaydedilmiş state'de eksik anahtar olabilir (ör. btc_trend yeni eklendi)
        loaded_weights  = self.state.get('weights', {})
        self.weights    = {**DEFAULT_WEIGHTS, **loaded_weights}
        self.blacklist  = self.state.get('blacklist', {})
        self.scan_log   = deque(maxlen=50)
        self._notified  = {}   # symbol → timestamp, spam önleyici

    # ── Kalıcılık ──────────────────────────────────────────────────────────
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {'weights': dict(DEFAULT_WEIGHTS), 'blacklist': {},
                'daily': {'trades': 0, 'wins': 0, 'pnl': 0.0, 'start_bal': 0.0},
                'scan_count': 0, 'total_pnl': 0.0}

    def _save_state(self):
        self.state['weights']   = self.weights
        self.state['blacklist'] = self.blacklist
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _load_perf(self):
        if os.path.exists(PERF_FILE):
            try:
                with open(PERF_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {k: {'wins': 0, 'total': 0} for k in DEFAULT_WEIGHTS}

    def _save_perf(self):
        with open(PERF_FILE, 'w') as f:
            json.dump(self.perf, f, indent=2)

    # ── Başlat / Durdur ────────────────────────────────────────────────────
    def start(self):
        if self._running:
            return False
        self._running = True
        for fn in [self._scanner_loop, self._monitor_loop,
                   self._hourly_loop, self._daily_loop, self._learn_loop]:
            threading.Thread(target=fn, daemon=True).start()

        cfg = load_config()
        client = get_client()
        try:
            bal = get_usdt_balance(client)
            self.state['daily']['start_bal'] = bal
        except Exception:
            bal = 0
        mode = '🔴 GERÇEK' if not cfg.get('testnet', True) else '🧪 TESTNET'
        print('[Edge] Başladı')
        send_telegram(
            f'{mode} <b>Edge Agent AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📡 Sinyal: Funding + Sweep + OI + CVD + Haber\n'
            f'⚡ Tarama: {SCAN_INTERVAL}s | Takip: {MONITOR_SEC}s\n'
            f'🎯 Min Skor: {MIN_SCORE}/10 | Max Pos: {MAX_POSITIONS}\n'
            f'⚠️ Geleneksel indikatör yok. Piyasa mekaniği.'
        )
        return True

    def stop(self):
        self._running = False
        self._save_state()

    # ── Tarama ─────────────────────────────────────────────────────────────
    def _scanner_loop(self):
        time.sleep(10)
        while self._running:
            try:
                self._scan()
            except Exception as e:
                print(f'[Edge] Tarama hata: {e}')
            time.sleep(SCAN_INTERVAL)

    def _scan(self):
        cfg    = load_config()
        client = get_client()

        from manager_agent import ceo_flag
        if not ceo_flag(cfg, 'edge_enabled', True):
            print('[Edge] CEO tarafından durduruldu, tarama atlandı')
            return

        positions = load_positions()
        open_count = sum(1 for p in positions.values() if p.get('qty', 0) > 0)
        if open_count >= MAX_POSITIONS:
            return

        # Günlük zarar limiti
        try:
            bal = get_usdt_balance(client)
            start_bal = self.state['daily'].get('start_bal', bal) or bal
            if start_bal > 0 and (bal - start_bal) / start_bal * 100 < -8.0:
                print('[Edge] Günlük zarar limiti: işlemler durduruldu')
                return
        except Exception:
            pass

        # Funding rates al
        fundings = _all_funding()
        symbols  = _futures_symbols()
        scan_no  = self.state.get('scan_count', 0) + 1
        print(f'[Edge] Tarama #{scan_no}: {len(symbols)} futures sembol, açık={open_count}')

        # Önce extreme funding'i olan coinlere bak
        candidates = []
        for sym in symbols:
            if sym in self.blacklist:
                bl_until = self.blacklist[sym]
                if time.time() < bl_until:
                    continue
                else:
                    del self.blacklist[sym]

            f = fundings.get(sym, 0.0)
            priority = abs(f - FUNDING_SQUEEZE)  # funding'e en yakın = en öncelikli
            candidates.append((sym, f, priority))

        # Önce extreme negatif funding olanlar
        candidates.sort(key=lambda x: x[2])

        checked = 0
        for sym, funding, _ in candidates:
            if not self._running:
                break
            if checked >= 40:
                break
            if sym in load_positions() and load_positions()[sym].get('qty', 0) > 0:
                checked += 1
                continue

            result = _score(client, sym, funding, self.weights, cfg)
            self.state['scan_count'] = self.state.get('scan_count', 0) + 1
            checked += 1

            log_line = f'{sym} {result["score"]:.1f}/10 {result["session"]}'
            self.scan_log.appendleft(log_line)

            if result['signal'] == 'buy':
                # Veto: yapısal aşağı trend + BTC zayıf → funding tek başına yetmez
                d = result.get('details', {})
                struct_score = d.get('struct', {}).get('score', 0)
                btc_score    = d.get('btc_trend', {}).get('score', 0)
                if struct_score < -0.5 and btc_score < 0:
                    self.scan_log.appendleft(f'{sym} VETO: struct={struct_score} btc={btc_score}')
                    checked += 1
                    continue

                self._do_buy(client, sym, result, cfg)
                open_count += 1
                if open_count >= MAX_POSITIONS:
                    break

        self._save_state()

    def _do_buy(self, client, symbol, result, cfg):
        is_real  = not cfg.get('testnet', True)
        try:
            bal = get_usdt_balance(client)
        except Exception:
            bal = 100.0

        # Pozisyon büyüklüğü: skor bazlı Kelly
        risk = 0.015 if is_real else 0.025
        score_mult = max(0.5, min(1.0, (result['score'] - 5.0) / 4.0))
        ceo_mult   = cfg.get('ceo_position_mult', 1.0)
        usdt = round(bal * risk * score_mult * ceo_mult, 2)
        usdt = max(5.0, min(usdt, bal * (0.05 if is_real else 0.10)))

        positions = load_positions()
        if len([p for p in positions.values() if p.get('qty', 0) > 0]) >= MAX_POSITIONS:
            return

        # Hangi sinyaller aktifti — öğrenme için kaydet
        active_signals = {k: v['score'] for k, v in result['details'].items() if abs(v['score']) > 0.3}

        score_str = '\n'.join(
            f"  {'✅' if v['score']>0 else '❌'} {k}: {v['score']:+.1f} — {v['reason'][:60]}"
            for k, v in result['details'].items()
            if v['reason']
        )
        send_telegram(
            f'🎯 <b>{symbol}</b> ALIM SİNYALİ\n'
            f'━━━━━━━━━━━━━━\n'
            f'📊 Skor: {result["score"]}/10\n'
            f'{score_str}\n'
            f'💰 Miktar: ${usdt:.2f} | Session: {result["session"]}\n'
            f'📈 Fiyat: ${result["price"]:.4f}'
        )

        res = execute_buy(client, symbol, usdt, source='EDGE', period=result['session'])
        if res.get('ok'):
            with self._lock:
                from bot import save_positions
                positions = load_positions()
                if symbol in positions:
                    positions[symbol]['agent']        = 'EDGE'
                    positions[symbol]['edge_signals'] = active_signals
                    positions[symbol]['edge_score']   = result['score']
                    positions[symbol]['open_time']    = time.time()
                    save_positions(positions)

    # ── Pozisyon Takibi ────────────────────────────────────────────────────
    def _monitor_loop(self):
        while self._running:
            try:
                self._monitor()
            except Exception as e:
                print(f'[Edge] Monitor hata: {e}')
            time.sleep(MONITOR_SEC)

    def _monitor(self):
        cfg       = load_config()
        client    = get_client()
        positions = load_positions()
        fundings  = {}

        for symbol, pos in list(positions.items()):
            qty = pos.get('qty', 0)
            if qty <= 0:
                continue
            if pos.get('agent', 'EDGE') != 'EDGE':
                continue

            # Aynı sembol için 60 saniye içinde tekrar bildirim gönderme
            last_notif = self._notified.get(symbol, 0)
            if time.time() - last_notif < 60:
                continue

            try:
                price     = get_price(client, symbol)
                avg_price = pos.get('avg_price', price)
                if avg_price <= 0:
                    continue
                pct = (price - avg_price) / avg_price * 100

                # ATR bazlı TP/SL (varsa)
                tp = pos.get('tp_pct', 0) or 0
                sl = pos.get('sl_pct', 0) or 0

                if tp > 0 and pct >= tp:
                    self._notified[symbol] = time.time()
                    send_telegram(f'💚 <b>{symbol}</b> KÂR HEDEFİ +%{pct:.2f}')
                    res = execute_sell(client, symbol, 100, source='EDGE TP', period='TP')
                    self._notified.pop(symbol, None)
                    self._force_clear(symbol, res)
                    self._record_exit(symbol, pos, pct, 'TP')
                    continue

                if sl > 0 and pct <= -sl:
                    self._notified[symbol] = time.time()
                    send_telegram(f'🔴 <b>{symbol}</b> STOP LOSS %{pct:.2f}')
                    res = execute_sell(client, symbol, 100, source='EDGE SL', period='SL')
                    self._notified.pop(symbol, None)
                    self._force_clear(symbol, res)
                    self.blacklist[symbol] = time.time() + 6 * 3600
                    self._record_exit(symbol, pos, pct, 'SL')
                    continue

                # Trailing stop: %40 TP'de aktif, peak'ten %2.5 düşüşte çık
                peak = pos.get('peak_price', avg_price)
                if price > peak:
                    positions[symbol]['peak_price'] = price

                if tp > 0 and pct >= tp * 0.4:
                    drawdown = (price - peak) / peak * 100 if peak > 0 else 0
                    if drawdown <= -2.5:
                        self._notified[symbol] = time.time()
                        send_telegram(f'🔁 <b>{symbol}</b> Trailing Stop %{pct:.2f} → çıkılıyor')
                        res = execute_sell(client, symbol, 100, source='EDGE TRAIL', period='TRAIL')
                        if res.get('ok'):
                            self._notified.pop(symbol, None)
                            self._record_exit(symbol, pos, pct, 'TRAIL')
                        continue

                # Funding rejim değişimi: long tutarken funding çok pozitif → çık
                if symbol not in fundings:
                    f = _all_funding().get(symbol, 0)
                    fundings[symbol] = f
                if fundings.get(symbol, 0) >= FUNDING_AVOID and pct > 0.5:
                    self._notified[symbol] = time.time()
                    send_telegram(
                        f'⚠️ <b>{symbol}</b> Funding {fundings[symbol]*100:.3f}% → long riski, çıkılıyor'
                    )
                    res = execute_sell(client, symbol, 100, source='EDGE FUNDING EXIT', period='FUND')
                    if res.get('ok'):
                        self._notified.pop(symbol, None)
                        self._record_exit(symbol, pos, pct, 'FUND_EXIT')
                    continue

                # Max tutma süresi: 48 saat
                open_ts = pos.get('open_time', time.time())
                if time.time() - open_ts > 48 * 3600:
                    send_telegram(f'⏰ <b>{symbol}</b> 48 saat doldu, kapatılıyor (P&L: %{pct:.2f})')
                    execute_sell(client, symbol, 100, source='EDGE TIME', period='TIMEOUT')
                    self._record_exit(symbol, pos, pct, 'TIMEOUT')

            except Exception as e:
                print(f'[Edge] Monitor {symbol}: {e}')

    def _force_clear(self, symbol, sell_result):
        """Satış başarısız olsa bile pozisyonu sıfırla (elle silinen pozisyonlar için)."""
        if not sell_result.get('ok'):
            try:
                from bot import save_positions
                positions = load_positions()
                if symbol in positions:
                    positions[symbol]['qty'] = 0
                    save_positions(positions)
                    print(f'[Edge] {symbol} zorla sıfırlandı (satış başarısız ama pozisyon temizlendi)')
            except Exception as e:
                print(f'[Edge] force_clear hata {symbol}: {e}')

    def _record_exit(self, symbol, pos, pct, reason):
        """Çıkış sonrası öğrenme güncelleme."""
        with self._lock:
            won = pct > 0
            signals = pos.get('edge_signals', {})
            for sig in signals:
                if sig not in self.perf:
                    self.perf[sig] = {'wins': 0, 'total': 0}
                self.perf[sig]['total'] += 1
                if won:
                    self.perf[sig]['wins'] += 1
            # Dolar bazlı PnL (yüzde değil)
            dollar_pnl = round(
                pos.get('qty', 0) * pos.get('avg_price', 0) * pct / 100, 2)
            self.state['total_pnl'] = round(
                self.state.get('total_pnl', 0) + dollar_pnl, 2)
            d = self.state.setdefault('daily', {})
            d['trades'] = d.get('trades', 0) + 1
            if won:
                d['wins'] = d.get('wins', 0) + 1
            self._save_state()
            self._save_perf()
            if symbol in self.blacklist:
                del self.blacklist[symbol]

    # ── Saatlik Rapor ──────────────────────────────────────────────────────
    def _hourly_loop(self):
        now = datetime.datetime.now()
        time.sleep(max(0, (60 - now.minute) * 60 - now.second))
        while self._running:
            try:
                self._hourly_report()
            except Exception as e:
                print(f'[Edge] Saatlik hata: {e}')
            interval = int(load_config().get('report_interval_hours', 1))
            time.sleep(interval * 3600)

    def _hourly_report(self):
        client    = get_client()
        positions = load_positions()
        open_pos  = {s: p for s, p in positions.items() if p.get('qty', 0) > 0}

        try:
            bal = get_usdt_balance(client)
        except Exception:
            bal = 0

        pos_lines = []
        total_pnl = 0.0
        for sym, pos in open_pos.items():
            try:
                price  = get_price(client, sym)
                avg    = pos.get('avg_price', price)
                pct    = (price - avg) / avg * 100 if avg > 0 else 0
                total_pnl += pct
                icon   = '🟢' if pct > 0 else '🔴'
                agent = pos.get('agent', 'EDGE')
                pos_lines.append(
                    f'{icon} {sym} [{agent}]: %{pct:+.2f} | Giriş: ${avg:.4f} | Şimdi: ${price:.4f}'
                )
            except Exception:
                pass

        sess, _, sess_note = _session()
        d = self.state.get('daily', {})

        msg = (
            f'📊 <b>Edge Agent Saatlik Rapor</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📦 Açık Pozisyon: {len(open_pos)}/{MAX_POSITIONS}\n'
        )
        if pos_lines:
            msg += '\n'.join(pos_lines) + '\n'
        msg += (
            f'━━━━━━━━━━━━━━\n'
            f'🔍 Tarama: {self.state.get("scan_count", 0)}x\n'
            f'📈 Bugün: {d.get("trades", 0)} işlem, '
            f'{d.get("wins", 0)} kazanan\n'
            f'🌍 Session: {sess} — {sess_note}\n'
            f'⚖️ Ağırlıklar: '
            + ', '.join(f'{k}={v:.1f}' for k, v in self.weights.items())
        )
        send_telegram(msg)

    # ── Günlük Özet ────────────────────────────────────────────────────────
    def _daily_loop(self):
        while self._running:
            now = datetime.datetime.utcnow()
            nxt = now.replace(hour=23, minute=55, second=0, microsecond=0)
            if now >= nxt:
                nxt += datetime.timedelta(days=1)
            time.sleep(max(0, (nxt - now).total_seconds()))
            try:
                self._daily_report()
                self.state['daily'] = {
                    'trades': 0, 'wins': 0, 'pnl': 0.0,
                    'start_bal': get_usdt_balance(get_client())
                }
                self._save_state()
            except Exception as e:
                print(f'[Edge] Günlük hata: {e}')

    def _daily_report(self):
        d = self.state.get('daily', {})
        t = d.get('trades', 0)
        w = d.get('wins', 0)
        wr = w / t * 100 if t > 0 else 0
        try:
            bal = get_usdt_balance(get_client())
        except Exception:
            bal = 0
        perf_lines = []
        for sig, p in self.perf.items():
            if p['total'] > 0:
                swr = p['wins'] / p['total'] * 100
                perf_lines.append(f'  {sig}: %{swr:.0f} ({p["wins"]}/{p["total"]})')
        send_telegram(
            f'📅 <b>Edge Agent Günlük Özet</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📈 İşlem: {t} | Kazanan: {w} | WR: %{wr:.1f}\n'
            f'━━━━━━━━━━━━━━\n'
            f'📡 Sinyal Başarı:\n' + ('\n'.join(perf_lines) or '  Veri yok henüz')
        )

    # ── Self-learning ──────────────────────────────────────────────────────
    def _learn_loop(self):
        time.sleep(3600 * 6)
        while self._running:
            try:
                self._adjust_weights()
            except Exception as e:
                print(f'[Edge] Öğrenme hata: {e}')
            time.sleep(3600 * 12)

    def _adjust_weights(self):
        changed = []
        for sig, p in self.perf.items():
            if p['total'] < 5:
                continue
            wr = p['wins'] / p['total']
            w  = self.weights.get(sig, DEFAULT_WEIGHTS.get(sig, 1.0))
            if wr > 0.65:
                new_w = min(round(w + 0.15, 2), 3.5)
                if new_w != w:
                    self.weights[sig] = new_w
                    changed.append(f'{sig}: {w:.1f}→{new_w:.1f} ↑ (WR%{wr*100:.0f})')
            elif wr < 0.38:
                new_w = max(round(w - 0.15, 2), 0.2)
                if new_w != w:
                    self.weights[sig] = new_w
                    changed.append(f'{sig}: {w:.1f}→{new_w:.1f} ↓ (WR%{wr*100:.0f})')
        if changed:
            self._save_state()
            send_telegram(
                '🧠 <b>Edge Agent Ağırlık Güncelleme</b>\n' +
                '\n'.join(changed)
            )

    # ── Status ─────────────────────────────────────────────────────────────
    def status(self):
        positions = load_positions()
        open_pos  = {s: p for s, p in positions.items() if p.get('qty', 0) > 0}
        d = self.state.get('daily', {})
        return {
            'running':     self._running,
            'open':        len(open_pos),
            'scan_count':  self.state.get('scan_count', 0),
            'total_pnl':   self.state.get('total_pnl', 0),
            'daily':       d,
            'weights':     self.weights,
            'blacklist':   {s: int(t - time.time()) for s, t in self.blacklist.items()
                            if t > time.time()},
            'last_scans':  list(self.scan_log)[:10],
        }

# ─── Global API ──────────────────────────────────────────────────────────────

_agent = None  # type: EdgeAgent
_agent_lock = threading.Lock()

def start_edge_agent():
    global _agent
    with _agent_lock:
        if _agent and _agent._running:
            return False
        _agent = EdgeAgent()
        return _agent.start()

def stop_edge_agent():
    global _agent
    with _agent_lock:
        if _agent:
            _agent.stop()

def trigger_edge_report():
    if _agent and _agent._running:
        try:
            _agent._hourly_report()
        except Exception as e:
            print(f'[Edge] Manuel rapor hatası: {e}')

def edge_agent_status():
    global _agent
    if not _agent:
        return {'running': False}
    return _agent.status()
