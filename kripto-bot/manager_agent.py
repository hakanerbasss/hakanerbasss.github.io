"""
CEO Agent — Portföy Patron
────────────────────────────────────────────────────────────────
Her 30 dakikada bir açık pozisyonlara bakar.
DeepSeek gerçek piyasa verisini (mum, hacim, RSI, trend, BTC) görür
ve kendi kararını verir:

  sell_partial(symbol, pct, reason) — kısmi sat
  sell_all(symbol, reason)          — tamamını kapat
  set_agent_enabled(agent, bool)    — ajanı aç/kapat
  set_position_mult(value)          — pozisyon büyüklüğünü ayarla

Hiçbir hardcode eşik yok. Karar tamamen DeepSeek'e ait.
config.json → ceo_agent_enabled: true/false
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, load_positions,
                 get_price, send_telegram, get_usdt_balance,
                 get_client, execute_sell, update_position,
                 get_data_client)

STATE_FILE    = 'ceo_state.json'
DEEPSEEK_URL  = 'https://api.deepseek.com/chat/completions'
REVIEW_MIN    = 5    # dakika — kaç dakikada bir pozisyon gözden geçirilir


# ─── Araç Şemaları ────────────────────────────────────────────────────────────

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'sell_partial',
            'description': (
                'Bir pozisyonun belirtilen yüzdesini sat. '
                'Örnek kullanım: kâr zirveye çıktı geri çekildi, hacim düştü, '
                'RSI aşırı alımdan iniyor, mum yapısı zayıflıyor. '
                'Kalan pozisyon ajanda trail ile izlenmeye devam eder.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string', 'description': 'Sembol, örn: PORTALUSDT'},
                    'pct':    {'type': 'integer', 'description': 'Satılacak yüzde (10-90 arası)',
                               'minimum': 10, 'maximum': 90},
                    'reason': {'type': 'string', 'description': 'Kararın teknik gerekçesi'},
                },
                'required': ['symbol', 'pct', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'sell_all',
            'description': (
                'Pozisyonun tamamını kapat. '
                'Örnek: güçlü ters sinyal, kötüleşen hacim + fiyat, zarar yönetimi, '
                'BTC sert düşüş, ya da pozisyon çok uzun tutuldu ve momentum bitti.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string'},
                    'reason': {'type': 'string', 'description': 'Kararın teknik gerekçesi'},
                },
                'required': ['symbol', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_agent_enabled',
            'description': (
                'Bir ticaret ajanını aç veya kapat. '
                'Yalnızca yeterli işlem sayısında (>15) sürekli zarar eden ajana uygula. '
                'Tek kötü işleme bakıp kapatma. Piyasa koşuluna göre geçici kapatma yapma.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'agent':   {'type': 'string',
                                'enum': ['edge', 'otonom', 'indicator', 'wyckoff', 'breakout']},
                    'enabled': {'type': 'boolean'},
                },
                'required': ['agent', 'enabled'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_position_mult',
            'description': (
                'Tüm ajanların pozisyon büyüklüğü çarpanını ayarla (0.5–1.2). '
                'BTC güçlü bear trendinde küçült, bull trendinde normale döndür.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'value': {'type': 'number', 'description': '0.5 ile 1.2 arası'},
                },
                'required': ['value'],
            },
        },
    },
]


# ─── Araç Yürütücüleri ────────────────────────────────────────────────────────

_CEO_AGENTS = ['edge', 'otonom', 'indicator', 'wyckoff', 'breakout']


def _exec_sell_partial(symbol, pct, reason):
    try:
        client = get_client()
        pct    = max(10, min(90, int(pct)))
        res    = execute_sell(client, symbol, pct, source='CEO_PARTIAL', period='ceo')
        if res.get('ok'):
            pnl = res.get('pnl', 0)
            update_position(symbol,
                ceo_last_action=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                ceo_last_action_type=f'partial_{pct}pct')
            send_telegram(
                f'👔 <b>CEO Kısmi Sat</b>\n'
                f'🔶 {symbol} — %{pct} satıldı\n'
                f'💰 PnL: ${pnl:+.2f}\n'
                f'📝 {reason}'
            )
            return f'{symbol}: %{pct} satıldı, PnL ${pnl:+.2f}'
        else:
            return f'{symbol}: satış BAŞARISIZ — {res.get("error")}'
    except Exception as e:
        return f'{symbol}: hata — {e}'


def _exec_sell_all(symbol, reason):
    try:
        client = get_client()
        res    = execute_sell(client, symbol, 100, source='CEO_SELL', period='ceo')
        if res.get('ok'):
            pnl = res.get('pnl', 0)
            send_telegram(
                f'👔 <b>CEO Tam Sat</b>\n'
                f'🔴 {symbol} — tamamı kapatıldı\n'
                f'💰 PnL: ${pnl:+.2f}\n'
                f'📝 {reason}'
            )
            return f'{symbol}: tamamı kapatıldı, PnL ${pnl:+.2f}'
        else:
            return f'{symbol}: satış BAŞARISIZ — {res.get("error")}'
    except Exception as e:
        return f'{symbol}: hata — {e}'


def _exec_set_agent_enabled(agent, enabled):
    cfg = load_config()
    key = f'{agent}_enabled'
    old = cfg.get(key, True)
    if old == bool(enabled):
        return None
    if not enabled:
        others_on = sum(1 for a in _CEO_AGENTS
                        if a != agent and cfg.get(f'{a}_enabled', True))
        if others_on == 0:
            return f'{agent} kapatılMADI: son açık ajan'
    cfg[key] = bool(enabled)
    save_config(cfg)
    return f'{agent}_enabled: {old} → {bool(enabled)}'


def _exec_set_position_mult(value):
    value = round(max(0.5, min(1.2, float(value))), 2)
    cfg   = load_config()
    old   = cfg.get('ceo_position_mult', 1.0)
    if old == value:
        return None
    cfg['ceo_position_mult'] = value
    save_config(cfg)
    return f'ceo_position_mult: {old} → {value}'


def _execute_tool_calls(tool_calls):
    results = []
    for tc in tool_calls:
        name = tc['function']['name']
        try:
            args = json.loads(tc['function']['arguments'])
        except Exception as e:
            print(f'[CEO] Bozuk araç argümanı ({name}): {e}')
            continue
        try:
            if name == 'sell_partial':
                r = _exec_sell_partial(args['symbol'], args['pct'], args['reason'])
            elif name == 'sell_all':
                r = _exec_sell_all(args['symbol'], args['reason'])
            elif name == 'set_agent_enabled':
                r = _exec_set_agent_enabled(args['agent'], args['enabled'])
            elif name == 'set_position_mult':
                r = _exec_set_position_mult(args['value'])
            else:
                r = f'Bilinmeyen araç: {name}'
        except Exception as e:
            r = f'{name} hata: {e}'
        if r is not None:
            print(f'[CEO] Araç: {name} → {r}')
            results.append(r)
    return results


# ─── Piyasa Verisi ────────────────────────────────────────────────────────────

def _calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 1)


def _klines_full(symbol, interval='1h', limit=30):
    """OHLCV kline verisi — hacim dahil."""
    try:
        from binance.client import Client as BClient
        interval_map = {
            '1h': BClient.KLINE_INTERVAL_1HOUR,
            '4h': BClient.KLINE_INTERVAL_4HOUR,
        }
        kl = get_data_client().get_klines(
            symbol=symbol,
            interval=interval_map.get(interval, BClient.KLINE_INTERVAL_1HOUR),
            limit=limit + 1
        )
        kl = kl[:-1]   # son kapanmamış mumu çıkar
        opens   = [float(k[1]) for k in kl]
        highs   = [float(k[2]) for k in kl]
        lows    = [float(k[3]) for k in kl]
        closes  = [float(k[4]) for k in kl]
        volumes = [float(k[5]) for k in kl]
        return opens, highs, lows, closes, volumes
    except Exception as e:
        print(f'[CEO] klines hata ({symbol}): {e}')
        return None


def _position_analysis(symbol, entry_price, current_price):
    """Bir pozisyon için teknik analiz özeti."""
    data = _klines_full(symbol, '1h', 30)
    if data is None:
        return 'Veri alınamadı.'

    opens, highs, lows, closes, volumes = data
    n = len(closes)
    if n < 5:
        return 'Yetersiz mum.'

    rsi      = _calc_rsi(closes)
    sma20    = sum(closes[-20:]) / min(20, n)
    avg_vol  = sum(volumes[-20:]) / min(20, n)
    last_vol = volumes[-1]
    vol_x    = round(last_vol / avg_vol, 2) if avg_vol > 0 else 1.0

    chg_1h   = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if n >= 2 else 0
    chg_4h   = round((closes[-1] - closes[-5]) / closes[-5] * 100, 2) if n >= 5 else 0
    chg_24h  = round((closes[-1] - closes[-25]) / closes[-25] * 100, 2) if n >= 25 else 0

    trend = 'SMA20 ÜZERİNDE (YUKARI)' if closes[-1] > sma20 else 'SMA20 ALTINDA (ASAGI)'

    # Son 5 mum metin özeti
    candle_lines = []
    for i in range(-5, 0):
        o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], volumes[i]
        yön    = '🟢' if c >= o else '🔴'
        body   = round(abs(c - o) / o * 100, 2)
        wick_u = round((h - max(o, c)) / o * 100, 2)
        wick_d = round((min(o, c) - l) / o * 100, 2)
        vx     = round(v / avg_vol, 1) if avg_vol > 0 else 1.0
        candle_lines.append(
            f'  {yön} kapanış={c:.5g} gövde={body:.1f}% '
            f'üst-fitil={wick_u:.1f}% alt-fitil={wick_d:.1f}% hacim={vx:.1f}x'
        )

    lines = [
        f'RSI(14): {rsi}  |  Trend: {trend}',
        f'Değişim: 1s={chg_1h:+.2f}%  4s={chg_4h:+.2f}%  24s={chg_24h:+.2f}%',
        f'Hacim (son mum): {vol_x:.1f}x 20-periyot ortalaması',
        f'Son 5 saat mum:',
    ] + candle_lines

    # 4h RSI
    data4 = _klines_full(symbol, '4h', 20)
    if data4:
        _, _, _, c4, _ = data4
        rsi4 = _calc_rsi(c4)
        lines.append(f'RSI(14) 4s: {rsi4}')

    return '\n'.join(lines)


# ─── Veri Toplama ─────────────────────────────────────────────────────────────

def _collect_data():
    cfg       = load_config()
    trades    = load_trades()
    positions = load_positions()

    # Ajan bazında özet (son 100 işlem)
    agent_stats = {}
    for t in trades[-100:]:
        if t.get('type') != 'sell':
            continue
        source = t.get('source', 'UNKNOWN')
        if source.startswith('CEO'):
            continue
        agent  = ('EDGE'      if 'EDGE'      in source else
                  'INDICATOR' if 'INDICATOR' in source else
                  'WYCKOFF'   if 'WYCKOFF'   in source else
                  'BREAKOUT'  if 'BREAKOUT'  in source else 'OTONOM')
        if agent not in agent_stats:
            agent_stats[agent] = {'wins': 0, 'losses': 0, 'total_pnl': 0.0}
        pnl = t.get('pnl', 0)
        agent_stats[agent]['total_pnl'] = round(agent_stats[agent]['total_pnl'] + pnl, 2)
        if pnl > 0:
            agent_stats[agent]['wins'] += 1
        else:
            agent_stats[agent]['losses'] += 1

    # Açık pozisyonlar
    try:
        client   = get_client()
        balance  = get_usdt_balance(client)
        open_pos = []
        for sym, pos in positions.items():
            if pos.get('qty', 0) <= 0:
                continue
            try:
                price    = get_price(client, sym)
                avg      = pos.get('avg_price', price)
                qty      = pos.get('qty', 0)
                pct      = (price - avg) / avg * 100 if avg > 0 else 0
                peak     = pos.get('peak_price', avg)
                peak_pct = (peak - avg) / avg * 100 if avg > 0 else 0

                buy_time = pos.get('buy_time', '')
                hours_held = '?'
                if buy_time:
                    try:
                        dt = datetime.datetime.strptime(buy_time, '%Y-%m-%d %H:%M:%S')
                        hours_held = round((datetime.datetime.now() - dt).total_seconds() / 3600, 1)
                    except Exception:
                        pass

                open_pos.append({
                    'symbol':     sym,
                    'agent':      pos.get('agent', '?'),
                    'pct':        round(pct, 2),
                    'peak_pct':   round(peak_pct, 1),
                    'entry':      round(avg, 6),
                    'price':      round(price, 6),
                    'value':      round(price * qty, 2),
                    'hours_held': hours_held,
                    'ceo_action': pos.get('ceo_last_action_type', ''),
                })
            except Exception:
                pass
        pos_total = round(sum(p['value'] for p in open_pos), 2)
    except Exception:
        balance   = 0
        open_pos  = []
        pos_total = 0

    # BTC durumu
    try:
        btc_data = _klines_full('BTCUSDT', '1h', 25)
        if btc_data:
            _, _, _, btc_c, _ = btc_data
            sma20      = sum(btc_c[-20:]) / 20
            btc_pct    = round((btc_c[-1] - btc_c[-2]) / btc_c[-2] * 100, 2)
            btc_vs_sma = round((btc_c[-1] - sma20) / sma20 * 100, 2)
            btc_trend  = 'YUKARI' if btc_c[-1] > sma20 else 'ASAGI'
        else:
            btc_pct = 0; btc_vs_sma = 0; btc_trend = '?'
    except Exception:
        btc_pct = 0; btc_vs_sma = 0; btc_trend = '?'

    # Fear & Greed
    try:
        fg_r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
        fg   = int(fg_r.json()['data'][0]['value'])
    except Exception:
        fg = '?'

    return {
        'balance':        round(balance, 2),
        'pos_total':      pos_total,
        'total':          round(balance + pos_total, 2),
        'btc_trend':      btc_trend,
        'btc_pct_1h':     btc_pct,
        'btc_vs_sma':     btc_vs_sma,
        'open_positions': open_pos,
        'agent_stats':    agent_stats,
        'fg':             fg,
        'cfg':            cfg,
    }


# ─── Prompt ───────────────────────────────────────────────────────────────────

def _build_prompt(data):
    fg    = data['fg']
    lines = [
        "Sen bir kripto portföy yöneticisisin. Her 5 dakikada bir açık pozisyonları inceliyorsun.",
        "",
        "TEMEL KURAL: ZARAR ETME. Kâr al. Trend bitti mi çık. Hacim düştü mü çık.",
        "Her pozisyon için aktif karar ver. 'Bekleyeyim' deme — trend devam etmiyorsa çık.",
        "",
        "ELİNDEKİ ARAÇLAR (tam yetki):",
        "  sell_partial(symbol, pct, reason)",
        "    → Pozisyonun %pct'ini sat. Trend zayıflıyor ama devam edebilir. Kâr al.",
        "    → Örnek: peak kâr sonrası geri çekilme başladı → %40-60 sat, kalan trendle git",
        "  sell_all(symbol, reason)",
        "    → Tamamını kapat. Trend döndü, hacim bitti, RSI aşırı alımdan indi.",
        "    → Zararda uzun süredir hareket yok → çık, parasını daha iyi yere koy.",
        "  set_agent_enabled(agent, bool)",
        "    → Ajan sürekli zarar ediyorsa kapat.",
        "  set_position_mult(value)",
        "    → Piyasa kötüye gidiyorsa pozisyon büyüklüğünü küçült (0.5-1.0).",
        "",
        "KARAR VERME MANTIĞI (sırayla kontrol et):",
        "  1. Peak kâr vs şu anki kâr: Geri çekilme başladı mı? Ne kadar?",
        "     → Geri çekilme + hacim düşüşü = trend bitti → sat",
        "     → Geri çekilme ama hacim hâlâ yüksek = düzeltme → bekle veya kısmi sat",
        "  2. RSI: Aşırı alım (>70) sonrası düşüyor mu?",
        "     → RSI 70+ ve düşüş başladı → kısmi veya tam sat",
        "  3. Mum yapısı: Son 3 mumda ne görüyorsun?",
        "     → Uzun üst fitil + küçük gövde = satış baskısı → sat",
        "     → Ardışık kırmızı + azalan hacim = güç kaybı → sat",
        "  4. Trend: SMA20 üzerinde mi, altında mı?",
        "     → Fiyat SMA20 altına düştüyse trend kırıldı → sat",
        "  5. BTC: Piyasa geneli ne yapıyor?",
        "     → BTC sert düşüyorsa altcoin de düşer → daha agresif sat",
        "  6. Süre: Çok uzun tutulmuş, hareket yok mu?",
        "     → 12+ saat kârsız bekleme = sermaye dondurma → çık",
        "",
        "ZARAR YÖNETİMİ:",
        "  → Zarardaki pozisyon: trend hâlâ güçlüyse bekle, değilse hemen çık",
        "  → Uzun süredir zararda + düşen hacim = umut bekleme → çık",
        "  → Birden fazla zararda pozisyon varsa en kötüyü önce kes",
        "",
        f"=== PİYASA DURUMU ===",
        f"BTC: {data['btc_trend']} | 1s: {data['btc_pct_1h']:+.2f}% | SMA20: {data['btc_vs_sma']:+.2f}%",
        f"Korku/Açgözlülük: {fg}/100",
        f"USDT: ${data['balance']} | Pozisyonlarda: ${data['pos_total']} | Toplam: ${data['total']}",
        "",
    ]

    if data['open_positions']:
        lines.append("=== AÇIK POZİSYONLAR ===")
        for p in data['open_positions']:
            sym  = p['symbol']
            pct  = p['pct']
            icon = '🟢' if pct >= 0 else '🔴'
            ceo_note = f" | Son CEO eylem: {p['ceo_action']}" if p.get('ceo_action') else ''
            lines.append(f"\n{icon} {sym} [{p['agent']}]{ceo_note}")
            lines.append(
                f"   Giriş: ${p['entry']} → Şu an: ${p['price']} | "
                f"P&L: {pct:+.2f}% | Peak kâr: +{p['peak_pct']}% | Süredir: {p['hours_held']}s"
            )
            peak_gap = p['peak_pct'] - pct
            if peak_gap > 1:
                lines.append(f"   ⚠️ Peak'ten {peak_gap:.1f}% geri çekildi")
            lines.append("   Teknik:")
            analysis = _position_analysis(sym, p['entry'], p['price'])
            for al in analysis.split('\n'):
                lines.append(f"   {al}")
    else:
        lines.append("Açık pozisyon yok.")

    lines += ["", "=== AJAN PERFORMANSI (son 100 işlem) ==="]
    for agent, stats in data['agent_stats'].items():
        total = stats['wins'] + stats['losses']
        wr    = round(stats['wins'] / total * 100, 1) if total > 0 else 0
        lines.append(f"  {agent}: {total} işlem | %{wr} WR | PnL: ${stats['total_pnl']}")

    params = data.get('cfg', {})
    lines += [
        "",
        "=== AJAN DURUMU ===",
        f"  Otonom: {'AÇIK' if params.get('otonom_enabled', True) else 'KAPALI'} | "
        f"Breakout: {'AÇIK' if params.get('breakout_enabled', True) else 'KAPALI'} | "
        f"Indicator: {'AÇIK' if params.get('indicator_enabled', True) else 'KAPALI'}",
        f"  Pozisyon çarpanı: {params.get('ceo_position_mult', 1.0)}",
    ]

    return '\n'.join(lines)


# ─── DeepSeek API ─────────────────────────────────────────────────────────────

def _call_deepseek(prompt, api_key):
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type':  'application/json',
            },
            json={
                'model':       'deepseek-chat',
                'messages':    [{'role': 'user', 'content': prompt}],
                'tools':       TOOLS,
                'tool_choice': 'auto',
                'max_tokens':  1500,
                'temperature': 0.2,
            },
            timeout=60,
        )
        r.raise_for_status()
        msg        = r.json()['choices'][0]['message']
        content    = msg.get('content') or ''
        tool_calls = msg.get('tool_calls') or []
        return {'content': content.strip(), 'tool_calls': tool_calls}
    except Exception as e:
        print(f'[CEO] DeepSeek hata: {e}')
        return None


def _mark_ceo_success():
    cfg = load_config()
    cfg['ceo_last_success'] = time.time()
    save_config(cfg)


# ─── Rapor ────────────────────────────────────────────────────────────────────

def _send_report(response, tool_results, data):
    if response is None:
        send_telegram('⚠️ <b>CEO</b>: DeepSeek yanıt vermedi.')
        return

    open_count = len(data['open_positions'])
    lines = [
        '👔 <b>CEO Değerlendirme</b>',
        f'📊 Toplam: ${data["total"]} | Açık poz: {open_count} | BTC: {data["btc_trend"]}',
    ]

    if response.get('content'):
        lines += ['', f'📝 {response["content"]}']

    if tool_results:
        lines += ['', '⚙️ <b>Kararlar:</b>']
        for r in tool_results:
            lines.append(f'  ✅ {r}')
    elif open_count > 0:
        lines += ['', '⚙️ Müdahale gerekmedi — pozisyonlar tutuldu.']

    send_telegram('\n'.join(lines))


# ─── Ana Döngü ────────────────────────────────────────────────────────────────

_running = False
_thread  = None


def _interruptible_sleep(seconds):
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(15)


def _run_once(api_key):
    """Manuel tetikleme."""
    try:
        data         = _collect_data()
        prompt       = _build_prompt(data)
        response     = _call_deepseek(prompt, api_key)
        tool_results = _execute_tool_calls(response['tool_calls']) if response else []
        _send_report(response, tool_results, data)
        _mark_ceo_success()
        state = _load_state()
        state['review_count'] += 1
        state['last_review']   = datetime.datetime.now().isoformat()
        if tool_results:
            state.setdefault('changes_made', []).extend(tool_results)
            state['changes_made'] = state['changes_made'][-50:]
        _save_state(state)
    except Exception as e:
        send_telegram(f'⚠️ CEO manuel analiz hata: {e}')


def _run_loop():
    global _running
    state = _load_state()
    print(f'[CEO] Başladı — her {REVIEW_MIN} dakikada bir pozisyon analizi')
    send_telegram(
        f'👔 <b>CEO Agent AKTİF</b>\n'
        f'Her {REVIEW_MIN} dakikada açık pozisyonları analiz ediyorum.\n'
        f'Tam yetki: kısmi sat, tamamını sat, ajan yönetimi.\n'
        f'Öncelik: kârlı kapanma, trend takibi, zarar etme.'
    )

    while _running:
        cfg = load_config()
        if not cfg.get('ceo_agent_enabled', False):
            print('[CEO] Devre dışı bırakıldı, duruyorum.')
            _running = False
            break

        api_key  = cfg.get('deepseek_api_key', '')
        interval = cfg.get('ceo_interval_min', REVIEW_MIN)  # config'den override edilebilir

        if not api_key:
            print('[CEO] deepseek_api_key yok — analiz atlandı')
            _interruptible_sleep(interval * 60)
            continue

        try:
            data = _collect_data()

            # Açık pozisyon yoksa stratejik kontrol için kısa bekle
            if not data['open_positions']:
                print('[CEO] Açık pozisyon yok.')
                _interruptible_sleep(interval * 60)
                continue

            print(f'[CEO] Analiz #{state["review_count"] + 1} — {len(data["open_positions"])} açık poz')
            prompt       = _build_prompt(data)
            response     = _call_deepseek(prompt, api_key)
            tool_results = _execute_tool_calls(response['tool_calls']) if response else []
            _send_report(response, tool_results, data)
            _mark_ceo_success()

            state['review_count'] += 1
            state['last_review']   = datetime.datetime.now().isoformat()
            if tool_results:
                state.setdefault('changes_made', []).extend(tool_results)
                state['changes_made'] = state['changes_made'][-50:]
            _save_state(state)

        except Exception as e:
            print(f'[CEO] Analiz hata: {e}')

        _interruptible_sleep(interval * 60)


# ─── Public API ───────────────────────────────────────────────────────────────

def ceo_flag(cfg, key, default=True):
    """Ajanın açık/kapalı bayrağını döndür."""
    return cfg.get(key, default)


def start_ceo_agent():
    global _running, _thread
    if _running:
        return False
    _running = True
    _thread  = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()
    return True


def restart_ceo_agent():
    global _running, _thread
    _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)
    _running = True
    _thread = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()
    return True


def stop_ceo_agent():
    global _running
    _running = False
    cfg = load_config()
    cfg['otonom_enabled']       = True
    cfg['edge_enabled']         = True
    cfg['indicator_enabled']    = True
    cfg['wyckoff_enabled']      = True
    cfg['breakout_enabled']     = True
    cfg['accumulation_enabled'] = True
    cfg['ceo_position_mult']    = 1.0
    save_config(cfg)
    send_telegram(
        '👔 CEO Agent durduruldu.\n'
        '✅ Tüm ajanlar varsayılan duruma döndürüldü.'
    )


def ceo_agent_status():
    state = _load_state()
    cfg   = load_config()
    return {
        'running':       _running,
        'enabled':       cfg.get('ceo_agent_enabled', False),
        'review_count':  state.get('review_count', 0),
        'last_review':   state.get('last_review'),
        'interval_min':  cfg.get('ceo_interval_min', REVIEW_MIN),
    }


def trigger_ceo_review():
    """Manuel olarak analiz tetikle."""
    if not _running:
        return False
    cfg     = load_config()
    api_key = cfg.get('deepseek_api_key', '')
    if not api_key:
        send_telegram('⚠️ CEO: API key yok!')
        return False
    threading.Thread(target=lambda: _run_once(api_key), daemon=True).start()
    return True


def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {'review_count': 0, 'last_review': None, 'changes_made': []}


def _save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass
