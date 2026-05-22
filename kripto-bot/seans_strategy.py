import datetime, pytz
from binance.client import Client

TR_TZ = pytz.timezone('Europe/Istanbul')
UTC_TZ = pytz.utc

def get_hourly_candles(client, symbol, limit=48):
    klines = client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_1HOUR,
        limit=limit
    )
    result = []
    for k in klines:
        dt_utc = datetime.datetime.fromtimestamp(k[0]/1000, tz=UTC_TZ)
        dt_tr  = dt_utc.astimezone(TR_TZ)
        result.append({
            'dt_tr':   dt_tr,
            'hour_tr': dt_tr.hour,
            'date_tr': dt_tr.strftime('%Y-%m-%d'),
            'open':    float(k[1]),
            'high':    float(k[2]),
            'low':     float(k[3]),
            'close':   float(k[4]),
            'volume':  float(k[5]),
        })
    return result

def get_day_candles(candles, date_str):
    return [c for c in candles if c['date_tr'] == date_str]

def day_change(day_candles):
    if not day_candles:
        return None
    return (day_candles[-1]['close'] - day_candles[0]['open']) / day_candles[0]['open'] * 100

def abd_first_hour_change(day_candles):
    h17 = [c for c in day_candles if c['hour_tr'] == 17]
    h18 = [c for c in day_candles if c['hour_tr'] == 18]
    if not h17 or not h18:
        return None
    return (h18[-1]['close'] - h17[0]['open']) / h17[0]['open'] * 100

def check_seans_signal(client, symbol, strategy='both'):
    """
    strategy seçenekleri:
      'abd_red'            — Coin ABD ilk saat kırmızıysa 20:00 al
      'prev_green'         — Coin önceki gün yeşilse 17:00 al
      'both'               — İkisi de
      'prev_green_btc'     — Coin önceki yeşil + BTC önceki yeşil → 17:00 al
      'abd_red_btc'        — Coin ABD kırmızı + BTC ABD kırmızı → 20:00 al
    """
    try:
        now_tr        = datetime.datetime.now(TR_TZ)
        current_hour  = now_tr.hour
        today_str     = now_tr.strftime('%Y-%m-%d')
        yesterday_str = (now_tr - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        # Coin verisi
        candles           = get_hourly_candles(client, symbol, limit=72)
        today_candles     = get_day_candles(candles, today_str)
        yesterday_candles = get_day_candles(candles, yesterday_str)

        # BTC verisi (filtreli stratejiler için)
        btc_candles           = get_hourly_candles(client, 'BTCUSDT', limit=72)
        btc_today             = get_day_candles(btc_candles, today_str)
        btc_yesterday         = get_day_candles(btc_candles, yesterday_str)

        coin_prev_chg  = day_change(yesterday_candles)
        coin_abd_chg   = abd_first_hour_change(today_candles)
        btc_prev_chg   = day_change(btc_yesterday)
        btc_abd_chg    = abd_first_hour_change(btc_today)

        # ── Strateji: prev_green_btc — 17:00 ────────────
        if strategy == 'prev_green_btc' and current_hour == 17:
            if (coin_prev_chg is not None and coin_prev_chg >= 0 and
                btc_prev_chg  is not None and btc_prev_chg  >= 0):
                return {
                    'signal':   'buy',
                    'reason':   f'Önceki yeşil ({round(coin_prev_chg,2)}%) + BTC yeşil ({round(btc_prev_chg,2)}%) → 17:00',
                    'buy_hour': 17,
                }

        # ── Strateji: abd_red_btc — 20:00 ───────────────
        elif strategy == 'abd_red_btc' and current_hour == 20:
            if (coin_abd_chg is not None and coin_abd_chg < 0 and
                btc_abd_chg  is not None and btc_abd_chg  < 0):
                return {
                    'signal':   'buy',
                    'reason':   f'ABD kırmızı ({round(coin_abd_chg,2)}%) + BTC kırmızı ({round(btc_abd_chg,2)}%) → 20:00',
                    'buy_hour': 20,
                }

        # ── Strateji: abd_red — 20:00 ───────────────────
        elif strategy in ['abd_red', 'both'] and current_hour == 20:
            if coin_abd_chg is not None and coin_abd_chg < 0:
                return {
                    'signal':   'buy',
                    'reason':   f'ABD açılış kırmızı ({round(coin_abd_chg,2)}%) → 20:00',
                    'buy_hour': 20,
                }

        # ── Strateji: prev_green — 17:00 ────────────────
        if strategy in ['prev_green', 'both'] and current_hour == 17:
            if coin_prev_chg is not None and coin_prev_chg >= 0:
                return {
                    'signal':   'buy',
                    'reason':   f'Önceki gün yeşil ({round(coin_prev_chg,2)}%) → 17:00',
                    'buy_hour': 17,
                }

        # ── Strateji 5: BTC 2 gün kırmızı + Coin kırmızı → 20:00 AL ─────
        if strategy == 'btc_2red_coin_red' and current_hour == 20:
            from bot import get_client
            btc_client = get_client()
            btc_candles = get_hourly_candles(btc_client, 'BTCUSDT', limit=72)
            btc_yesterday  = get_day_candles(btc_candles, yesterday_str)
            day_before_str = (now_tr - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
            btc_day_before = get_day_candles(btc_candles, day_before_str)
            btc_prev1 = day_change(btc_yesterday)
            btc_prev2 = day_change(btc_day_before)
            coin_today_chg = day_change(today_candles)
            if (btc_prev1 is not None and btc_prev1 < 0 and
                btc_prev2 is not None and btc_prev2 < 0 and
                coin_today_chg is not None and coin_today_chg < 0):
                return {
                    'signal':   'buy',
                    'reason':   f'BTC 2 gün kırmızı ({round(btc_prev2,2)}%, {round(btc_prev1,2)}%) + Coin kırmızı ({round(coin_today_chg,2)}%) → 20:00 alım',
                    'buy_hour': 20,
                }

        return {'signal': None, 'reason': f'Koşul sağlanmadı (saat {current_hour}:00)'}

    except Exception as e:
        return {'signal': None, 'reason': f'Hata: {e}'}

def check_seans_sell(sell_hour=13):
    now_tr = datetime.datetime.now(TR_TZ)
    return now_tr.hour == sell_hour
