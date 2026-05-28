"""
CEO Agent — Yönetici Yapay Zeka
────────────────────────────────────────────────────────────────
• Her N saatte bir tüm ajanların performansını analiz eder
• DeepSeek function calling ile araç tabanlı karar verir
• 5 araç: set_agent_enabled, set_position_mult,
          close_position, partial_take_profit, set_stop_loss
• config.json → ceo_agent_enabled: true/false ile açılır
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, load_positions,
                 save_positions, get_price, send_telegram, get_usdt_balance,
                 get_client, execute_sell)

STATE_FILE   = 'ceo_state.json'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
DEFAULT_INTERVAL = 1   # saat

# ─── Araç Şemaları ────────────────────────────────────────────────────────────

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'set_agent_enabled',
            'description': 'Bir ticaret ajanını aç veya kapat. Sadece sürekli zarar eden ajanlara uygula.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'agent':   {'type': 'string', 'enum': ['edge', 'otonom', 'indicator', 'wyckoff']},
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
            'description': 'Tüm ajanların pozisyon büyüklüğü çarpanını ayarla (0.3–1.5). Bear trendinde düşür.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'value': {'type': 'number', 'description': '0.3 ile 1.5 arası'},
                },
                'required': ['value'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'close_position',
            'description': 'Açık bir pozisyonu tamamen kapat (piyasa fiyatından sat).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string', 'description': 'Örn: XLMUSDT'},
                },
                'required': ['symbol'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'partial_take_profit',
            'description': 'Açık pozisyonun bir kısmını sat, kalanı tut (kademeli kâr alma).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol':   {'type': 'string',  'description': 'Örn: XLMUSDT'},
                    'fraction': {'type': 'number',  'description': '0.1–0.9 arası, örn 0.5 = yarısını sat'},
                },
                'required': ['symbol', 'fraction'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'set_stop_loss',
            'description': "Açık pozisyonun stop-loss yüzdesini güncelle (giriş fiyatına göre %).",
            'parameters': {
                'type': 'object',
                'properties': {
                    'symbol': {'type': 'string', 'description': 'Örn: XLMUSDT'},
                    'pct':    {'type': 'number', 'description': 'Giriş fiyatından % düşüş, örn 3.0 = %3 SL'},
                },
                'required': ['symbol', 'pct'],
            },
        },
    },
]


# ─── Araç Yürütücüleri ────────────────────────────────────────────────────────

def _exec_set_agent_enabled(agent, enabled):
    cfg = load_config()
    key = f'{agent}_enabled'
    old = cfg.get(key, True)
    if old == bool(enabled):
        return None  # değişiklik yok
    cfg[key] = bool(enabled)
    save_config(cfg)
    return f'{agent}_enabled: {old} → {bool(enabled)}'


def _exec_set_position_mult(value):
    value = round(max(0.3, min(1.5, float(value))), 2)
    cfg   = load_config()
    old   = cfg.get('ceo_position_mult', 1.0)
    if old == value:
        return None  # değişiklik yok
    cfg['ceo_position_mult'] = value
    save_config(cfg)
    return f'ceo_position_mult: {old} → {value}'


def _resolve_symbol(symbol):
    """positions.json'daki gerçek sembol anahtarını bul (0/O karışıklığına karşı)."""
    positions = load_positions()
    s = symbol.upper()
    if s in positions:
        return s
    # 0 ↔ O karışıklığını gider
    normalized = s.replace('0', 'O')
    for key in positions:
        if key.upper().replace('0', 'O') == normalized:
            return key
    return s  # bulunamazsa orijinali döndür


def _exec_close_position(symbol):
    real = _resolve_symbol(symbol)
    try:
        client = get_client()
        result = execute_sell(client, real, 100, source='CEO_KAPAT')
        if result.get('ok'):
            return f'{real} tamamen kapatıldı'
        return f'{real} kapatma başarısız: {result.get("error", "?")}'
    except Exception as e:
        return f'{real} kapatma hata: {e}'


def _exec_partial_take_profit(symbol, fraction):
    real     = _resolve_symbol(symbol)
    fraction = max(0.1, min(0.9, float(fraction)))
    pct      = round(fraction * 100, 1)
    try:
        client = get_client()
        result = execute_sell(client, real, pct, source='CEO_KISMI_KAR')
        if result.get('ok'):
            return f'{symbol} %{pct} satıldı (kısmi kâr)'
        return f'{symbol} kısmi satış başarısız: {result.get("error", "?")}'
    except Exception as e:
        return f'{symbol} kısmi satış hata: {e}'


def _exec_set_stop_loss(symbol, pct):
    real = _resolve_symbol(symbol)
    pct  = max(0.5, min(15.0, float(pct)))
    try:
        positions = load_positions()
        if real not in positions:
            return f'{real} açık pozisyon yok'
        old = positions[real].get('sl_pct', '?')
        positions[real]['sl_pct'] = pct
        save_positions(positions)
        return f'{real} SL: {old} → %{pct}'
    except Exception as e:
        return f'{symbol} SL güncelleme hata: {e}'


def _execute_tool_calls(tool_calls):
    """Modelin istediği araç çağrılarını sırayla yürüt."""
    results = []
    for tc in tool_calls:
        name = tc['function']['name']
        try:
            args = json.loads(tc['function']['arguments'])
        except Exception:
            continue
        try:
            if name == 'set_agent_enabled':
                r = _exec_set_agent_enabled(args['agent'], args['enabled'])
            elif name == 'set_position_mult':
                r = _exec_set_position_mult(args['value'])
            elif name == 'close_position':
                r = _exec_close_position(args['symbol'])
            elif name == 'partial_take_profit':
                r = _exec_partial_take_profit(args['symbol'], args['fraction'])
            elif name == 'set_stop_loss':
                r = _exec_set_stop_loss(args['symbol'], args['pct'])
            else:
                r = f'Bilinmeyen araç: {name}'
        except Exception as e:
            r = f'{name} hata: {e}'
        if r is not None:
            print(f'[CEO] Araç: {name} → {r}')
            results.append(r)
    return results


# ─── Teknik Analiz Yardımcıları ──────────────────────────────────────────────

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


def _position_technicals(client, symbol):
    """RSI, trend, değişim ve bearish/bullish divergence hesapla."""
    from signal_engine import get_klines
    result = {}
    for tf, lookback in (('1h', 4), ('4h', 3)):
        try:
            closes, _, _, _ = get_klines(client, symbol, tf, limit=35)
            sma       = sum(closes[-20:]) / min(20, len(closes))
            rsi_now   = _calc_rsi(closes)
            rsi_prev  = _calc_rsi(closes[:-5])   # 5 mum önceki RSI
            trend     = 'YUKARI' if closes[-1] > sma else 'ASAGI'
            chg       = round((closes[-1] - closes[-lookback]) / closes[-lookback] * 100, 2) if len(closes) >= lookback else 0

            # Bearish divergence: fiyat higher high ama RSI lower high
            divergence = None
            if rsi_now is not None and rsi_prev is not None:
                price_up = closes[-1] > closes[-6]
                rsi_down = rsi_now < rsi_prev
                if price_up and rsi_down:
                    divergence = 'BEARISH'   # momentum zayıflıyor
                elif (not price_up) and (not rsi_down):
                    divergence = 'BULLISH'   # düşüşe rağmen RSI yükseliyor

            result[tf] = {'rsi': rsi_now, 'trend': trend, 'chg': chg, 'div': divergence}
        except Exception:
            result[tf] = None
    return result


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
        agent  = ('EDGE'      if 'EDGE'      in source else
                  'INDICATOR' if 'INDICATOR' in source else
                  'WYCKOFF'   if 'WYCKOFF'   in source else 'OTONOM')
        if agent not in agent_stats:
            agent_stats[agent] = {'wins': 0, 'losses': 0, 'total_pnl': 0.0, 'trades': []}
        pnl = t.get('pnl', 0)
        agent_stats[agent]['total_pnl'] = round(agent_stats[agent]['total_pnl'] + pnl, 2)
        if pnl > 0:
            agent_stats[agent]['wins'] += 1
        else:
            agent_stats[agent]['losses'] += 1
        agent_stats[agent]['trades'].append({
            'symbol': t.get('symbol', '?'),
            'pnl':    round(pnl, 2),
        })

    # Açık pozisyonlar
    try:
        client   = get_client()
        balance  = get_usdt_balance(client)
        open_pos = []
        for sym, pos in positions.items():
            if pos.get('qty', 0) <= 0:
                continue
            try:
                price = get_price(client, sym)
                avg   = pos.get('avg_price', price)
                pct   = (price - avg) / avg * 100 if avg > 0 else 0

                # Tutma süresi
                buy_time = pos.get('buy_time', '')
                if buy_time:
                    try:
                        dt         = datetime.datetime.strptime(buy_time, '%Y-%m-%d %H:%M:%S')
                        hours_held = round((datetime.datetime.now() - dt).total_seconds() / 3600, 1)
                    except Exception:
                        hours_held = '?'
                else:
                    hours_held = '?'

                tech      = _position_technicals(client, sym)
                pos_value = round(price * pos.get('qty', 0), 2)
                open_pos.append({
                    'symbol':     sym,
                    'agent':      pos.get('agent', '?'),
                    'pct':        round(pct, 2),
                    'entry':      round(avg, 6),
                    'price':      round(price, 6),
                    'value':      pos_value,
                    'sl_pct':     pos.get('sl_pct', '?'),
                    'tp_pct':     pos.get('tp_pct', '?'),
                    'hours_held': hours_held,
                    'tech':       tech,
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
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, 'BTCUSDT', '1h', limit=25)
        sma20      = sum(closes[-20:]) / 20
        btc_pct    = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
        btc_vs_sma = round((closes[-1] - sma20) / sma20 * 100, 2)
        btc_trend  = 'YUKARI' if closes[-1] > sma20 else 'ASAGI'
    except Exception:
        btc_pct = 0; btc_vs_sma = 0; btc_trend = '?'

    params = {
        'ceo_position_mult': cfg.get('ceo_position_mult', 1.0),
        'edge_enabled':      cfg.get('edge_enabled', True),
        'otonom_enabled':    cfg.get('otonom_enabled', True),
        'indicator_enabled': cfg.get('indicator_enabled', True),
        'wyckoff_enabled':   cfg.get('wyckoff_enabled', True),
    }

    return {
        'balance':        round(balance, 2),
        'pos_total':      pos_total,
        'total':          round(balance + pos_total, 2),
        'btc_trend':      btc_trend,
        'btc_pct_1h':     btc_pct,
        'btc_vs_sma':     btc_vs_sma,
        'open_positions': open_pos,
        'agent_stats':    agent_stats,
        'params':         params,
    }


# ─── Prompt ───────────────────────────────────────────────────────────────────

def _build_prompt(data):
    lines = [
        "Sen deneyimli bir kripto portföy risk yöneticisisin.",
        "4 ticaret ajanın (EDGE, OTONOM, INDICATOR, WYCKOFF) açtığı pozisyonları izliyorsun.",
        "Alım kararları ajanlara ait, sen karışmazsın.",
        "Senin işin: açık pozisyonlarda riski yönetmek — kâr zirvesinde çık, zararı kes, SL ayarla, sürekli batan ajanı durdur, piyasa çok kötüyse pozisyon boyutlarını küçült.",
        "Müdahale gerekmiyorsa araç çağırma.",
        "",
        f"=== ANLIK DURUM ===",
        f"Serbest USDT: ${data['balance']} | Pozisyonlarda: ${data['pos_total']} | Toplam: ${data['total']}",
        f"BTC Trend: {data['btc_trend']} (SMA20'ye göre {data['btc_vs_sma']:+.2f}%, 1s değişim: {data['btc_pct_1h']:+.2f}%)",
        "",
        "=== AÇIK POZİSYONLAR ===",
    ]

    if data['open_positions']:
        for p in data['open_positions']:
            icon = '🟢' if p['pct'] > 0 else '🔴'
            lines.append(
                f"{icon} {p['symbol']} [{p['agent']}]: {p['pct']:+.2f}% | "
                f"Giriş: {p['entry']} | SL: %{p['sl_pct']} | TP: %{p['tp_pct']} | "
                f"Süredir: {p['hours_held']}s"
            )
            tech = p.get('tech', {})
            for tf in ('1h', '4h'):
                t = tech.get(tf)
                if t:
                    rsi_str = f"RSI={t['rsi']}" if t['rsi'] else 'RSI=?'
                    div_str = f" | DIV={t['div']}" if t.get('div') else ''
                    lines.append(
                        f"   {tf}: {rsi_str} | Trend={t['trend']} | Değişim={t['chg']:+.2f}%{div_str}"
                    )
    else:
        lines.append("Açık pozisyon yok.")

    lines += ["", "=== AJAN PERFORMANSI (son 100 işlem) ==="]
    for agent, stats in data['agent_stats'].items():
        total = stats['wins'] + stats['losses']
        wr    = round(stats['wins'] / total * 100, 1) if total > 0 else 0
        lines.append(f"{agent}: {total} işlem | %{wr} kazanma | PnL: ${stats['total_pnl']}")
        for t in stats['trades'][-3:]:
            lines.append(f"  → {t['symbol']}: ${t['pnl']}")

    lines += [
        "",
        "=== MEVCUT PARAMETRELER ===",
        json.dumps(data['params'], indent=2, ensure_ascii=False),
    ]

    return '\n'.join(lines)


# ─── DeepSeek API ─────────────────────────────────────────────────────────────

def _call_deepseek(prompt, api_key):
    """Function calling ile DeepSeek çağrısı. {'content': str, 'tool_calls': list} döner."""
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
                'max_tokens':  1000,
                'temperature': 0.3,
            },
            timeout=40,
        )
        r.raise_for_status()
        msg         = r.json()['choices'][0]['message']
        content     = msg.get('content') or ''
        tool_calls  = msg.get('tool_calls') or []
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
        send_telegram('⚠️ <b>CEO Rapor</b>: DeepSeek yanıt vermedi.')
        return

    lines = [
        '👔 <b>CEO Değerlendirmesi</b>',
        '━━━━━━━━━━━━━━',
        f'📊 USDT: ${data["balance"]} | Poz: ${data["pos_total"]} | Toplam: ${data["total"]} | BTC: {data["btc_trend"]}',
    ]

    if response.get('content'):
        lines += ['', f'📝 {response["content"]}']

    if tool_results:
        lines += ['', '⚙️ <b>Yapılan İşlemler:</b>']
        for r in tool_results:
            lines.append(f'  ✅ {r}')
    else:
        lines += ['', '⚙️ Müdahale gerekmedi.']

    send_telegram('\n'.join(lines))


# ─── Ana Döngü ────────────────────────────────────────────────────────────────

_running = False
_thread  = None


def _interruptible_sleep(seconds):
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(30)


def _run_once(api_key):
    try:
        state        = _load_state()
        data         = _collect_data()
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
        send_telegram(f'⚠️ CEO manuel analiz hata: {e}')


def _run_loop():
    global _running
    state      = _load_state()
    interval_h = load_config().get('ceo_interval_hours', DEFAULT_INTERVAL)
    print(f'[CEO] Başladı — aralık: {interval_h}s')
    send_telegram(f'👔 <b>CEO Agent AKTİF</b>\nHer {interval_h} saatte bir analiz yapacağım.')

    while _running:
        cfg = load_config()
        if not cfg.get('ceo_agent_enabled', False):
            print('[CEO] Devre dışı bırakıldı, duruyorum.')
            _running = False
            break

        interval = cfg.get('ceo_interval_hours', DEFAULT_INTERVAL)
        api_key  = cfg.get('deepseek_api_key', '')

        if not api_key:
            send_telegram('⚠️ CEO: deepseek_api_key config.json\'da tanımlı değil!')
            _interruptible_sleep(3600)
            continue

        print(f'[CEO] Analiz başlıyor (#{state["review_count"] + 1})')
        try:
            data         = _collect_data()
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
            send_telegram(f'⚠️ CEO hata: {e}')

        _interruptible_sleep(interval * 3600)


# ─── Public API ───────────────────────────────────────────────────────────────

def ceo_flag(cfg, key, default=True):
    """CEO sessiz kaldıysa (kota/hata) default döner — ajanlar kendi çalışır."""
    if not cfg.get('ceo_agent_enabled', False):
        return default
    interval = cfg.get('ceo_interval_hours', DEFAULT_INTERVAL)
    last_ok  = cfg.get('ceo_last_success', 0)
    if time.time() - last_ok > interval * 3 * 3600:
        return default
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
    """Aralık değişince döngüyü yeniden başlat — ajan flag'lerini sıfırlamaz."""
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
    cfg['otonom_enabled']    = True
    cfg['edge_enabled']      = True
    cfg['indicator_enabled'] = True
    cfg['wyckoff_enabled']   = True
    cfg['ceo_position_mult'] = 1.0
    save_config(cfg)
    send_telegram(
        '👔 CEO Agent durduruldu.\n'
        '✅ Tüm ajanlar varsayılan duruma döndürüldü (hepsi açık, çarpan 1.0).'
    )


def ceo_agent_status():
    state = _load_state()
    cfg   = load_config()
    return {
        'running':        _running,
        'enabled':        cfg.get('ceo_agent_enabled', False),
        'review_count':   state.get('review_count', 0),
        'last_review':    state.get('last_review'),
        'interval_hours': cfg.get('ceo_interval_hours', DEFAULT_INTERVAL),
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
