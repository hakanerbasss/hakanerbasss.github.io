"""
Smart Composite Indicator
4 bağımsız faktörden min_score tanesi yeşilse → alım sinyali.

Faktörler:
  1. Mum Formasyonu : Çekiç / Ters Çekiç / Yutan / Sabah Yıldızı (backtestlenebilir)
  2. Funding Rate   : Futures funding < 0.01% (market over-longed değil)
  3. Volume         : Son mum hacmi > 1.5× 20 mumluk ortalama (backtestlenebilir)
  4. RSI(14)        : 30-65 arası — ne aşırı alım ne panik satış (backtestlenebilir)

Satış sinyali: RSI > 72 (aşırı alım)
"""

from binance.client import Client


# ── Mum Formasyonu ────────────────────────────────

def _get_candles(client, symbol, limit=5):
    klines = client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_1HOUR,
        limit=limit + 1
    )
    completed = klines[:-1]  # son kapanmamış mumu çıkar
    return [
        {'o': float(k[1]), 'h': float(k[2]), 'l': float(k[3]), 'c': float(k[4])}
        for k in completed
    ]


def detect_bullish_pattern(candles):
    """
    Yükseliş dönüş formasyonları:
      - Çekiç         : Uzun alt fitil, küçük gövde
      - Ters Çekiç    : Uzun üst fitil, küçük gövde
      - Yutan         : Yeşil mum kırmızı mumu yutar
      - Sabah Yıldızı : Kırmızı → Küçük mum → Yeşil (3 mum)
    Returns: (score: 0|1, pattern_name: str)
    """
    if len(candles) < 3:
        return 0, 'Veri yetersiz'

    curr  = candles[-1]
    prev  = candles[-2]
    prev2 = candles[-3]

    o,  h,  l,  c  = curr['o'],  curr['h'],  curr['l'],  curr['c']
    po, ph, pl, pc = prev['o'],  prev['h'],  prev['l'],  prev['c']
    p2o, p2c       = prev2['o'], prev2['c']

    body       = abs(c - o)
    rng        = h - l
    if rng < 1e-12:
        return 0, 'Düz mum'

    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    # Çekiç: uzun alt fitil ≥ 2× gövde, üst fitil küçük
    if (body > 0
            and lower_wick >= 2.0 * body
            and upper_wick <= 0.5 * body
            and lower_wick / rng >= 0.55):
        return 1, 'Çekiç'

    # Ters Çekiç: uzun üst fitil ≥ 2× gövde, alt fitil küçük
    if (body > 0
            and upper_wick >= 2.0 * body
            and lower_wick <= 0.5 * body
            and upper_wick / rng >= 0.55):
        return 1, 'Ters Çekiç'

    # Bullish Engulfing: önceki kırmızı → şimdiki yeşil ve tamamen yutar
    if (pc < po          # önceki mum kırmızı
            and c > o    # şimdiki mum yeşil
            and o <= pc  # açılış ≤ önceki kapanış
            and c >= po):  # kapanış ≥ önceki açılış
        return 1, 'Yutan Formasyonu'

    # Sabah Yıldızı: kırmızı → küçük gövde → yeşil (orta noktanın üstüne çıkar)
    mid_body  = abs(pc - po)
    prev_body = abs(p2c - p2o)
    if (p2c < p2o                           # prev2 kırmızı
            and prev_body > 0
            and mid_body < prev_body * 0.35  # prev küçük gövde
            and c > o                        # şimdiki yeşil
            and c > (p2o + p2c) / 2):        # orta noktanın üstünde kapandı
        return 1, 'Sabah Yıldızı'

    return 0, 'Yok'


def _candle_pattern_score(client, symbol):
    try:
        candles = _get_candles(client, symbol, limit=5)
        score, name = detect_bullish_pattern(candles)
        return score, name
    except Exception as e:
        return 0, f'Hata:{e}'


# ── Funding Rate ──────────────────────────────────

def _funding_score(client, symbol):
    try:
        rates = client.futures_funding_rate(symbol=symbol, limit=1)
        if rates:
            fr = float(rates[-1]['fundingRate'])
            return (1 if fr < 0.0001 else 0), round(fr * 100, 4)
        return 0, None
    except Exception:
        return 0, None


# ── Volume ────────────────────────────────────────

def _volume_score(client, symbol, lookback=20):
    klines = client.get_klines(
        symbol=symbol,
        interval=Client.KLINE_INTERVAL_1HOUR,
        limit=lookback + 2
    )
    completed = klines[:-1]
    vols = [float(k[5]) for k in completed]
    if len(vols) < 2:
        return 0, None
    current = vols[-1]
    avg     = sum(vols[:-1]) / len(vols[:-1])
    ratio   = current / (avg + 1e-9)
    return (1 if ratio > 1.5 else 0), round(ratio, 2)


# ── RSI ───────────────────────────────────────────

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
        rs  = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = round(rsi, 1)
    return (1 if 30 <= rsi <= 65 else 0), rsi


# ── Ana sinyal fonksiyonları ──────────────────────

def check_smart_signal(client, symbol, min_score=3):
    """
    Composite alım sinyali — 4 faktörden min_score tanesi yeşilse al.
    Döndürür: {'signal': 'buy'|None, 'score': int, 'detail': str}
    """
    try:
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, symbol, '1h', limit=60)

        pat_s, pat_v = _candle_pattern_score(client, symbol)
        fr_s,  fr_v  = _funding_score(client, symbol)
        vol_s, vol_v = _volume_score(client, symbol)
        rsi_s, rsi_v = _rsi_score(closes)

        scores = [pat_s, fr_s,  vol_s, rsi_s]
        labels = ['Formasyon', 'Funding', 'Volume', 'RSI']
        values = [pat_v, fr_v,  vol_v, rsi_v]
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
    """RSI > 72 → aşırı alım → sat."""
    try:
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, symbol, '1h', limit=60)
        _, rsi = _rsi_score(closes)
        if rsi is not None and rsi > 72:
            return {'signal': 'sell', 'reason': f'RSI aşırı alım ({rsi})'}
        return {'signal': None, 'reason': f'RSI normal ({rsi})'}
    except Exception as e:
        return {'signal': None, 'reason': f'Hata: {e}'}
