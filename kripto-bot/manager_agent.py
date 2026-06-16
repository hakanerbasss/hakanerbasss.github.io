"""
CEO Agent — Portföy Yöneticisi
────────────────────────────────────────────────────────────────
Her 5 dakikada bir DeepSeek tüm portföyü görür ve karar verir.
Hiçbir kural yok — DeepSeek bir insan yönetici gibi hareket eder.
config.json → ceo_agent_enabled: true/false
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, load_positions,
                 get_price, send_telegram, get_usdt_balance,
                 get_client, execute_buy, execute_sell, update_position,
                 get_data_client)

STATE_FILE  = 'ceo_state.json'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
REVIEW_MIN  = 5   # dakika


# ─── Trail stop hesabı (breakout_agent ile senkron) ──────────────────────────

def _trail_distance(peak_pct):
    if peak_pct >= 40:   return 10.0
    if peak_pct >= 25:   return 6.0
    if peak_pct >= 10:   return 5.0
    return 3.0


# ─── Araç Şemaları ────────────────────────────────────────────────────────────

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'sell_partial',
            'description': 'Pozisyonun belirtilen yüzdesini sat.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string'},
                    'pct':    {'type': 'integer', 'minimum': 10, 'maximum': 90},
                    'reason': {'type': 'string'},
                },
                'required': ['symbol', 'pct', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'sell_all',
            'description': 'Pozisyonun tamamını kapat.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string'},
                    'reason': {'type': 'string'},
                },
                'required': ['symbol', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'buy_more',
            'description': 'Mevcut açık bir pozisyona ekleme yap (daha fazla al).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string'},
                    'usdt':   {'type': 'number', 'description': 'Eklenecek USDT miktarı'},
                    'reason': {'type': 'string'},
                },
                'required': ['symbol', 'usdt', 'reason'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_agent_enabled',
            'description': 'Bir ticaret ajanını aç veya kapat.',
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
            'description': 'Tüm ajanların pozisyon büyüklüğü çarpanını ayarla (0.3–1.5).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'value': {'type': 'number'},
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
            send_telegram(f'👔 <b>CEO Kısmi Sat</b>\n🔶 {symbol} %{pct}\n💰 PnL: ${pnl:+.2f}\n📝 {reason}')
            return f'{symbol}: %{pct} satıldı PnL ${pnl:+.2f}'
        return f'{symbol}: BAŞARISIZ — {res.get("error")}'
    except Exception as e:
        return f'{symbol}: hata — {e}'


def _exec_sell_all(symbol, reason):
    try:
        client = get_client()
        res    = execute_sell(client, symbol, 100, source='CEO_SELL', period='ceo')
        if res.get('ok'):
            pnl = res.get('pnl', 0)
            send_telegram(f'👔 <b>CEO Tam Sat</b>\n🔴 {symbol}\n💰 PnL: ${pnl:+.2f}\n📝 {reason}')
            return f'{symbol}: kapatıldı PnL ${pnl:+.2f}'
        return f'{symbol}: BAŞARISIZ — {res.get("error")}'
    except Exception as e:
        return f'{symbol}: hata — {e}'


def _exec_buy_more(symbol, usdt, reason):
    try:
        client    = get_client()
        positions = load_positions()
        if symbol not in positions or positions[symbol].get('qty', 0) <= 0:
            return f'{symbol}: açık pozisyon yok, ekleme iptal'
        res = execute_buy(client, symbol, float(usdt),
                          source='CEO_ADD', period='ceo_add',
                          agent=positions[symbol].get('agent', 'CEO'))
        if res.get('ok'):
            send_telegram(f'👔 <b>CEO Ekleme</b>\n🟢 {symbol} +${usdt}\n📝 {reason}')
            return f'{symbol}: +${usdt} eklendi'
        return f'{symbol}: ekleme BAŞARISIZ — {res.get("error")}'
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
    value = round(max(0.3, min(1.5, float(value))), 2)
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
            if   name == 'sell_partial':       r = _exec_sell_partial(args['symbol'], args['pct'], args['reason'])
            elif name == 'sell_all':           r = _exec_sell_all(args['symbol'], args['reason'])
            elif name == 'buy_more':           r = _exec_buy_more(args['symbol'], args['usdt'], args['reason'])
            elif name == 'set_agent_enabled':  r = _exec_set_agent_enabled(args['agent'], args['enabled'])
            elif name == 'set_position_mult':  r = _exec_set_position_mult(args['value'])
            else:                              r = f'Bilinmeyen araç: {name}'
        except Exception as e:
            r = f'{name} hata: {e}'
        if r is not None:
            print(f'[CEO] {name} → {r}')
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
    return round(100 - 100 / (1 + ag / al), 1) if al > 0 else 100.0


def _klines_full(symbol, interval='1h', limit=30):
    try:
        from binance.client import Client as BClient
        imap = {'1h': BClient.KLINE_INTERVAL_1HOUR, '4h': BClient.KLINE_INTERVAL_4HOUR,
                '15m': BClient.KLINE_INTERVAL_15MINUTE}
        kl = get_data_client().get_klines(
            symbol=symbol, interval=imap.get(interval, BClient.KLINE_INTERVAL_1HOUR),
            limit=limit + 1)
        kl = kl[:-1]
        opens   = [float(k[1]) for k in kl]
        highs   = [float(k[2]) for k in kl]
        lows    = [float(k[3]) for k in kl]
        closes  = [float(k[4]) for k in kl]
        volumes = [float(k[5]) for k in kl]
        return opens, highs, lows, closes, volumes
    except Exception as e:
        print(f'[CEO] klines hata ({symbol}): {e}')
        return None


def _position_market_block(symbol):
    """Bir pozisyon için tam teknik veri bloğu."""
    lines = []
    for tf, limit in (('1h', 30), ('4h', 20)):
        data = _klines_full(symbol, tf, limit)
        if not data:
            lines.append(f'  [{tf}] veri alınamadı')
            continue
        opens, highs, lows, closes, volumes = data
        n = len(closes)
        if n < 5:
            continue
        rsi     = _calc_rsi(closes)
        sma20   = sum(closes[-min(20, n):]) / min(20, n)
        avg_vol = sum(volumes[-min(20, n):]) / min(20, n)
        chg_1p  = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if n >= 2 else 0
        chg_5p  = round((closes[-1] - closes[-6]) / closes[-6] * 100, 2) if n >= 6 else 0
        trend   = 'SMA20 ÜZERİNDE' if closes[-1] > sma20 else 'SMA20 ALTINDA'
        high52  = max(closes[-min(n, limit):])
        low52   = min(closes[-min(n, limit):])

        lines.append(f'  [{tf}] RSI={rsi} | {trend} | son={closes[-1]:.5g} | yüksek={high52:.5g} | düşük={low52:.5g}')
        lines.append(f'        Değişim: son mum {chg_1p:+.2f}% | son 5 mum {chg_5p:+.2f}%')
        lines.append(f'        Hacim son/ort: {volumes[-1]:.0f}/{avg_vol:.0f} ({volumes[-1]/avg_vol:.1f}x)')

        # Son 5 mum
        candles = []
        for i in range(-min(5, n), 0):
            o, h, l, c, v = opens[i], highs[i], lows[i], closes[i], volumes[i]
            d   = '🟢' if c >= o else '🔴'
            bdy = round(abs(c - o) / o * 100, 2)
            wu  = round((h - max(o, c)) / o * 100, 2)
            wd  = round((min(o, c) - l) / o * 100, 2)
            vx  = round(v / avg_vol, 1) if avg_vol > 0 else 1.0
            candles.append(f'{d}gövde={bdy:.1f}%|üst={wu:.1f}%|alt={wd:.1f}%|vol={vx:.1f}x')
        lines.append(f'        Son mumlar: {" | ".join(candles)}')
    return '\n'.join(lines)


# ─── Veri Toplama ─────────────────────────────────────────────────────────────

def _collect_data():
    cfg       = load_config()
    trades    = load_trades()
    positions = load_positions()

    # Gerçekleşen toplam K/Z
    realized_pnl = round(sum(t.get('pnl', 0) for t in trades if t.get('type') == 'sell'), 2)

    # Son 50 işlem (tam log)
    recent_trades = []
    for t in reversed(trades[-50:]):
        if t.get('type') == 'buy':
            recent_trades.append(
                f"🛒 {t.get('time','?')} | {t.get('symbol','?')} [{t.get('source','?')}] "
                f"${t.get('usdt',0):.0f}"
            )
        elif t.get('type') == 'sell':
            pnl = t.get('pnl', 0)
            icon = '🟢' if pnl >= 0 else '🔴'
            recent_trades.append(
                f"{icon} {t.get('time','?')} | {t.get('symbol','?')} [{t.get('source','?')}] "
                f"PnL ${pnl:+.2f}"
            )

    # Ajan bazında istatistik
    agent_stats = {}
    for t in trades[-100:]:
        if t.get('type') != 'sell':
            continue
        src = t.get('source', 'UNKNOWN')
        if src.startswith('CEO'):
            continue
        ag = ('EDGE' if 'EDGE' in src else 'INDICATOR' if 'INDICATOR' in src
              else 'WYCKOFF' if 'WYCKOFF' in src else 'BREAKOUT' if 'BREAKOUT' in src
              else 'OTONOM')
        if ag not in agent_stats:
            agent_stats[ag] = {'wins': 0, 'losses': 0, 'pnl': 0.0}
        pnl = t.get('pnl', 0)
        agent_stats[ag]['pnl'] = round(agent_stats[ag]['pnl'] + pnl, 2)
        if pnl > 0: agent_stats[ag]['wins'] += 1
        else:       agent_stats[ag]['losses'] += 1

    # Açık pozisyonlar (trail stop hesabı dahil)
    try:
        client    = get_client()
        balance   = get_usdt_balance(client)
        open_pos  = []
        unrealized = 0.0

        for sym, pos in positions.items():
            if pos.get('qty', 0) <= 0:
                continue
            try:
                price    = get_price(client, sym)
                entry    = pos.get('avg_price', price)
                qty      = pos.get('qty', 0)
                pnl_abs  = (price - entry) * qty
                pnl_pct  = (price - entry) / entry * 100 if entry > 0 else 0
                peak     = pos.get('peak_price', entry)
                peak_pct = (peak - entry) / entry * 100 if entry > 0 else 0
                value    = price * qty
                unrealized += pnl_abs

                # Trail stop hesabı
                trail_active = pos.get('trail_active', False)
                trail_dist   = _trail_distance(peak_pct)
                trail_price  = peak * (1 - trail_dist / 100) if trail_active else None

                # Tutma süresi
                buy_time = pos.get('buy_time', '')
                hours_held = '?'
                if buy_time:
                    try:
                        dt = datetime.datetime.strptime(buy_time, '%Y-%m-%d %H:%M:%S')
                        hours_held = round((datetime.datetime.now() - dt).total_seconds() / 3600, 1)
                    except Exception:
                        pass

                open_pos.append({
                    'symbol':       sym,
                    'agent':        pos.get('agent', '?'),
                    'entry':        round(entry, 6),
                    'price':        round(price, 6),
                    'qty':          round(qty, 4),
                    'value':        round(value, 2),
                    'pnl_abs':      round(pnl_abs, 2),
                    'pnl_pct':      round(pnl_pct, 2),
                    'peak_price':   round(peak, 6),
                    'peak_pct':     round(peak_pct, 1),
                    'trail_active': trail_active,
                    'trail_dist':   trail_dist if trail_active else None,
                    'trail_price':  round(trail_price, 6) if trail_price else None,
                    'hours_held':   hours_held,
                    'ceo_action':   pos.get('ceo_last_action_type', ''),
                })
            except Exception:
                pass

        pos_total = round(sum(p['value'] for p in open_pos), 2)
    except Exception:
        balance = 0; open_pos = []; pos_total = 0; unrealized = 0.0

    # BTC
    try:
        btc_data = _klines_full('BTCUSDT', '1h', 25)
        if btc_data:
            _, _, _, btc_c, _ = btc_data
            sma20      = sum(btc_c[-20:]) / 20
            btc_pct_1h = round((btc_c[-1] - btc_c[-2]) / btc_c[-2] * 100, 2)
            btc_pct_4h = round((btc_c[-1] - btc_c[-5]) / btc_c[-5] * 100, 2) if len(btc_c) >= 5 else 0
            btc_trend  = 'YUKARI' if btc_c[-1] > sma20 else 'ASAGI'
            btc_price  = round(btc_c[-1], 2)
        else:
            btc_pct_1h = btc_pct_4h = 0; btc_trend = '?'; btc_price = 0
    except Exception:
        btc_pct_1h = btc_pct_4h = 0; btc_trend = '?'; btc_price = 0

    # Fear & Greed
    try:
        fg_r = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5)
        fg_val   = int(fg_r.json()['data'][0]['value'])
        fg_label = fg_r.json()['data'][0]['value_classification']
    except Exception:
        fg_val = '?'; fg_label = '?'

    return {
        'balance':       round(balance, 2),
        'pos_total':     pos_total,
        'total':         round(balance + pos_total, 2),
        'realized_pnl':  realized_pnl,
        'unrealized_pnl': round(unrealized, 2),
        'btc_price':     btc_price,
        'btc_trend':     btc_trend,
        'btc_pct_1h':    btc_pct_1h,
        'btc_pct_4h':    btc_pct_4h,
        'open_positions': open_pos,
        'agent_stats':   agent_stats,
        'recent_trades': recent_trades,
        'fg_val':        fg_val,
        'fg_label':      fg_label,
        'cfg':           cfg,
    }


# ─── Prompt ───────────────────────────────────────────────────────────────────

def _build_prompt(data):
    cfg = data['cfg']
    lines = [
        "Sen bir kripto portföy yöneticisisin. Aşağıdaki tüm veriyi görüyorsun.",
        "Araçların: sell_partial, sell_all, buy_more, set_agent_enabled, set_position_mult.",
        "Kendi kararını ver.",
        "",
        "=== PORTFÖY ÖZET ===",
        f"Serbest USDT: ${data['balance']}",
        f"Pozisyonlarda: ${data['pos_total']}",
        f"Toplam Değer: ${data['total']}",
        f"Gerçekleşen K/Z (tüm zamanlar): ${data['realized_pnl']:+.2f}",
        f"Kağıt K/Z (anlık): ${data['unrealized_pnl']:+.2f}",
        "",
        "=== PİYASA ===",
        f"BTC: ${data['btc_price']} | Trend: {data['btc_trend']} | 1s: {data['btc_pct_1h']:+.2f}% | 4s: {data['btc_pct_4h']:+.2f}%",
        f"Korku/Açgözlülük: {data['fg_val']}/100 ({data['fg_label']})",
        "",
    ]

    if data['open_positions']:
        lines.append("=== AÇIK POZİSYONLAR ===")
        for p in data['open_positions']:
            icon = '🟢' if p['pnl_pct'] >= 0 else '🔴'
            ceo  = f" | CEO geçmişi: {p['ceo_action']}" if p.get('ceo_action') else ''
            lines.append(f"\n{icon} {p['symbol']} [{p['agent']}]{ceo}")
            lines.append(f"   Giriş: ${p['entry']} | Anlık: ${p['price']} | Miktar: {p['qty']}")
            lines.append(f"   K/Z: {p['pnl_pct']:+.2f}% (${p['pnl_abs']:+.2f}) | Değer: ${p['value']}")
            lines.append(f"   Peak: ${p['peak_price']} (+{p['peak_pct']}%) | Peak'ten geri: {p['peak_pct'] - p['pnl_pct']:.1f}%")
            if p['trail_active']:
                lines.append(f"   Trail AKTIF: mesafe -%{p['trail_dist']}% → stop fiyatı ${p['trail_price']}")
            else:
                lines.append(f"   Trail henüz aktif değil (aktivasyon: +%3 kâr)")
            lines.append(f"   Tutulma süresi: {p['hours_held']} saat")
            lines.append("   Teknik:")
            lines.append(_position_market_block(p['symbol']))
    else:
        lines.append("Açık pozisyon yok.")

    lines += ["", "=== SON 50 İŞLEM (ALIM/SATIM GEÇMİŞİ) ==="]
    lines += data['recent_trades']

    lines += ["", "=== AJAN PERFORMANSI (son 100 işlem) ==="]
    for ag, st in data['agent_stats'].items():
        total = st['wins'] + st['losses']
        wr    = round(st['wins'] / total * 100, 1) if total > 0 else 0
        lines.append(f"  {ag}: {total} işlem | %{wr} kazanma | PnL: ${st['pnl']:+.2f}")

    lines += ["", "=== AJAN DURUMU ==="]
    for ag in _CEO_AGENTS:
        status = 'AÇIK' if cfg.get(f'{ag}_enabled', True) else 'KAPALI'
        lines.append(f"  {ag}: {status}")
    lines.append(f"  Pozisyon çarpanı: {cfg.get('ceo_position_mult', 1.0)}")

    return '\n'.join(lines)


# ─── DeepSeek API ─────────────────────────────────────────────────────────────

def _call_deepseek(prompt, api_key):
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model':       'deepseek-chat',
                'messages':    [{'role': 'user', 'content': prompt}],
                'tools':       TOOLS,
                'tool_choice': 'auto',
                'max_tokens':  2000,
                'temperature': 0.1,
            },
            timeout=60,
        )
        r.raise_for_status()
        msg = r.json()['choices'][0]['message']
        return {'content': (msg.get('content') or '').strip(),
                'tool_calls': msg.get('tool_calls') or []}
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
        f'💼 Toplam: ${data["total"]} | Kağıt K/Z: ${data["unrealized_pnl"]:+.2f} | BTC: {data["btc_trend"]}',
    ]
    if response.get('content'):
        lines += ['', f'📝 {response["content"]}']
    if tool_results:
        lines += ['', '⚙️ <b>Kararlar:</b>']
        for r in tool_results:
            lines.append(f'  ✅ {r}')
    elif open_count > 0:
        lines += ['', '⚙️ Müdahale gerekmedi.']
    send_telegram('\n'.join(lines))


# ─── Ana Döngü ────────────────────────────────────────────────────────────────

_running = False
_thread  = None


def _interruptible_sleep(seconds):
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(10)


def _run_once(api_key):
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
    interval = load_config().get('ceo_interval_min', REVIEW_MIN)
    print(f'[CEO] Başladı — her {interval} dakikada bir analiz')
    send_telegram(
        f'👔 <b>CEO Agent AKTİF</b>\n'
        f'Her {interval} dakikada tam portföy analizi.\n'
        f'Araçlar: kısmi sat, tamamını sat, ekleme yap, ajan yönetimi.'
    )

    while _running:
        cfg = load_config()
        if not cfg.get('ceo_agent_enabled', False):
            print('[CEO] Devre dışı.')
            _running = False
            break

        interval = cfg.get('ceo_interval_min', REVIEW_MIN)
        api_key  = cfg.get('deepseek_api_key', '')

        if not api_key:
            print('[CEO] deepseek_api_key yok')
            _interruptible_sleep(interval * 60)
            continue

        try:
            data = _collect_data()
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
    for ag in _CEO_AGENTS:
        cfg[f'{ag}_enabled'] = True
    cfg['accumulation_enabled'] = True
    cfg['ceo_position_mult']    = 1.0
    save_config(cfg)
    send_telegram('👔 CEO durduruldu. Tüm ajanlar varsayılan duruma döndü.')


def ceo_agent_status():
    state = _load_state()
    cfg   = load_config()
    return {
        'running':      _running,
        'enabled':      cfg.get('ceo_agent_enabled', False),
        'review_count': state.get('review_count', 0),
        'last_review':  state.get('last_review'),
        'interval_min': cfg.get('ceo_interval_min', REVIEW_MIN),
    }


def trigger_ceo_review():
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
