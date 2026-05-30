"""
Accumulation Agent — Sessiz Birikim Tarayıcı
─────────────────────────────────────────────
Herkesin görmezden geldiği anda giriyor: hacim kurumuş, fiyat bantlanmış.

3 katmanlı filtre:
  1. Hacim sıkışması — 21 günlük ortalamanın %65'inden az işlem görüyor
  2. Dar fiyat bandı — 7 günlük yüksek-alçak farkı <%10
  3. Bollinger sıkışması — BB genişliği tarihsel minimuma yakın

Tetik: hacmin ilk kez dönmeye başlaması (saatlik vol > 1.5× ort, fiyat henüz <%2 artmamış).
Fark: BREAKOUT patlama SONRASI girer. Bu ajan patlamadan ÖNCE.
"""

import time, threading, json, os, datetime

from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, get_price, send_telegram, get_usdt_balance,
                 update_position, check_breakeven, get_total_equity,
                 position_size_by_score)

STATE_FILE = 'accumulation_state.json'

STABLECOINS = {
    'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'FDUSDUSDT', 'EURUSDT',
    'GBPUSDT',  'DAIUSDT',  'FRAXUSDT', 'USDPUSDT',  'PYUSDUSDT', 'USDTUSDT',
}

GLOBAL_MAX      = 6          # sistem geneli maksimum açık pozisyon
AGENT_MAX       = 2          # bu ajan aynı anda en fazla 2 pozisyon tutar
SCORE_MIN       = 55         # tarama eşiği (0-100)
SCAN_INTERVAL   = 900        # 15dk — günlük data çekimi yavaş
TRIGGER_SEC     = 120        # 2dk — hacim dönüşü kontrolü
MONITOR_SEC     = 10
MIN_VOL_21D_AVG = 1_000_000  # 21 günlük ort. hacim >= $1M (canlı coin)
MIN_VOL_CURR    = 200_000    # anlık 24h hacim >= $200K (tamamen ölü değil)
MAX_VOL_CURR    = 10_000_000 # anlık hacim <= $10M (zaten popüler olanı değil)
MAX_DROP_7D_PCT = -20.0      # 7 günde -%20 altı = dağıtım bölgesi, atla
TP_PCT          = 12.0
SL_PCT          = 4.0
TIMEOUT_H       = 72


# ── Yardımcı fonksiyonlar ────────────────────────────────────────────────────

def _klines_vol(client, symbol, interval, limit=25):
    """closes, highs, lows, quote_volumes (USDT cinsinden) döndür."""
    from binance.client import Client
    imap = {
        '1h': Client.KLINE_INTERVAL_1HOUR,
        '4h': Client.KLINE_INTERVAL_4HOUR,
        '1d': Client.KLINE_INTERVAL_1DAY,
    }
    kl = client.get_klines(symbol=symbol, interval=imap[interval], limit=limit)
    kl = kl[:-1]  # açık mumu çıkar
    closes = [float(k[4]) for k in kl]
    highs  = [float(k[2]) for k in kl]
    lows   = [float(k[3]) for k in kl]
    vols   = [float(k[7]) for k in kl]  # k[7] = quoteAssetVolume (USDT)
    return closes, highs, lows, vols


def _bb_width(closes, period=20):
    """Bollinger Bant Genişliği % = (upper − lower) / sma × 100."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    sma = sum(window) / period
    if sma <= 0:
        return None
    var = sum((c - sma) ** 2 for c in window) / period
    std = var ** 0.5
    return (4 * std / sma) * 100


def _accumulation_score(client, symbol):
    """
    Sessiz birikim skoru döndür (0–100). Coin uygun değilse None.

    Bileşenler:
      Hacim sıkışması  → 0–40 puan  (oran ne kadar düşükse o kadar yüksek)
      Fiyat bant darlığı → 0–30 puan  (7g yüksek-alçak yüzde aralığı)
      BB squeeze       → 0–30 puan  (BB genişliği tarihsel ne kadar altta)
    """
    try:
        closes, highs, lows, vols = _klines_vol(client, symbol, '1d', limit=23)
        if len(closes) < 15:
            return None

        # Hacim kontrolleri
        vol_21 = vols[-21:]
        avg21  = sum(vol_21) / len(vol_21)
        curr_v = vols[-1]
        if avg21 < MIN_VOL_21D_AVG or curr_v < MIN_VOL_CURR:
            return None
        vol_ratio = curr_v / avg21
        if vol_ratio > 0.65:
            return None   # hâlâ çok aktif, sıkışma yok

        # Fiyat bandı (7 gün)
        hi7 = max(highs[-7:])
        lo7 = min(lows[-7:])
        range_pct = (hi7 - lo7) / lo7 * 100 if lo7 > 0 else 99
        if range_pct > 10:
            return None

        # 7 günlük yön: keskin düşüş = dağıtım bölgesi, atla
        chg7 = (closes[-1] - closes[-7]) / closes[-7] * 100 if closes[-7] > 0 else 0
        if chg7 < MAX_DROP_7D_PCT:
            return None

        # BB genişliği tarihsel yüzdelik dilimi
        bb_curr = _bb_width(closes)
        bb_rank = 50.0  # varsayılan
        if bb_curr is not None and len(closes) >= 25:
            hist = []
            for i in range(22, len(closes)):
                w = _bb_width(closes[:i])
                if w is not None:
                    hist.append(w)
            if hist:
                # Kaçı bizden geniş? → bb_rank yüksekse çok sıkışmış
                bb_rank = sum(1 for w in hist if w > bb_curr) / len(hist) * 100

        # Skor
        vol_score   = max(0.0, (0.65 - vol_ratio) / 0.65 * 40)
        range_score = max(0.0, (10 - range_pct) / 10 * 30)
        bb_score    = bb_rank * 0.30
        score       = round(vol_score + range_score + bb_score, 1)

        if score < SCORE_MIN:
            return None

        return {
            'score':     score,
            'vol_ratio': round(vol_ratio, 3),
            'range_pct': round(range_pct, 1),
            'bb_rank':   round(bb_rank, 0),
            'chg7d':     round(chg7, 1),
        }
    except Exception as e:
        print(f'[Accum] Skor {symbol}: {e}')
        return None


def _entry_trigger(client, symbol):
    """
    Hacim dönüşü tetikleyicisi.
    Döner: (tetiklendi: bool, vol_return_ratio: float)

    Koşullar:
      - Saatlik vol mevcut saatte 24s ortalamanın 1.5–6× arasında
      - Fiyat henüz < +%2.5 saatlik artış (patlama değil, kıpırdama)
    """
    try:
        closes_h, _, _, vols_h = _klines_vol(client, symbol, '1h', limit=26)
        if len(vols_h) < 24:
            return False, 0
        avg24 = sum(vols_h[-24:]) / 24
        if avg24 <= 0:
            return False, 0
        ratio = vols_h[-1] / avg24
        chg1h = (closes_h[-1] - closes_h[-2]) / closes_h[-2] * 100 if closes_h[-2] > 0 else 0
        triggered = 1.5 <= ratio <= 6.0 and chg1h < 2.5
        return triggered, round(ratio, 2)
    except Exception:
        return False, 0


# ── Ajan sınıfı ─────────────────────────────────────────────────────────────

class AccumulationAgent:
    def __init__(self):
        self._running   = False
        self._lock      = threading.Lock()
        self.state      = self._load()
        self.candidates = {}   # symbol → score_dict

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {'scan_count': 0, 'total_pnl': 0.0,
                'wins': 0, 'total': 0, 'blacklist': {}}

    def _save(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def _bl(self, sym):
        return time.time() < self.state['blacklist'].get(sym, 0)

    def _add_bl(self, sym, h=24):
        self.state['blacklist'][sym] = time.time() + h * 3600

    # ── Başlat / Durdur ──────────────────────────────────────────────────────
    def start(self):
        if self._running:
            return False
        self._running = True
        for fn in [self._scan_loop, self._trigger_loop,
                   self._monitor_loop, self._report_loop]:
            threading.Thread(target=fn, daemon=True).start()
        cfg  = load_config()
        mode = '🧪 TESTNET' if cfg.get('testnet', True) else '🔴 GERÇEK'
        try:
            bal = get_usdt_balance(get_client())
        except Exception:
            bal = 0
        send_telegram(
            f'{mode} <b>Birikim Ajanı AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'🔍 Sessiz Birikim: Hacim Squeeze + BB Sıkışması\n'
            f'⚡ Tarama: {SCAN_INTERVAL//60}dk | Tetik: {TRIGGER_SEC}s\n'
            f'🎯 TP: +%{TP_PCT} | SL: -%{SL_PCT} | Timeout: {TIMEOUT_H}s\n'
            f'📦 Ajan slotu: {AGENT_MAX} pozisyon'
        )
        print('[Accum] Başladı')
        return True

    def stop(self):
        self._running = False
        self._save()
        send_telegram('⛔ <b>Birikim Ajanı durduruldu.</b>')

    # ── Aşama 1: Günlük tarama — birikim adayları ────────────────────────────
    def _scan_loop(self):
        time.sleep(90)   # diğer ajanlar başlasın
        while self._running:
            try:
                self._scan()
            except Exception as e:
                print(f'[Accum] Tarama hata: {e}')
            time.sleep(SCAN_INTERVAL)

    def _scan(self):
        client = get_client()
        cfg    = load_config()
        from manager_agent import ceo_flag
        if not ceo_flag(cfg, 'accumulation_enabled', True):
            return

        tickers = client.get_ticker()
        pool = [
            t for t in tickers
            if t['symbol'].endswith('USDT')
            and t['symbol'] not in STABLECOINS
            and MIN_VOL_CURR < float(t.get('quoteVolume', 0)) < MAX_VOL_CURR
            and float(t.get('lastPrice', 0)) > 0.001
        ]
        # Sessiz olanı bulmak istiyoruz → en az hacimliden tara (küçükten büyüğe)
        pool.sort(key=lambda x: float(x['quoteVolume']))
        symbols = [t['symbol'] for t in pool]

        print(f'[Accum] Tarama başladı: {len(symbols)} aday havuzu')
        found = {}
        for sym in symbols[:200]:
            if self._bl(sym):
                continue
            sc = _accumulation_score(client, sym)
            if sc:
                found[sym] = sc
                print(f'[Accum] ⭐ {sym} skor={sc["score"]} '
                      f'vol={sc["vol_ratio"]}x bant=%{sc["range_pct"]} '
                      f'bb={sc["bb_rank"]:.0f}.pct')
            time.sleep(0.08)   # rate limit koruması

        self.candidates = found
        self.state['scan_count'] = self.state.get('scan_count', 0) + 1
        self._save()
        print(f'[Accum] Tarama bitti: {len(found)} birikim adayı')

    # ── Aşama 2: Tetik — hacim kıpırdıyor mu? ────────────────────────────────
    def _trigger_loop(self):
        time.sleep(180)
        while self._running:
            try:
                self._check_triggers()
            except Exception as e:
                print(f'[Accum] Tetik hata: {e}')
            time.sleep(TRIGGER_SEC)

    def _check_triggers(self):
        if not self.candidates:
            return
        client = get_client()
        cfg    = load_config()
        from manager_agent import ceo_flag
        if not ceo_flag(cfg, 'accumulation_enabled', True):
            return

        from bot import is_trading_halted
        if is_trading_halted(client):
            print('[Accum] Global devre kesici aktif — yeni alım yok')
            return

        positions  = load_positions()
        open_all   = sum(1 for p in positions.values() if p.get('qty', 0) > 0)
        open_mine  = sum(1 for p in positions.values()
                         if p.get('qty', 0) > 0 and p.get('agent') == 'ACCUMULATION')
        held       = {s for s, p in positions.items() if p.get('qty', 0) > 0}

        if open_all >= GLOBAL_MAX or open_mine >= AGENT_MAX:
            return

        # En yüksek skorlu adaydan başla
        ranked = sorted(self.candidates.items(),
                        key=lambda x: x[1]['score'], reverse=True)

        for sym, sc in ranked:
            if sym in held or self._bl(sym):
                continue

            triggered, vol_ret = _entry_trigger(client, sym)
            if not triggered:
                continue

            equity   = get_total_equity(client)
            ceo_mult = cfg.get('ceo_position_mult', 1.0)
            # Skor 55-100 aralığını → 5.5-10 eşdeğerine çevir (position_size_by_score uyumlu)
            equiv_score = sc['score'] / 10
            usdt = position_size_by_score(equity, equiv_score, mult=ceo_mult)

            send_telegram(
                f'🔍 <b>BİRİKİM ALIM</b>\n'
                f'━━━━━━━━━━━━━━\n'
                f'🪙 <b>{sym}</b>\n'
                f'📊 Birikim skoru: {sc["score"]}/100\n'
                f'📉 Hacim sıkışması: {sc["vol_ratio"]}× (21g ort)\n'
                f'📏 7g fiyat bandı: %{sc["range_pct"]}\n'
                f'💥 BB sıkışması: %{sc["bb_rank"]:.0f}. dilim\n'
                f'🔔 Hacim dönüşü: {vol_ret}×\n'
                f'💰 Miktar: ${usdt:.2f}\n'
                f'🎯 TP: +%{TP_PCT} | SL: -%{SL_PCT}'
            )
            res = execute_buy(client, sym, usdt,
                              source='ACCUMULATION', period='ACCUM',
                              agent='ACCUMULATION')
            if res.get('ok'):
                update_position(sym,
                                agent='ACCUMULATION',
                                accum_score=sc['score'],
                                open_time=time.time(),
                                tp_pct=TP_PCT,
                                sl_pct=SL_PCT)
                self.candidates.pop(sym, None)
            break   # tek tetik turunda bir alım yeter

    # ── Pozisyon takibi ──────────────────────────────────────────────────────
    def _monitor_loop(self):
        while self._running:
            try:
                self._monitor()
            except Exception as e:
                print(f'[Accum] Monitor hata: {e}')
            time.sleep(MONITOR_SEC)

    def _monitor(self):
        client    = get_client()
        positions = load_positions()

        for sym, pos in list(positions.items()):
            if pos.get('qty', 0) <= 0 or pos.get('agent') != 'ACCUMULATION':
                continue
            try:
                price = get_price(client, sym)
                if price <= 0:        # ağ hatası → 0.0; sahte SL tetiklemesini önle
                    continue
                avg   = pos.get('avg_price', price)
                if avg <= 0:
                    continue
                pct = (price - avg) / avg * 100
                tp  = pos.get('tp_pct', TP_PCT)
                sl  = pos.get('sl_pct', SL_PCT)

                if pct >= tp:
                    res = execute_sell(client, sym, 100,
                                       source='ACCUMULATION TP', period='TP')
                    if res.get('ok'):
                        self._record(sym, pos, pct, True)
                    continue

                if pct <= -sl:
                    res = execute_sell(client, sym, 100,
                                       source='ACCUMULATION SL', period='SL')
                    if res.get('ok'):
                        self._add_bl(sym, 24)
                        self._record(sym, pos, pct, False)
                    continue

                # Başabaş koruması (+%2 görüldüyse zarar kapanmaz)
                if check_breakeven(sym, pos, pct):
                    res = execute_sell(client, sym, 100,
                                       source='ACCUMULATION BE', period='BE')
                    if res.get('ok'):
                        self._record(sym, pos, pct, pct > 0)
                    continue

                # Trailing stop: TP'nin %50'sine ulaşınca aktif, peak'ten -%3
                peak = pos.get('peak_price', avg)
                if price > peak:
                    update_position(sym, peak_price=price)
                    peak = price
                if pct >= tp * 0.5:
                    drawdown = (price - peak) / peak * 100 if peak > 0 else 0
                    if drawdown <= -3.0:
                        res = execute_sell(client, sym, 100,
                                           source='ACCUMULATION TRAIL', period='TRAIL')
                        if res.get('ok'):
                            self._record(sym, pos, pct, pct > 0)
                        continue

                # 72 saat timeout — sinyal gerçekleşmedi
                open_secs = time.time() - pos.get('open_time', time.time())
                if open_secs > TIMEOUT_H * 3600:
                    res = execute_sell(client, sym, 100,
                                       source='ACCUMULATION TIME', period='TIMEOUT')
                    if res.get('ok'):
                        self._record(sym, pos, pct, pct > 0)

            except Exception as e:
                print(f'[Accum] Monitor {sym}: {e}')

    def _record(self, sym, pos, pct, won):
        with self._lock:
            self.state['total'] = self.state.get('total', 0) + 1
            if won:
                self.state['wins'] = self.state.get('wins', 0) + 1
            dollar_pnl = round(pos.get('qty', 0) * pos.get('avg_price', 0) * pct / 100, 2)
            self.state['total_pnl'] = round(
                self.state.get('total_pnl', 0.0) + dollar_pnl, 2)
            self._save()

    # ── Saatlik rapor ────────────────────────────────────────────────────────
    def _report_loop(self):
        now = datetime.datetime.now()
        time.sleep(max(0, (60 - now.minute) * 60 - now.second))
        while self._running:
            try:
                self._report()
            except Exception as e:
                print(f'[Accum] Rapor hata: {e}')
            interval = int(load_config().get('report_interval_hours', 1))
            time.sleep(interval * 3600)

    def _report(self):
        positions = load_positions()
        open_pos  = {s: p for s, p in positions.items()
                     if p.get('qty', 0) > 0 and p.get('agent') == 'ACCUMULATION'}
        try:
            bal = get_usdt_balance(get_client())
        except Exception:
            bal = 0

        pos_lines = []
        for sym, pos in open_pos.items():
            try:
                price = get_price(get_client(), sym)
                avg   = pos.get('avg_price', price)
                pct   = (price - avg) / avg * 100 if avg > 0 else 0
                icon  = '🟢' if pct > 0 else '🔴'
                pos_lines.append(
                    f'{icon} {sym}: %{pct:+.2f} (skor:{pos.get("accum_score", "-")})')
            except Exception:
                pass

        t  = self.state.get('total', 0)
        w  = self.state.get('wins', 0)
        wr = round(w / t * 100, 1) if t > 0 else 0

        top5 = sorted(self.candidates.items(),
                      key=lambda x: x[1]['score'], reverse=True)[:5]
        cand_lines = [
            f'  • {s}: {v["score"]:.0f}p vol={v["vol_ratio"]}× bant=%{v["range_pct"]}'
            for s, v in top5
        ]

        msg = (
            f'🔍 <b>Birikim Ajanı Raporu</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📦 Açık: {len(open_pos)}/{AGENT_MAX} | '
            f'Tarama: {self.state.get("scan_count", 0)}×\n'
            f'💹 Toplam PnL: ${self.state.get("total_pnl", 0.0):.2f}\n'
            f'🏆 Kazanma: %{wr} ({w}/{t})\n'
        )
        if pos_lines:
            msg += '\n'.join(pos_lines) + '\n'
        if cand_lines:
            msg += '━━━━━━━━━━━━━━\n🎯 Güncel Adaylar:\n' + '\n'.join(cand_lines)
        send_telegram(msg)

    def status(self):
        positions = load_positions()
        open_pos  = sum(1 for p in positions.values()
                        if p.get('qty', 0) > 0 and p.get('agent') == 'ACCUMULATION')
        t = self.state.get('total', 0)
        w = self.state.get('wins', 0)
        return {
            'running':    self._running,
            'scan_count': self.state.get('scan_count', 0),
            'total_pnl':  self.state.get('total_pnl', 0.0),
            'wins':       w,
            'total':      t,
            'win_rate':   round(w / t * 100, 1) if t > 0 else 0,
            'open':       open_pos,
            'candidates': len(self.candidates),
            'blacklist':  {s: int(ts - time.time())
                           for s, ts in self.state.get('blacklist', {}).items()
                           if ts > time.time()},
        }


# ── Global API ────────────────────────────────────────────────────────────────

_agent      = None
_agent_lock = threading.Lock()


def start_accumulation_agent():
    global _agent
    with _agent_lock:
        if _agent and _agent._running:
            return False
        _agent = AccumulationAgent()
        return _agent.start()


def stop_accumulation_agent():
    global _agent
    with _agent_lock:
        if _agent:
            _agent.stop()


def accumulation_agent_status():
    global _agent
    if not _agent:
        return {'running': False}
    return _agent.status()
