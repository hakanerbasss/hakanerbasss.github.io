"""
Breakout Agent — Momentum Kırılım Tespiti
──────────────────────────────────────────
Diğer ajanlar hacme göre sıralar → HEIUSDT +141%, ALLOUSDT +113% kaçırılır.

Bu ajan tam tersini yapar:
  1. Tüm USDT spot çiftlerini tara (hacim sıralaması yok)
  2. Son 2 saatte fiyat %4+ hareket edenleri bul
  3. Hacim spike > 2x olmalı (sahte hareket filtresi)
  4. SATIN AL

Çıkış — Sabit TP KESİNLİKLE YOK, KADEMELİ TRAIL:
  • Hard stop:  -%5   (yanlış kırılım koruması)
  • Trail +%3'te aktif, peak kârına göre daralan mesafe:
      +3-10%  → peak'ten -%3  (küçük kârı hemen kilitle)
      +10-25% → peak'ten -%8  (orta)
      +25%+   → peak'ten -%15 (büyük trendi sür)
  • Sonuç: %6 pump'ta +%3 kâr kilitlenir, %141 hareket → %120+ yakalanır
"""

import time, datetime, threading, json, os
from collections import deque
from binance.client import Client as BC
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, load_trades, get_price,
                 send_telegram, get_usdt_balance, get_total_equity,
                 position_size_by_score, update_position, check_breakeven)

STATE_FILE = 'breakout_state.json'

STABLECOINS = {
    'USDCUSDT','BUSDUSDT','TUSDUSDT','USDTUSDT','FDUSDUSDT',
    'EURUSDT','GBPUSDT','DAIUSDT','FRAXUSDT','USDPUSDT','PYUSDUSDT',
    'UUSDT','USDEUSDT','SUSDEUSDT','CRVUSDUSDT','GHOUSDT','USDTBUSDT',
    'AEURUSDT','EURSUSDT','IDRTUSDT','BIDRUSDT','BRLAUSDT','USDSBUSDT',
}

SCAN_INTERVAL    = 180      # saniye (3 dakika) — pump genellikle 10-30dk sürer, 3dk'da içerideyiz
MONITOR_SEC      = 5        # saniye
MIN_VOL_24H      = 500_000  # $500K min 24h hacim — düşük likidite → slippage hard stop'u aşıyor
MAX_BREAKOUT_POS = 3        # aynı anda max breakout pozisyonu
MIN_COIN_PRICE   = 0.01     # $0.01 altı coinler: step size granülaritesi %10+ → stop güvenilmez

# Kırılım kriterleri
MIN_PRICE_CHG_2H = 5.0   # 4→5%: güçlü kırılım filtresi, zayıf sinyalleri eler
MIN_VOL_SPIKE    = 3.0   # minimum 3x hacim spike
MAX_CHG_24H      = 20.0  # 35→20%: daha önce pompanmış coinlere geç girişi önle
MIN_SCORE        = 5.5   # minimum skor eşiği — düşük skorda işlem açma

# Re-entry — config'deki reentry_cooldown_hours sıfırlanmış olsa bile
# aynı coinden çıkıp 1 saat geçmeden tekrar girme (25sn re-entry bug'ını kapatır)
MIN_REENTRY_HOURS = 1.0

# Çıkış parametreleri — SABİT TP YOK, KADEMELİ TRAIL
# Kâr arttıkça trail daralır → küçük kârı kilitle, büyük pump'a yer aç
TRAIL_ACTIVATE_PCT = 3.0   # bu kadar kazanç → trailing başlasın
HARD_STOP_PCT      = 5.0   # bu kadar zarar → anında çık

# Piyasa durumu eşiği — Aşırı Korku ortamında breakout stratejisi başarısız olur
FG_MIN           = 35     # Fear & Greed bu değerin altındaysa yeni alım yok

def _trail_distance(peak_pct):
    """Peak kâr yüzdesine göre trail mesafesi (peak'ten % düşüş).
    Küçük pump'larda dar (kârı kilitle), büyük pump'larda geniş (moon'a izin ver)."""
    if peak_pct >= 25:   return 15.0   # +25%+ : geniş trail, büyük trendi sür
    if peak_pct >= 10:   return 8.0    # +10-25% : orta
    return 3.0                          # +3-10% : dar, küçük kârı hemen kilitle


# ─── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {'scan_count': 0, 'running': False}


def _save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def _klines_with_vol(client, symbol, limit=26):
    """1h kline: close + quoteVolume (USDT bazlı). Son açık mumu çıkarır."""
    kl = client.get_klines(
        symbol=symbol,
        interval=BC.KLINE_INTERVAL_1HOUR,
        limit=limit + 1
    )
    kl = kl[:-1]  # son açık mumu çıkar
    closes = [float(k[4]) for k in kl]
    vols   = [float(k[7]) for k in kl]  # quoteAssetVolume (USDT)
    return closes, vols


def _btc_ok(client):
    """BTC son 2 saatte flat veya yukarı olmalı (≥-1%). Daha sert düşüşte breakout = sahte."""
    try:
        kl = client.get_klines(symbol='BTCUSDT', interval=BC.KLINE_INTERVAL_1HOUR, limit=4)
        kl = kl[:-1]
        closes = [float(k[4]) for k in kl]
        return closes[-1] >= closes[-3] * 0.99
    except Exception:
        return True


def _fear_greed_ok():
    """Fear & Greed Index ≥ FG_MIN ise True. Aşırı korkuda breakout = sahte breakout."""
    try:
        import urllib.request
        url = 'https://api.alternative.me/fng/?limit=1'
        with urllib.request.urlopen(url, timeout=4) as r:
            data = json.loads(r.read())
            val = int(data['data'][0]['value'])
            if val < FG_MIN:
                print(f'[Breakout] Fear & Greed={val} < {FG_MIN} — aşırı korku, tarama atlandı')
                return False
        return True
    except Exception:
        return True  # API erişilemezse engelleme


def _detect_breakouts(client):
    """
    2 aşamalı tarama:
    Aşama 1 — Ticker: 24h değişim > MIN_PRICE_CHG_2H olan top-50 aday
    Aşama 2 — Kline:  son 2 saatin hareketi ve hacim spike kontrolü
    """
    try:
        tickers = client.get_ticker()
    except Exception as e:
        print(f'[Breakout] Ticker hatası: {e}')
        return []

    # Aşama 1: Hızlı ön filtre
    candidates = []
    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym in STABLECOINS:
            continue
        try:
            price = float(t.get('lastPrice', 0))
            vol24 = float(t.get('quoteVolume', 0))
            chg24 = float(t.get('priceChangePercent', 0))
        except (ValueError, TypeError):
            continue
        if 0.85 <= price <= 1.15:   # stablecoin fiyat aralığı
            continue
        if vol24 < MIN_VOL_24H:     # çok illiquid
            continue
        if price < MIN_COIN_PRICE:  # çok düşük fiyat → step size stop'u bozar
            continue
        if chg24 < MIN_PRICE_CHG_2H:
            continue
        if chg24 > MAX_CHG_24H:     # zaten aşırı pompalanmış → tepeden alma
            continue
        candidates.append({'symbol': sym, 'price': price, 'chg24': chg24, 'vol24': vol24})

    # En çok yükselenden başlayarak ilk 50 aday
    candidates.sort(key=lambda x: x['chg24'], reverse=True)
    candidates = candidates[:50]

    # Aşama 2: Kline ile son 2 saatlik hacim spike kontrolü
    results = []
    for c in candidates:
        sym = c['symbol']
        try:
            closes, vols = _klines_with_vol(client, sym, limit=24)
            if len(closes) < 6 or len(vols) < 6:
                continue

            # Son 2 saatin ortalama saatlik hacmi
            recent_avg_vol = (vols[-1] + vols[-2]) / 2
            # Önceki 20 saatin ortalama saatlik hacmi
            baseline_vol   = sum(vols[:-2]) / max(len(vols[:-2]), 1)

            if baseline_vol <= 0:
                continue

            vol_spike = recent_avg_vol / baseline_vol

            # Son 2 saatin fiyat hareketi (kapanış bazlı)
            price_2h_ago = closes[-3]
            price_now    = closes[-1]
            pct_2h       = (price_now - price_2h_ago) / price_2h_ago * 100

            if pct_2h < MIN_PRICE_CHG_2H:
                continue
            if vol_spike < MIN_VOL_SPIKE:
                continue

            # Skor: kırılım gücü (0-10)
            # pct_2h=4% vol=2x → skor~5  |  pct_2h=10% vol=5x → skor~9
            price_component = min(5.0, pct_2h / 4.0 * 2.0)
            vol_component   = min(5.0, (vol_spike - 1.0) / 3.0 * 5.0)
            score           = round(price_component + vol_component, 2)

            results.append({
                'symbol':    sym,
                'price':     c['price'],
                'pct_2h':    round(pct_2h, 2),
                'vol_spike': round(vol_spike, 2),
                'vol24':     c['vol24'],
                'score':     score,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x['score'], reverse=True)
    return results


# ─── Agent Sınıfı ─────────────────────────────────────────────────────────────

class BreakoutAgent:
    def __init__(self):
        self.state       = _load_state()
        self._running    = False
        self._stop_event = threading.Event()
        self.scan_log    = deque(maxlen=30)

    def start(self):
        if self._running:
            return False
        self._running = True
        self._stop_event.clear()
        self.state['running'] = True
        # Günlük başlangıç bakiyesini kaydet
        try:
            self.state['day_start_bal'] = get_usdt_balance(get_client())
        except Exception:
            pass
        _save_state(self.state)
        threading.Thread(target=self._scan_loop,    daemon=True).start()
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        threading.Thread(target=self._report_loop,  daemon=True).start()
        print('[Breakout] Agent başladı')
        cfg  = load_config()
        mode = '🧪 TESTNET' if cfg.get('testnet', True) else '🔴 GERÇEK'
        bal  = self.state.get('day_start_bal', 0)
        send_telegram(
            f'{mode} <b>Breakout Agent AKTİF</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📡 Yöntem: Hacim spike + fiyat kırılımı (2s)\n'
            f'⚡ Tarama: {SCAN_INTERVAL//60}dk | Takip: {MONITOR_SEC}s\n'
            f'🎯 Min Hareket: +%{MIN_PRICE_CHG_2H} | Vol Spike: {MIN_VOL_SPIKE}x\n'
            f'📊 Min Skor: {MIN_SCORE}/10 | Min Hacim: ${MIN_VOL_24H/1_000:.0f}K\n'
            f'🔒 Kademeli Trail: +3-10%→-3% | +10-25%→-8% | +25%+→-15%\n'
            f'🛑 Hard Stop: -%{HARD_STOP_PCT}\n'
            f'⏰ Alım saatleri: 20:00–13:00 TR (13-20 arası kapalı)\n'
            f'⚠️ Sabit TP YOK — kâr arttıkça trail genişler'
        )
        return True

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.state['running'] = False
        _save_state(self.state)
        print('[Breakout] Agent durduruldu')

    # ── Tarama Döngüsü ────────────────────────────────────────────────────────

    def _scan_loop(self):
        while not self._stop_event.is_set():
            try:
                self._scan()
            except Exception as e:
                print(f'[Breakout] Tarama hatası: {e}')
            self._stop_event.wait(SCAN_INTERVAL)

    def _scan(self):
        from manager_agent import ceo_flag
        cfg = load_config()
        if not ceo_flag(cfg, 'breakout_enabled', True):
            print('[Breakout] Kapalı (breakout_enabled=false)')
            return
        if cfg.get('bot_paused'):
            return

        client    = get_client()
        from bot import is_trading_halted
        if is_trading_halted(client):
            print('[Breakout] Global devre kesici aktif — yeni alım yok')
            return
        positions = load_positions()

        breakout_open = [
            s for s, p in positions.items()
            if p.get('agent') == 'BREAKOUT' and p.get('qty', 0) > 0
        ]
        if len(breakout_open) >= MAX_BREAKOUT_POS:
            print(f'[Breakout] Maks pozisyon ({MAX_BREAKOUT_POS}) doldu')
            return

        if not _btc_ok(client):
            print('[Breakout] BTC düşüşte — tarama atlandı')
            return

        if not _fear_greed_ok():
            return

        # Günlük zarar limiti: -%8
        try:
            bal       = get_usdt_balance(client)
            start_bal = self.state.get('day_start_bal', bal) or bal
            if start_bal > 0 and (bal - start_bal) / start_bal * 100 < -8.0:
                print('[Breakout] Günlük zarar limiti aşıldı, tarama durduruldu')
                return
        except Exception:
            pass

        candidates = _detect_breakouts(client)
        scan_no    = self.state.get('scan_count', 0) + 1
        self.state['scan_count'] = scan_no
        print(f'[Breakout] Tarama #{scan_no}: {len(candidates)} kırılım adayı')

        max_total = cfg.get('max_positions', 6)
        already_open = set(positions.keys())

        for r in candidates:
            sym = r['symbol']
            if sym in already_open:
                continue
            total_open = sum(1 for p in positions.values() if p.get('qty', 0) > 0)
            if total_open >= max_total or len(breakout_open) >= MAX_BREAKOUT_POS:
                break

            # Skor filtresi — zayıf sinyalde işlem açma
            if r['score'] < MIN_SCORE:
                print(f'[Breakout] {sym} skor yetersiz: {r["score"]:.1f} < {MIN_SCORE}')
                continue

            # Hard-coded min re-entry: config reentry_cooldown_hours=0 olsa bile
            # aynı coinden çıkıp MIN_REENTRY_HOURS geçmeden yeniden alma
            from bot import _check_reentry
            if not _check_reentry(sym, MIN_REENTRY_HOURS):
                print(f'[Breakout] {sym} min {MIN_REENTRY_HOURS}s re-entry koruması aktif')
                continue

            log = (f"{sym} +{r['pct_2h']}% "
                   f"vol={r['vol_spike']}x "
                   f"score={r['score']}")
            self.scan_log.appendleft(log)
            print(f'[Breakout] ✅ {log}')
            self._do_buy(client, sym, r, cfg)
            breakout_open.append(sym)
            already_open.add(sym)
            positions = load_positions()

        _save_state(self.state)

    def _do_buy(self, client, symbol, result, cfg):
        equity   = get_total_equity(client)
        ceo_mult = cfg.get('ceo_position_mult', 1.0)
        usdt     = position_size_by_score(equity, result['score'], mult=ceo_mult)

        res = execute_buy(client, symbol, usdt, source='BREAKOUT', period='1h', agent='BREAKOUT')
        if not res.get('ok'):
            print(f'[Breakout] Alım başarısız: {symbol} — {res.get("error")}')
            return

        # Pozisyona trailing meta verisi ekle (tek sembol, kilit altında)
        pos_now = load_positions().get(symbol, {})
        update_position(symbol,
                        agent='BREAKOUT',
                        peak_price=pos_now.get('avg_price', result['price']),
                        trail_active=False)

        send_telegram(
            f'🚀 <b>BREAKOUT ALIM</b>\n'
            f'💎 {symbol}\n'
            f'📈 Son 2s hareket: +{result["pct_2h"]}%\n'
            f'📊 Hacim spike: {result["vol_spike"]}x\n'
            f'🎯 Skor: {result["score"]}/10\n'
            f'💵 Tutar: ${usdt}\n'
            f'🔒 Kademeli Trail | Hard Stop -%{HARD_STOP_PCT}\n'
            f'⚠️ Sabit TP YOK — kâr arttıkça trail genişler\n'
            f'⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'
        )

    # ── İzleme Döngüsü (Trailing Stop) ───────────────────────────────────────

    def _monitor_loop(self):
        while not self._stop_event.is_set():
            try:
                self._monitor()
            except Exception as e:
                print(f'[Breakout] Monitor hatası: {e}')
            self._stop_event.wait(MONITOR_SEC)

    def _monitor(self):
        client    = get_client()
        positions = load_positions()

        for sym, pos in list(positions.items()):
            if pos.get('agent') != 'BREAKOUT':
                continue
            qty = pos.get('qty', 0)
            if qty <= 0:
                continue

            try:
                price = get_price(client, sym)
            except Exception:
                continue
            if price <= 0:            # ağ hatası → 0.0; sahte hard-stop tetiklemesini önle
                continue

            entry       = pos.get('avg_price', price)
            if entry <= 0:
                continue

            peak         = pos.get('peak_price', entry)
            trail_active = pos.get('trail_active', False)
            pnl_pct      = (price - entry) / entry * 100
            meta_update  = {}

            # Peak güncelle (yalnız bu sembol, kilit altında — lost-update yok)
            if price > peak:
                peak = price
                meta_update['peak_price'] = peak

            # Trailing stop'u aktif et
            if not trail_active and pnl_pct >= TRAIL_ACTIVATE_PCT:
                trail_active = True
                meta_update['trail_active'] = True
                peak_pct = round((peak - entry) / entry * 100, 1)
                print(f'[Breakout] {sym} trailing aktif '
                      f'(pnl={pnl_pct:.1f}% peak=+{peak_pct}%)')

            if meta_update:
                update_position(sym, **meta_update)

            reason = None
            peak_pct = (peak - entry) / entry * 100

            # 1. Hard stop: -%5
            if pnl_pct <= -HARD_STOP_PCT:
                reason = f'HARD STOP ({pnl_pct:.1f}%)'

            # 2. Kademeli trailing stop: peak kârına göre daralan mesafe
            elif trail_active:
                trail_dist  = _trail_distance(peak_pct)
                trail_price = peak * (1 - trail_dist / 100)
                if price <= trail_price:
                    reason = (f'TRAIL STOP -{trail_dist:.0f}% | peak=+{peak_pct:.1f}% '
                              f'pnl=+{pnl_pct:.1f}%')

            # 3. Başabaş koruması: +%2 görüldüyse net zarara dönmesin
            #    (trailing daha yüksekte yakalamadıysa devreye girer)
            if not reason and check_breakeven(sym, pos, pnl_pct):
                reason = f'BAŞABAŞ +{pnl_pct:.1f}%'

            if reason:
                print(f'[Breakout] {sym} ÇIKIŞ: {reason}')
                # Kaynak etiketi raporlama içindir; cooldown gerçekleşen PnL'e bakar.
                if 'HARD STOP' in reason:
                    sell_source = 'BREAKOUT HARD_STOP'
                elif 'BAŞABAŞ' in reason:
                    sell_source = 'BREAKOUT BE'
                else:
                    sell_source = 'BREAKOUT TRAIL_STOP'
                res = execute_sell(client, sym, 100,
                                   source=sell_source, period='trail')
                if res.get('ok'):
                    pnl = res.get('pnl', 0)
                    peak_pct = round((peak - entry) / entry * 100, 1)
                    send_telegram(
                        f'🏁 <b>BREAKOUT ÇIKIŞ</b>\n'
                        f'💎 {sym}\n'
                        f'💰 K/Z: {"+" if pnl >= 0 else ""}{round(pnl, 2)}$\n'
                        f'📈 Peak: +{peak_pct}% → Çıkış: {pnl_pct:.1f}%\n'
                        f'🔒 Sebep: {reason.split("|")[0].strip()}\n'
                        f'⏰ {datetime.datetime.now().strftime("%H:%M:%S")}'
                    )

    # ── Rapor Döngüsü ────────────────────────────────────────────────────────

    def _report_loop(self):
        """Periyodik durum raporu — her saat (report_interval_hours ayarına uyar)."""
        import datetime as _dt
        now = _dt.datetime.now()
        self._stop_event.wait(max(0, (60 - now.minute) * 60 - now.second))
        while not self._stop_event.is_set():
            try:
                self._send_report()
            except Exception as e:
                print(f'[Breakout] Rapor hatası: {e}')
            interval = int(load_config().get('report_interval_hours', 1))
            self._stop_event.wait(interval * 3600)

    def _send_report(self):
        cfg = load_config()
        if not cfg.get('breakout_enabled', True):
            return
        positions = load_positions()
        client    = get_client()

        open_pos = [
            (s, p) for s, p in positions.items()
            if p.get('agent') == 'BREAKOUT' and p.get('qty', 0) > 0
        ]

        try:
            bal = get_usdt_balance(client)
        except Exception:
            bal = 0

        lines = [
            f'🚀 <b>Breakout Agent Raporu</b>\n'
            f'━━━━━━━━━━━━━━\n'
            f'💰 Bakiye: ${bal:.2f}\n'
            f'📦 Açık: {len(open_pos)}/{MAX_BREAKOUT_POS} | 🔍 Tarama: {self.state.get("scan_count",0)}x'
        ]

        total_pnl = 0.0
        for sym, pos in open_pos:
            try:
                price    = get_price(client, sym)
                entry    = pos.get('avg_price', price)
                peak     = pos.get('peak_price', entry)
                pnl_pct  = (price - entry) / entry * 100
                peak_pct = (peak - entry) / entry * 100
                trail_ok = '🔒' if pos.get('trail_active') else '⏳'
                icon     = '🟢' if pnl_pct >= 0 else '🔴'
                lines.append(
                    f'{icon} {trail_ok} {sym}: %{pnl_pct:+.2f} '
                    f'(peak +{round(peak_pct,1)}%)'
                )
                total_pnl += (price - entry) * pos.get('qty', 0)
            except Exception:
                pass

        if not open_pos:
            lines.append('📭 Açık pozisyon yok — kırılım bekleniyor')

        lines.append(f'━━━━━━━━━━━━━━\n💹 Toplam PnL: ${total_pnl:+.2f}')
        send_telegram('\n'.join(lines))


# ─── Singleton & Public API ───────────────────────────────────────────────────

_agent: BreakoutAgent = None


def start_breakout_agent():
    global _agent
    if _agent is None:
        _agent = BreakoutAgent()
    return _agent.start()


def stop_breakout_agent():
    global _agent
    if _agent:
        _agent.stop()


def breakout_agent_status():
    global _agent
    if _agent is None:
        s = _load_state()
        return {'running': False, 'scan_count': s.get('scan_count', 0), 'log': []}
    return {
        'running':    _agent._running,
        'scan_count': _agent.state.get('scan_count', 0),
        'log':        list(_agent.scan_log),
    }


def trigger_breakout_report():
    global _agent
    if _agent:
        try:
            _agent._send_report()
        except Exception as e:
            print(f'[Breakout] Manuel rapor hatası: {e}')
