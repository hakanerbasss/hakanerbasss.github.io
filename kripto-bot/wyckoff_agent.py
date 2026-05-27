"""
Wyckoff Akümülasyon Ajanı
─────────────────────────────────────────────────────
• Aylarca dar bantta gezen coinleri tespit eder
• Sahte pump sayar — balina test ediyor, mal topluyor
• Higher low izler — satış baskısı azalıyor
• Bant kırılışında alım — gerçek hareket başlıyor
• TP %25, SL -%8 — uzun vadeli pozisyon
"""

import time, threading, datetime, json, os
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, get_price, send_telegram, get_usdt_balance)
from binance.client import Client as BClient

STATE_FILE = 'wyckoff_state.json'

STABLECOINS = {
    'USDCUSDT','BUSDUSDT','TUSDUSDT','FDUSDUSDT','EURUSDT',
    'GBPUSDT','DAIUSDT','FRAXUSDT','USDPUSDT','PYUSDUSDT','USDTUSDT',
}

SCAN_INTERVAL  = 4 * 3600   # 4 saatte bir (günlük mum bazlı)
MONITOR_SEC    = 30
MAX_POSITIONS  = 3

BAND_DAYS        = 60        # Sıkışma analizi için gün
BAND_THRESHOLD   = 20        # Bant genişliği <%20 olmalı
MIN_FAKE_PUMPS   = 2         # En az 2 sahte pump
PUMP_MIN_PCT     = 4         # Pump sayılması için min %4 yükseliş
PUMP_RETRACE_PCT = 70        # Geri dönüşün %70'i geri alınmış olmalı
BREAKOUT_PCT     = 3         # Bant üstünde %3 kırılış
BREAKOUT_VOL     = 1.5       # Hacim ortalamanın 1.5x üstünde
MIN_SCORE        = 6.0       # Alım için minimum skor


class WyckoffAgent:

    def __init__(self):
        self._running = False
        self._lock    = threading.Lock()
        self.state    = self._load()

    def _load(self):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {
                'scan_count':  0,
                'total_pnl':   0.0,
                'blacklist':   {},
                'candidates':  {},
                'day_start_bal': 0,
            }

    def _save(self):
        with open(STATE_FILE, 'w') as f:
            json.dump(self.state, f)

    def _bl(self, sym):
        bl = self.state.get('blacklist', {})
        return sym in bl and time.time() < bl[sym]

    # ── Başlat / Durdur ───────────────────────────────────────────────────────

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
            f'{mode} <b>Wyckoff Ajanı AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'🔍 Yöntem: Akümülasyon tespiti (Wyckoff)\n'
            f'⚡ Tarama: 4 saatte bir\n'
            f'📐 Kriterler:\n'
            f'  • {BAND_DAYS} günlük dar bant (%{BAND_THRESHOLD} altı)\n'
            f'  • Min {MIN_FAKE_PUMPS} sahte pump\n'
            f'  • Higher low oluşumu\n'
            f'  • Kırılış: bant üstü %{BREAKOUT_PCT} + hacim x{BREAKOUT_VOL}\n'
            f'🎯 TP: %25 | SL: -%8'
        )
        print('[Wyckoff] Başladı')
        return True

    def stop(self):
        self._running = False
        self._save()

    # ── Veri ─────────────────────────────────────────────────────────────────

    def _get_daily(self, client, sym, days=120):
        klines = client.get_klines(
            symbol=sym,
            interval=BClient.KLINE_INTERVAL_1DAY,
            limit=days + 1,
        )
        klines = klines[:-1]
        closes  = [float(k[4]) for k in klines]
        highs   = [float(k[2]) for k in klines]
        lows    = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        return closes, highs, lows, volumes

    # ── Analiz ───────────────────────────────────────────────────────────────

    def _band_compression(self, closes):
        if len(closes) < BAND_DAYS:
            return 100.0
        window = closes[-BAND_DAYS:]
        high = max(window)
        low  = min(window)
        if low <= 0:
            return 100.0
        return (high - low) / low * 100

    def _count_fake_pumps(self, closes, highs, lows):
        count = 0
        i = 1
        while i < len(closes) - 5:
            base     = closes[i - 1]
            window_h = highs[i:i + 5]
            peak_val = max(window_h)
            pump_pct = (peak_val - base) / base * 100 if base > 0 else 0
            if pump_pct >= PUMP_MIN_PCT:
                peak_offset = window_h.index(peak_val)
                peak_i      = i + peak_offset
                future      = closes[peak_i:peak_i + 10]
                if future:
                    retrace = (peak_val - min(future)) / (peak_val - base) * 100 if (peak_val - base) > 0 else 0
                    if retrace >= PUMP_RETRACE_PCT:
                        count += 1
                        i = peak_i + 10
                        continue
            i += 1
        return count

    def _higher_lows(self, lows, lookback=45):
        if len(lows) < lookback:
            return False
        window = lows[-lookback:]
        third  = lookback // 3
        l1 = min(window[:third])
        l2 = min(window[third:2 * third])
        l3 = min(window[2 * third:])
        return l2 > l1 and l3 > l2

    def _breakout_signal(self, closes, volumes):
        if len(closes) < BAND_DAYS + 5:
            return False, 0
        band_high = max(closes[-BAND_DAYS:])
        breakout_level = band_high * (1 + BREAKOUT_PCT / 100)
        if closes[-1] < breakout_level:
            return False, band_high
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 0
        vol_ok  = avg_vol > 0 and volumes[-1] >= avg_vol * BREAKOUT_VOL
        return vol_ok, band_high

    def _wyckoff_score(self, client, sym):
        try:
            closes, highs, lows, volumes = self._get_daily(client, sym, days=120)
            if len(closes) < 50:
                return None

            band_pct   = self._band_compression(closes)
            band_score = max(0.0, (BAND_THRESHOLD - band_pct) / BAND_THRESHOLD * 3.0)

            fake_pumps = self._count_fake_pumps(closes, highs, lows)
            pump_score = min(3.0, fake_pumps * 1.0)

            hl       = self._higher_lows(lows, lookback=45)
            hl_score = 2.0 if hl else 0.0

            breakout, band_high = self._breakout_signal(closes, volumes)
            br_score = 2.0 if breakout else 0.0

            total = round(band_score + pump_score + hl_score + br_score, 2)

            detail = (
                f'Bant %{band_pct:.1f} | '
                f'Fake pump {fake_pumps}x | '
                f'Higher low {"✅" if hl else "❌"} | '
                f'Kırılış {"✅" if breakout else "⏳"}'
            )

            return {
                'score':       total,
                'signal':      breakout and total >= MIN_SCORE,
                'detail':      detail,
                'fake_pumps':  fake_pumps,
                'band_pct':    round(band_pct, 1),
                'higher_lows': hl,
                'breakout':    breakout,
                'band_high':   band_high,
            }
        except Exception:
            return None

    # ── Tarama ───────────────────────────────────────────────────────────────

    def _scan_loop(self):
        time.sleep(120)
        while self._running:
            try:
                self._scan()
            except Exception as e:
                print(f'[Wyckoff] Tarama hata: {e}')
            time.sleep(SCAN_INTERVAL)

    def _scan(self):
        client    = get_client()
        cfg       = load_config()
        positions = load_positions()
        open_cnt  = sum(
            1 for p in positions.values()
            if p.get('qty', 0) > 0 and p.get('agent') == 'WYCKOFF'
        )
        if open_cnt >= MAX_POSITIONS:
            return

        tickers = client.get_ticker()
        usdt = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in STABLECOINS
            and float(t.get('quoteVolume', 0)) > 1_000_000
            and float(t.get('lastPrice', 0)) > 0
        ]
        usdt.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        candidates = [t['symbol'] for t in usdt[:100]]

        scan_no = self.state.get('scan_count', 0) + 1
        print(f'[Wyckoff] Tarama #{scan_no}: {len(candidates)} coin taranıyor')

        best_sym    = None
        best_result = None
        aday_count  = 0

        for sym in candidates:
            if self._bl(sym):
                continue
            if sym in positions and positions[sym].get('qty', 0) > 0:
                continue

            result = self._wyckoff_score(client, sym)
            if result is None:
                continue

            if result['fake_pumps'] >= 1 or result['band_pct'] < BAND_THRESHOLD:
                self.state.setdefault('candidates', {})[sym] = {
                    'score':   result['score'],
                    'detail':  result['detail'],
                    'updated': datetime.datetime.now().strftime('%d/%m %H:%M'),
                }
                aday_count += 1

            if result['signal']:
                if best_result is None or result['score'] > best_result['score']:
                    best_sym    = sym
                    best_result = result

        self.state['scan_count'] = scan_no
        self._save()

        # Tarama özeti
        top = sorted(
            self.state.get('candidates', {}).items(),
            key=lambda x: x[1].get('score', 0),
            reverse=True,
        )[:5]
        if top:
            lines = [f'🏗 <b>Wyckoff Tarama #{scan_no}</b> — {aday_count} aday\n━━━━━━━━━━━━━━']
            for s, v in top:
                lines.append(f'<b>{s}</b>: {v["score"]}/10\n  {v["detail"]}')
            if not best_sym:
                lines.append('\n⏳ Kırılış bekleniyor...')
            send_telegram('\n'.join(lines))

        if best_sym and best_result:
            self._do_buy(client, best_sym, best_result, cfg)

    def _do_buy(self, client, sym, result, cfg):
        is_real = not cfg.get('testnet', True)
        try:
            bal = get_usdt_balance(client)
        except Exception:
            bal = 100.0

        risk = 0.03 if is_real else 0.05
        usdt = round(bal * risk, 2)
        usdt = max(10.0, min(usdt, bal * (0.15 if is_real else 0.25)))

        send_telegram(
            f'🏗 <b>WYCKOFF ALIM SİNYALİ</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'🪙 <b>{sym}</b>\n'
            f'📊 Skor: {result["score"]}/10\n'
            f'📐 {result["detail"]}\n'
            f'💰 Miktar: ${usdt:.2f}\n'
            f'🎯 TP: %25 | SL: -%8'
        )

        res = execute_buy(client, sym, usdt, source='WYCKOFF', period='Akümülasyon')
        if res.get('ok'):
            from bot import save_positions
            pos = load_positions()
            if sym in pos:
                pos[sym].update({
                    'agent':         'WYCKOFF',
                    'open_time':     time.time(),
                    'wyckoff_score': result['score'],
                    'tp_pct':        25.0,
                    'sl_pct':         8.0,
                })
                save_positions(pos)

    # ── Pozisyon İzleme ──────────────────────────────────────────────────────

    def _monitor_loop(self):
        while self._running:
            try:
                self._monitor()
            except Exception as e:
                print(f'[Wyckoff] Monitor hata: {e}')
            time.sleep(MONITOR_SEC)

    def _monitor(self):
        client    = get_client()
        positions = load_positions()

        for sym, pos in list(positions.items()):
            if pos.get('qty', 0) <= 0 or pos.get('agent') != 'WYCKOFF':
                continue
            try:
                price     = get_price(client, sym)
                avg_price = pos.get('avg_price', price)
                if avg_price <= 0:
                    continue
                pct = (price - avg_price) / avg_price * 100
                tp  = pos.get('tp_pct', 25.0)
                sl  = pos.get('sl_pct',  8.0)

                if pct >= tp:
                    send_telegram(f'🏗✅ <b>WYCKOFF KÂR</b> {sym} +%{pct:.2f}')
                    res = execute_sell(client, sym, 100, source='WYCKOFF TP', period='TP')
                    if res.get('ok'):
                        pos['qty'] = 0
                        self.state['total_pnl'] = round(
                            self.state.get('total_pnl', 0) + res.get('pnl', 0), 2)
                        self.state['blacklist'][sym] = time.time() + 24 * 3600
                        self._save()

                elif pct <= -sl:
                    send_telegram(f'🏗🔴 <b>WYCKOFF STOP</b> {sym} %{pct:.2f}')
                    res = execute_sell(client, sym, 100, source='WYCKOFF SL', period='SL')
                    if res.get('ok'):
                        pos['qty'] = 0
                        self.state['total_pnl'] = round(
                            self.state.get('total_pnl', 0) + res.get('pnl', 0), 2)
                        self.state['blacklist'][sym] = time.time() + 48 * 3600
                        self._save()

            except Exception as e:
                print(f'[Wyckoff] Monitor {sym}: {e}')

    # ── Rapor ────────────────────────────────────────────────────────────────

    def _report_loop(self):
        now = datetime.datetime.now()
        time.sleep((60 - now.minute) * 60 - now.second)
        while self._running:
            try:
                self._report()
            except Exception as e:
                print(f'[Wyckoff] Rapor hata: {e}')
            time.sleep(3600)

    def _report(self):
        try:
            bal = get_usdt_balance(get_client())
        except Exception:
            bal = 0
        positions = load_positions()
        open_pos  = [(s, p) for s, p in positions.items()
                     if p.get('qty', 0) > 0 and p.get('agent') == 'WYCKOFF']
        top = sorted(
            self.state.get('candidates', {}).items(),
            key=lambda x: x[1].get('score', 0),
            reverse=True,
        )[:3]

        lines = [
            '🏗 <b>Wyckoff Ajan Saatlik Rapor</b>',
            '━━━━━━━━━━━━━━',
            f'💰 Bakiye: ${bal:.2f}',
            f'📦 Açık: {len(open_pos)}/{MAX_POSITIONS} | 🔍 Tarama: {self.state.get("scan_count",0)}x',
            f'💹 Toplam PnL: ${self.state.get("total_pnl",0):.2f}',
        ]
        if open_pos:
            lines.append('━━━━━━━━━━━━━━')
            client = get_client()
            for sym, pos in open_pos:
                try:
                    price = get_price(client, sym)
                    pct   = (price - pos['avg_price']) / pos['avg_price'] * 100
                    icon  = '🟢' if pct >= 0 else '🔴'
                    lines.append(f'{icon} {sym}: {"+"+str(round(pct,2)) if pct>=0 else str(round(pct,2))}%')
                except Exception:
                    lines.append(f'⚪ {sym}: fiyat alınamadı')
        if top:
            lines.append('━━━━━━━━━━━━━━')
            lines.append('👀 İzleme Listesi:')
            for s, v in top:
                lines.append(f'  • {s}: {v["score"]}/10 — {v["detail"]}')
        send_telegram('\n'.join(lines))

    def status(self):
        positions = load_positions()
        open_pos  = sum(1 for p in positions.values()
                        if p.get('qty', 0) > 0 and p.get('agent') == 'WYCKOFF')
        return {
            'running':        self._running,
            'scan_count':     self.state.get('scan_count', 0),
            'total_pnl':      self.state.get('total_pnl', 0),
            'open_positions': open_pos,
            'candidates':     len(self.state.get('candidates', {})),
        }


# ── Global API ────────────────────────────────────────────────────────────────

_agent      = None
_agent_lock = threading.Lock()


def start_wyckoff_agent():
    global _agent
    with _agent_lock:
        if _agent and _agent._running:
            return False
        _agent = WyckoffAgent()
        return _agent.start()


def stop_wyckoff_agent():
    global _agent
    with _agent_lock:
        if _agent:
            _agent.stop()


def wyckoff_agent_status():
    global _agent
    if not _agent:
        return {'running': False}
    return _agent.status()
