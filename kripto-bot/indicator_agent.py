"""
Indicator Agent — Kodlanmış İndikatörler ile Otonom Tarayıcı
─────────────────────────────────────────────────────────────
• Top 50 coin hacme göre otomatik taranır — kullanıcı seçimi yok
• 3 kodlu indikatör sırayla uygulanır:
    1. UT Bot   → signal_engine.calc_ut_bot
    2. Smart    → smart_strategy.check_smart_signal
    3. Seans    → seans_strategy.check_seans_signal
• Her indikatör için ayrı performans takibi
• İşlemler 'INDICATOR-UTBOT' | 'INDICATOR-SMART' | 'INDICATOR-SEANS' kaynağıyla etiketlenir
"""

import time, threading, json, os
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, get_price, send_telegram, get_usdt_balance)
from signal_engine import calc_ut_bot, get_klines
from smart_strategy import check_smart_signal, check_smart_sell
from seans_strategy import check_seans_signal

STATE_FILE = 'indicator_state.json'

STABLECOINS = {
    'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'FDUSDUSDT', 'EURUSDT',
    'GBPUSDT',  'DAIUSDT',  'FRAXUSDT', 'USDPUSDT',  'PYUSDUSDT', 'USDTUSDT',
}

MAX_POSITIONS  = 6
SCAN_INTERVAL  = 90    # saniye
MONITOR_SEC    = 8
MIN_VOLUME     = 3_000_000   # $3M günlük hacim

# UT Bot sabit parametreler (tüm coinlere aynı uygulanır)
UTBOT_KEY    = 2.0
UTBOT_ATR    = 7
UTBOT_PERIOD = '1h'
UTBOT_MODE   = 'crossover'

SMART_MIN_SCORE = 2    # 4 üzerinden en az 2 faktör
SEANS_STRATEGY  = 'both'   # sabah (9-12) + akşam (20-23)

INDICATORS = ['UTBOT', 'SMART', 'SEANS']


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


def _btc_up(client):
    try:
        closes, _, _, _ = get_klines(client, 'BTCUSDT', '1h', limit=25)
        return closes[-1] > sum(closes[-20:]) / 20
    except Exception:
        return True


class IndicatorAgent:
    def __init__(self):
        self._running = False
        self._lock    = threading.Lock()
        self.state    = self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    # Eski 'combo_stats' formatını yeni 'indicator_stats'a geçir
                    data.setdefault('indicator_stats', {
                        ind: {'wins': 0, 'total': 0, 'pnl': 0.0}
                        for ind in INDICATORS
                    })
                    return data
            except Exception:
                pass
        return {
            'scan_count':      0,
            'indicator_stats': {
                ind: {'wins': 0, 'total': 0, 'pnl': 0.0}
                for ind in INDICATORS
            },
            'blacklist':       {},
            'total_pnl':       0.0,
            'day_start_bal':   0.0,
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
        cfg  = load_config()
        mode = '🧪 TESTNET' if cfg.get('testnet', True) else '🔴 GERÇEK'
        send_telegram(
            f'{mode} <b>Indicator Agent AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'🔍 Yöntem: Kodlu İndikatörler (UT Bot + Smart + Seans)\n'
            f'⚡ Tarama: {SCAN_INTERVAL}s | Takip: {MONITOR_SEC}s\n'
            f'📐 Aktif İndikatörler:\n'
            f'  • UT Bot (key={UTBOT_KEY}, atr={UTBOT_ATR}, {UTBOT_PERIOD}, {UTBOT_MODE})\n'
            f'  • Smart Composite (min skor {SMART_MIN_SCORE}/4)\n'
            f'  • Seans Stratejisi ({SEANS_STRATEGY}: sabah 9-12 + akşam 20-23)\n'
            f'🪙 Evren: Top 50 coin (hacme göre, otomatik)'
        )
        return True

    def stop(self):
        self._running = False
        self._save()
        send_telegram('⛔ <b>Indicator Agent durduruldu.</b>')

    # ── Tarama ────────────────────────────────────────────────────────────────
    def _scan_loop(self):
        time.sleep(30)
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

        bal       = get_usdt_balance(client)
        start_bal = self.state.get('day_start_bal', bal) or bal
        if start_bal > 0 and (bal - start_bal) / start_bal * 100 < -8:
            print('[Indicator] Günlük zarar limiti aşıldı, tarama atlandı')
            return

        btc_ok     = _btc_up(client)
        candidates = _scan_candidates(client)
        held       = {s for s, p in positions.items() if p.get('qty', 0) > 0}

        for sym in candidates:
            if sym in held or self._bl(sym) or not btc_ok:
                continue

            sig_result = self._check_all_indicators(client, sym)
            if not sig_result:
                continue

            indicator, reason = sig_result
            is_real = not cfg.get('testnet', True)
            usdt    = max(10.0, min(
                round(bal * (0.02 if is_real else 0.03), 2),
                bal * (0.15 if is_real else 0.20),
            ))
            source = f'INDICATOR-{indicator}'
            send_telegram(
                f'📐 <b>INDICATOR ALIM</b>\n'
                f'━━━━━━━━━━━━━━\n'
                f'🪙 <b>{sym}</b>\n'
                f'⚙️ İndikatör: {indicator}\n'
                f'📊 Neden: {reason}\n'
                f'💰 Miktar: ${usdt:.2f}'
            )
            res = execute_buy(client, sym, usdt, source=source, period=indicator)
            if res.get('ok'):
                with self._lock:
                    stats    = self.state.setdefault('indicator_stats', {})
                    ind_stat = stats.setdefault(indicator, {'wins': 0, 'total': 0, 'pnl': 0.0})
                    ind_stat['total'] = ind_stat.get('total', 0) + 1

                from bot import save_positions
                pos_now = load_positions()
                if sym in pos_now:
                    pos_now[sym].update({
                        'indicator_name': indicator,
                        'open_time':      time.time(),
                    })
                    save_positions(pos_now)
                break  # Tek taramada bir alım yeter

        self.state['scan_count'] = self.state.get('scan_count', 0) + 1
        self._save()

    def _check_all_indicators(self, client, sym):
        """Tüm indikatörleri dene — ilk buy sinyalini (indikatör, neden) olarak döndür."""
        # 1. UT Bot
        try:
            closes, highs, lows, _ = get_klines(client, sym, UTBOT_PERIOD, limit=100)
            if len(closes) >= 20:
                sig = calc_ut_bot(closes, highs, lows,
                                  key_value=UTBOT_KEY,
                                  atr_period=UTBOT_ATR,
                                  mode=UTBOT_MODE)
                if sig == 'buy':
                    return ('UTBOT', f'UT Bot crossover ({UTBOT_PERIOD})')
        except Exception as e:
            print(f'[Indicator] UTBOT {sym}: {e}')

        # 2. Smart Composite
        try:
            sig = check_smart_signal(client, sym, SMART_MIN_SCORE)
            if sig.get('signal') == 'buy':
                return ('SMART', sig.get('detail', 'Smart sinyal'))
        except Exception as e:
            print(f'[Indicator] SMART {sym}: {e}')

        # 3. Seans Stratejisi
        try:
            sig = check_seans_signal(client, sym, SEANS_STRATEGY)
            if sig.get('signal') == 'buy':
                return ('SEANS', sig.get('reason', 'Seans alımı'))
        except Exception as e:
            print(f'[Indicator] SEANS {sym}: {e}')

        return None

    # ── Pozisyon İzleme ───────────────────────────────────────────────────────
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
            if pos.get('qty', 0) <= 0 or not pos.get('indicator_name'):
                continue
            try:
                price = get_price(client, sym)
                avg   = pos.get('avg_price', price)
                if avg <= 0:
                    continue
                pct = (price - avg) / avg * 100
                tp  = pos.get('tp_pct', 0) or 0
                sl  = pos.get('sl_pct', 0) or 0
                ind = pos.get('indicator_name', '')

                if tp > 0 and pct >= tp:
                    res = execute_sell(client, sym, 100,
                                       source=f'INDICATOR-{ind} TP', period='TP')
                    if res.get('ok'):
                        self._record(sym, pos, pct, True)
                    continue

                if sl > 0 and pct <= -sl:
                    res = execute_sell(client, sym, 100,
                                       source=f'INDICATOR-{ind} SL', period='SL')
                    if res.get('ok'):
                        self._add_bl(sym, 6)
                        self._record(sym, pos, pct, False)
                    continue

                # Trailing stop — TP'nin %40'ına ulaşınca aktif, peak'ten -%2 düşüşte çık
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
                                           source=f'INDICATOR-{ind} TRAIL', period='TRAIL')
                        if res.get('ok'):
                            self._record(sym, pos, pct, pct > 0)
                        continue

                # Smart: teknik satış sinyali kontrolü
                if ind == 'SMART':
                    try:
                        sell_sig = check_smart_sell(client, sym)
                        if sell_sig.get('signal') == 'sell':
                            res = execute_sell(client, sym, 100,
                                               source='INDICATOR-SMART SELL',
                                               period=sell_sig.get('reason', 'SELL'))
                            if res.get('ok'):
                                self._record(sym, pos, pct, pct > 0)
                            continue
                    except Exception:
                        pass

                # 36 saat timeout
                if time.time() - pos.get('open_time', time.time()) > 36 * 3600:
                    res = execute_sell(client, sym, 100,
                                       source=f'INDICATOR-{ind} TIME', period='TIMEOUT')
                    if res.get('ok'):
                        self._record(sym, pos, pct, pct > 0)

            except Exception as e:
                print(f'[Indicator] Monitor {sym}: {e}')

    def _record(self, sym, pos, pct, won):
        ind = pos.get('indicator_name', '')
        with self._lock:
            if ind:
                stats    = self.state.setdefault('indicator_stats', {})
                ind_stat = stats.setdefault(ind, {'wins': 0, 'total': 0, 'pnl': 0.0})
                ind_stat['total'] = ind_stat.get('total', 0) + 1
                if won:
                    ind_stat['wins'] = ind_stat.get('wins', 0) + 1
                dollar_pnl = round(
                    pos.get('qty', 0) * pos.get('avg_price', 0) * pct / 100, 2)
                ind_stat['pnl'] = round(ind_stat.get('pnl', 0.0) + dollar_pnl, 2)
                self.state['total_pnl'] = round(
                    self.state.get('total_pnl', 0.0) + dollar_pnl, 2)
            self._save()

    # ── Saatlik Rapor ─────────────────────────────────────────────────────────
    def _report_loop(self):
        time.sleep(4 * 3600)
        while self._running:
            try:
                self._report()
            except Exception as e:
                print(f'[Indicator] Rapor hata: {e}')
            time.sleep(4 * 3600)

    def _report(self):
        client    = get_client()
        positions = load_positions()
        open_pos  = {s: p for s, p in positions.items()
                     if p.get('qty', 0) > 0 and p.get('indicator_name')}
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
                pos_lines.append(f'{icon} {sym}: %{pct:+.2f} [{pos.get("indicator_name","")}]')
            except Exception:
                pass

        stats = self.state.get('indicator_stats', {})
        ind_lines = []
        for ind in INDICATORS:
            stat = stats.get(ind, {})
            t = stat.get('total', 0)
            if t > 0:
                wr  = round(stat.get('wins', 0) / t * 100, 1)
                pnl = round(stat.get('pnl', 0.0), 2)
                ind_lines.append(f'  • {ind}: %{wr} WR | {stat["wins"]}/{t} | ${pnl:+.2f}')
            else:
                ind_lines.append(f'  • {ind}: Henüz işlem yok')

        msg = (
            f'📐 <b>Indicator Agent Saatlik Rapor</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📦 Açık: {len(open_pos)} | 🔍 Tarama: {self.state.get("scan_count",0)}x\n'
            f'💹 Toplam PnL: ${self.state.get("total_pnl",0.0):.2f}\n'
        )
        if pos_lines:
            msg += '\n'.join(pos_lines) + '\n'
        msg += '━━━━━━━━━━━━━━\n📊 <b>İndikatör Performansı:</b>\n'
        msg += '\n'.join(ind_lines)
        send_telegram(msg)

    def status(self):
        positions = load_positions()
        open_pos  = sum(1 for p in positions.values()
                        if p.get('qty', 0) > 0 and p.get('indicator_name'))
        return {
            'running':          self._running,
            'scan_count':       self.state.get('scan_count', 0),
            'total_pnl':        self.state.get('total_pnl', 0),
            'indicator_stats':  self.state.get('indicator_stats', {}),
            'open_positions':   open_pos,
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
