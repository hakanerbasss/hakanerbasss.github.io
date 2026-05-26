"""Smart Composite Strategy — Çoklu faktör skoru (4 faktör üzerinden)"""
from binance.client import Client as BClient


def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return 50.0
    d = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    g = sum(max(v, 0) for v in d[-n:]) / n
    l = sum(max(-v, 0) for v in d[-n:]) / n
    return 100.0 if l == 0 else round(100 - 100 / (1 + g / l), 1)


def _get_klines(client, symbol, limit=60):
    klines = client.get_klines(
        symbol=symbol,
        interval=BClient.KLINE_INTERVAL_1HOUR,
        limit=limit + 1,
    )
    klines = klines[:-1]  # Son kapanmamış mumu çıkar
    closes  = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    return closes, volumes


def check_smart_signal(client, symbol, min_score=3):
    """
    4 faktör üzerinden alım skoru hesaplar.
    Returns: {'signal': 'buy'|'', 'score': int, 'detail': str}
    """
    try:
        closes, volumes = _get_klines(client, symbol, limit=60)
        if len(closes) < 25:
            return {'signal': '', 'score': 0, 'detail': 'Yetersiz veri'}

        score = 0
        factors = []

        # Faktör 1: RSI aşırı satım (< 40)
        rsi = _rsi(closes)
        if rsi < 40:
            score += 1
            factors.append(f'RSI={rsi}')

        # Faktör 2: Fiyat SMA20 üzerinde (yukarı trend)
        sma20 = sum(closes[-20:]) / 20
        if closes[-1] > sma20:
            score += 1
            factors.append('Fiyat>SMA20')

        # Faktör 3: Hacim artışı (mevcut hacim > ortalama x1.5)
        if len(volumes) >= 20:
            avg_vol = sum(volumes[-20:]) / 20
            if avg_vol > 0 and volumes[-1] > avg_vol * 1.5:
                score += 1
                factors.append('Hacim↑')

        # Faktör 4: Bollinger Band alt bandına yakın (% 2 tolerans)
        if len(closes) >= 20:
            std20 = (sum((c - sma20) ** 2 for c in closes[-20:]) / 20) ** 0.5
            lower_band = sma20 - 2 * std20
            if std20 > 0 and closes[-1] <= lower_band * 1.02:
                score += 1
                factors.append('BB Alt Band')

        detail = ' | '.join(factors) if factors else 'Sinyal yok'
        return {
            'signal': 'buy' if score >= min_score else '',
            'score':  score,
            'detail': detail,
        }
    except Exception as e:
        return {'signal': '', 'score': 0, 'detail': f'Hata: {e}'}


def check_smart_sell(client, symbol):
    """
    Satış sinyali kontrolü.
    Returns: {'signal': 'sell'|'', 'reason': str}
    """
    try:
        closes, _ = _get_klines(client, symbol, limit=30)
        if len(closes) < 15:
            return {'signal': '', 'reason': 'Yetersiz veri'}

        rsi = _rsi(closes)
        if rsi > 75:
            return {'signal': 'sell', 'reason': f'RSI={rsi} aşırı alım'}

        sma20 = sum(closes[-20:]) / 20
        if closes[-1] < sma20 * 0.98:
            return {'signal': 'sell', 'reason': 'Fiyat SMA20 altında'}

        std20 = (sum((c - sma20) ** 2 for c in closes[-20:]) / 20) ** 0.5
        upper_band = sma20 + 2 * std20
        if std20 > 0 and closes[-1] > upper_band:
            return {'signal': 'sell', 'reason': 'BB üst bandı aşıldı'}

        return {'signal': '', 'reason': ''}
    except Exception as e:
        return {'signal': '', 'reason': f'Hata: {e}'}
