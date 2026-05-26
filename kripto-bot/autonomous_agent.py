"""
Otonom Kripto Ajan
- Top 100 coini sürekli tarar
- Kendi kararlarını kendi verir (ne alacak, ne kadar, ne zaman satacak)
- Hiçbir manuel müdahale gerektirmez
- Telegram üzerinden bildirim gönderir
"""

import time, datetime, threading, json, os, math
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, save_positions, load_trades, get_price,
                 send_telegram, get_usdt_balance)

STATE_FILE = 'agent_state.json'

STABLECOINS = {
    'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'USDTUSDT', 'FDUSDUSDT',
    'EURUSDT', 'GBPUSDT', 'DAIUSDT', 'FRAXUSDT', 'USDPUSDT',
}

# Skor ağırlıkları — agent kendi performansına göre bunları günceller
DEFAULT_WEIGHTS = {
    'trend':    2.0,
    'momentum': 3.0,
    'volume':   2.0,
    'pattern':  2.0,
    'market':   1.0,
}


# ── Yardımcı Matematik ───────────────────────────────────────────────────────

def _ema(closes, period):
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0)  for d in deltas[-period:]]
    losses = [max(-d, 0) for d in deltas[-period:]]
    ag = sum(gains)  / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return 0.0, 0.0
    macd_series = []
    for i in range(slow - 1, len(closes)):
        ef = _ema(closes[:i + 1], fast)
        es = _ema(closes[:i + 1], slow)
        macd_series.append(ef - es)
    macd_now  = macd_series[-1]
    sig_now   = sum(macd_series[-signal:]) / signal
    return macd_now, sig_now


def _adx(highs, lows, closes, period=14):
    """Basit ADX hesabı — trend gücü 0-100"""
    if len(closes) < period + 2:
        return 25.0
    tr_list, pdm_list, ndm_list = [], [], []
    for i in range(1, len(closes)):
        tr  = max(highs[i] - lows[i],
                  abs(highs[i] - closes[i - 1]),
                  abs(lows[i]  - closes[i - 1]))
        pdm = max(highs[i] - highs[i - 1], 0)
        ndm = max(lows[i - 1] - lows[i], 0)
        if pdm < ndm: pdm = 0
        if ndm < pdm: ndm = 0
        tr_list.append(tr); pdm_list.append(pdm); ndm_list.append(ndm)

    atr = sum(tr_list[-period:]) / period
    if atr == 0:
        return 25.0
    pdi = (sum(pdm_list[-period:]) / period) / atr * 100
    ndi = (sum(ndm_list[-period:]) / period) / atr * 100
    denom = pdi + ndi
    dx  = abs(pdi - ndi) / denom * 100 if denom else 25.0
    return round(dx, 1)


def _atr_pct(highs, lows, closes, period=7):
    if len(closes) < period + 2:
        return 2.0
    trs = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    atr = sum(trs[-period:]) / period
    return round(atr / closes[-1] * 100, 3)


# ── State ────────────────────────────────────────────────────────────────────

def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'blacklist':   {},      # symbol → expire_timestamp
        'weights':     DEFAULT_WEIGHTS.copy(),
        'scan_count':  0,
        'total_pnl':   0.0,
        'signal_stats': {},     # 'signal_key' → {wins, total}
        'last_regime':  'SIDEWAYS',
        'started_at':   datetime.datetime.now().isoformat(),
    }


def _save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


# ── Market Data ──────────────────────────────────────────────────────────────

def _get_klines(client, symbol, interval='1h', limit=110):
    from binance.client import Client as BC
    interval_map = {
        '5m': BC.KLINE_INTERVAL_5MINUTE,
        '15m': BC.KLINE_INTERVAL_15MINUTE,
        '1h': BC.KLINE_INTERVAL_1HOUR,
        '4h': BC.KLINE_INTERVAL_4HOUR,
    }
    kl = client.get_klines(
        symbol=symbol,
        interval=interval_map.get(interval, BC.KLINE_INTERVAL_1HOUR),
        limit=limit
    )
    kl = kl[:-1]  # kapanmamış mumu çıkar
    opens   = [float(k[1]) for k in kl]
    highs   = [float(k[2]) for k in kl]
    lows    = [float(k[3]) for k in kl]
    closes  = [float(k[4]) for k in kl]
    volumes = [float(k[5]) for k in kl]
    return opens, highs, lows, closes, volumes


def _get_top_100(client):
    tickers = client.get_ticker()
    usdt = [
        t for t in tickers
        if t['symbol'].endswith('USDT')
        and t['symbol'] not in STABLECOINS
        and float(t.get('quoteVolume', 0)) > 500_000
        and float(t.get('lastPrice', 0)) > 0
    ]
    usdt.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
    return [t['symbol'] for t in usdt[:100]]


# ── Piyasa Rejimi ────────────────────────────────────────────────────────────

def _get_market_regime(client):
    try:
        _, highs, lows, closes, _ = _get_klines(client, 'BTCUSDT', '1h', 60)
        e20  = _ema(closes, 20)
        e50  = _ema(closes, 50)
        rsi  = _rsi(closes, 14)
        adx  = _adx(highs, lows, closes, 14)
        curr = closes[-1]

        if curr > e20 > e50 and rsi > 45 and adx > 20:
            return 'BULL'
        elif curr < e20 < e50 and rsi < 55 and adx > 20:
            return 'BEAR'
        else:
            return 'SIDEWAYS'
    except Exception:
        return 'SIDEWAYS'


# ── Fırsat Skoru ─────────────────────────────────────────────────────────────

def _score_coin(client, symbol, regime, weights):
    """Coini 0-10 arasında puanlar. None döndürürse bu coin taranamadı."""
    try:
        opens, highs, lows, closes, volumes = _get_klines(client, symbol, '1h', 110)
        if len(closes) < 50:
            return None

        # ── Trend (0 - weights['trend']) ──────────────
        e20  = _ema(closes, 20)
        e50  = _ema(closes, 50)
        e100 = _ema(closes, 100)
        curr = closes[-1]
        adx  = _adx(highs, lows, closes, 14)

        trend_raw = 0.0
        if curr > e20:   trend_raw += 0.35
        if e20  > e50:   trend_raw += 0.35
        if e50  > e100:  trend_raw += 0.20
        if adx  > 25:    trend_raw += 0.10
        trend = trend_raw * weights['trend']

        # ── Momentum (0 - weights['momentum']) ────────
        rsi = _rsi(closes, 14)
        macd_now, sig_now = _macd(closes)
        macd_prev, sig_prev = _macd(closes[:-1])
        fresh_cross = macd_prev <= sig_prev and macd_now > sig_now

        mom_raw = 0.0
        if 35 <= rsi <= 60:   mom_raw += 0.40
        elif 60 < rsi <= 70:  mom_raw += 0.20   # hafif aşırı alım
        if macd_now > sig_now: mom_raw += 0.35
        if fresh_cross:        mom_raw += 0.25   # taze cross bonus
        momentum = mom_raw * weights['momentum']

        # ── Hacim (0 - weights['volume']) ─────────────
        avg_vol  = sum(volumes[-21:-1]) / 20 if len(volumes) > 21 else volumes[-1]
        curr_vol = volumes[-1]
        vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
        vol_raw = min(vol_ratio / 3.0, 1.0)   # 3x hacim = tam puan
        volume = vol_raw * weights['volume']

        # ── Formasyon (0 - weights['pattern']) ────────
        pat_raw = 0.0
        o1, h1, l1, c1 = opens[-2], highs[-2], lows[-2], closes[-2]
        o0, h0, l0, c0 = opens[-1], highs[-1], lows[-1], closes[-1]
        body0 = abs(c0 - o0)
        body1 = abs(c1 - o1)
        lower0 = min(o0, c0) - l0
        upper0 = h0 - max(o0, c0)

        # Bullish engulfing
        if c1 < o1 and c0 > o0 and c0 > o1 and o0 < c1:
            pat_raw += 0.55
        # Hammer
        if lower0 > 2 * body0 and upper0 < body0 and c0 > o0:
            pat_raw += 0.45
        # Fiyat 20 günlük düşükten toparlanıyor
        low20 = min(lows[-20:])
        high20 = max(highs[-20:])
        range20 = high20 - low20
        if range20 > 0:
            pos_in_range = (c0 - low20) / range20
            if 0.2 <= pos_in_range <= 0.6:   # diplere yakın ama toparlanıyor
                pat_raw += 0.30
        pat_raw = min(pat_raw, 1.0)
        pattern = pat_raw * weights['pattern']

        # ── Piyasa Koşulu (0 - weights['market']) ─────
        if   regime == 'BULL':     mkt_raw = 1.00
        elif regime == 'SIDEWAYS': mkt_raw = 0.55
        else:                      mkt_raw = 0.10
        market = mkt_raw * weights['market']

        total = trend + momentum + volume + pattern + market
        max_total = sum(weights.values())
        normalized = round(total / max_total * 10, 2)   # 0-10

        return {
            'total':    normalized,
            'trend':    round(trend, 2),
            'momentum': round(momentum, 2),
            'volume':   round(volume, 2),
            'pattern':  round(pattern, 2),
            'market':   round(market, 2),
            'rsi':      rsi,
            'adx':      adx,
            'vol_ratio': round(vol_ratio, 2),
            'fresh_cross': fresh_cross,
            'atr_pct':  _atr_pct(highs, lows, closes),
        }
    except Exception as e:
        return None


# ── Pozisyon Boyutu ──────────────────────────────────────────────────────────

def _calc_position_size(balance, score_total, max_pct=0.20, min_usdt=10.0):
    """Skora orantılı pozisyon büyüklüğü."""
    confidence = max(0.0, (score_total - 5.0) / 5.0)   # 5→0%, 10→100%
    amount = balance * max_pct * confidence
    return max(min_usdt, min(amount, balance * max_pct))


# ── Çıkış Mantığı ────────────────────────────────────────────────────────────

def _should_exit(client, symbol, pos, regime):
    """Çıkış kararı ver. ('reason', sell_pct) veya None döndürür."""
    try:
        price = get_price(client, symbol)
        if price <= 0:
            return None

        avg    = pos['avg_price']
        change = (price - avg) / avg * 100
        tp     = pos.get('tp_pct', 5.0)
        sl     = pos.get('sl_pct', 2.5)
        peak   = pos.get('peak_price', avg)

        # Peak güncelle
        if price > peak:
            pos['peak_price'] = price
            peak = price

        # ── Trailing Stop ────────────────────────────
        trail_act = pos.get('trail_activated', False)
        if change >= tp * 0.5 and not trail_act:
            pos['trail_activated'] = True
            trail_act = True

        if trail_act:
            trail_threshold = sl * 0.7
            drawdown_pct = (peak - price) / peak * 100
            if drawdown_pct >= trail_threshold:
                return ('TRAIL STOP', 100)

        # ── Kâr Hedefi ───────────────────────────────
        if change >= tp:
            return ('KAR HEDEFİ', 100)

        # ── Stop Loss ────────────────────────────────
        if change <= -sl:
            return ('STOP LOSS', 100)

        # ── Momentum Kaybı ───────────────────────────
        # MACD bearish cross + pozisyon kârda → çık
        try:
            _, _, _, closes, _ = _get_klines(client, symbol, '1h', 50)
            macd_now, sig_now  = _macd(closes)
            macd_prev, sig_prev = _macd(closes[:-1])
            bearish_cross = macd_prev >= sig_prev and macd_now < sig_now
            if bearish_cross and change > 0.5:
                return ('MOMENTUM KAYBI', 100)
        except Exception:
            pass

        # ── Piyasa Çöküşü ────────────────────────────
        if regime == 'BEAR' and change < 0:
            return ('PİYASA ÇÖKÜŞÜ', 100)

        # ── Süre Bazlı Çıkış ─────────────────────────
        # 48 saatten uzun tutuldu ve kâr yok
        buy_time_str = pos.get('buy_time')
        if buy_time_str:
            try:
                buy_time = datetime.datetime.strptime(buy_time_str, '%Y-%m-%d %H:%M:%S')
                held_hours = (datetime.datetime.now() - buy_time).total_seconds() / 3600
                if held_hours >= 48 and change < 0.5:
                    return ('SÜRE DOLDU', 100)
            except Exception:
                pass

        return None
    except Exception:
        return None


# ── Ana Agent ────────────────────────────────────────────────────────────────

class AutonomousAgent:
    MIN_SCORE     = 5.5    # alım için minimum skor
    MAX_POSITIONS = 5      # aynı anda max açık pozisyon
    MAX_POS_PCT   = 0.20   # bakiyenin max %20'si per trade
    MIN_USDT      = 10.0   # minimum işlem tutarı
    SCAN_INTERVAL = 300    # saniye (5 dakika)
    SCAN_TOP_N    = 60     # ilk N coin'i tara (hız için)

    def __init__(self):
        self.running = False
        self.state   = _load_state()
        self._lock   = threading.Lock()

    # ── Blacklist ─────────────────────────────────────────────────────────
    def _is_blacklisted(self, symbol):
        bl = self.state['blacklist']
        if symbol in bl:
            if time.time() < bl[symbol]:
                return True
            del bl[symbol]
        return False

    def _blacklist(self, symbol, hours=4):
        self.state['blacklist'][symbol] = time.time() + hours * 3600

    # ── Ana Döngü ─────────────────────────────────────────────────────────
    def run(self):
        self.running = True
        _save_state(self.state)

        send_telegram(
            "🤖 <b>Otonom Ajan AKTİF</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"📊 Min Skor: {self.MIN_SCORE}/10\n"
            f"📦 Max Pozisyon: {self.MAX_POSITIONS}\n"
            f"💰 Max Tutar: %{int(self.MAX_POS_PCT*100)} bakiye/pozisyon\n"
            f"⏱ Tarama Aralığı: {self.SCAN_INTERVAL//60} dakika\n"
            "Piyasa taranıyor..."
        )

        threading.Thread(target=self._hourly_report_loop, daemon=True).start()
        threading.Thread(target=self._daily_summary_loop, daemon=True).start()
        threading.Thread(target=self._weight_update_loop, daemon=True).start()

        while self.running:
            try:
                with self._lock:
                    regime = _get_market_regime(get_client())
                    if regime != self.state.get('last_regime'):
                        self._on_regime_change(regime)
                    self.state['last_regime'] = regime

                    self._scan_and_open(regime)
                    self._monitor_and_close(regime)
                    self.state['scan_count'] += 1
                    _save_state(self.state)
            except Exception as e:
                print(f'[Agent] Ana döngü hatası: {e}')
            time.sleep(self.SCAN_INTERVAL)

    # ── Tarama & Alım ─────────────────────────────────────────────────────
    def _scan_and_open(self, regime):
        if regime == 'BEAR':
            return   # Ayı piyasasında yeni pozisyon açma

        client    = get_client()
        positions = load_positions()
        held      = {s for s, p in positions.items() if p.get('qty', 0) > 0}

        if len(held) >= self.MAX_POSITIONS:
            return

        top100 = _get_top_100(client)
        candidates = [
            s for s in top100
            if s not in held and not self._is_blacklisted(s)
        ]

        scores = []
        for symbol in candidates[:self.SCAN_TOP_N]:
            s = _score_coin(client, symbol, regime, self.state['weights'])
            if s and s['total'] >= self.MIN_SCORE:
                scores.append((symbol, s))

        if not scores:
            return

        scores.sort(key=lambda x: x[1]['total'], reverse=True)
        best_sym, best_sc = scores[0]

        balance = get_usdt_balance(client)
        amount  = _calc_position_size(
            balance, best_sc['total'],
            self.MAX_POS_PCT, self.MIN_USDT
        )
        if amount > balance * 0.95:
            return

        result = execute_buy(
            client, best_sym, amount,
            source='OTONOM', period='Ajan'
        )
        if not result.get('ok'):
            return

        # Dinamik TP/SL
        atr = best_sc.get('atr_pct', 2.0)
        sl  = max(1.5, min(5.0, atr * 1.5))
        tp  = max(3.0, min(15.0, atr * 3.0))

        positions = load_positions()
        if best_sym in positions:
            positions[best_sym].update({
                'tp_pct':          tp,
                'sl_pct':          sl,
                'trail_activated': False,
                'peak_price':      result['price'],
                'buy_time':        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'open_score':      best_sc['total'],
            })
        save_positions(positions)

        # Telegram — karar gerekçesiyle birlikte
        emoji_regime = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(regime, '⚪')
        send_telegram(
            f"🧠 <b>AJAN KARAR GEREKÇESİ</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🪙 {best_sym} | Skor: <b>{best_sc['total']:.1f}/10</b>\n"
            f"  📈 Trend: {best_sc['trend']:.1f} "
            f"(ADX {best_sc['adx']:.0f})\n"
            f"  ⚡ Momentum: {best_sc['momentum']:.1f} "
            f"(RSI {best_sc['rsi']:.0f}"
            f"{' 🔀CROSS' if best_sc['fresh_cross'] else ''})\n"
            f"  📊 Hacim: {best_sc['volume']:.1f} "
            f"({best_sc['vol_ratio']:.1f}x ortalama)\n"
            f"  🕯 Formasyon: {best_sc['pattern']:.1f}\n"
            f"  {emoji_regime} Rejim: {regime}\n"
            f"🎯 TP: +%{tp:.1f} | 🛑 SL: -%{sl:.1f} | 💰 ${amount:.2f}"
        )

    # ── İzleme & Satış ────────────────────────────────────────────────────
    def _monitor_and_close(self, regime):
        client    = get_client()
        positions = load_positions()

        for symbol, pos in list(positions.items()):
            if pos.get('qty', 0) <= 0:
                continue
            decision = _should_exit(client, symbol, pos, regime)
            if decision:
                reason, sell_pct = decision
                save_positions(positions)
                result = execute_sell(
                    client, symbol, sell_pct,
                    source=reason, period='Ajan'
                )
                if result.get('ok'):
                    pnl = result.get('pnl', 0)
                    self.state['total_pnl'] = round(
                        self.state.get('total_pnl', 0) + pnl, 2
                    )
                    bl_hours = 8 if 'STOP' in reason else 2
                    self._blacklist(symbol, hours=bl_hours)

                    self._update_signal_stats(pos, pnl)

    # ── Ağırlık Güncelleme (Basit Reinforcement) ──────────────────────────
    def _update_signal_stats(self, pos, pnl):
        """Hangi bileşen kârlı işlemlerle korelasyonu yüksek? Kaydet."""
        score = pos.get('open_score', 0)
        key   = f"score_{int(score)}"
        stats = self.state.setdefault('signal_stats', {})
        if key not in stats:
            stats[key] = {'wins': 0, 'total': 0, 'pnl': 0.0}
        stats[key]['total'] += 1
        stats[key]['pnl']   = round(stats[key]['pnl'] + pnl, 2)
        if pnl > 0:
            stats[key]['wins'] += 1

    def _weight_update_loop(self):
        """Her 12 saatte bir performans verilerine göre ağırlıkları ayarla."""
        while self.running:
            time.sleep(12 * 3600)
            try:
                trades = load_trades()
                sells  = [t for t in trades if t.get('type') == 'sell'
                          and t.get('source') == 'OTONOM' or 'Ajan' in t.get('period','')]
                if len(sells) < 5:
                    continue

                wins = [t for t in sells if t.get('pnl', 0) > 0]
                wr   = len(wins) / len(sells)

                # Kazanma oranı düşükse momentum ağırlığını artır
                # (en belirleyici faktör genellikle momentum)
                w = self.state['weights']
                if wr < 0.45:
                    w['momentum'] = min(w['momentum'] * 1.1, 4.0)
                    w['pattern']  = max(w['pattern']  * 0.95, 1.0)
                elif wr > 0.65:
                    # İyi gidiyorsa koruyucu ol, trend'e daha fazla bak
                    w['trend']    = min(w['trend'] * 1.05, 3.0)
                _save_state(self.state)
                send_telegram(
                    f"⚙️ <b>Ağırlık Güncellemesi</b>\n"
                    f"Kazanma Oranı: %{round(wr*100,1)}\n"
                    f"Trend: {w['trend']:.2f} | Momentum: {w['momentum']:.2f}"
                )
            except Exception as e:
                print(f'[Agent Weights] {e}')

    # ── Rejim Değişikliği ─────────────────────────────────────────────────
    def _on_regime_change(self, new_regime):
        emoji = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(new_regime, '⚪')
        old   = self.state.get('last_regime', '?')
        send_telegram(
            f"{emoji} <b>REJİM DEĞİŞTİ</b>\n"
            f"{old} → <b>{new_regime}</b>\n"
            f"{'Yeni alımlar durduruldu.' if new_regime == 'BEAR' else 'Tarama devam ediyor.'}"
        )

    # ── Saatlik Rapor ─────────────────────────────────────────────────────
    def _hourly_report_loop(self):
        while self.running:
            time.sleep(3600)
            try:
                self._send_status_report()
            except Exception as e:
                print(f'[Agent HourlyReport] {e}')

    def _send_status_report(self):
        client    = get_client()
        positions = load_positions()
        balance   = get_usdt_balance(client)
        open_pos  = [(s, p) for s, p in positions.items() if p.get('qty', 0) > 0]
        regime    = self.state.get('last_regime', '?')
        emoji_r   = {'BULL': '🟢', 'SIDEWAYS': '🟡', 'BEAR': '🔴'}.get(regime, '⚪')

        lines = [
            "📊 <b>SAATLIK DURUM RAPORU</b>",
            f"━━━━━━━━━━━━━━",
            f"💰 Bakiye: <b>${round(balance,2)}</b> USDT",
            f"📈 Açık Poz: {len(open_pos)} / {self.MAX_POSITIONS}",
            f"💹 Toplam PnL: ${round(self.state.get('total_pnl',0),2)}",
            f"{emoji_r} Rejim: {regime}",
            f"🔍 Tarama: {self.state['scan_count']}x",
        ]

        if open_pos:
            lines.append("")
            lines.append("📌 <b>Pozisyonlar:</b>")
            for sym, pos in open_pos:
                price  = get_price(client, sym)
                chg    = (price - pos['avg_price']) / pos['avg_price'] * 100
                sign   = '+' if chg >= 0 else ''
                icon   = '🟢' if chg >= 0 else '🔴'
                lines.append(f"  {icon} {sym}: {sign}{round(chg,2)}%")

        send_telegram('\n'.join(lines))

    # ── Günlük Özet ───────────────────────────────────────────────────────
    def _daily_summary_loop(self):
        while self.running:
            time.sleep(24 * 3600)
            try:
                self._send_daily_summary()
            except Exception as e:
                print(f'[Agent DailySummary] {e}')

    def _send_daily_summary(self):
        trades = load_trades()
        now    = datetime.datetime.now()
        day_ago = now - datetime.timedelta(days=1)
        recent = [
            t for t in trades
            if t.get('type') == 'sell'
            and t.get('time', '') >= day_ago.strftime('%Y-%m-%d')
        ]
        if not recent:
            return

        wins     = [t for t in recent if t.get('pnl', 0) > 0]
        total_pnl = sum(t.get('pnl', 0) for t in recent)
        wr        = round(len(wins) / len(recent) * 100, 1)
        best  = max(recent, key=lambda t: t.get('pnl', 0), default=None)
        worst = min(recent, key=lambda t: t.get('pnl', 0), default=None)

        lines = [
            "🌙 <b>GÜNLÜK ÖZET</b>",
            f"━━━━━━━━━━━━━━",
            f"📊 İşlem: {len(recent)} | Kazanma: %{wr}",
            f"💹 Net PnL: ${round(total_pnl,2)}",
        ]
        if best:
            lines.append(f"🏆 En İyi: {best['symbol']} +${round(best.get('pnl',0),2)}")
        if worst:
            lines.append(f"💀 En Kötü: {worst['symbol']} ${round(worst.get('pnl',0),2)}")

        w = self.state['weights']
        lines += [
            "",
            f"⚙️ Ağırlıklar: T:{w['trend']:.1f} M:{w['momentum']:.1f} "
            f"V:{w['volume']:.1f} P:{w['pattern']:.1f}",
        ]
        send_telegram('\n'.join(lines))

    def stop(self):
        self.running = False
        send_telegram("⛔ <b>Otonom Ajan durduruldu.</b>")


# ── Global Instance & API ─────────────────────────────────────────────────────

_agent_instance: AutonomousAgent | None = None
_agent_thread:   threading.Thread | None = None


def start_autonomous_agent():
    global _agent_instance, _agent_thread
    if _agent_instance and _agent_instance.running:
        return False  # zaten çalışıyor
    _agent_instance = AutonomousAgent()
    _agent_thread   = threading.Thread(target=_agent_instance.run, daemon=True)
    _agent_thread.start()
    return True


def stop_autonomous_agent():
    global _agent_instance
    if _agent_instance:
        _agent_instance.stop()
        _agent_instance.running = False
    return True


def agent_status():
    if _agent_instance and _agent_instance.running:
        s = _agent_instance.state
        return {
            'running':      True,
            'scan_count':   s.get('scan_count', 0),
            'total_pnl':    s.get('total_pnl', 0.0),
            'last_regime':  s.get('last_regime', 'SIDEWAYS'),
            'weights':      s.get('weights', DEFAULT_WEIGHTS),
            'blacklisted':  [k for k, v in s.get('blacklist', {}).items()
                             if v > time.time()],
            'started_at':   s.get('started_at', ''),
        }
    return {'running': False}
