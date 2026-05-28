"""Seans (Session) Strategy — Türkiye saatine göre al/sat"""
import datetime

# Türkiye UTC+3, 2016'dan beri yaz saati yok — pytz gerekmez
_TR_TZ = datetime.timezone(datetime.timedelta(hours=3))


def _now_tr():
    return datetime.datetime.now(_TR_TZ)


def check_seans_sell(sell_hour):
    """Şu an satış saatiyse True döner."""
    return _now_tr().hour == sell_hour


def check_seans_signal(client, symbol, strategy='both'):
    """
    strategy: 'morning' | 'evening' | 'both' | 'simple'
    Returns: {'signal': 'buy'|'', 'reason': str}
    """
    from binance.client import Client as BClient

    now  = _now_tr()
    hour = now.hour

    morning = 9 <= hour < 12    # Avrupa açılışı
    evening = 20 <= hour < 23   # ABD seansı
    asia    = 4 <= hour < 8     # Tokyo/Şangay (04:00-08:00 TR = 01:00-05:00 UTC)

    if strategy == 'morning':
        in_session = morning
    elif strategy == 'evening':
        in_session = evening
    elif strategy == 'asia':
        in_session = asia
    else:  # 'both' veya 'simple' → tüm seanslar
        in_session = morning or evening or asia

    if not in_session:
        return {'signal': '', 'reason': f'Seans dışı ({hour}:00 TR)'}

    session_name = 'Sabah' if morning else ('Akşam' if evening else 'Asya')

    if strategy == 'simple':
        return {'signal': 'buy', 'reason': f'{session_name} seansı ({hour}:00)'}

    try:
        klines = client.get_klines(
            symbol=symbol,
            interval=BClient.KLINE_INTERVAL_1HOUR,
            limit=26,
        )
        klines = klines[:-1]  # Son kapanmamış mumu çıkar
        if len(klines) < 15:
            return {'signal': '', 'reason': 'Yetersiz veri'}

        closes = [float(k[4]) for k in klines]

        # RSI < 65 ve son mum yükselen
        d = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        n = 14
        g = sum(max(v, 0) for v in d[-n:]) / n
        l = sum(max(-v, 0) for v in d[-n:]) / n
        rsi = 100.0 if l == 0 else round(100 - 100 / (1 + g / l), 1)

        if rsi > 65:
            return {'signal': '', 'reason': f'RSI yüksek ({rsi})'}

        if closes[-1] > closes[-2]:
            return {'signal': 'buy', 'reason': f'{session_name} seansı + RSI={rsi}'}

        return {'signal': '', 'reason': 'Son mum düşüşte'}
    except Exception as e:
        return {'signal': '', 'reason': f'Hata: {e}'}
