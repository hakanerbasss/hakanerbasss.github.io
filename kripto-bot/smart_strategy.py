"""
Smart Composite Indicator
4 bağımsız faktörden min_score tanesi yeşilse → alım sinyali.

Faktörler:
  1. Order Book  : Anlık bid/ask hacim oranı > 1.2 (alım baskısı dominant)
  2. Funding Rate: Futures funding < 0.01% (market over-longed değil)
  3. Volume      : Son tamamlanan mum hacmi > 1.5× 20 mumluk ortalama
  4. RSI(14)     : 30-65 arası (ne aşırı alım ne panik satış bölgesi)

Satış sinyali: RSI > 72 (aşırı alım)
"""

from binance.client import Client


def _order_book_score(client, symbol, limit=100):
    ob = client.get_order_book(symbol=symbol, limit=limit)
    bid_vol = sum(float(b[1]) for b in ob['bids'])
    ask_vol = sum(float(a[1]) for a in ob['asks'])
    ratio = bid_vol / (ask_vol + 1e-9)
    return (1 if ratio > 1.2 else 0), round(ratio, 2)


def _funding_score(client, symbol):
    try:
        rates = client.futures_funding_rate(symbol=symbol, limit=1)
        if rates:
            fr = float(rates[-1]['fundingRate'])
            return (1 if fr < 0.0001 else 0), round(fr * 100, 4)
        return 0, None
    except Exception:
        return 0, None


def _volume_score(client, symbol, lookback=20):
    klines = client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_1HOUR,
        limit=lookback + 2
    )
    # Son mum henüz kapanmadı — çıkar
    completed = klines[:-1]
    vols = [float(k[5]) for k in completed]
    if len(vols) < 2:
        return 0, None
    current = vols[-1]
    avg = sum(vols[:-1]) / len(vols[:-1])
    ratio = current / (avg + 1e-9)
    return (1 if ratio > 1.5 else 0), round(ratio, 2)


def _rsi_score(closes, period=14):
    if len(closes) < period + 1:
        return 0, None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = round(rsi, 1)
    return (1 if 30 <= rsi <= 65 else 0), rsi


def check_smart_signal(client, symbol, min_score=3):
    """
    Composite alım sinyali.
    Döndürür: {'signal': 'buy'|None, 'score': int, 'detail': str}
    """
    try:
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, symbol, '1h', limit=60)

        ob_s,  ob_v  = _order_book_score(client, symbol)
        fr_s,  fr_v  = _funding_score(client, symbol)
        vol_s, vol_v = _volume_score(client, symbol)
        rsi_s, rsi_v = _rsi_score(closes)

        scores = [ob_s, fr_s, vol_s, rsi_s]
        labels = ['OrderBook', 'Funding', 'Volume', 'RSI']
        values = [ob_v, fr_v, vol_v, rsi_v]
        total  = sum(scores)

        detail = ' | '.join(
            f'{l}:{"🟢" if s else "🔴"}({v})'
            for l, s, v in zip(labels, scores, values)
        )

        if total >= min_score:
            return {'signal': 'buy', 'score': total, 'detail': detail}
        return {'signal': None, 'score': total, 'detail': detail}

    except Exception as e:
        return {'signal': None, 'score': 0, 'detail': f'Hata: {e}'}


def check_smart_sell(client, symbol):
    """
    RSI > 72 → aşırı alım → sat.
    Döndürür: {'signal': 'sell'|None, 'reason': str}
    """
    try:
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, symbol, '1h', limit=60)
        _, rsi = _rsi_score(closes)
        if rsi is not None and rsi > 72:
            return {'signal': 'sell', 'reason': f'RSI aşırı alım ({rsi})'}
        return {'signal': None, 'reason': f'RSI normal ({rsi})'}
    except Exception as e:
        return {'signal': None, 'reason': f'Hata: {e}'}
