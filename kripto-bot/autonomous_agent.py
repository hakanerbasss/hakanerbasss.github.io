"""
Otonom Kripto Ajan v2 — Gerçek Zamanlı
─────────────────────────────────────────
• Her 3 saniyede pozisyon takibi (SL/TP/trailing)
• Her 90 saniyede top-100 fırsat taraması
• Çoklu zaman dilimi (15m + 1h) confluance
• Bollinger Bands + Stochastic RSI + VWAP
• Kelly Criterion ile dinamik pozisyon boyutu
• Günlük kayıp limiti (-8% → işlemler durur)
• Gerçek/testnet modu farkı: gerçekte daha muhafazakâr
• Telegram: her alım/satış gerekçe + saatlik rapor + günlük özet
"""

import time, datetime, threading, json, os, math
from collections import deque
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, save_positions, load_trades, get_price,
                 send_telegram, get_usdt_balance)

# ─── Sabitler ────────────────────────────────────────────────────────────────
STATE_FILE    = 'agent_state.json'
STABLECOINS   = {
    'USDCUSDT','BUSDUSDT','TUSDUSDT','USDTUSDT','FDUSDUSDT',
    'EURUSDT','GBPUSDT','DAIUSDT','FRAXUSDT','USDPUSDT','PYUSDUSDT',
    'UUSDT','USDEUSDT','SUSDEUSDT','CRVUSDUSDT','GHOUSDT','USDTBUSDT',
    'AEURUSDT','EURSUSDT','IDRTUSDT','BIDRUSDT','BRLAUSDT','USDSBUSDT',
}

_stable_cache: set = set()

def _build_stable_cache(client):
    """Binance top 200'de fiyatı $0.90-$1.10 arası olan coinleri tespit eder."""
    global _stable_cache
    try:
        tickers = client.get_ticker()
        found = set()
        for t in tickers:
            sym = t.get('symbol', '')
            if not sym.endswith('USDT'):
                continue
            price  = float(t.get('lastPrice', 0))
            change = abs(float(t.get('priceChangePercent', 99)))
            vol    = float(t.get('quoteVolume', 0))
            if 0.90 <= price <= 1.10 and change < 1.0 and vol > 100_000:
                found.add(sym)
        _stable_cache = found
        if found:
            print(f'[Otonom] Stablecoin tespiti: {sorted(found)}')
    except Exception as e:
        print(f'[Otonom] Stablecoin tarama hatası: {e}')

DEFAULT_WEIGHTS = {
    'trend': 2.5, 'momentum': 3.0, 'volume': 1.5,
    'pattern': 1.5, 'bb': 1.0, 'market': 0.5,
}


# ─── Matematik Yardımcıları ───────────────────────────────────────────────────

def _ema(s, n):
    if len(s) < n: return s[-1] if s else 0
    k = 2 / (n + 1); e = sum(s[:n]) / n
    for v in s[n:]: e = v * k + e * (1 - k)
    return e

def _rsi(s, n=14):
    if len(s) < n + 1: return 50.0
    d = [s[i] - s[i-1] for i in range(1, len(s))]
    g = sum(max(v,0) for v in d[-n:]) / n
    l = sum(max(-v,0) for v in d[-n:]) / n
    return 100.0 if l == 0 else round(100 - 100/(1 + g/l), 1)

def _stoch_rsi(closes, rsi_n=14, stoch_n=14):
    if len(closes) < rsi_n + stoch_n + 1: return 50.0
    rsi_vals = [_rsi(closes[:i+1], rsi_n) for i in range(rsi_n, len(closes))]
    if len(rsi_vals) < stoch_n: return 50.0
    window = rsi_vals[-stoch_n:]
    mn, mx = min(window), max(window)
    if mx == mn: return 50.0
    return round((rsi_vals[-1] - mn) / (mx - mn) * 100, 1)

def _macd(s, fast=12, slow=26, sig=9):
    if len(s) < slow + sig: return 0.0, 0.0, False
    macd_s = [_ema(s[:i+1], fast) - _ema(s[:i+1], slow)
               for i in range(slow-1, len(s))]
    macd_now = macd_s[-1]
    sig_now  = sum(macd_s[-sig:]) / sig
    cross    = len(macd_s) > 1 and macd_s[-2] <= (sum(macd_s[-sig-1:-1]) / sig) and macd_now > sig_now
    return macd_now, sig_now, cross

def _bollinger(closes, n=20, std_mult=2.0):
    if len(closes) < n: return closes[-1], closes[-1], closes[-1]
    window = closes[-n:]
    mid  = sum(window) / n
    std  = math.sqrt(sum((v - mid)**2 for v in window) / n)
    return mid - std_mult * std, mid, mid + std_mult * std

def _atr(highs, lows, closes, n=14):
    if len(closes) < n + 2: return closes[-1] * 0.02
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1, len(closes))]
    return sum(trs[-n:]) / n

def _adx(highs, lows, closes, n=14):
    if len(closes) < n + 2: return 20.0
    trs, pdms, ndms = [], [], []
    for i in range(1, len(closes)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        pdm = max(highs[i]-highs[i-1], 0)
        ndm = max(lows[i-1]-lows[i], 0)
        if pdm < ndm: pdm = 0
        if ndm < pdm: ndm = 0
        pdms.append(pdm); ndms.append(ndm)
    atr = sum(trs[-n:]) / n
    if atr == 0: return 20.0
    pdi = (sum(pdms[-n:]) / n) / atr * 100
    ndi = (sum(ndms[-n:]) / n) / atr * 100
    denom = pdi + ndi
    return round(abs(pdi-ndi) / denom * 100, 1) if denom else 20.0

def _vwap(highs, lows, closes, volumes, n=20):
    if len(closes) < n: return closes[-1]
    tp_vol = sum((highs[i]+lows[i]+closes[i])/3 * volumes[i]
                 for i in range(-n, 0))
    vol_sum = sum(volumes[-n:])
    return tp_vol / vol_sum if vol_sum else closes[-1]


# ─── Veri Çekme ──────────────────────────────────────────────────────────────

def _klines(client, sym, interval='1h', limit=120):
    from binance.client import Client as BC
    imap = {'1m': BC.KLINE_INTERVAL_1MINUTE,  '5m':  BC.KLINE_INTERVAL_5MINUTE,
            '15m': BC.KLINE_INTERVAL_15MINUTE, '1h':  BC.KLINE_INTERVAL_1HOUR,
            '4h': BC.KLINE_INTERVAL_4HOUR,     '1d':  BC.KLINE_INTERVAL_1DAY}
    kl = client.get_klines(symbol=sym, interval=imap.get(interval, BC.KLINE_INTERVAL_1HOUR), limit=limit)
    kl = kl[:-1]
    o = [float(k[1]) for k in kl]; h = [float(k[2]) for k in kl]
    l = [float(k[3]) for k in kl]; c = [float(k[4]) for k in kl]
    v = [float(k[5]) for k in kl]
    return o, h, l, c, v

def _top_100(client):
    tickers = client.get_ticker()
    all_stable = STABLECOINS | _stable_cache
    usdt = [t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in all_stable
            and float(t.get('quoteVolume', 0)) > 1_000_000
            and float(t.get('lastPrice', 0)) > 0
            and not (0.90 <= float(t.get('lastPrice', 0)) <= 1.10)
            and float(t.get('priceChangePercent', 0)) <= 20.0]  # zirve sonrası alım engeli
    usdt.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
    return [t['symbol'] for t in usdt[:100]]


# ─── Piyasa Rejimi ────────────────────────────────────────────────────────────

def _regime(client):
    try:
        _, h, l, c, _ = _klines(client, 'BTCUSDT', '1h', 60)
        e20 = _ema(c, 20); e50 = _ema(c, 50)
        rsi = _rsi(c, 14);  adx = _adx(h, l, c, 14)
        curr = c[-1]
        if   curr > e20 > e50 and rsi > 45 and adx > 20: return 'BULL'
        elif curr < e20 < e50 and rsi < 55 and adx > 20: return 'BEAR'
        else:                                              return 'SIDEWAYS'
    except Exception:
        return 'SIDEWAYS'


# ─── Fırsat Skoru (0-10) ─────────────────────────────────────────────────────

def _score(client, sym, regime, weights):
    try:
        o1, h1, l1, c1, v1 = _klines(client, sym, '1h', 120)
        o2, h2, l2, c2, v2 = _klines(client, sym, '15m', 80)
        if len(c1) < 60 or len(c2) < 30: return None

        # ── Trend (1h) ───────────────────────────────
        e20  = _ema(c1, 20); e50  = _ema(c1, 50); e100 = _ema(c1, 100)
        adx  = _adx(h1, l1, c1, 14)
        curr = c1[-1]
        t = 0.0
        if curr > e20:  t += 0.35
        if e20  > e50:  t += 0.35
        if e50  > e100: t += 0.20
        if adx  > 22:   t += 0.10
        trend = t * weights['trend']

        # ── Momentum (15m + 1h confluance) ──────────
        rsi1h  = _rsi(c1, 14)
        rsi15m = _rsi(c2, 14)
        srsi   = _stoch_rsi(c1, 14, 14)
        m1, s1, cross1h  = _macd(c1)
        m2, s2, cross15m = _macd(c2)
        mom = 0.0
        if 35 <= rsi1h  <= 62: mom += 0.25
        if 30 <= rsi15m <= 60: mom += 0.15
        if srsi < 30:          mom += 0.20
        if m1 > s1:            mom += 0.20
        if cross1h:            mom += 0.20
        if cross15m:           mom += 0.10
        if m1 > s1 and m2 > s2: mom = min(mom + 0.10, 1.0)
        momentum = mom * weights['momentum']

        # ── Hacim ────────────────────────────────────
        avg_v  = sum(v1[-21:-1]) / 20 if len(v1) > 21 else v1[-1]
        vr     = v1[-1] / avg_v if avg_v > 0 else 1.0
        volume = min(vr / 3.0, 1.0) * weights['volume']

        # ── Bollinger Bands pozisyonu ─────────────────
        bb_low, bb_mid, bb_up = _bollinger(c1, 20)
        bb_pos = (curr - bb_low) / (bb_up - bb_low) if (bb_up - bb_low) > 0 else 0.5
        if   0.05 <= bb_pos <= 0.25: bb_sc = 1.0
        elif 0.25 <  bb_pos <= 0.45: bb_sc = 0.6
        elif bb_pos < 0.05:          bb_sc = 0.3
        else:                        bb_sc = 0.0
        bb = bb_sc * weights['bb']

        # ── Formasyon ────────────────────────────────
        o0, h0, l0, c0 = o1[-1], h1[-1], l1[-1], c1[-1]
        o_1, h_1, l_1, c_1 = o1[-2], h1[-2], l1[-2], c1[-2]
        body0 = abs(c0 - o0); lower0 = min(o0,c0) - l0; upper0 = h0 - max(o0,c0)
        pat = 0.0
        if c_1 < o_1 and c0 > o0 and c0 > o_1 and o0 < c_1: pat += 0.55
        if lower0 > 2*body0 and upper0 < body0 and c0 > o0:  pat += 0.45
        vwap = _vwap(h1, l1, c1, v1)
        if curr < vwap * 1.002:                               pat += 0.20
        pattern = min(pat, 1.0) * weights['pattern']

        # ── Piyasa ───────────────────────────────────
        mkt_raw = {'BULL': 1.0, 'SIDEWAYS': 0.5, 'BEAR': 0.1}.get(regime, 0.5)
        market  = mkt_raw * weights['market']

        total     = trend + momentum + volume + bb + pattern + market
        max_total = sum(weights.values())
        score     = round(total / max_total * 10, 2)

        atr_v   = _atr(h1, l1, c1)
        atr_pct = round(atr_v / curr * 100, 3)

        return {
            'total': score,       'trend': round(trend,2),
            'momentum': round(momentum,2),  'volume': round(volume,2),
            'bb': round(bb,2),    'pattern': round(pattern,2),
            'market': round(market,2),
            'rsi1h': rsi1h,       'rsi15m': rsi15m,
            'srsi': srsi,         'adx': adx,
            'vol_ratio': round(vr,2),
            'cross1h': cross1h,   'cross15m': cross15m,
            'bb_pos': round(bb_pos,2),
            'vwap': round(vwap,4), 'atr_pct': atr_pct,
        }
    except Exception as e:
        print(f'[Score] {sym}: {e}')
        return None


# ─── Risk Yönetimi ────────────────────────────────────────────────────────────

def _position_size(balance, score, atr_pct, is_real, max_positions):
    risk_per_trade = 0.01 if is_real else 0.02
    sl_pct_est     = max(atr_pct * 1.5, 1.5) / 100
    raw_size       = balance * risk_per_trade / sl_pct_est
    multiplier = max(0.4, min(1.0, (score - 5.0) / 4.0))
    size       = raw_size * multiplier
    max_pct  = 0.05 if is_real else 0.10
    size     = min(size, balance * max_pct)
    per_slot = balance / max_positions * 0.30
    size     = min(size, per_slot)
    return max(10.0, round(size, 2))


def _daily_loss_ok(trades, balance_start, balance_now, max_loss_pct=8.0):
    if balance_start <= 0: return True
    loss_pct = (balance_start - balance_now) / balance_start * 100
    return loss_pct < max_loss_pct


# ─── Çıkış Kararı ────────────────────────────────────────────────────────────

def _exit_decision(client, sym, pos, regime, live_price=None):
    try:
        price = live_price or get_price(client, sym)
        if price <= 0: return None

        avg    = pos['avg_price']
        change = (price - avg) / avg * 100
        tp     = pos.get('tp_pct', 5.0)
        sl     = pos.get('sl_pct', 2.5)
        peak   = pos.get('peak_price', avg)

        if price > peak:
            pos['peak_price'] = price; peak = price

        trail_active = pos.get('trail_active', False)
        if change >= tp * 0.40 and not trail_active:
            pos['trail_active'] = True; trail_active = True

        if trail_active:
            drawdown = (peak - price) / peak * 100
            if drawdown >= sl * 0.70:
                return 'TRAIL STOP'

        if change >= tp:         return 'KAR HEDEFİ'
        if change <= -sl:        return 'STOP LOSS'

        if pos.get('check_momentum', False):
            try:
                _, _, _, c, _ = _klines(client, sym, '1h', 40)
                m, s, _ = _macd(c)
                prev_m = _ema(c[:-1], 12) - _ema(c[:-1], 26)
                prev_s = sum([_ema(c[:i+1], 12) - _ema(c[:i+1], 26)
                              for i in range(26, len(c)-1)][-9:]) / 9
                bearish = prev_m >= prev_s and m < s
                if bearish and change > 0.3:
                    return 'MOMENTUM KAYBI'
            except Exception:
                pass

        if regime == 'BEAR' and change < -0.5:
            return 'PİYASA ÇÖKÜŞÜ'

        bt = pos.get('buy_time', '')
        if bt:
            try:
                elapsed = (datetime.datetime.now() -
                           datetime.datetime.strptime(bt, '%Y-%m-%d %H:%M:%S')).total_seconds() / 3600
                if elapsed >= 60 and abs(change) < 0.5:
                    return 'SÜRE DOLDU'
            except Exception:
                pass

        return None
    except Exception:
        return None


# ─── Ana Ajan ────────────────────────────────────────────────────────────────

class AutonomousAgent:
    SCAN_INTERVAL    = 90
    MONITOR_INTERVAL = 3
    MOMENTUM_EVERY   = 20
    MAX_POSITIONS    = 6
    MIN_SCORE        = 5.2
    DAILY_LOSS_LIMIT = 8.0

    def __init__(self):
        self.running     = False
        self.state       = self._load()
        self._lock       = threading.Lock()
        self._mon_count  = 0
        self._balance_start = 0.0

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f: return json.load(f)
            except Exception: pass
        return {
            'blacklist': {}, 'weights': DEFAULT_WEIGHTS.copy(),
            'scan_count': 0, 'total_pnl': 0.0, 'signal_stats': {},
            'last_regime': 'SIDEWAYS', 'started_at': datetime.datetime.now().isoformat(),
            'day_start_balance': 0.0,
        }

    def _save(self):
        try:
            with open(STATE_FILE, 'w') as f: json.dump(self.state, f, indent=2)
        except Exception: pass

    def _bl(self, sym): return time.time() < self.state['blacklist'].get(sym, 0)
    def _add_bl(self, sym, h=4): self.state['blacklist'][sym] = time.time() + h * 3600

    def run(self):
        self.running = True
        cfg = load_config()
        is_real = not cfg.get('testnet', True)

        try:
            self._balance_start = get_usdt_balance(get_client())
            self.state['day_start_balance'] = self._balance_start
        except Exception:
            pass

        send_telegram(
            f"{'🔴 GERÇEK' if is_real else '🧪 TESTNET'} <b>Otonom Ajan v2 AKTİF</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 Başlangıç Bakiye: ${round(self._balance_start,2)}\n"
            f"📊 Min Skor: {self.MIN_SCORE}/10\n"
            f"📦 Max Pozisyon: {self.MAX_POSITIONS}\n"
            f"🛡 Günlük Kayıp Limiti: -%{self.DAILY_LOSS_LIMIT}\n"
            f"⚡ Pozisyon Takip: her {self.MONITOR_INTERVAL}s\n"
            f"🔍 Fırsat Tarama: her {self.SCAN_INTERVAL}s\n"
            "Piyasa izleniyor..."
        )

        print('[Otonom] Başladı')
        try:
            _build_stable_cache(get_client())
        except Exception:
            pass
        threading.Thread(target=self._monitor_loop,  daemon=True).start()
        threading.Thread(target=self._scanner_loop,  daemon=True).start()
        threading.Thread(target=self._hourly_loop,   daemon=True).start()
        threading.Thread(target=self._daily_loop,    daemon=True).start()
        threading.Thread(target=self._weight_loop,   daemon=True).start()
        threading.Thread(target=self._day_reset_loop, daemon=True).start()

        while self.running:
            time.sleep(30)

    def _monitor_loop(self):
        while self.running:
            try:
                self._mon_count += 1
                client    = get_client()
                positions = load_positions()
                regime    = self.state.get('last_regime', 'SIDEWAYS')
                changed   = False

                for sym, pos in list(positions.items()):
                    if pos.get('qty', 0) <= 0: continue
                    if pos.get('agent') != 'OTONOM': continue
                    pos['check_momentum'] = (self._mon_count % self.MOMENTUM_EVERY == 0)

                    # Trailing stop'un çalışması için zirve/trail durumunu kalıcı yap
                    pre_peak  = pos.get('peak_price')
                    pre_trail = pos.get('trail_active')

                    reason = _exit_decision(client, sym, pos, regime)

                    # _exit_decision peak_price/trail_active'i güncellediyse diske yaz
                    if pos.get('peak_price') != pre_peak or pos.get('trail_active') != pre_trail:
                        changed = True

                    if reason:
                        positions[sym] = pos
                        res = execute_sell(client, sym, 100, source='OTONOM', period=reason)
                        if res.get('ok'):
                            positions[sym]['qty'] = 0  # local dict'i hemen güncelle
                            pnl = res.get('pnl', 0)
                            self.state['total_pnl'] = round(self.state.get('total_pnl',0) + pnl, 2)
                            self._add_bl(sym, 8 if 'STOP' in reason else 2)
                            self._track_signal(pos, pnl)
                        changed = True
                    else:
                        positions[sym] = pos

                if changed:
                    save_positions(positions)
                    self._save()

            except Exception as e:
                print(f'[Monitor] {e}')
            time.sleep(self.MONITOR_INTERVAL)

    def _scanner_loop(self):
        while self.running:
            try:
                with self._lock:
                    client = get_client()
                    cfg    = load_config()
                    is_real = not cfg.get('testnet', True)

                    from manager_agent import ceo_flag
                    if not ceo_flag(cfg, 'otonom_enabled', True):
                        print('[Otonom] CEO tarafından durduruldu, tarama atlandı')
                        time.sleep(self.SCAN_INTERVAL)
                        continue

                    balance = get_usdt_balance(client)
                    if not _daily_loss_ok({}, self.state.get('day_start_balance', balance),
                                          balance, self.DAILY_LOSS_LIMIT):
                        print('[Scanner] Günlük kayıp limiti — tarama durduruldu')
                        time.sleep(self.SCAN_INTERVAL)
                        continue

                    regime = _regime(client)
                    if regime != self.state.get('last_regime'):
                        self._on_regime_change(regime)
                    self.state['last_regime'] = regime
                    print(f'[Otonom] Tarama #{self.state.get("scan_count",0)+1}: rejim={regime}')

                    if regime == 'BEAR':
                        self.state['scan_count'] += 1
                        self._save()
                        time.sleep(self.SCAN_INTERVAL)
                        continue

                    positions = load_positions()
                    held = {s for s, p in positions.items() if p.get('qty',0) > 0}
                    if len(held) >= self.MAX_POSITIONS:
                        self.state['scan_count'] += 1
                        self._save()
                        time.sleep(self.SCAN_INTERVAL)
                        continue

                    top100     = _top_100(client)
                    candidates = [s for s in top100 if s not in held and not self._bl(s)]
                    w          = self.state['weights']

                    best_sym, best_sc = None, None
                    for sym in candidates[:55]:
                        sc = _score(client, sym, regime, w)
                        if sc and sc['total'] >= self.MIN_SCORE:
                            if best_sc is None or sc['total'] > best_sc['total']:
                                best_sym, best_sc = sym, sc

                    if best_sym:
                        atr_pct  = best_sc.get('atr_pct', 2.0)
                        ceo_mult = cfg.get('ceo_position_mult', 1.0)
                        # ORTAK skor-bazlı boyutlama (tüm ajanlarda aynı kural)
                        from bot import get_total_equity, position_size_by_score
                        equity   = get_total_equity(client)
                        amount   = position_size_by_score(equity, best_sc['total'], mult=ceo_mult)
                        if amount <= balance * 0.95:
                            res = execute_buy(client, best_sym, amount,
                                              source='OTONOM', period='Ajan', agent='OTONOM')
                            if res.get('ok'):
                                sl  = max(1.5, min(6.0, atr_pct * 1.5))
                                tp  = max(3.0, min(18.0, atr_pct * 3.0))
                                positions = load_positions()
                                if best_sym in positions:
                                    positions[best_sym].update({
                                        'agent': 'OTONOM',
                                        'tp_pct': tp, 'sl_pct': sl,
                                        'trail_active': False,
                                        'peak_price': res['price'],
                                        'buy_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'open_score': best_sc['total'],
                                    })
                                save_positions(positions)
                                self._send_buy_rationale(best_sym, best_sc, amount, tp, sl, regime, is_real)

                    self.state['scan_count'] += 1
                    self._save()

            except Exception as e:
                print(f'[Scanner] {e}')
            time.sleep(self.SCAN_INTERVAL)

    def _send_buy_rationale(self, sym, sc, amount, tp, sl, regime, is_real):
        er = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(regime, '⚪')
        parts = []
        if sc['cross1h']:  parts.append('1h MACD ✂️')
        if sc['cross15m']: parts.append('15m MACD ✂️')
        if sc['srsi'] < 30: parts.append(f"StochRSI {sc['srsi']:.0f}↓")
        if sc['bb_pos'] < 0.3: parts.append(f"BB dipte {sc['bb_pos']:.2f}")
        signal_str = ' | '.join(parts) if parts else '—'

        send_telegram(
            f"🧠 <b>AJAN ALIM GEREKÇESİ</b>"
            f"{'  🔴GERÇEK' if is_real else ''}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🪙 <b>{sym}</b>  Skor: <b>{sc['total']:.1f}/10</b>\n"
            f"  📈 Trend {sc['trend']:.1f} (ADX {sc['adx']:.0f})\n"
            f"  ⚡ Momentum {sc['momentum']:.1f}"
            f"  RSI1h {sc['rsi1h']:.0f} / 15m {sc['rsi15m']:.0f}\n"
            f"  📊 Hacim {sc['volume']:.1f}  ({sc['vol_ratio']:.1f}x avg)\n"
            f"  🕯 BB {sc['bb']:.1f}  Formasyon {sc['pattern']:.1f}\n"
            f"  💡 Sinyaller: {signal_str}\n"
            f"  {er} Rejim: {regime}\n"
            f"💰 ${amount:.2f}  |  🎯 TP+%{tp:.1f}  🛑 SL-%{sl:.1f}"
        )

    def _weight_loop(self):
        while self.running:
            time.sleep(12 * 3600)
            try:
                trades = load_trades()
                ajan_sells = [t for t in trades
                              if t.get('type') == 'sell'
                              and 'Ajan' in t.get('period','')]
                if len(ajan_sells) < 5: continue
                wins = [t for t in ajan_sells if t.get('pnl',0) > 0]
                wr   = len(wins) / len(ajan_sells)
                w    = self.state['weights']
                if wr < 0.45:
                    w['momentum'] = min(w['momentum'] * 1.08, 4.0)
                    w['bb']       = min(w['bb']       * 1.05, 2.0)
                    w['pattern']  = max(w['pattern']  * 0.95, 0.8)
                elif wr > 0.65:
                    w['trend']    = min(w['trend'] * 1.05, 3.5)
                self._save()
                send_telegram(
                    f"⚙️ <b>Ağırlık Güncellemesi</b>\n"
                    f"Kazanma: %{round(wr*100,1)} ({len(ajan_sells)} işlem)\n"
                    f"T:{w['trend']:.2f} M:{w['momentum']:.2f} "
                    f"V:{w['volume']:.2f} BB:{w['bb']:.2f}"
                )
            except Exception as e:
                print(f'[Weights] {e}')

    def _on_regime_change(self, new):
        old = self.state.get('last_regime', '?')
        er  = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(new, '⚪')
        send_telegram(
            f"{er} <b>REJİM DEĞİŞTİ</b>  {old} → <b>{new}</b>\n"
            f"{'⛔ Yeni alımlar durduruldu!' if new == 'BEAR' else '✅ Tarama aktif.'}"
        )

    def _day_reset_loop(self):
        while self.running:
            now  = datetime.datetime.now()
            next_midnight = (now + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=5, microsecond=0)
            time.sleep((next_midnight - now).total_seconds())
            try:
                bal = get_usdt_balance(get_client())
                self.state['day_start_balance'] = bal
                self._save()
            except Exception: pass

    def _send_report(self):
        client    = get_client()
        # Saatlik rapor öncesi toz temizliği — MIN_NOTIONAL altı pozisyonlar silinir
        try:
            from bot import cleanup_dust_positions
            removed = cleanup_dust_positions(client)
            if removed:
                print(f'[Otonom] Toz temizlendi: {removed}')
                from bot import send_telegram
                send_telegram('🧹 Toz pozisyonlar temizlendi: ' + ', '.join(removed))
        except Exception as e:
            print(f'[Otonom] Toz temizlik hatası: {e}')
        positions = load_positions()
        try:
            balance = get_usdt_balance(client)
        except Exception:
            balance = 0
        open_pos  = [(s,p) for s,p in positions.items() if p.get('qty',0)>0]
        regime    = self.state.get('last_regime','?')
        er        = {'BULL':'🟢','SIDEWAYS':'🟡','BEAR':'🔴'}.get(regime,'⚪')
        day_bal   = self.state.get('day_start_balance', balance)
        day_chg   = round((balance - day_bal) / day_bal * 100, 2) if day_bal else 0

        lines = [
            "🤖 <b>Otonom Ajan Rapor</b>",
            f"━━━━━━━━━━━━━━",
            f"💰 Bakiye: <b>${round(balance,2)}</b>  "
            f"({'+' if day_chg>=0 else ''}{day_chg}% bugün)",
            f"💹 Toplam PnL: ${round(self.state.get('total_pnl',0),2)}",
            f"{er} Rejim: {regime}  |  🔍 Tarama: {self.state.get('scan_count',0)}x",
            f"📦 Açık: {len(open_pos)}/{self.MAX_POSITIONS}",
        ]
        if open_pos:
            lines.append("")
            for sym, pos in open_pos:
                try:
                    price = get_price(client, sym)
                    chg   = (price - pos['avg_price']) / pos['avg_price'] * 100
                    icon  = '🟢' if chg >= 0 else '🔴'
                    agent = pos.get('agent', 'OTONOM')
                    trail = ' 🎯trail' if pos.get('trail_active') else ''
                    lines.append(f"  {icon} {sym} [{agent}]: {'+' if chg>=0 else ''}{round(chg,2)}%{trail}")
                except Exception:
                    lines.append(f"  ⚪ {sym}: fiyat alınamadı")
        bl = [k for k,v in self.state.get('blacklist',{}).items() if v > time.time()]
        if bl:
            lines.append(f"\n⛔ Kara liste ({len(bl)}): {', '.join(bl[:5])}")
        send_telegram('\n'.join(lines))

    def _hourly_loop(self):
        now = datetime.datetime.now()
        time.sleep(max(0, (60 - now.minute) * 60 - now.second))
        while self.running:
            try:
                self._send_report()
            except Exception as e:
                print(f'[Otonom Hourly] {e}')
            interval = int(load_config().get('report_interval_hours', 1))
            time.sleep(interval * 3600)

    def _daily_loop(self):
        while self.running:
            time.sleep(24 * 3600)
            try:
                trades  = load_trades()
                today   = datetime.datetime.now().strftime('%Y-%m-%d')
                recent  = [t for t in trades if t.get('type')=='sell'
                           and t.get('time','')[:10]==today
                           and not t.get('source','').startswith('CEO_')]
                if not recent: continue
                wins     = [t for t in recent if t.get('pnl',0) > 0]
                pnl_sum  = sum(t.get('pnl',0) for t in recent)
                wr       = round(len(wins)/len(recent)*100,1)
                best     = max(recent, key=lambda t: t.get('pnl',0), default=None)
                worst    = min(recent, key=lambda t: t.get('pnl',0), default=None)
                w        = self.state['weights']
                lines = [
                    "🌙 <b>GÜNLÜK ÖZET</b>",
                    f"━━━━━━━━━━━━━━",
                    f"📊 {len(recent)} işlem | Kazanma %{wr}",
                    f"💹 Net PnL: ${round(pnl_sum,2)}",
                ]
                if best:  lines.append(f"🏆 En İyi:  {best['symbol']} +${round(best.get('pnl',0),2)}")
                if worst: lines.append(f"💀 En Kötü: {worst['symbol']} ${round(worst.get('pnl',0),2)}")
                lines += [
                    "",
                    f"⚙️ Ağırlıklar — Trend:{w['trend']:.1f} "
                    f"Mom:{w['momentum']:.1f} Vol:{w['volume']:.1f} "
                    f"BB:{w['bb']:.1f}",
                ]
                send_telegram('\n'.join(lines))
            except Exception as e:
                print(f'[Daily] {e}')

    def _track_signal(self, pos, pnl):
        key  = f"sc_{int(pos.get('open_score',0))}"
        stats = self.state.setdefault('signal_stats', {})
        if key not in stats: stats[key] = {'wins':0,'total':0,'pnl':0.0}
        stats[key]['total'] += 1
        stats[key]['pnl']    = round(stats[key]['pnl'] + pnl, 2)
        if pnl > 0: stats[key]['wins'] += 1

    def stop(self):
        self.running = False
        send_telegram("⛔ <b>Otonom Ajan durduruldu.</b>")


# ─── Global API ───────────────────────────────────────────────────────────────

_agent: AutonomousAgent | None = None
_thread: threading.Thread | None = None


def start_autonomous_agent():
    global _agent, _thread
    if _agent and _agent.running: return False
    _agent  = AutonomousAgent()
    _thread = threading.Thread(target=_agent.run, daemon=True)
    _thread.start()
    return True


def stop_autonomous_agent():
    global _agent
    if _agent: _agent.stop(); _agent.running = False
    return True


def trigger_otonom_report():
    if _agent and _agent.running:
        try:
            _agent._send_report()
        except Exception as e:
            print(f'[Otonom] Manuel rapor hatası: {e}')

def agent_status():
    if not (_agent and _agent.running): return {'running': False}
    s = _agent.state
    cfg = load_config()
    return {
        'running':     True,
        'is_real':     not cfg.get('testnet', True),
        'scan_count':  s.get('scan_count', 0),
        'total_pnl':   s.get('total_pnl', 0.0),
        'last_regime': s.get('last_regime', 'SIDEWAYS'),
        'weights':     s.get('weights', DEFAULT_WEIGHTS),
        'blacklisted': [k for k,v in s.get('blacklist',{}).items() if v > time.time()],
        'started_at':  s.get('started_at', ''),
        'day_pnl':     round(s.get('total_pnl', 0), 2),
    }
