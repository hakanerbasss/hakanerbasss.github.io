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

def get_17_20_change(day_candles):
    """17:00 açılış → 20:00 açılış değişimi (ABD seansı başlangıcı)"""
    h17 = [c for c in day_candles if c['hour_tr'] == 17]
    h20 = [c for c in day_candles if c['hour_tr'] == 20]
    if not h17 or not h20:
        return None
    return (h20[0]['open'] - h17[0]['open']) / h17[0]['open'] * 100

def abd_first_hour_change(day_candles):
    h17 = [c for c in day_candles if c['hour_tr'] == 17]
    h18 = [c for c in day_candles if c['hour_tr'] == 18]
    if not h17 or not h18:
        return None
    return (h18[-1]['close'] - h17[0]['open']) / h17[0]['open'] * 100

# Strateji → okunabilir ad
STRATEGY_LABELS = {
    'btc_yy_coin_y': 'BTC 2gün🟢 + Coin bugün🟢',
    'btc_yy_coin_r': 'BTC 2gün🟢 + Coin bugün🔴',
    'btc_rr_coin_y': 'BTC 2gün🔴 + Coin bugün🟢',
    'btc_rr_coin_r': 'BTC 2gün🔴 + Coin bugün🔴',
    'btc_yr_coin_y': 'BTC dün🟢 bugün🔴 + Coin bugün🟢',
    'btc_yr_coin_r': 'BTC dün🟢 bugün🔴 + Coin bugün🔴',
    'btc_ry_coin_y': 'BTC dün🔴 bugün🟢 + Coin bugün🟢',
    'btc_ry_coin_r': 'BTC dün🔴 bugün🟢 + Coin bugün🔴',
    'coin_yy':        'Coin dün🟢 bugün🟢',
    'coin_ky':        'Coin dün🔴 bugün🟢',
    'coin_kk':        'Coin dün🔴 bugün🔴',
    'coin_yk':        'Coin dün🟢 bugün🔴',
    'composite_3':   '⚡ Composite ≥3/5 Faktör Yeşil',
    'composite_4':   '⚡ Composite ≥4/5 Faktör Yeşil',
    'composite_5':   '⚡ Composite 5/5 Faktör Yeşil',
    'rel_strong':    '💪 Coin BTC\'den Güçlü',
    'abd_red':       'ABD Kırmızı',
    'prev_green':    'Önceki Yeşil',
    'both':          'ABD Kırmızı + Önceki Yeşil',
    'prev_green_btc':'Önceki Yeşil + BTC Yeşil',
    'abd_red_btc':   'ABD + BTC Kırmızı',
}

# Strateji koşulları: (btc_prev_op, btc_1720_op, coin_1720_op)
# None = bu değer kontrol edilmez
_BTC_CONDS = {
    'btc_yy_coin_y': ('>=0', '>=0', '>=0'),
    'btc_yy_coin_r': ('>=0', '>=0', '<0'),
    'btc_rr_coin_y': ('<0',  '<0',  '>=0'),
    'btc_rr_coin_r': ('<0',  '<0',  '<0'),
    'btc_yr_coin_y': ('>=0', '<0',  '>=0'),
    'btc_yr_coin_r': ('>=0', '<0',  '<0'),
    'btc_ry_coin_y': ('<0',  '>=0', '>=0'),
    'btc_ry_coin_r': ('<0',  '>=0', '<0'),
}

_COIN_CONDS = {
    'coin_yy': ('>=0', '>=0'),
    'coin_ky': ('<0',  '>=0'),
    'coin_kk': ('<0',  '<0'),
    'coin_yk': ('>=0', '<0'),
}


def _chk(v, op):
    return v >= 0 if op == '>=0' else v < 0


def check_seans_signal(client, symbol, strategy='both'):
    """
    Canlı seans sinyali — 20:00'de alım, seçilen saatte satış.

    Desteklenen stratejiler:
      BTC filtreli : btc_yy_coin_y/r, btc_rr_coin_y/r,
                     btc_yr_coin_y/r, btc_ry_coin_y/r
      Coin-only    : coin_yy, coin_ky, coin_kk, coin_yk
      Eski (uyumluluk): abd_red, prev_green, both,
                        prev_green_btc, abd_red_btc
    """
    try:
        now_tr        = datetime.datetime.now(TR_TZ)
        current_hour  = now_tr.hour
        today_str     = now_tr.strftime('%Y-%m-%d')
        yesterday_str = (now_tr - datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        candles           = get_hourly_candles(client, symbol, limit=72)
        today_candles     = get_day_candles(candles, today_str)
        yesterday_candles = get_day_candles(candles, yesterday_str)

        btc_candles   = get_hourly_candles(client, 'BTCUSDT', limit=72)
        btc_today     = get_day_candles(btc_candles, today_str)
        btc_yesterday = get_day_candles(btc_candles, yesterday_str)

        coin_prev_chg = day_change(yesterday_candles)
        btc_prev_chg  = day_change(btc_yesterday)
        coin_17_20    = get_17_20_change(today_candles)
        btc_17_20     = get_17_20_change(btc_today)
        coin_abd_chg  = abd_first_hour_change(today_candles)
        btc_abd_chg   = abd_first_hour_change(btc_today)

        def _buy(reason):
            return {'signal': 'buy', 'reason': reason, 'buy_hour': 20}

        def _none():
            return {'signal': None, 'reason': f'Koşul sağlanmadı (saat {current_hour}:00)'}

        # ── 17:00 stratejileri (eski) ─────────────────
        if strategy in ['prev_green', 'both'] and current_hour == 17:
            if coin_prev_chg is not None and coin_prev_chg >= 0:
                return _buy(f'Önceki gün yeşil ({round(coin_prev_chg,2)}%) → 17:00')

        if strategy == 'prev_green_btc' and current_hour == 17:
            if (coin_prev_chg is not None and coin_prev_chg >= 0 and
                btc_prev_chg  is not None and btc_prev_chg  >= 0):
                return _buy(
                    f'Önceki yeşil ({round(coin_prev_chg,2)}%) '
                    f'+ BTC yeşil ({round(btc_prev_chg,2)}%) → 17:00'
                )

        # ── 20:00 stratejileri ────────────────────────
        if current_hour != 20:
            return _none()

        # BTC filtreli kombinasyonlar
        if strategy in _BTC_CONDS:
            op1, op2, op3 = _BTC_CONDS[strategy]
            if any(v is None for v in [btc_prev_chg, btc_17_20, coin_17_20]):
                return _none()
            if _chk(btc_prev_chg, op1) and _chk(btc_17_20, op2) and _chk(coin_17_20, op3):
                return _buy(
                    f'{STRATEGY_LABELS[strategy]} — '
                    f'BTC dün {round(btc_prev_chg,2)}% '
                    f'BTC bugün {round(btc_17_20,2)}% '
                    f'Coin {round(coin_17_20,2)}%'
                )
            return _none()

        # ── Composite Skor stratejileri ──────────────
        if strategy.startswith('composite_'):
            min_score = int(strategy.split('_')[1])
            # Asya seansı: dünün 03:00-10:00 değişimi
            asian_vals = [c for c in candles if c['date_tr'] == yesterday_str]
            h3  = [c for c in asian_vals if c['hour_tr'] == 3]
            h10 = [c for c in asian_vals if c['hour_tr'] == 10]
            asian = None
            if h3 and h10:
                asian = (h10[-1]['close'] - h3[0]['open']) / h3[0]['open'] * 100

            factors = [btc_prev_chg, btc_17_20, coin_17_20, coin_prev_chg, asian]
            score = sum(1 for v in factors if v is not None and v >= 0)
            labels = ['BTC dün', 'BTC 17-20', 'Coin 17-20', 'Coin dün', 'Asya']
            detail = ' | '.join(
                f'{l}:{"🟢" if v is not None and v>=0 else "🔴"}{round(v,1) if v is not None else "?"}'
                for l, v in zip(labels, factors)
            )
            if score >= min_score:
                return _buy(f'Composite {score}/5 → {detail}')
            return {'signal': None, 'reason': f'Composite {score}/5 < {min_score} | {detail}'}

        # ── Relatif güç stratejisi ────────────────────
        if strategy == 'rel_strong':
            if coin_17_20 is None or btc_17_20 is None:
                return _none()
            rs = coin_17_20 - btc_17_20
            if rs >= 0:
                return _buy(
                    f'Coin BTC\'den güçlü (Coin:{round(coin_17_20,2)}% BTC:{round(btc_17_20,2)}% Fark:+{round(rs,2)}%) → 20:00'
                )
            return {'signal': None, 'reason': f'Coin zayıf vs BTC (fark:{round(rs,2)}%)'}

        # Coin-only kombinasyonlar
        if strategy in _COIN_CONDS:
            op1, op2 = _COIN_CONDS[strategy]
            if coin_prev_chg is None or coin_17_20 is None:
                return _none()
            if _chk(coin_prev_chg, op1) and _chk(coin_17_20, op2):
                return _buy(
                    f'{STRATEGY_LABELS[strategy]} — '
                    f'dün {round(coin_prev_chg,2)}% '
                    f'bugün {round(coin_17_20,2)}%'
                )
            return _none()

        # Eski stratejiler (geriye dönük uyumluluk)
        if strategy in ['abd_red', 'both']:
            if coin_abd_chg is not None and coin_abd_chg < 0:
                return _buy(f'ABD açılış kırmızı ({round(coin_abd_chg,2)}%) → 20:00')

        if strategy == 'abd_red_btc':
            if (coin_abd_chg is not None and coin_abd_chg < 0 and
                btc_abd_chg  is not None and btc_abd_chg  < 0):
                return _buy(
                    f'ABD kırmızı ({round(coin_abd_chg,2)}%) '
                    f'+ BTC kırmızı ({round(btc_abd_chg,2)}%) → 20:00'
                )

        return _none()

    except Exception as e:
        return {'signal': None, 'reason': f'Hata: {e}'}


def check_seans_sell(sell_hour=13):
    now_tr = datetime.datetime.now(TR_TZ)
    return now_tr.hour == sell_hour
