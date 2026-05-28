"""
CEO Agent — Yönetici Yapay Zeka
────────────────────────────────────────────────────────────────
• Her N saatte bir tüm ajanların performansını analiz eder
• DeepSeek API ile değerlendirme yapar
• Parametre önerilerini config.json'a yazar
• Telegram'a yönetim raporu gönderir
• config.json → ceo_agent_enabled: true/false ile açılır
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, load_positions,
                 get_price, send_telegram, get_usdt_balance, get_client)

STATE_FILE = 'ceo_state.json'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'

DEFAULT_INTERVAL = 1   # saat


def ceo_flag(cfg, key, default=True):
    """
    CEO flag okur ama CEO sessiz kaldıysa (kota/hata) default değeri döner.
    CEO cevap vermezse ajanlar kendi kendine çalışmaya devam eder.
    """
    if not cfg.get('ceo_agent_enabled', False):
        return default  # CEO kapalıysa flag'e bakma
    interval  = cfg.get('ceo_interval_hours', DEFAULT_INTERVAL)
    last_ok   = cfg.get('ceo_last_success', 0)
    timeout   = interval * 3 * 3600   # 3 başarısız döngü = timeout
    if time.time() - last_ok > timeout:
        return default  # CEO süresi doldu, varsayılana dön
    return cfg.get(key, default)


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


def _collect_data():
    """Tüm ajanların durumunu ve son işlemleri topla."""
    cfg       = load_config()
    trades    = load_trades()
    positions = load_positions()

    # Son 48 saat işlemler
    cutoff = time.time() - 48 * 3600
    recent = [t for t in trades
              if t.get('timestamp', t.get('time_ts', 0)) > cutoff
              or (isinstance(t.get('time', ''), str) and len(t.get('time','')) > 10)]

    # Ajan bazında özet
    agent_stats = {}
    for t in trades[-100:]:  # son 100 işlem
        if t.get('type') != 'sell':
            continue
        source = t.get('source', 'UNKNOWN')
        agent  = 'EDGE' if 'EDGE' in source else \
                 'INDICATOR' if 'INDICATOR' in source else \
                 'WYCKOFF' if 'WYCKOFF' in source else 'OTONOM'
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
            'source': source,
        })

    # Açık pozisyonlar
    try:
        client    = get_client()
        balance   = get_usdt_balance(client)
        open_pos  = []
        for sym, pos in positions.items():
            if pos.get('qty', 0) <= 0:
                continue
            try:
                price   = get_price(client, sym)
                avg     = pos.get('avg_price', price)
                pct     = (price - avg) / avg * 100 if avg > 0 else 0
                open_pos.append({
                    'symbol': sym,
                    'agent':  pos.get('agent', '?'),
                    'pct':    round(pct, 2),
                    'entry':  round(avg, 6),
                    'price':  round(price, 6),
                })
            except Exception:
                pass
    except Exception:
        balance  = 0
        open_pos = []

    # BTC durumu
    try:
        from signal_engine import get_klines
        closes, _, _, _ = get_klines(client, 'BTCUSDT', '1h', limit=25)
        sma20   = sum(closes[-20:]) / 20
        btc_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
        btc_vs_sma = round((closes[-1] - sma20) / sma20 * 100, 2)
        btc_trend = 'YUKARI' if closes[-1] > sma20 else 'ASAGI'
    except Exception:
        btc_pct = 0; btc_vs_sma = 0; btc_trend = '?'

    # Mevcut parametreler
    params = {
        'ceo_position_mult':    cfg.get('ceo_position_mult', 1.0),
        'edge_enabled':         cfg.get('edge_enabled', True),
        'otonom_enabled':       cfg.get('otonom_enabled', True),
        'indicator_enabled':    cfg.get('indicator_enabled', True),
        'wyckoff_enabled':      cfg.get('wyckoff_enabled', True),
        'report_interval_hours': cfg.get('report_interval_hours', 1),
    }

    return {
        'balance':     round(balance, 2),
        'btc_trend':   btc_trend,
        'btc_pct_1h':  btc_pct,
        'btc_vs_sma':  btc_vs_sma,
        'open_positions': open_pos,
        'agent_stats': agent_stats,
        'params':      params,
    }


def _build_prompt(data):
    """DeepSeek için Türkçe prompt oluştur."""
    lines = [
        "Sen bir kripto trading şirketinin CEO'susun.",
        "4 ticaret ajanın var: EDGE, OTONOM, INDICATOR, WYCKOFF.",
        "Görevin: performansı değerlendirmek, parametreleri ayarlamak, strateji belirlemek.",
        "",
        f"=== ANLIK DURUM ===",
        f"Bakiye: ${data['balance']}",
        f"BTC Trend: {data['btc_trend']} (SMA20'ye göre {data['btc_vs_sma']:+.2f}%, 1s değişim: {data['btc_pct_1h']:+.2f}%)",
        "",
        "=== AÇIK POZİSYONLAR ===",
    ]

    if data['open_positions']:
        for p in data['open_positions']:
            icon = '🟢' if p['pct'] > 0 else '🔴'
            lines.append(f"{icon} {p['symbol']} [{p['agent']}]: {p['pct']:+.2f}% (giriş: {p['entry']})")
    else:
        lines.append("Açık pozisyon yok.")

    lines += ["", "=== AJAN PERFORMANSI (son 100 işlem) ==="]
    for agent, stats in data['agent_stats'].items():
        total = stats['wins'] + stats['losses']
        wr    = round(stats['wins'] / total * 100, 1) if total > 0 else 0
        lines.append(
            f"{agent}: {total} işlem | %{wr} kazanma | PnL: ${stats['total_pnl']}"
        )
        if stats['trades'][-3:]:
            for t in stats['trades'][-3:]:
                lines.append(f"  → {t['symbol']}: ${t['pnl']}")

    lines += [
        "",
        "=== MEVCUT PARAMETRELER ===",
        json.dumps(data['params'], indent=2, ensure_ascii=False),
        "",
        "=== GÖREVIN ===",
        "Yukarıdaki verileri analiz et ve aşağıdaki JSON formatında cevap ver:",
        "",
        '{"ozet": "kısa analiz (max 3 cümle)",',
        ' "degisiklikler": {',
        '   "ceo_position_mult": 0.5-1.5 (pozisyon büyüklük çarpanı),',
        '   "edge_enabled": true/false,',
        '   "otonom_enabled": true/false,',
        '   "indicator_enabled": true/false,',
        '   "wyckoff_enabled": true/false',
        ' },',
        ' "tavsiyeler": ["öneri 1", "öneri 2"],',
        ' "risk": "dusuk/orta/yuksek"',
        "}",
        "",
        "KURAL: Sadece JSON döndür. Başka metin ekleme.",
        "KURAL: Kazanan ajanı kapatma. Sadece sürekli zarar edeni kapat.",
        "KURAL: BTC BEAR trendinde position_mult en fazla 0.7 olabilir.",
    ]

    return '\n'.join(lines)


def _call_deepseek(prompt, api_key):
    """DeepSeek API çağrısı."""
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'deepseek-chat',
                'messages': [{'role': 'user', 'content': prompt}],
                'response_format': {'type': 'json_object'},
                'max_tokens': 800,
                'temperature': 0.3,
            },
            timeout=30,
        )
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
        return json.loads(content)
    except Exception as e:
        print(f'[CEO] DeepSeek hata: {e}')
        return None


def _apply_changes(result):
    """CEO kararlarını config.json'a yaz."""
    if not result:
        return []
    cfg     = load_config()
    changes = result.get('degisiklikler', {})
    applied = []

    allowed_keys = {
        'ceo_position_mult', 'edge_enabled', 'otonom_enabled',
        'indicator_enabled', 'wyckoff_enabled',
    }

    for key, val in changes.items():
        if key not in allowed_keys:
            continue
        old = cfg.get(key)
        if old != val:
            cfg[key] = val
            applied.append(f'{key}: {old} → {val}')

    if applied:
        save_config(cfg)

    # Başarılı analiz zaman damgası — ajanlar bu damgayı kontrol eder
    cfg2 = load_config()
    cfg2['ceo_last_success'] = time.time()
    save_config(cfg2)

    return applied


def _send_report(result, applied, data):
    """Telegram'a CEO raporu gönder."""
    if not result:
        send_telegram('⚠️ <b>CEO Rapor</b>: DeepSeek yanıt vermedi.')
        return

    risk_icon = {'dusuk': '🟢', 'orta': '🟡', 'yuksek': '🔴'}.get(result.get('risk', ''), '⚪')

    lines = [
        f'👔 <b>CEO Değerlendirmesi</b>',
        f'━━━━━━━━━━━━━━',
        f'📊 Bakiye: ${data["balance"]} | BTC: {data["btc_trend"]}',
        f'{risk_icon} Risk: {result.get("risk", "?")}',
        f'',
        f'📝 {result.get("ozet", "")}',
    ]

    if result.get('tavsiyeler'):
        lines.append('')
        lines.append('💡 <b>Tavsiyeler:</b>')
        for t in result['tavsiyeler']:
            lines.append(f'  • {t}')

    if applied:
        lines.append('')
        lines.append('⚙️ <b>Uygulanan Değişiklikler:</b>')
        for a in applied:
            lines.append(f'  ✅ {a}')
    else:
        lines.append('')
        lines.append('⚙️ Parametre değişikliği yok.')

    send_telegram('\n'.join(lines))


# ─── Ana Döngü ────────────────────────────────────────────────────────────────

_running = False
_thread  = None


def _interruptible_sleep(seconds):
    """Sleep in 30s chunks so _running=False wakes us quickly."""
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(30)


def _run_loop():
    global _running
    state = _load_state()
    print('[CEO] Başladı')
    interval_h = load_config().get('ceo_interval_hours', DEFAULT_INTERVAL)
    send_telegram(f'👔 <b>CEO Agent AKTİF</b>\nHer {interval_h} saatte bir analiz yapacağım.')

    while _running:
        cfg      = load_config()
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
            data    = _collect_data()
            prompt  = _build_prompt(data)
            result  = _call_deepseek(prompt, api_key)
            applied = _apply_changes(result)
            _send_report(result, applied, data)

            state['review_count'] += 1
            state['last_review']   = datetime.datetime.now().isoformat()
            if applied:
                state['changes_made'].extend(applied)
                state['changes_made'] = state['changes_made'][-50:]
            _save_state(state)
        except Exception as e:
            print(f'[CEO] Analiz hata: {e}')
            send_telegram(f'⚠️ CEO hata: {e}')

        _interruptible_sleep(interval * 3600)


# ─── Public API ───────────────────────────────────────────────────────────────

def start_ceo_agent():
    global _running, _thread
    if _running:
        return False
    _running = True
    _thread  = threading.Thread(target=_run_loop, daemon=True)
    _thread.start()
    return True


def restart_ceo_agent():
    """Restart loop after interval change — does NOT reset agent flags."""
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
    # CEO kapanınca tüm ajanları varsayılana döndür
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
        'running':       _running,
        'enabled':       cfg.get('ceo_agent_enabled', False),
        'review_count':  state.get('review_count', 0),
        'last_review':   state.get('last_review'),
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


def _run_once(api_key):
    try:
        state   = _load_state()
        data    = _collect_data()
        prompt  = _build_prompt(data)
        result  = _call_deepseek(prompt, api_key)
        applied = _apply_changes(result)
        _send_report(result, applied, data)
        state['review_count'] += 1
        state['last_review']   = datetime.datetime.now().isoformat()
        _save_state(state)
    except Exception as e:
        send_telegram(f'⚠️ CEO manuel analiz hata: {e}')
