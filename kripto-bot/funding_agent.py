"""
Funding Rate Agent — Delta-Nötr Funding Geliri
──────────────────────────────────────────────
Fiyat tahmin etmez. Long/short dengesizliğinden doğan
funding ödemelerini toplar.

Strateji:
  1. Her 30dk funding rate tara (BTC, ETH, SOL)
  2. Rate > %0.01 (8h) → delta-nötr aç:
       • Spot testnet  → AL  (fiyat düşünce kazanç kaybı karşılar)
       • Futures demo  → SHORT aç (funding ödemesi alır)
  3. Her 8 saatte bir funding ödenir → short taraf alır
  4. Rate negatif → kapat (ödeyici konuma geçmeden çık)

Testnet notu:
  Spot (testnet.binance.vision) ve futures (demo-fapi) ayrı hesaplar.
  Gerçek hedge değil — strateji simülasyonu. Gerçek hesapta
  aynı hesapta spot+futures olacağından tam delta-nötr çalışır.

Gelir tahmini:
  Rate %0.01 × 3 ödeme/gün = %0.03/gün
  $500 pozisyonla ≈ $0.15/gün, $9800 tam dolu ≈ $3/gün
  Düşük ama risksiz ve birikimli.
"""

import time, datetime, threading, json, os, math
from binance.client import Client as BC
from bot import (load_config, get_client, execute_buy, execute_sell,
                 send_telegram, get_usdt_balance, get_price)

STATE_FILE       = 'funding_state.json'
FUTURES_BASE_URL = 'https://testnet.binancefuture.com'

SCAN_INTERVAL   = 1800   # 30 dakika — funding 8 saatte bir, 30dk yeterli
MONITOR_INTERVAL = 300   # 5 dakika — rate takibi
MIN_RATE        = 0.0001  # %0.01 per 8h minimum eşik
MAX_POSITIONS   = 2       # aynı anda max delta-nötr pozisyon
DEFAULT_ALLOC   = 500.0   # her pozisyon varsayılan USDT

COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

# Funding ödemeleri 00:00, 08:00, 16:00 UTC
FUNDING_HOURS = {0, 8, 16}

_stop   = threading.Event()
_thread = None


# ─── İstemci ──────────────────────────────────────────────────────────────────

def _futures_client():
    cfg    = load_config()
    key    = cfg.get('funding_futures_key', '')
    secret = cfg.get('funding_futures_secret', '')
    c = BC(key, secret)
    c.FUTURES_URL = FUTURES_BASE_URL
    return c


# ─── Durum Dosyası ────────────────────────────────────────────────────────────

def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            'positions':     {},
            'total_funding': 0.0,
            'scan_count':    0,
            'closed_log':    [],
        }


def _save_state(s):
    with open(STATE_FILE, 'w') as f:
        json.dump(s, f, indent=2)


# ─── Funding Rate ─────────────────────────────────────────────────────────────

def _get_funding_rate(fc, symbol):
    """Güncel funding rate — ondalık (0.0001 = %0.01 per 8h)."""
    try:
        data = fc.futures_funding_rate(symbol=symbol, limit=1)
        if data:
            return float(data[-1]['fundingRate'])
    except Exception:
        pass
    return 0.0


def _next_funding_mins():
    """Bir sonraki funding ödemesine kaç dakika kaldı."""
    now_utc = datetime.datetime.utcnow()
    for h in sorted(FUNDING_HOURS):
        t = now_utc.replace(hour=h, minute=0, second=0, microsecond=0)
        if t > now_utc:
            return int((t - now_utc).total_seconds() / 60)
    tomorrow = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    return int((tomorrow - now_utc).total_seconds() / 60)


# ─── Miktar Hassasiyeti ───────────────────────────────────────────────────────

def _qty_precision(fc, symbol):
    try:
        info = fc.futures_exchange_info()
        for s in info['symbols']:
            if s['symbol'] == symbol:
                return s['quantityPrecision']
    except Exception:
        pass
    return 3


def _floor_qty(qty, precision):
    factor = 10 ** precision
    return math.floor(qty * factor) / factor


# ─── Pozisyon Aç ─────────────────────────────────────────────────────────────

def _open_position(symbol, state):
    cfg   = load_config()
    alloc = float(cfg.get('funding_allocation_usdt', DEFAULT_ALLOC))

    spot_client = get_client()
    fc          = _futures_client()

    price = get_price(spot_client, symbol)
    if not price or price <= 0:
        return False, 'Fiyat alınamadı'

    precision    = _qty_precision(fc, symbol)
    target_qty   = _floor_qty(alloc / price, precision)
    if target_qty <= 0:
        return False, 'Miktar sıfır — alloc çok küçük'

    # 1. Spot al
    spot_result = execute_buy(spot_client, symbol, alloc, source='FUNDING-SPOT')
    if not spot_result.get('ok'):
        return False, f'Spot alım hatası: {spot_result.get("error", "?")}'
    spot_qty = float(spot_result.get('qty', target_qty))

    # 2. Futures short aç
    futures_qty = _floor_qty(spot_qty, precision)
    try:
        fc.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=futures_qty,
        )
    except Exception as e:
        # Spot alındı, futures açılamadı → spot'u geri sat
        execute_sell(spot_client, symbol, 100, source='FUNDING-ROLLBACK')
        return False, f'Futures short hatası: {e}'

    rate      = _get_funding_rate(fc, symbol)
    daily_est = alloc * rate * 3

    state['positions'][symbol] = {
        'spot_qty':          spot_qty,
        'futures_qty':       futures_qty,
        'entry_price':       price,
        'usdt_size':         alloc,
        'opened_at':         datetime.datetime.utcnow().isoformat(),
        'funding_collected': 0.0,
        'payments_received': 0,
        'last_rate':         rate,
    }
    _save_state(state)

    mins = _next_funding_mins()
    send_telegram(
        f'💰 <b>FUNDING POZİSYON AÇILDI</b>\n'
        f'📊 {symbol}\n'
        f'💵 Boyut: ${alloc:.0f}\n'
        f'📈 Funding rate: {rate*100:.4f}% (8h)\n'
        f'🎯 Günlük tahmini: ${daily_est:.3f}\n'
        f'⏰ Sonraki ödeme: {mins} dk sonra\n'
        f'ℹ️ Spot LONG + Futures SHORT = Delta-Nötr'
    )
    return True, 'Açıldı'


# ─── Pozisyon Kapat ───────────────────────────────────────────────────────────

def _close_position(symbol, state, reason='Manuel'):
    fc  = _futures_client()
    pos = state['positions'].get(symbol)
    if not pos:
        return

    spot_client = get_client()

    # 1. Spot sat
    execute_sell(spot_client, symbol, 100, source='FUNDING-KAPAT')

    # 2. Futures short kapat
    try:
        fc.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='MARKET',
            quantity=pos['futures_qty'],
            reduceOnly=True,
        )
    except Exception as e:
        send_telegram(f'⚠️ Futures kapatma hatası ({symbol}): {e}')

    collected = pos.get('funding_collected', 0.0)
    payments  = pos.get('payments_received', 0)

    # Kapalı log'a ekle
    state.setdefault('closed_log', []).append({
        'symbol':    symbol,
        'closed_at': datetime.datetime.utcnow().isoformat(),
        'reason':    reason,
        'collected': collected,
        'payments':  payments,
    })
    state['total_funding'] = round(state.get('total_funding', 0) + collected, 6)
    del state['positions'][symbol]
    _save_state(state)

    send_telegram(
        f'🔒 <b>FUNDING POZİSYON KAPATILDI</b>\n'
        f'📊 {symbol} | {reason}\n'
        f'💰 Bu pozisyondan toplanan: ${collected:.4f}\n'
        f'📊 Ödeme sayısı: {payments}\n'
        f'🏦 Toplam funding: ${state["total_funding"]:.4f}'
    )


# ─── Funding Tahmini Güncelle ─────────────────────────────────────────────────

def _update_funding_estimates(state):
    """
    Her 8 saatte bir ödeme gerçekleşir. Son güncellemeden bu yana
    kaç ödeme dönemi geçtiğini sayarak tahmini günceller.
    """
    fc = _futures_client()
    now = datetime.datetime.utcnow()

    for symbol, pos in state['positions'].items():
        try:
            opened = datetime.datetime.fromisoformat(pos['opened_at'])
            elapsed_h = (now - opened).total_seconds() / 3600

            # Kaç 8h dönemi geçti
            periods = int(elapsed_h / 8)
            already = pos.get('payments_received', 0)
            new_periods = periods - already

            if new_periods > 0:
                rate = _get_funding_rate(fc, symbol)
                if rate <= 0:
                    rate = pos.get('last_rate', 0)
                earned = pos['usdt_size'] * rate * new_periods
                pos['funding_collected'] = round(
                    pos.get('funding_collected', 0) + earned, 6
                )
                pos['payments_received'] = periods
                pos['last_rate'] = rate

        except Exception:
            pass

    _save_state(state)


# ─── Ana Döngüler ─────────────────────────────────────────────────────────────

def _scan_loop():
    """30 dakikada bir yeni yüksek-funding fırsatı ara."""
    fc = _futures_client()
    while not _stop.is_set():
        state      = _load_state()
        open_syms  = set(state['positions'].keys())
        open_count = len(open_syms)

        for symbol in COINS:
            if _stop.is_set():
                break
            if symbol in open_syms or open_count >= MAX_POSITIONS:
                continue
            rate = _get_funding_rate(fc, symbol)
            if rate >= MIN_RATE:
                ok, msg = _open_position(symbol, state)
                if ok:
                    open_count += 1
                    state = _load_state()

        _stop.wait(SCAN_INTERVAL)


def _monitor_loop():
    """5 dakikada bir açık pozisyonları izle, rate negatife dönünce kapat."""
    fc = _futures_client()
    while not _stop.is_set():
        state = _load_state()

        _update_funding_estimates(state)

        for symbol in list(state['positions'].keys()):
            rate = _get_funding_rate(fc, symbol)
            if rate < 0:
                _close_position(
                    symbol, state,
                    reason=f'Rate negatife döndü ({rate*100:.4f}%)'
                )
                state = _load_state()

        _stop.wait(MONITOR_INTERVAL)


# ─── Günlük Rapor ─────────────────────────────────────────────────────────────

def _daily_report():
    """Her gün 08:00 UTC'de günlük funding özeti gönder."""
    while not _stop.is_set():
        now    = datetime.datetime.utcnow()
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= target:
            target += datetime.timedelta(days=1)
        secs = (target - now).total_seconds()
        _stop.wait(secs)
        if _stop.is_set():
            break

        state    = _load_state()
        total    = state.get('total_funding', 0)
        open_pos = state.get('positions', {})

        lines = [f'📊 <b>Funding Agent — Günlük Rapor</b>']
        lines.append(f'🏦 Toplam kazanılan: ${total:.4f}')
        if open_pos:
            lines.append(f'\n<b>Açık pozisyonlar:</b>')
            for sym, pos in open_pos.items():
                lines.append(
                    f'  • {sym}: ${pos.get("funding_collected",0):.4f} '
                    f'({pos.get("payments_received",0)} ödeme)'
                )
        else:
            lines.append('📭 Açık pozisyon yok')

        send_telegram('\n'.join(lines))


# ─── Public API ───────────────────────────────────────────────────────────────

def start_funding_agent():
    global _thread, _stop
    cfg = load_config()
    if not cfg.get('funding_agent_enabled', False):
        return False
    if not cfg.get('funding_futures_key', ''):
        send_telegram('⚠️ Funding Agent: futures API key eksik (funding_futures_key)')
        return False
    if _thread and _thread.is_alive():
        return False

    _stop.clear()
    t_scan    = threading.Thread(target=_scan_loop,    daemon=True, name='funding-scan')
    t_monitor = threading.Thread(target=_monitor_loop, daemon=True, name='funding-monitor')
    t_report  = threading.Thread(target=_daily_report, daemon=True, name='funding-report')
    t_scan.start()
    t_monitor.start()
    t_report.start()
    _thread = t_scan

    send_telegram(
        '💹 <b>Funding Rate Agent başlatıldı</b>\n'
        f'🎯 Min rate: {MIN_RATE*100:.3f}% | Max pozisyon: {MAX_POSITIONS}\n'
        f'⏰ Tarama: 30dk | İzleme: 5dk'
    )
    return True


def stop_funding_agent():
    _stop.set()
    state = _load_state()
    send_telegram(
        f'⏹ Funding Agent durduruldu\n'
        f'🏦 Toplam kazanılan: ${state.get("total_funding", 0):.4f}'
    )


def funding_agent_status():
    state   = _load_state()
    running = not _stop.is_set() and bool(_thread)
    cfg     = load_config()

    positions_summary = {}
    for sym, pos in state.get('positions', {}).items():
        positions_summary[sym] = {
            'usdt_size':   pos.get('usdt_size', 0),
            'collected':   round(pos.get('funding_collected', 0), 6),
            'payments':    pos.get('payments_received', 0),
            'last_rate':   round(pos.get('last_rate', 0) * 100, 4),
            'opened_at':   pos.get('opened_at', ''),
        }

    return {
        'running':         running,
        'enabled':         cfg.get('funding_agent_enabled', False),
        'positions':       positions_summary,
        'open_count':      len(positions_summary),
        'total_funding':   round(state.get('total_funding', 0), 6),
        'scan_count':      state.get('scan_count', 0),
        'closed_log':      state.get('closed_log', [])[-5:],
    }
