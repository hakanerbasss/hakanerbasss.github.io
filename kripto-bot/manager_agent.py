"""
CEO Agent — Yönetici Yapay Zeka
────────────────────────────────────────────────────────────────
• Her N saatte bir tüm ajanların performansını analiz eder
• DeepSeek function calling ile araç tabanlı karar verir
• ROL: Risk yöneticisi (trader DEĞİL). Tek pozisyona dokunmaz —
  ajanlar kendi giriş VE çıkışlarını (TP/SL/trailing) yönetir.
• 2 araç: set_agent_enabled (batan ajanı kapat),
          set_position_mult (bear'de pozisyon boyutunu küçült)
• config.json → ceo_agent_enabled: true/false ile açılır
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, load_positions,
                 get_price, send_telegram, get_usdt_balance,
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
                    'agent':   {'type': 'string', 'enum': ['edge', 'otonom', 'indicator', 'wyckoff', 'breakout']},
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
        if source.startswith('CEO_'):
            continue  # CEO satışlarını ajan istatistiğine sayma
        agent  = ('EDGE'      if 'EDGE'      in source else
                  'INDICATOR' if 'INDICATOR' in source else
                  'WYCKOFF'   if 'WYCKOFF'   in source else
                  'BREAKOUT'  if 'BREAKOUT'  in source else 'OTONOM')
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
                pos_value  = round(price * pos.get('qty', 0), 2)
                net_pct    = round(pct - 0.2, 2)  # brüt % - alım(%0.1) - satım(%0.1)

                # CEO'nun son müdahalesinden bu yana geçen süre
                ceo_action_ago = None
                ceo_action_type = pos.get('ceo_last_action_type')
                last_act = pos.get('ceo_last_action', '')
                if last_act:
                    try:
                        dt = datetime.datetime.strptime(last_act, '%Y-%m-%d %H:%M:%S')
                        ceo_action_ago = round((datetime.datetime.now() - dt).total_seconds() / 60)
                    except Exception:
                        pass

                open_pos.append({
                    'symbol':          sym,
                    'agent':           pos.get('agent', '?'),
                    'pct':             round(pct, 2),
                    'net_pct':         net_pct,
                    'entry':           round(avg, 6),
                    'price':           round(price, 6),
                    'value':           pos_value,
                    'sl_pct':          pos.get('sl_pct', '?'),
                    'tp_pct':          pos.get('tp_pct', '?'),
                    'hours_held':      hours_held,
                    'tech':            tech,
                    'ceo_action_ago':  ceo_action_ago,
                    'ceo_action_type': ceo_action_type,
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
        'breakout_enabled':     cfg.get('breakout_enabled', True),
        'accumulation_enabled': cfg.get('accumulation_enabled', True),
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
        "Sen bir kripto portföy RİSK YÖNETİCİSİSİN — trader değilsin.",
        "5 ticaret ajanı var: EDGE, OTONOM, INDICATOR, WYCKOFF, BREAKOUT.",
        "Her ajan kendi giriş VE çıkışını (TP/SL/trailing) kendi yönetir. Tek tek pozisyonlara ASLA karışmazsın.",
        "Senin SADECE iki yetkin var:",
        "  1) set_agent_enabled — bir ajan uzun vadede (yeterli işlem sayısıyla) sürekli zarar ediyorsa kapat. Tek kötü işleme bakıp kapatma.",
        "  2) set_position_mult — BTC bear trendindeyse veya portföy genel zarardaysa tüm pozisyon boyutlarını küçült (0.3–1.0); güçlü bull'da normale döndür (1.0).",
        "Sabırlı ol: az işlemle veya tek pozisyonun anlık zararına bakıp karar verme. Müdahale gerekmiyorsa hiç araç çağırma.",
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
            ceo_note = ''
            if p.get('ceo_action_ago') is not None:
                ceo_note = f" | ⚠️ CEO {p['ceo_action_ago']}dk önce müdahale etti ({p['ceo_action_type']})"
            lines.append(
                f"{icon} {p['symbol']} [{p['agent']}]: brüt {p['pct']:+.2f}% | net {p['net_pct']:+.2f}% | "
                f"Giriş: {p['entry']} | SL: %{p['sl_pct']} | TP: %{p['tp_pct']} | "
                f"Süredir: {p['hours_held']}s{ceo_note}"
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
        state = _load_state()
        data  = _collect_data()
        if data['balance'] == 0 and data['btc_trend'] == '?':
            send_telegram('⚠️ CEO: Binance verisi alınamadı, analiz iptal edildi.')
            return
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
            data = _collect_data()

            # Binance bağlantısı henüz hazır değilse atla
            if data['balance'] == 0 and data['btc_trend'] == '?':
                print('[CEO] Veri alınamadı (Binance hazır değil), 2 dakika sonra tekrar deneniyor.')
                _interruptible_sleep(120)
                continue

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
    """Ajanın açık/kapalı bayrağını döndür.
    Hem kullanıcının manuel toggle'ı (/indicatoroff vb.) hem CEO'nun
    set_agent_enabled'ı AYNI bayrağı yazar; ikisine de saygı duyulur.
    Bayrak False ise ajan yeni alım yapmaz (açık pozisyonlar izlenmeye
    devam eder, çıkışlar normal işler).
    NOT: Eskiden CEO kapalıyken bu fonksiyon bayrağı yok sayıp default
    dönüyordu — bu yüzden manuel kapatma çalışmıyordu. Düzeltildi."""
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
    cfg['otonom_enabled']       = True
    cfg['edge_enabled']         = True
    cfg['indicator_enabled']    = True
    cfg['wyckoff_enabled']      = True
    cfg['breakout_enabled']     = True
    cfg['accumulation_enabled'] = True
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
