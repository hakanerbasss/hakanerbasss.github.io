import time, datetime, json, threading, os
from bot import (load_config, get_client, execute_buy, execute_sell,
                 load_positions, get_price, send_telegram)
from seans_strategy import check_seans_signal, check_seans_sell

SIGNAL_STATE_FILE = 'signal_state.json'

def load_signal_state():
    if os.path.exists(SIGNAL_STATE_FILE):
        with open(SIGNAL_STATE_FILE) as f:
            return json.load(f)
    return {}

def save_signal_state(state):
    with open(SIGNAL_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ── ATR / UT Bot ─────────────────────────────────
def calc_rma(values, period):
    rma = sum(values[:period]) / period
    for v in values[period:]:
        rma = (rma * (period - 1) + v) / period
    return rma

def calc_ut_bot(closes, highs, lows, key_value=2, atr_period=7):
    n = len(closes)
    if n < atr_period + 2:
        return None

    # Per-candle True Range
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)

    if len(trs) < atr_period:
        return None

    # Per-candle ATR — Wilder's smoothing (her mum için ayrı)
    atr_val = sum(trs[:atr_period]) / atr_period
    atr_per_candle = [None] * atr_period
    atr_per_candle.append(atr_val)
    for tr in trs[atr_period:]:
        atr_val = (atr_val * (atr_period - 1) + tr) / atr_period
        atr_per_candle.append(atr_val)
    # atr_per_candle[i] → closes[i+1] için n_loss

    # Trailing stop — ilk geçerli ATR'den başla
    start = atr_period + 1
    trail = closes[start - 1]
    prev_close = closes[start - 1]

    for i in range(start, n):
        c = closes[i]
        prev_trail = trail
        n_loss = key_value * atr_per_candle[i - 1]

        if c > prev_trail:
            trail = max(prev_trail, c - n_loss)
        else:
            trail = min(prev_trail, c + n_loss)

        # Sinyal sadece SON mumda crossover olursa dönderilir
        if i == n - 1:
            if prev_close <= prev_trail and c > trail:
                return 'buy'
            if prev_close >= prev_trail and c < trail:
                return 'sell'

        prev_close = c

    return None

def get_klines(client, symbol, interval, limit=150):
    from binance.client import Client
    interval_map = {
        '5m':  Client.KLINE_INTERVAL_5MINUTE,
        '15m': Client.KLINE_INTERVAL_15MINUTE,
        '1h':  Client.KLINE_INTERVAL_1HOUR,
        '4h':  Client.KLINE_INTERVAL_4HOUR,
        '1d':  Client.KLINE_INTERVAL_1DAY,
    }
    kl = client.get_klines(
        symbol=symbol,
        interval=interval_map.get(interval, Client.KLINE_INTERVAL_1HOUR),
        limit=limit
    )
    # Son mum henüz kapanmadı — çıkar
    kl = kl[:-1]
    closes = [float(k[4]) for k in kl]
    highs  = [float(k[2]) for k in kl]
    lows   = [float(k[3]) for k in kl]
    # Son kapanan mumun açılış zamanı (ms) — tekrar işleme önlemi
    last_candle_time = int(kl[-1][0]) if kl else 0
    return closes, highs, lows, last_candle_time

PERIOD_SECONDS = {
    '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400,
}

def run_engine():
    print('[Engine] Başladı')
    signal_state = load_signal_state()
    # {symbol: {'last_candle_time': int, 'last_signal': str}}

    while True:
        try:
            cfg = load_config()
            coins = cfg.get('coins', [])
            check_interval = int(cfg.get('check_interval', 45))
            client = get_client()

            # Bot duraklatıldıysa işlem yapma
            if cfg.get('bot_paused', False):
                time.sleep(check_interval)
                continue

            for coin in coins:
                if not coin.get('active', True):
                    continue

                symbol = coin['symbol']
                period = coin.get('period', '1h')
                source = coin.get('signal_source', 'utbot')

                # ── Anlık fiyat izleme (her coin, her döngü) ──
                try:
                    current_price = get_price(client, symbol)
                    positions = load_positions()
                    pos = positions.get(symbol)

                    if pos and pos.get('qty', 0) > 0:
                        avg_price = pos['avg_price']
                        change_pct = ((current_price - avg_price) / avg_price) * 100

                        # Kâr hedefi
                        tp = float(coin.get('take_profit_pct', 0))
                        tp_sell_pct = float(coin.get('take_profit_sell_pct', 100))
                        if tp > 0 and change_pct >= tp:
                            print(f'[Engine] {symbol} KÂR HEDEFİ +%{round(change_pct,2)}')
                            execute_sell(client, symbol, tp_sell_pct, source='KAR HEDEFİ', period=period)

                        # Stop loss
                        sl = float(coin.get('stop_loss_pct', 0))
                        sl_sell_pct = float(coin.get('stop_loss_sell_pct', 100))
                        if sl > 0 and change_pct <= -sl:
                            print(f'[Engine] {symbol} STOP LOSS %{round(change_pct,2)}')
                            execute_sell(client, symbol, sl_sell_pct, source='STOP LOSS', period=period)

                except Exception as e:
                    print(f'[Engine] Anlık izleme hatası {symbol}: {e}')

                # ── UT Bot (sadece utbot veya both) ──────────
                if source not in ['utbot', 'both']:
                    continue

                try:
                    closes, highs, lows, last_candle_time = get_klines(client, symbol, period)

                    state = signal_state.get(symbol, {})
                    prev_candle_time = state.get('last_candle_time', 0)
                    prev_signal = state.get('last_signal', None)

                    # Aynı mumu tekrar işleme
                    if last_candle_time == prev_candle_time:
                        continue

                    signal = calc_ut_bot(
                        closes, highs, lows,
                        key_value=float(coin.get('ut_key', 2)),
                        atr_period=int(coin.get('ut_atr', 7))
                    )

                    # State güncelle — sinyal olsa da olmasa da bu mumu işaretle
                    signal_state[symbol] = {
                        'last_candle_time': last_candle_time,
                        'last_signal': signal or prev_signal
                    }
                    save_signal_state(signal_state)

                    if not signal:
                        continue

                    print(f'[UT Bot] {symbol} → {signal.upper()}')

                    positions = load_positions()

                    if signal == 'buy':
                        pos = positions.get(symbol, {})
                        pos_qty = pos.get('qty', 0)
                        pos_price = get_price(client, symbol)
                        pos_value = pos_qty * pos_price
                        if pos_qty > 0 and pos_value >= 1.0:
                            print(f'[UT Bot] {symbol} zaten pozisyon var (${round(pos_value,2)}), atlandı')
                            continue
                        usdt = float(coin.get('usdt_amount', 10))
                        execute_buy(client, symbol, usdt, source='UT BOT', period=period)

                    elif signal == 'sell':
                        if positions.get(symbol, {}).get('qty', 0) <= 0:
                            print(f'[UT Bot] {symbol} pozisyon yok, satış atlandı')
                            continue
                        sell_pct = float(coin.get('close_sell_pct', 100))
                        execute_sell(client, symbol, sell_pct, source='UT BOT', period=period)

                except Exception as e:
                    print(f'[Engine] UT Bot hatası {symbol}: {e}')

            # ── Seans Stratejisi ─────────────────────────
            for coin in coins:
                if not coin.get('active', True):
                    continue
                source = coin.get('signal_source', 'utbot')
                if source not in ['seans', 'both']:
                    continue

                symbol   = coin['symbol']
                strategy = coin.get('seans_strategy', 'both')
                sell_hour = int(coin.get('seans_sell_hour', 13))

                try:
                    positions = load_positions()
                    pos = positions.get(symbol, {})
                    pos_qty = pos.get('qty', 0)

                    # Satış kontrolü
                    if pos_qty > 0 and check_seans_sell(sell_hour):
                        pos_value = pos_qty * get_price(client, symbol)
                        if pos_value >= 1.0:
                            result = execute_sell(client, symbol, 100,
                                source='SEANS', period=f'Saat {sell_hour}:00')
                            print(f'[Seans] {symbol} satış — saat {sell_hour}:00')

                    # Alım kontrolü
                    elif pos_qty == 0 or pos_qty * get_price(client, symbol) < 1.0:
                        sig = check_seans_signal(client, symbol, strategy)
                        if sig['signal'] == 'buy':
                            usdt = float(coin.get('usdt_amount', 10))
                            result = execute_buy(client, symbol, usdt,
                                source='SEANS', period=sig['reason'])
                            print(f'[Seans] {symbol} alım — {sig["reason"]}')

                except Exception as e:
                    print(f'[Seans] {symbol} hata: {e}')

            # ── Smart Composite Stratejisi ───────────────
            for coin in coins:
                if not coin.get('active', True):
                    continue
                if coin.get('signal_source', 'utbot') != 'smart':
                    continue

                symbol    = coin['symbol']
                min_score = int(coin.get('smart_min_score', 3))

                try:
                    from smart_strategy import check_smart_signal, check_smart_sell
                    positions = load_positions()
                    pos       = positions.get(symbol, {})
                    pos_qty   = pos.get('qty', 0)
                    pos_value = pos_qty * get_price(client, symbol) if pos_qty > 0 else 0

                    if pos_qty > 0 and pos_value >= 1.0:
                        sell_sig = check_smart_sell(client, symbol)
                        if sell_sig['signal'] == 'sell':
                            send_telegram(
                                f'🧠 <b>{symbol}</b> | {sell_sig["reason"]} → SATIŞ'
                            )
                            execute_sell(client, symbol, 100,
                                source='SMART', period=sell_sig['reason'])
                            print(f'[Smart] {symbol} SATIŞ — {sell_sig["reason"]}')
                    else:
                        sig = check_smart_signal(client, symbol, min_score)
                        print(f'[Smart] {symbol} Skor:{sig["score"]}/4 {sig["detail"]}')
                        if sig['signal'] == 'buy':
                            send_telegram(
                                f'🧠 <b>{symbol}</b> | Skor: {sig["score"]}/4\n'
                                f'{sig["detail"]} → ALIM'
                            )
                            usdt = float(coin.get('usdt_amount', 10))
                            execute_buy(client, symbol, usdt,
                                source='SMART', period=sig['detail'])
                            print(f'[Smart] {symbol} ALIM — {sig["detail"]}')

                except Exception as e:
                    print(f'[Smart] {symbol} hata: {e}')

            time.sleep(check_interval)

        except Exception as e:
            print(f'[Engine] Genel hata: {e}')
            time.sleep(10)

def start_engine():
    t = threading.Thread(target=run_engine, daemon=True)
    t.start()
    return t
