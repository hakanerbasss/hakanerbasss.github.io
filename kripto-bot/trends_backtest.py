"""
Google Trends vs Binance Price Correlation Backtest
Hipotez: Arama hacmi pumpa 3-7 gün önceden artar mı?
"""

import time
import datetime
import numpy as np

try:
    from pytrends.request import TrendReq
    PYTRENDS_OK = True
except ImportError:
    PYTRENDS_OK = False
    print('[HATA] pytrends kurulu değil: pip install pytrends')

try:
    from binance.client import Client
    BINANCE_OK = True
except ImportError:
    BINANCE_OK = False
    print('[HATA] python-binance kurulu değil')

# ---------- Bilinen pump olayları (coin, pump başlangıç tarihi, pump boyutu) ----------
PUMP_EVENTS = [
    # Coin adı, Binance sembolü, Trends keyword, pump başlangıcı, tahmini pik
    {'coin': 'PEPE',  'sym': 'PEPEUSDT',  'kw': 'PEPE coin',  'start': '2023-04-14', 'peak': '2023-05-05'},
    {'coin': 'WIF',   'sym': 'WIFUSDT',   'kw': 'WIF crypto', 'start': '2024-01-10', 'peak': '2024-03-15'},
    {'coin': 'BONK',  'sym': 'BONKUSDT',  'kw': 'BONK coin',  'start': '2023-12-01', 'peak': '2023-12-25'},
    {'coin': 'SHIB',  'sym': 'SHIBUSDT',  'kw': 'Shiba Inu',  'start': '2021-10-01', 'peak': '2021-10-28'},
    {'coin': 'DOGE',  'sym': 'DOGEUSDT',  'kw': 'Dogecoin',   'start': '2021-04-01', 'peak': '2021-05-08'},
]

LEAD_DAYS_TEST = [1, 2, 3, 5, 7, 10, 14]  # kaç gün önceden arıyoruz


def get_binance_daily(sym, start_str, end_str):
    """Binance günlük kapanış fiyatları (API key gereksiz, public)"""
    import requests
    start_dt = datetime.datetime.strptime(start_str, '%Y-%m-%d')
    end_dt   = datetime.datetime.strptime(end_str,   '%Y-%m-%d')
    # 60 gün önce başla
    from_dt = start_dt - datetime.timedelta(days=30)
    to_dt   = end_dt   + datetime.timedelta(days=10)

    url = 'https://api.binance.com/api/v3/klines'
    params = {
        'symbol':    sym,
        'interval':  '1d',
        'startTime': int(from_dt.timestamp() * 1000),
        'endTime':   int(to_dt.timestamp()   * 1000),
        'limit':     200,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    prices = {}
    for row in data:
        ts  = row[0] // 1000
        dt  = datetime.datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d')
        prices[dt] = float(row[4])  # kapanış
    return prices


def get_trends_weekly(keyword, start_str, end_str):
    """pytrends: haftalık arama hacmi (günlük genelde 0 döner uzak tarihler için)"""
    if not PYTRENDS_OK:
        return {}
    # 90 günden fazla aralıkta trends haftalık verir
    start_dt = datetime.datetime.strptime(start_str, '%Y-%m-%d') - datetime.timedelta(days=30)
    end_dt   = datetime.datetime.strptime(end_str,   '%Y-%m-%d') + datetime.timedelta(days=14)

    timeframe = f"{start_dt.strftime('%Y-%m-%d')} {end_dt.strftime('%Y-%m-%d')}"
    try:
        pt = TrendReq(hl='en-US', tz=0, timeout=(10, 25))
        pt.build_payload([keyword], timeframe=timeframe, geo='')
        df = pt.interest_over_time()
        if df.empty:
            return {}
        result = {}
        for idx, row in df.iterrows():
            result[idx.strftime('%Y-%m-%d')] = int(row[keyword])
        return result
    except Exception as e:
        print(f'  [Trends hata] {keyword}: {e}')
        return {}


def nearest_trends_value(trends_data, date_str, window=7):
    """Verilen tarihe en yakın trends değerini döner (±window gün)"""
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    best_val  = None
    best_diff = 9999
    for k, v in trends_data.items():
        kdt  = datetime.datetime.strptime(k, '%Y-%m-%d')
        diff = abs((kdt - dt).days)
        if diff <= window and diff < best_diff:
            best_diff = diff
            best_val  = v
    return best_val


def price_change_pct(prices, from_date, to_date):
    """İki tarih arasındaki fiyat değişimi %"""
    p1 = prices.get(from_date)
    p2 = prices.get(to_date)
    if p1 and p2 and p1 > 0:
        return (p2 - p1) / p1 * 100
    return None


def analyze_event(ev):
    print(f"\n{'='*60}")
    print(f"  {ev['coin']}  |  pump: {ev['start']} → {ev['peak']}")
    print(f"{'='*60}")

    # 1. Binance fiyatları
    try:
        prices = get_binance_daily(ev['sym'], ev['start'], ev['peak'])
        pump_start_price = prices.get(ev['start'])
        pump_peak_price  = prices.get(ev['peak'])
        if pump_start_price and pump_peak_price:
            total_pump = (pump_peak_price - pump_start_price) / pump_start_price * 100
            print(f"  Fiyat: ${pump_start_price:.6f} → ${pump_peak_price:.6f}  (+%{total_pump:.0f})")
        else:
            print(f"  Fiyat verisi eksik ({ev['sym']})")
            total_pump = None
    except Exception as e:
        print(f'  Binance hatası: {e}')
        prices = {}
        total_pump = None

    time.sleep(1)

    # 2. Google Trends
    print(f"  Trends çekiliyor: '{ev['kw']}'...")
    trends = get_trends_weekly(ev['kw'], ev['start'], ev['peak'])
    if trends:
        print(f"  Trends veri sayısı: {len(trends)} nokta")
    else:
        print('  Trends verisi alınamadı (boş)')
        return None

    time.sleep(2)  # rate limit

    # 3. Trends değerleri: pump başından N gün önce
    results = {}
    trend_at_pump   = nearest_trends_value(trends, ev['start'], window=7)
    trend_at_peak   = nearest_trends_value(trends, ev['peak'],  window=7)

    print(f"  Trends @ pump başı ({ev['start']}): {trend_at_pump}")
    print(f"  Trends @ peak     ({ev['peak']}):  {trend_at_peak}")

    for lead in LEAD_DAYS_TEST:
        lead_date = (datetime.datetime.strptime(ev['start'], '%Y-%m-%d')
                     - datetime.timedelta(days=lead)).strftime('%Y-%m-%d')
        trend_lead  = nearest_trends_value(trends, lead_date, window=7)
        price_change = price_change_pct(prices, lead_date, ev['peak'])

        if trend_lead is not None and trend_at_pump is not None and trend_at_pump > 0:
            trend_change = (trend_at_pump - trend_lead) / max(trend_lead, 1) * 100
        else:
            trend_change = None

        results[lead] = {
            'lead_date':    lead_date,
            'trend_lead':   trend_lead,
            'trend_start':  trend_at_pump,
            'trend_change': trend_change,
            'price_change': price_change,
        }
        sign = '↑' if (trend_change or 0) > 10 else ('→' if (trend_change or 0) > -10 else '↓')
        print(f"  {lead:2d} gün önce ({lead_date}): trends={trend_lead} {sign}  fiyat o günden pike: {price_change:.0f}%" if price_change else f"  {lead:2d} gün önce ({lead_date}): trends={trend_lead}")

    return {
        'coin':        ev['coin'],
        'total_pump':  total_pump,
        'trend_start': trend_at_pump,
        'trend_peak':  trend_at_peak,
        'leads':       results,
    }


def summarize(all_results):
    print(f"\n{'='*60}")
    print("  ÖZET: Arama hacmi pump'tan kaç gün önce yükseliyor?")
    print(f"{'='*60}")

    lead_scores = {lead: [] for lead in LEAD_DAYS_TEST}

    for r in all_results:
        if not r:
            continue
        for lead, data in r['leads'].items():
            tc = data.get('trend_change')
            if tc is not None:
                lead_scores[lead].append(tc)

    print(f"\n  {'Önceki gün':>12} | {'Ort. Trend Değişimi':>20} | {'Pozitif Oran':>14}")
    print(f"  {'-'*12}-+-{'-'*20}-+-{'-'*14}")
    for lead in LEAD_DAYS_TEST:
        vals = lead_scores[lead]
        if not vals:
            continue
        avg    = np.mean(vals)
        pos_rt = sum(1 for v in vals if v > 5) / len(vals) * 100
        bar    = '█' * int(max(avg, 0) / 5)
        print(f"  {lead:>10} gün | {avg:>+19.1f}% | {pos_rt:>13.0f}%  {bar}")

    print()
    best_lead = max(LEAD_DAYS_TEST, key=lambda l: np.mean(lead_scores[l]) if lead_scores[l] else -999)
    best_avg  = np.mean(lead_scores[best_lead]) if lead_scores[best_lead] else 0
    print(f"  En iyi öngörü süresi: {best_lead} GÜN ÖNCE  (ort. +{best_avg:.0f}% trend artışı)")

    if best_avg > 20:
        print("\n  SONUÇ: ✅ GÜÇLÜ korelasyon — Trends bota entegre edilmeli!")
    elif best_avg > 5:
        print("\n  SONUÇ: ⚠️  ZAYIF korelasyon — ek filtrelerle kullanılabilir")
    else:
        print("\n  SONUÇ: ❌ Korelasyon yok — Trends bu varlıklar için güvenilir değil")


if __name__ == '__main__':
    print("Google Trends vs Binance Pump Korelasyon Testi")
    print(f"Test edilen coinler: {[e['coin'] for e in PUMP_EVENTS]}")
    print(f"Başlıyor...\n")

    all_results = []
    for ev in PUMP_EVENTS:
        res = analyze_event(ev)
        all_results.append(res)
        time.sleep(3)  # pytrends rate limit

    summarize(all_results)
