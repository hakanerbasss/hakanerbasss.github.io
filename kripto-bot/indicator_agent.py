"""
Indicator Agent — Otomatik UT Bot Tarayıcı
────────────────────────────────────────────
• Manuel coin eklemeye gerek yok — top 50 coini kendisi tarar
• Öncelik: kullanıcının dashboard'da ayarladığı parametreler
• Fallback: varsayılan 4 kombinasyon (kullanıcı ayarı yoksa)
• UT Bot sinyali + RSI filtresi + mini backtest (son 200 mum)
• En yüksek backtest win rate'li kombinasyonu seçer
• Kaynak: 'INDICATOR' — karşılaştırma tablosunda ayrı gösterilir
"""

import time, datetime, threading, json, os
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, get_price, send_telegram, get_usdt_balance)
from signal_engine import calc_ut_bot, get_klines

STATE_FILE = 'indicator_state.json'

STABLECOINS = {
    'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'FDUSDUSDT', 'EURUSDT',
    'GBPUSDT',  'DAIUSDT',  'FRAXUSDT', 'USDPUSDT',  'PYUSDUSDT', 'USDTUSDT',
}

MAX_POSITIONS = 6
SCAN_INTERVAL = 120   # saniye
MONITOR_SEC   = 8
MIN_VOLUME    = 3_000_000   # $3M günlük hacim

# Kullanıcı henüz coin eklemediyse kullanılacak varsayılanlar
DEFAULT_COMBOS = [
    {'key': 1.0, 'atr': 7,  'period': '1h', 'mode': 'crossover', 'label': 'UT(1.0,7,1h)'},
    {'key': 2.0, 'atr': 7,  'period': '1h', 'mode': 'crossover', 'label': 'UT(2.0,7,1h)'},
    {'key': 3.0, 'atr': 10, 'period': '1h', 'mode': 'crossover', 'label': 'UT(3.0,10,1h)'},
    {'key': 2.0, 'atr': 7,  'period': '4h', 'mode': 'crossover', 'label': 'UT(2.0,7,4h)'},
]


def _user_combos(cfg):
    """
    Kullanıcının dashboard'da yapılandırdığı indikatör ayarlarını okur.
    Her coin'in ut_key / ut_atr / period / ut_mode değerlerinden
    benzersiz kombinasyonlar oluşturur — bunlar Indicator Agent'ın
    tüm piyasaya uyguladığı parametreler olur.
    Hiç coin eklenmemişse DEFAULT_COMBOS döner.
    """
    coins = cfg.get('coins', [])
    seen, combos = set(), []
    for coin in coins:
        key    = float(coin.get('ut_key', 2.0))
        atr    = int(coin.get('ut_atr', 7))
        period = coin.get('period', '1h')
        mode   = coin.get('ut_mode', 'crossover')
        uid    = (key, atr, period, mode)
        if uid in seen:
            continue
        seen.add(uid)
        label = f'UT({key},{atr},{period})'
        if mode != 'crossover':
            label += f'[{mode}]'
        combos.append({'key': key, 'atr': atr, 'period': period,
                       'mode': mode, 'label': label})
    return combos if combos else DEFAULT_COMBOS


# ── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────────

def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return 50.0
    d = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    g = sum(max(v, 0) for v in d[-n:]) / n
    l = sum(max(-v, 0) for v in d[-n:]) / n
    return 100.0 if l == 0 else round(100 - 100 / (1 + g / l), 1)


def _btc_up(client):
    try:
        closes, _, _, _ = get_klines(client, 'BTCUSDT', '1h', limit=25)
        return closes[-1] > sum(closes[-20:]) / 20
    except Exception:
        return True


def _scan_candidates(client):
    tickers = client.get_ticker()
    usdt = [
        t for t in tickers
        if t['symbol'].endswith('USDT')
        and t['symbol'] not in STABLECOINS
        and float(t.get('quoteVolume', 0)) > MIN_VOLUME
        and float(t.get('lastPrice', 0)) > 0
    ]
    usdt.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
    return [t['symbol'] for t in usdt[:50]]


def _ut_bot_history(closes, highs, lows, key_value, atr_period):
    """Tüm geçmiş için UT Bot sinyallerini tek geçişte hesapla — O(n)."""
    n = len(closes)
    if n < atr_period + 2:
        return []
    trs = [
        max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        for i in range(1, n)
    ]
    if len(trs) < atr_period:
        return []
    atr_val = sum(trs[:atr_period]) / atr_period
    atr_list = [None] * atr_period
    atr_list.append(atr_val)
    for tr in trs[atr_period:]:
        atr_val = (atr_val * (atr_period - 1) + tr) / atr_period
        atr_list.append(atr_val)

    start = atr_period + 1
    trail = closes[start - 1]
    prev_close = closes[start - 1]
    signals = []
    for i in range(start, n):
        c = closes[i]
        prev_trail = trail
        nl = key_value * atr_list[i - 1]
        if c > prev_trail and prev_close > prev_trail:
            trail = max(prev_trail, c - nl)
        elif c < prev_trail and prev_close < prev_trail:
            trail = min(prev_trail, c + nl)
        elif c > prev_trail:
            trail = c - nl
        else:
            trail = c + nl
        if prev_close <= prev_trail and c > trail:
            signals.append(('buy', i))
        elif prev_close >= prev_trail and c < trail:
            signals.append(('sell', i))
        prev_close = c
    return signals


def _mini_backtest(closes, highs, lows, key, atr, exit_bars=8):
    """O(n) mini backtest — son 200 mum üzerinde UT Bot win rate'i."""
    sigs = _ut_bot_history(closes, highs, lows, key, atr)
    buys = [i for sig, i in sigs if sig == 'buy']
    wins = total = 0
    for i in buys:
        if i + exit_bars >= len(closes):
            continue
        pnl = (closes[i + exit_bars] - closes[i]) / closes[i] * 100 - 0.2
        if pnl > 0:
            wins += 1
        total += 1
    wr = round(wins / total * 100, 1) if total >= 3 else None
    return wr, total


# ── Ana Ajan ──────────────────────────────────────────────────────────────────

class IndicatorAgent:
    def __init__(self):
        self._running = False
        self._lock    = threading.Lock()
        self.state    = self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            'scan_count':  0,
            'combo_stats': {},   # dinamik — her kombinasyon ilk kullanımda eklenir
            'blacklist':   {},
            'total_pnl':   0.0,
            'day_start_bal': 0.0,
        }

    def _save(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def _bl(self, sym):
        return time.time() < self.state['blacklist'].get(sym, 0)

    def _add_bl(self, sym, h=4):
        self.state['blacklist'][sym] = time.time() + h * 3600

    def start(self):
        if self._running:
            return False
        self._running = True
        for fn in [self._scan_loop, self._monitor_loop, self._report_loop]:
            threading.Thread(target=fn, daemon=True).start()
        try:
            bal = get_usdt_balance(get_client())
            self.state['day_start_bal'] = bal
        except Exception:
            bal = 0
        cfg    = load_config()
        mode   = '🧪 TESTNET' if cfg.get('testnet', True) else '🔴 GERÇEK'
        combos = _user_combos(cfg)
        src    = 'Sizin ayarlarınız' if cfg.get('coins') else 'Varsayılan (coin eklenmemiş)'
        send_telegram(
            f'{mode} <b>Indicator Agent AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'🔍 Yöntem: UT Bot + RSI + Mini Backtest\n'
            f'⚡ Tarama: {SCAN_INTERVAL}s | Takip: {MONITOR_SEC}s\n'
            f'📐 Parametreler ({src}):\n'
            + '\n'.join(f'  • {c["label"]}' for c in combos)
        )
        return True

    def stop(self):
        self._running = False
        self._save()
        send_telegram('⛔ <b>Indicator Agent durduruldu.</b>')

    # ── Tarama ─────────────────────────────────────────────────────────────
    def _scan_loop(self):
        time.sleep(25)
        while self._running:
            try:
                self._scan()
            except Exception as e:
                print(f'[Indicator] Tarama hata: {e}')
            time.sleep(SCAN_INTERVAL)

    def _scan(self):
        client    = get_client()
        cfg       = load_config()
        positions = load_positions()
        open_cnt  = sum(1 for p in positions.values() if p.get('qty', 0) > 0)
        if open_cnt >= MAX_POSITIONS:
            return

        # Günlük zarar limiti
        bal       = get_usdt_balance(client)
        start_bal = self.state.get('day_start_bal', bal) or bal
        if start_bal > 0 and (bal - start_bal) / start_bal * 100 < -8:
            print('[Indicator] Günlük zarar limiti')
            return

        btc_ok     = _btc_up(client)
        candidates = _scan_candidates(client)
        held       = {s for s, p in positions.items() if p.get('qty', 0) > 0}
        combos     = _user_combos(cfg)   # kullanıcının kendi indikatör ayarları

        # Period'a göre klines önbelleği — aynı coini iki kez çekme
        klines_cache: dict = {}
        best = None   # (wr, sym, combo, rsi, bt_total)

        for sym in candidates:
            if sym in held or self._bl(sym) or not btc_ok:
                continue

            for combo in combos:
                cache_key = (sym, combo['period'])
                if cache_key not in klines_cache:
                    try:
                        c, h, l, _ = get_klines(
                            client, sym, combo['period'], limit=200)
                        klines_cache[cache_key] = (c, h, l)
                    except Exception:
                        continue
                closes, highs, lows = klines_cache[cache_key]
                if len(closes) < 50:
                    continue

                # Mevcut UT Bot sinyali — kullanıcının mode ayarı dahil
                signal = calc_ut_bot(closes, highs, lows,
                                     key_value=combo['key'],
                                     atr_period=combo['atr'],
                                     mode=combo.get('mode', 'crossover'))
                if signal != 'buy':
                    continue

                # RSI filtresi
                rsi = _rsi(closes)
                if not (30 <= rsi <= 65):
                    continue

                # Mini backtest — sadece buy sinyali olan coinler için
                wr, bt_total = _mini_backtest(
                    closes, highs, lows, combo['key'], combo['atr'])
                if wr is None or wr < 50:
                    continue

                if best is None or wr > best[0]:
                    best = (wr, sym, combo, rsi, bt_total)

        if best:
            wr, sym, combo, rsi, bt_total = best
            is_real  = not cfg.get('testnet', True)
            usdt     = max(10.0, min(
                round(bal * (0.02 if is_real else 0.03), 2),
                bal * (0.15 if is_real else 0.20)
            ))
            send_telegram(
                f'📐 <b>INDICATOR ALIM</b>\n'
                f'━━━━━━━━━━━━━━\n'
                f'🪙 <b>{sym}</b>\n'
                f'⚙️ {combo["label"]} | RSI: {rsi}\n'
                f'📊 Backtest: %{wr} WR ({bt_total} işlem, son 200 mum)\n'
                f'💰 Miktar: ${usdt:.2f}'
            )
            res = execute_buy(client, sym, usdt,
                              source='INDICATOR', period=combo['label'])
            if res.get('ok'):
                with self._lock:
                    stat = self.state['combo_stats'].setdefault(
                        combo['label'], {'wins': 0, 'total': 0, 'pnl': 0.0})
                    stat['total'] = stat.get('total', 0) + 1
                from bot import save_positions
                pos_now = load_positions()
                if sym in pos_now:
                    pos_now[sym].update({
                        'indicator_combo': combo['label'],
                        'open_time':       time.time(),
                    })
                    save_positions(pos_now)

        self.state['scan_count'] = self.state.get('scan_count', 0) + 1
        self._save()

    # ── Pozisyon İzleme ────────────────────────────────────────────────────
    def _monitor_loop(self):
        while self._running:
            try:
                self._monitor()
            except Exception as e:
                print(f'[Indicator] Monitor hata: {e}')
            time.sleep(MONITOR_SEC)

    def _monitor(self):
        client    = get_client()
        positions = load_positions()

        for sym, pos in list(positions.items()):
            if pos.get('qty', 0) <= 0 or not pos.get('indicator_combo'):
                continue
            try:
                price = get_price(client, sym)
                avg   = pos.get('avg_price', price)
                if avg <= 0:
                    continue
                pct = (price - avg) / avg * 100
                tp  = pos.get('tp_pct', 0) or 0
                sl  = pos.get('sl_pct', 0) or 0

                if tp > 0 and pct >= tp:
                    res = execute_sell(client, sym, 100,
                                       source='INDICATOR TP', period='TP')
                    if res.get('ok'):
                        self._record(sym, pos, pct, True)
                    continue

                if sl > 0 and pct <= -sl:
                    res = execute_sell(client, sym, 100,
                                       source='INDICATOR SL', period='SL')
                    if res.get('ok'):
                        self._add_bl(sym, 6)
                        self._record(sym, pos, pct, False)
                    continue

                # Trailing: TP'nin %40'ında aktif, peak'ten -%2 düşüşte çık
                peak = pos.get('peak_price', avg)
                if price > peak:
                    from bot import save_positions
                    pos_now = load_positions()
                    if sym in pos_now:
                        pos_now[sym]['peak_price'] = price
                        save_positions(pos_now)
                        peak = price

                if tp > 0 and pct >= tp * 0.4:
                    drawdown = (price - peak) / peak * 100 if peak > 0 else 0
                    if drawdown <= -2.0:
                        res = execute_sell(client, sym, 100,
                                           source='INDICATOR TRAIL', period='TRAIL')
                        if res.get('ok'):
                            self._record(sym, pos, pct, pct > 0)
                        continue

                # 36 saat timeout
                if time.time() - pos.get('open_time', time.time()) > 36 * 3600:
                    res = execute_sell(client, sym, 100,
                                       source='INDICATOR TIME', period='TIMEOUT')
                    if res.get('ok'):
                        self._record(sym, pos, pct, pct > 0)

            except Exception as e:
                print(f'[Indicator] Monitor {sym}: {e}')

    def _record(self, sym, pos, pct, won):
        combo = pos.get('indicator_combo', '')
        with self._lock:
            if combo:
                stat = self.state['combo_stats'].setdefault(
                    combo, {'wins': 0, 'total': 0, 'pnl': 0.0})
                stat['total'] = stat.get('total', 0) + 1
                if won:
                    stat['wins'] = stat.get('wins', 0) + 1
                dollar_pnl = round(
                    pos.get('qty', 0) * pos.get('avg_price', 0) * pct / 100, 2)
                stat['pnl'] = round(stat.get('pnl', 0.0) + dollar_pnl, 2)
                self.state['total_pnl'] = round(
                    self.state.get('total_pnl', 0.0) + dollar_pnl, 2)
            self._save()

    # ── Saatlik Rapor ──────────────────────────────────────────────────────
    def _report_loop(self):
        time.sleep(3600)
        while self._running:
            try:
                self._report()
            except Exception as e:
                print(f'[Indicator] Rapor hata: {e}')
            time.sleep(3600)

    def _report(self):
        client    = get_client()
        positions = load_positions()
        open_pos  = {s: p for s, p in positions.items()
                     if p.get('qty', 0) > 0 and p.get('indicator_combo')}
        try:
            bal = get_usdt_balance(client)
        except Exception:
            bal = 0

        pos_lines = []
        for sym, pos in open_pos.items():
            try:
                price = get_price(client, sym)
                avg   = pos.get('avg_price', price)
                pct   = (price - avg) / avg * 100 if avg > 0 else 0
                icon  = '🟢' if pct > 0 else '🔴'
                pos_lines.append(
                    f'{icon} {sym}: %{pct:+.2f} [{pos.get("indicator_combo","")}]')
            except Exception:
                pass

        combo_lines = []
        for label, stat in self.state.get('combo_stats', {}).items():
            t = stat.get('total', 0)
            if t > 0:
                wr  = round(stat.get('wins', 0) / t * 100, 1)
                pnl = round(stat.get('pnl', 0.0), 2)
                combo_lines.append(
                    f'  📐 {label}: %{wr} WR | {stat["wins"]}/{t} | ${pnl:+.2f}')

        msg = (
            f'📐 <b>Indicator Agent Saatlik Rapor</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📦 Açık: {len(open_pos)} | 🔍 Tarama: {self.state.get("scan_count",0)}x\n'
            f'💹 Toplam PnL: ${self.state.get("total_pnl",0.0):.2f}\n'
        )
        if pos_lines:
            msg += '\n'.join(pos_lines) + '\n'
        msg += '━━━━━━━━━━━━━━\n📊 <b>Parametre Performansı:</b>\n'
        msg += '\n'.join(combo_lines) if combo_lines else '  Henüz veri yok'
        send_telegram(msg)

    def status(self):
        positions = load_positions()
        open_pos  = sum(1 for p in positions.values()
                        if p.get('qty', 0) > 0 and p.get('indicator_combo'))
        return {
            'running':        self._running,
            'scan_count':     self.state.get('scan_count', 0),
            'total_pnl':      self.state.get('total_pnl', 0),
            'combo_stats':    self.state.get('combo_stats', {}),
            'open_positions': open_pos,
            'blacklist': {s: int(t - time.time())
                          for s, t in self.state.get('blacklist', {}).items()
                          if t > time.time()},
        }


# ── Global API ────────────────────────────────────────────────────────────────

_agent      = None
_agent_lock = threading.Lock()


def start_indicator_agent():
    global _agent
    with _agent_lock:
        if _agent and _agent._running:
            return False
        _agent = IndicatorAgent()
        return _agent.start()


def stop_indicator_agent():
    global _agent
    with _agent_lock:
        if _agent:
            _agent.stop()


def indicator_agent_status():
    global _agent
    if not _agent:
        return {'running': False}
    return _agent.status()
