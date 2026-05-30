import json, os, time, datetime, threading, urllib.request, urllib.parse
from binance.client import Client

FEE_RATE = 0.001  # Binance spot %0.1 alım + %0.1 satım = %0.2 toplam

# Tüm ajanlar bu kilidi kullanır — çakışan alım emirlerini VE positions.json
# eşzamanlı yazımını (lost-update) önler. RLock: aynı thread içinde
# execute_buy/sell zaten kilidi tutarken yardımcıları çağırabilsin.
_TRADE_LOCK = threading.RLock()

CONFIG_FILE = 'config.json'
TRADES_FILE = 'trades.json'
POSITIONS_FILE = 'positions.json'

# ── Config ──────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {'testnet': True, 'api_key': '', 'api_secret': '', 'coins': [],
            'webhook_secret': 'secret123', 'max_positions': 6}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ── Trades ──────────────────────────────────────
def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_trades(trades):
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

# ── Positions ───────────────────────────────────
def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f, indent=2)

# ── Atomik pozisyon/trade güncelleme ────────────────
# Ajanlar tüm positions.json'ı okuyup-değiştirip-geri yazınca (5 thread
# eşzamanlı) "lost update" oluşuyordu: A {X,Y} okur, B {X,Y} okur, A X'i
# yazar, B Y'yi yazarken X'i eski haliyle ezer. Aşağıdaki yardımcılar tek
# sembolü kilit altında günceller → ne kayıp güncelleme ne de kapanmış
# pozisyonun "hayalet" olarak geri yazılması olur.
def update_position(symbol, **fields):
    """Var olan bir pozisyonun alanlarını kilit altında güncelle.
    Pozisyon yoksa HİÇBİR ŞEY yapmaz (kapanmış pozisyonu diriltmez)."""
    with _TRADE_LOCK:
        positions = load_positions()
        if symbol not in positions:
            return None
        positions[symbol].update(fields)
        save_positions(positions)
        return positions[symbol]

def clear_position(symbol):
    """Pozisyonu kilit altında sil."""
    with _TRADE_LOCK:
        positions = load_positions()
        if symbol in positions:
            del positions[symbol]
            save_positions(positions)

def append_trade(trade):
    """trades.json'a kilit altında ekle (eşzamanlı append kaybını önler)."""
    with _TRADE_LOCK:
        trades = load_trades()
        trades.append(trade)
        save_trades(trades)
        return trades

# ── Binance Client ──────────────────────────────
def get_client():
    cfg = load_config()
    is_testnet = cfg.get('testnet', True)
    if is_testnet:
        api_key    = cfg.get('api_key', '')
        api_secret = cfg.get('api_secret', '')
        client = Client(api_key, api_secret, testnet=True)
        client.API_URL = 'https://testnet.binance.vision/api'
    else:
        api_key    = cfg.get('real_api_key', '')
        api_secret = cfg.get('real_api_secret', '')
        client = Client(api_key, api_secret)
    return client

# ── Market Data ─────────────────────────────────
def get_market_summary(client):
    tickers = client.get_ticker()
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT')]
    total = len(usdt_pairs)
    red = [t for t in usdt_pairs if float(t['priceChangePercent']) < 0]
    green = [t for t in usdt_pairs if float(t['priceChangePercent']) >= 0]
    red_pct = round(len(red) / total * 100, 1) if total > 0 else 0

    top_gainers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]
    top_losers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:5]
    top50 = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)[:50]

    return {
        'total': total,
        'red': len(red),
        'green': len(green),
        'red_pct': red_pct,
        'green_pct': round(100 - red_pct, 1),
        'top_gainers': [{'symbol': t['symbol'], 'change': float(t['priceChangePercent']), 'price': float(t['lastPrice'])} for t in top_gainers],
        'top_losers': [{'symbol': t['symbol'], 'change': float(t['priceChangePercent']), 'price': float(t['lastPrice'])} for t in top_losers],
        'top50': [{'symbol': t['symbol'], 'price': float(t['lastPrice']), 'change': float(t['priceChangePercent']), 'volume': float(t['quoteVolume']), 'high': float(t['highPrice']), 'low': float(t['lowPrice'])} for t in top50],
    }

def get_fear_greed():
    try:
        import urllib.request
        url = 'https://api.alternative.me/fng/?limit=1'
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            d = data['data'][0]
            return {'value': int(d['value']), 'label': d['value_classification']}
    except:
        return {'value': 0, 'label': 'N/A'}

def get_price(client, symbol):
    try:
        t = client.get_ticker(symbol=symbol)
        return float(t['lastPrice'])
    except:
        return 0.0

# ── Bakiye ───────────────────────────────────────
def get_usdt_balance(client):
    try:
        account = client.get_account()
        for b in account['balances']:
            if b['asset'] == 'USDT':
                return float(b['free'])
        return 0.0
    except:
        return 0.0

def cleanup_dust_positions(client):
    """MIN_NOTIONAL altındaki toz pozisyonları positions.json'dan siler.
    Saatlik raporlarda otomatik çağrılır; /toztemizle ve web butonu da bunu kullanır.
    Returns: temizlenen sembol listesi (boşsa [])."""
    positions = load_positions()
    removed = []
    changed = False
    for sym in list(positions.keys()):
        p = positions[sym]
        qty = p.get('qty', 0)
        if qty <= 0:
            del positions[sym]
            changed = True
            continue
        try:
            _, mn = get_symbol_filters(client, sym)
            price  = get_price(client, sym)
            val    = qty * price
            if val < mn:
                removed.append(f'{sym} (${val:.2f}<${mn:.0f}min)')
                del positions[sym]
                changed = True
        except Exception:
            pass
    if changed:
        save_positions(positions)
    return removed


def get_total_equity(client):
    """Serbest USDT + tüm açık pozisyonların güncel piyasa değeri.
    Pozisyon boyutlama bunun üzerinden yapılır (cash daraldıkça boyut da
    daralmasın, gerçek sermaye baz alınsın)."""
    try:
        total = get_usdt_balance(client)
    except Exception:
        total = 0.0
    try:
        for sym, pos in load_positions().items():
            q = pos.get('qty', 0)
            if q > 0:
                try:
                    total += q * get_price(client, sym)
                except Exception:
                    pass
    except Exception:
        pass
    return total


def position_size_by_score(equity, score, mult=1.0,
                           lo_pct=0.01, hi_pct=0.03, min_usd=10.0):
    """Skora göre değişken pozisyon boyutu — tüm ajanlar için ORTAK kural.
    Güçlü sinyalde büyük, zayıfta küçük:
       skor 5  → %1   (lo_pct)
       skor 7.5→ %2
       skor 10 → %3   (hi_pct)
    Skor 0–10 ölçeğinde beklenir; skoru olmayan ajan (UT Bot) ~6 geçer.
    `mult`: CEO pozisyon çarpanı (bear'de küçültür)."""
    try:
        frac = max(0.0, min(1.0, (float(score) - 5.0) / 5.0))
    except Exception:
        frac = 0.0
    pct  = lo_pct + (hi_pct - lo_pct) * frac
    size = equity * pct * max(0.0, float(mult))
    return max(min_usd, round(size, 2))


# ── Başabaş koruması (TÜM ajanlar için ortak) ────
# Felsefe: bir işlem bir kez anlamlı yeşile geçtiyse, bir daha NET zarara
# dönmemeli. Trailing'e EK güvenlik ağıdır (trailing tek başına zirveden geri
# çekilirken hâlâ küçük zarara izin verebilir). Eşik bilinçli olarak çok düşük
# DEĞİL — yoksa her ufak dalgada satıp komisyona boğar (tutarlı kazancın düşmanı).
BE_ARM_PCT   = 2.0   # +%2 görülünce koruma kurulur
BE_FLOOR_PCT = 0.3   # +%0.3 altına düşerse çık → round-trip komisyon (~%0.2) üstü, net zarar yok

def check_breakeven(symbol, pos, pct, arm=BE_ARM_PCT, floor=BE_FLOOR_PCT):
    """+arm% bir kez görüldüyse 'be_armed' bayrağını kalıcı kurar; sonra fiyat
    +floor% altına düşerse True döner (çağıran %100 satmalı). floor komisyonun
    üstünde olduğundan tetiklenince kazanan işlem net zarara dönmez.
    pos: ajanın elindeki canlı sözlük (bayrak hem bellekte hem diske yazılır)."""
    try:
        if not pos.get('be_armed') and pct >= arm:
            pos['be_armed'] = True
            update_position(symbol, be_armed=True)
        return bool(pos.get('be_armed') and pct <= floor)
    except Exception:
        return False

# ── Portfolio ────────────────────────────────────
def get_portfolio_summary(client):
    positions = load_positions()
    trades = load_trades()
    result = []
    total_invested = 0
    total_current = 0

    for symbol, pos in positions.items():
        if pos.get('qty', 0) <= 0:
            continue
        current_price = get_price(client, symbol)
        if pos.get('qty', 0) * current_price < 1.0:
            continue
        invested = pos['avg_price'] * pos['qty']
        current_val = current_price * pos['qty']
        pnl = current_val - invested
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0
        total_invested += invested
        total_current += current_val
        result.append({
            'symbol': symbol,
            'qty': pos['qty'],
            'avg_price': pos['avg_price'],
            'current_price': current_price,
            'invested': round(invested, 2),
            'current_val': round(current_val, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

    closed = [t for t in trades if t.get('type') == 'sell']
    wins = [t for t in closed if t.get('pnl', 0) > 0]
    success_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0
    # Gerçekleşen net K/Z: kapanan tüm işlemlerin net PnL toplamı (botun gerçekten
    # kazandığı/kaybettiği para — total_pnl ise açık pozisyonların kâğıt K/Z'si).
    realized_pnl = round(sum(t.get('pnl', 0) for t in closed), 2)

    return {
        'positions': result,
        'total_invested': round(total_invested, 2),
        'total_current': round(total_current, 2),
        'total_pnl': round(total_current - total_invested, 2),
        'total_pnl_pct': round((total_current - total_invested) / total_invested * 100, 1) if total_invested > 0 else 0,
        'realized_pnl': realized_pnl,
        'success_rate': success_rate,
        'total_trades': len(closed),
        'win_trades': len(wins),
    }

# ── Execute Order ────────────────────────────────
# Sembol filtreleri neredeyse hiç değişmez → her alım/satış/toz-temizlikte
# exchangeInfo çekmek yerine 6 saat cache'le (rate-limit + gecikme azaltır).
_SYMBOL_FILTER_CACHE = {}   # symbol -> (step, min_notional, ts)
_SYMBOL_FILTER_TTL   = 6 * 3600

def get_symbol_filters(client, symbol):
    cached = _SYMBOL_FILTER_CACHE.get(symbol)
    if cached and (time.time() - cached[2]) < _SYMBOL_FILTER_TTL:
        return cached[0], cached[1]
    info = client.get_symbol_info(symbol)
    step = 0.001
    min_notional = 5.0  # varsayılan $5
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step = float(f['stepSize'])
        if f['filterType'] == 'NOTIONAL':
            min_notional = float(f['minNotional'])
        if f['filterType'] == 'MIN_NOTIONAL':
            min_notional = float(f['minNotional'])
    _SYMBOL_FILTER_CACHE[symbol] = (step, min_notional, time.time())
    return step, min_notional

def get_step_size(client, symbol):
    step, _ = get_symbol_filters(client, symbol)
    return step

def round_step(qty, step):
    import math
    precision = int(round(-math.log10(step)))
    return round(math.floor(qty / step) * step, precision)

def _calc_atr_pct(client, symbol, atr_period=7):
    """Saatlik ATR'yi fiyata göre yüzde olarak döndür."""
    try:
        klines = client.get_klines(
            symbol=symbol,
            interval=Client.KLINE_INTERVAL_1HOUR,
            limit=atr_period + 5
        )
        closes = [float(k[4]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        trs = [
            max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            for i in range(1, len(closes))
        ]
        if len(trs) < atr_period:
            return None
        atr = sum(trs[-atr_period:]) / atr_period
        return round(atr / closes[-1] * 100, 3)
    except:
        return None

def _source_emoji(source):
    s = (source or '').upper()
    if 'KAR' in s or 'HEDEF' in s: return '🎯'
    if 'STOP' in s: return '🛑'
    if 'SMART' in s: return '🧠'
    if 'SEANS' in s: return '📅'
    if 'UT' in s: return '🤖'
    return '📤'

def _hold_duration(symbol, trades_list):
    last_buy = next(
        (t for t in reversed(trades_list)
         if t.get('type') == 'buy' and t.get('symbol') == symbol), None)
    if not last_buy:
        return ''
    try:
        buy_dt = datetime.datetime.strptime(last_buy['time'], '%Y-%m-%d %H:%M:%S')
        delta  = datetime.datetime.now() - buy_dt
        total  = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m      = rem // 60
        return f'{h}s {m}dk' if h else f'{m}dk'
    except:
        return ''

def _fmt_price(p):
    return f'{p:.8f}'.rstrip('0') if p < 0.01 else f'{p:,.4f}'.rstrip('0').rstrip('.')

def _buy_msg(symbol, price, qty, usdt, source, period, tp_pct=0, sl_pct=0):
    emoji = _source_emoji(source)
    p = _fmt_price(price)
    lines = [
        f'{emoji} <b>ALIM</b> [{source}]',
        f'━━━━━━━━━━━━━━',
        f'🪙 <b>{symbol}</b>',
        f'💰 Fiyat: ${p}',
        f'📦 Miktar: {qty} | Tutar: ${usdt}',
    ]
    if tp_pct > 0:
        lines.append(f'🎯 TP: ${_fmt_price(round(price*(1+tp_pct/100),8))} (+%{tp_pct})')
    if sl_pct > 0:
        lines.append(f'🛑 SL: ${_fmt_price(round(price*(1-sl_pct/100),8))} (-%{sl_pct})')
    lines.append(f'⏱ Periyot: {period}')
    return '\n'.join(lines)

def _sell_msg(symbol, price, avg_price, qty, pnl, pnl_pct, fee, source, hold):
    emoji = _source_emoji(source)
    net   = round(pnl - fee, 2)
    win   = net >= 0
    p = _fmt_price(price)
    a = _fmt_price(avg_price)
    sign  = '+' if win else ''
    hold_line = f'\n⏱ Süre: {hold}' if hold else ''
    return (
        f'{emoji} <b>SATIM</b> [{source}]\n'
        f'━━━━━━━━━━━━━━\n'
        f'🪙 <b>{symbol}</b>\n'
        f'💰 Satış: ${p} | Alış: ${a}\n'
        f'{"🟢" if win else "🔴"} <b>{sign}{pnl_pct}%</b> → {sign}${net}'
        f'\n💸 Komisyon: -${round(fee,3)}{hold_line}'
    )

def _is_sl_source(source: str) -> bool:
    """Trade kaydının bir SL/STOP satışı olup olmadığını tespit eder.
    'EDGE SL', 'INDICATOR-X SL', 'BREAKOUT TRAIL_STOP', 'OTONOM SL' hepsini yakalar.
    NOT: Cooldown artık buna değil, gerçekleşen PnL'e bakar (aşağı bkz)."""
    s = source.upper()
    return 'STOP' in s or s.endswith(' SL') or ' SL ' in s

def _last_sell(symbol):
    trades = load_trades()
    return next((t for t in reversed(trades)
                 if t.get('symbol') == symbol and t.get('type') == 'sell'), None)

def _check_sl_cooldown(symbol, cooldown_hours=3):
    """Son çıkış ZARARLA bittiyse cooldown süresi geçti mi? True = alım serbest.

    Eskiden kaynak string'ine ('... SL', 'STOP') bakılıyordu; bu yüzden KÂRLI
    bir 'TRAIL STOP' çıkışı bile SL sayılıp tekrar girişi blokluyordu. Artık
    sadece son satışın net PnL'i < 0 ise bekleme uygulanır — kazanan trailing
    çıkışları cezalandırılmaz ve davranış tüm ajanlarda tutarlıdır."""
    last = _last_sell(symbol)
    if not last:
        return True
    if last.get('pnl', 0) >= 0:   # son çıkış kârlı/başabaş → bekleme yok
        return True
    try:
        sl_time = datetime.datetime.strptime(last['time'], '%Y-%m-%d %H:%M:%S')
        elapsed = (datetime.datetime.now() - sl_time).total_seconds() / 3600
        return elapsed >= cooldown_hours
    except:
        return True

def _parse_fill(order, req_qty, req_price, symbol):
    """Binance market emir yanıtından GERÇEKLEŞEN (qty, ortalama fiyat) çıkar.
    executedQty + cummulativeQuoteQty kullanır; base-asset cinsinden alınan
    komisyonu da düşer (net eldeki miktar). Yanıt beklenmedikse istenen
    değerlere düşer (testnet/fallback güvenli)."""
    try:
        filled = float(order.get('executedQty', 0) or 0)
        quote  = float(order.get('cummulativeQuoteQty', 0) or 0)
        if filled <= 0:
            return req_qty, req_price
        avg = quote / filled if quote > 0 else req_price
        # Komisyon base asset'ten kesildiyse net miktarı düşür (yoksa toz birikir)
        base = symbol[:-4] if symbol.endswith('USDT') else None
        comm = 0.0
        for f in order.get('fills', []) or []:
            if base and f.get('commissionAsset') == base:
                comm += float(f.get('commission', 0) or 0)
        net = filled - comm
        return (net if net > 0 else filled), (avg if avg > 0 else req_price)
    except Exception:
        return req_qty, req_price

def execute_buy(client, symbol, usdt_amount, source='MANUEL', period='—', agent=None):
    try:
        price = get_price(client, symbol)
        if price <= 0:
            return {'ok': False, 'error': 'Fiyat alınamadı'}

        # SL cooldown kontrolü — öncelik: coin ayarı > global ayar > hardcoded default (3s)
        cfg_data   = load_config()
        coin_cfg   = next((c for c in cfg_data.get('coins', []) if c['symbol'] == symbol), {})
        global_cd  = float(cfg_data.get('sl_cooldown_hours', 3))
        cooldown_h = float(coin_cfg.get('sl_cooldown_hours', global_cd))
        if cooldown_h > 0 and not _check_sl_cooldown(symbol, cooldown_h):
            last_sl = _last_sell(symbol)   # zararla biten son çıkış
            if last_sl:
                try:
                    sl_time = datetime.datetime.strptime(last_sl['time'], '%Y-%m-%d %H:%M:%S')
                    elapsed = (datetime.datetime.now() - sl_time).total_seconds() / 3600
                    kalan   = round(cooldown_h - elapsed, 1)
                except Exception:
                    kalan = cooldown_h
                print(f'[Bot] {symbol} SL cooldown aktif — {kalan}s kaldı')
                return {'ok': False, 'error': f'SL cooldown: {kalan}s kaldı'}

        # ATR bazlı TP/SL — emir vermeden önce hesapla
        tp_pct = float(coin_cfg.get('take_profit_pct', 0))
        sl_pct = float(coin_cfg.get('stop_loss_pct', 0))
        if coin_cfg.get('auto_tp_sl', False):
            atr = _calc_atr_pct(client, symbol, int(coin_cfg.get('ut_atr', 7)))
            if atr:
                sl_pct = max(1.0, min(5.0,  round(atr * 1.5, 2)))
                tp_pct = max(2.0, min(10.0, round(atr * 3.0, 2)))
                min_tp = float(coin_cfg.get('min_tp_pct', 0))
                if min_tp > 0 and tp_pct < min_tp:
                    msg = f'ATR düşük: TP %{tp_pct} < min %{min_tp}, alım atlandı'
                    print(f'[Bot] {symbol} {msg}')
                    return {'ok': False, 'error': msg}
        elif not coin_cfg:
            # Otonom ajan tarafından bulunan coin — config yok, ATR ile otomatik belirle
            # TP max %6: trailing %2.4'te aktif olur → hızlı küçük kâr kilitleme
            atr = _calc_atr_pct(client, symbol, 7)
            if atr:
                sl_pct = max(1.5, min(5.0, round(atr * 1.5, 2)))
                tp_pct = max(3.0, min(6.0, round(atr * 3.0, 2)))
            else:
                sl_pct = 2.5   # varsayılan: -%2.5
                tp_pct = 5.0   # varsayılan: +%5.0
            print(f'[Bot] {symbol} otonom ajan — ATR TP/SL: +%{tp_pct} / -%{sl_pct}')

        # ── Kritik bölge: çakışma önleyici kilit ────────────────────────────
        # Bakiye kontrolü de kilidin İÇİNDE: iki ajan aynı anda "yeterli" görüp
        # ikisi de alım yapamaz (alımlar seri hale gelir).
        with _TRADE_LOCK:
            balance = get_usdt_balance(client)
            if balance < usdt_amount:
                return {'ok': False, 'error': f'Yetersiz bakiye: ${round(balance,2)} USDT'}

            positions = load_positions()

            # Binance min satış tutarını al — toz tespiti için gerçek eşik
            step, min_notional = get_symbol_filters(client, symbol)
            pos = positions.get(symbol, {'qty': 0, 'avg_price': 0})
            pos_value = pos.get('qty', 0) * price

            if pos_value >= min_notional:
                # Gerçek açık pozisyon — engelle
                return {'ok': False, 'error': f'{symbol} zaten açık pozisyon var'}
            elif pos_value > 0:
                # Toz pozisyon (MIN_NOTIONAL altı → Binance satmaya izin vermiyor)
                # Yeni alımla sıfırdan başlat; ortalama hesabını bozmamak için sıfırla
                print(f'[Bot] {symbol} toz pozisyon (${pos_value:.2f} < ${min_notional} min) yoksayıldı')
                pos = {'qty': 0, 'avg_price': 0}

            # Global maksimum pozisyon limiti (tüm ajanlar paylaşır)
            # Slot sayımında MIN_NOTIONAL altı tozlar sayılmaz
            max_pos = int(cfg_data.get('max_positions', 6))
            open_count = sum(1 for p in positions.values()
                             if p.get('qty', 0) > 0
                             and p.get('qty', 0) * p.get('avg_price', 0) >= 2.0)
            if open_count >= max_pos:
                return {'ok': False, 'error': f'Pozisyon limiti dolu: {open_count}/{max_pos}'}

            qty = round_step(usdt_amount / price, step)
            if qty <= 0:
                return {'ok': False, 'error': f'Miktar çok küçük (step: {step})'}

            order = client.order_market_buy(symbol=symbol, quantity=qty)

            # Gerçek dolum: istenen değil, GERÇEKLEŞEN miktar ve ortalama fiyat.
            # Market emir slippage/kısmi dolum yapabilir; defter ile cüzdan
            # sürüklenmesin diye order yanıtını baz al.
            fill_qty, fill_price = _parse_fill(order, qty, price, symbol)

            total_qty = pos['qty'] + fill_qty
            avg = (((pos['qty'] * pos['avg_price']) + (fill_qty * fill_price)) / total_qty
                   if total_qty > 0 else fill_price)
            positions[symbol] = {
                'qty': total_qty, 'avg_price': avg,
                'tp_pct': tp_pct, 'sl_pct': sl_pct,
                'agent': agent,
                'open_time': time.time(),   # epoch — timeout/trailing meta'sı kilit içinde garanti
            }
            save_positions(positions)
            qty   = fill_qty     # trade kaydı ve dönüş için gerçekleşen değerler
            price = fill_price
        # ── Kilit bitti ─────────────────────────────────────────────────────

        append_trade({
            'type': 'buy', 'symbol': symbol, 'qty': qty,
            'price': price, 'usdt': usdt_amount,
            'source': source,
            'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        send_telegram(_buy_msg(symbol, price, qty, usdt_amount, source, period, tp_pct, sl_pct))
        return {'ok': True, 'qty': qty, 'price': price}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def execute_sell(client, symbol, sell_pct, source='MANUEL', period='—'):
    # Tüm kritik bölge kilit altında: aynı pozisyona eşzamanlı çift satışı
    # (manuel + ajan, ya da iki ajan) önler. İlk satış pozisyonu kilit içinde
    # düşürür/siler; ikinci çağrı "Açık pozisyon yok" alır.
    try:
        with _TRADE_LOCK:
            positions = load_positions()
            pos = positions.get(symbol)
            if not pos or pos.get('qty', 0) <= 0:
                return {'ok': False, 'error': 'Açık pozisyon yok'}
            step, min_notional = get_symbol_filters(client, symbol)
            price = get_price(client, symbol)
            if price <= 0:
                return {'ok': False, 'error': 'Fiyat alınamadı'}
            total_qty = pos['qty']

            # İstenen satış miktarı
            sell_qty = round_step(total_qty * (sell_pct / 100), step)
            sell_value = sell_qty * price

            # Satış tutarı min tutarın altındaysa min tutara yükselt
            if sell_value < min_notional:
                sell_qty = round_step(min_notional / price * 1.01, step)
                sell_value = sell_qty * price
                print(f'[Bot] {symbol} satış tutarı min altında, {min_notional}$ seviyesine yükseltildi')

            # Satış sonrası kalan min tutarın altında kalıyorsa tamamını sat
            remaining_value = (total_qty - sell_qty) * price
            if remaining_value < min_notional or sell_qty > total_qty:
                sell_qty = round_step(total_qty, step)
                print(f'[Bot] {symbol} kalan bakiye min altında kalacak, tamamı satılıyor')

            qty = sell_qty
            if qty <= 0:
                return {'ok': False, 'error': 'Satılacak miktar hesaplanamadı'}

            order = client.order_market_sell(symbol=symbol, quantity=qty)

            # Gerçekleşen satış: order yanıtından miktar + ortalama dolum fiyatı
            avg_price = pos['avg_price']
            filled_qty = qty
            try:
                ex = float(order.get('executedQty', 0) or 0)
                qv = float(order.get('cummulativeQuoteQty', 0) or 0)
                if ex > 0:
                    filled_qty = ex
                    if qv > 0:
                        price = qv / ex   # gerçek ortalama satış fiyatı
            except Exception:
                pass

            gross_pnl = (price - avg_price) * filled_qty
            fee       = (avg_price + price) * filled_qty * FEE_RATE
            net_pnl   = round(gross_pnl - fee, 2)
            pnl_pct   = round((price - avg_price) / avg_price * 100, 2) if avg_price > 0 else 0

            new_qty = round(pos['qty'] - filled_qty, 6)
            if new_qty <= 0:
                clear_position(symbol)
            else:
                update_position(symbol, qty=new_qty)

            trades = append_trade({
                'type': 'sell', 'symbol': symbol, 'qty': filled_qty,
                'price': price, 'pnl': net_pnl,
                'source': source,
                'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        hold_str = _hold_duration(symbol, trades)
        send_telegram(_sell_msg(symbol, price, avg_price, filled_qty, gross_pnl, pnl_pct, fee, source, hold_str))
        return {'ok': True, 'qty': filled_qty, 'price': price, 'pnl': net_pnl}
    except Exception as e:
        return {'ok': False, 'error': str(e)}



def send_telegram(msg):
    try:
        cfg = load_config()
        token   = cfg.get('telegram_token', '')
        chat_id = cfg.get('telegram_chat_id', '')
        if not token or not chat_id:
            return
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': msg,
            'parse_mode': 'HTML'
        }).encode()
        urllib.request.urlopen(url, data, timeout=5)
    except Exception as e:
        print('Telegram hata:', e)
