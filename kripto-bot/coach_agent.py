"""
Koç Ajanı — Kendi Kendini Geliştiren Öğrenme Katmanı
────────────────────────────────────────────────────────────────
CEO ajanı saatlik RİSK yöneticisidir (ajan aç/kapat, boyut çarpanı).
Koç ise günlük STRATEJİ öğretmenidir — botun "hatalarından ders alması" budur:

  1. Veri miladından (data_epoch) sonraki kapanan işlemleri ajan bazında
     analiz eder: kazanma oranı, net PnL, profit factor.
     (Milad öncesi kirli veri — test alımları, kod hatası işlemleri — yok sayılır.)
  2. KAÇIRILAN FIRSATLARI bulur: son 24 saatte %15+ fırlayan ama botun hiç
     alamadığı coinler + HANGİ filtrenin engellediğinin teşhisi.
  3. Bu iki raporu DeepSeek'e verir; model set_param aracıyla parametreleri
     değiştirebilir — ama SADECE kodda sabitlenmiş güvenli sınırlar
     (PARAM_BOUNDS) içinde ve tur başına en fazla 3 değişiklik.
  4. Her değişiklik Telegram'a bildirilir ve coach_state.json'a loglanır;
     eski değer kayıtlıdır, istenirse geri alınabilir.

DeepSeek key yoksa: rapor yine gönderilir, otomatik değişiklik yapılmaz.
config.json → coach_enabled: false ile kapatılır (varsayılan: açık).
"""

import time, datetime, json, threading, os, requests
from bot import (load_config, save_config, load_trades, trades_since_epoch,
                 load_positions, send_telegram, get_client, get_total_equity)

STATE_FILE   = 'coach_state.json'
DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'

FIRST_RUN_DELAY_MIN = 15     # başlangıçtan sonra ilk analiz (dk)
DEFAULT_INTERVAL_H  = 24     # sonraki analizler (saat)
MAX_CHANGES_PER_RUN = 3      # tek turda en fazla parametre değişikliği

MOVER_MIN_CHG  = 15.0        # "fırlayan coin" eşiği: 24s %15+
MOVER_MIN_VOL  = 2_000_000   # min $2M 24s hacim (manipülatif mikro-coinleri ele)

STABLES = {'USDCUSDT','BUSDUSDT','TUSDUSDT','FDUSDUSDT','EURUSDT','GBPUSDT',
           'DAIUSDT','USDPUSDT','PYUSDUSDT','AEURUSDT','USDEUSDT','SUSDEUSDT'}

# Ayarlanabilir parametreler: key → (min, max, varsayılan, açıklama)
# SINIRLAR KODDA SABİT — LLM ne önerirse önersin bu aralığın dışına çıkamaz.
PARAM_BOUNDS = {
    'breakout_min_score':     (4.0, 7.0,  5.5,  'Breakout min skor (0-10)'),
    'breakout_min_chg_2h':    (2.5, 8.0,  5.0,  'Breakout son-2s min fiyat hareketi %'),
    'breakout_min_vol_spike': (1.5, 5.0,  3.0,  'Breakout min hacim spike çarpanı'),
    'breakout_max_chg_24h':   (15.0, 50.0, 30.0, 'Breakout 24s max pompalanma %'),
    'breakout_fg_min':        (0, 50, 35, 'Breakout Fear&Greed alt eşiği (0=filtre yok)'),
    'breakout_max_pos':       (1, 5, 3, 'Breakout aynı anda max pozisyon'),
    'otonom_min_score':       (5.0, 7.5, 6.0, 'Otonom ajan min skor (0-10)'),
    'otonom_fg_min':          (0, 50, 30, 'Otonom Fear&Greed alt eşiği'),
    'edge_min_score':         (3.5, 6.5, 4.5, 'Edge ajan min skor (0-10)'),
    'max_positions':          (3, 10, 6, 'Tüm ajanların toplam max pozisyonu'),
    'reentry_cooldown_hours': (0.5, 6.0, 2.0, 'Satış sonrası tekrar alım bekleme (saat)'),
    'sl_cooldown_hours':      (0.0, 12.0, 3.0, 'Zararlı çıkış sonrası bekleme (saat)'),
    'hour_ban_enabled':       (0, 1, 1, '13-20 TR alım yasağı (1=açık 0=kapalı; BREAKOUT zaten muaf)'),
    'min_position_usd':       (5.0, 50.0, 10.0, 'Minimum pozisyon büyüklüğü $'),
    'global_halt_pct':        (5.0, 20.0, 10.0, 'Günlük portföy devre kesici eşiği %'),
}

TOOLS = [{
    'type': 'function',
    'function': {
        'name': 'set_param',
        'description': ('Bir strateji parametresini değiştir. Sadece izin listesi '
                        'içindeki anahtarlar; değer güvenli sınıra kıskaçlanır.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'key':    {'type': 'string', 'enum': list(PARAM_BOUNDS.keys())},
                'value':  {'type': 'number'},
                'reason': {'type': 'string', 'description': 'Tek cümle gerekçe (Türkçe)'},
            },
            'required': ['key', 'value', 'reason'],
        },
    },
}]


# ─── State ────────────────────────────────────────────────────────────────────

def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {'review_count': 0, 'history': [], 'last_review': ''}


def _save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f'[Koç] state kaydı başarısız: {e}')


# ─── 1) Performans Analizi ────────────────────────────────────────────────────

def _agent_family(source):
    """'INDICATOR-UTBOT SL' → 'INDICATOR', 'EDGE TRAIL' → 'EDGE', 'OTONOM' → 'OTONOM'"""
    s = (source or 'BILINMEYEN').upper()
    return s.split()[0].split('-')[0]


def _perf_by_agent():
    """Veri miladından sonraki kapanan işlemler, ajan ailesi bazında istatistik."""
    sells = [t for t in trades_since_epoch() if t.get('type') == 'sell']
    fams = {}
    for t in sells:
        fam = _agent_family(t.get('source'))
        d = fams.setdefault(fam, {'n': 0, 'win': 0, 'pnl': 0.0,
                                  'gain': 0.0, 'loss': 0.0})
        pnl = float(t.get('pnl', 0) or 0)
        d['n']   += 1
        d['pnl'] += pnl
        if pnl > 0:
            d['win']  += 1
            d['gain'] += pnl
        else:
            d['loss'] += abs(pnl)
    out = {}
    for fam, d in fams.items():
        out[fam] = {
            'n':       d['n'],
            'winrate': round(d['win'] / d['n'] * 100, 1) if d['n'] else 0,
            'pnl':     round(d['pnl'], 2),
            'pf':      round(d['gain'] / d['loss'], 2) if d['loss'] > 0 else (9.99 if d['gain'] > 0 else 0),
        }
    return out


# ─── 2) Kaçırılan Fırsat Analizi ──────────────────────────────────────────────

def _read_blacklists():
    """Tüm ajan state dosyalarından blacklist'leri topla: sym → bitiş epoch."""
    bl = {}
    for fname in ('agent_state.json', 'edge_state.json',
                  'indicator_state.json', 'breakout_state.json'):
        try:
            with open(fname) as f:
                data = json.load(f)
            for sym, until in (data.get('blacklist') or {}).items():
                bl[sym] = max(bl.get(sym, 0), float(until))
        except Exception:
            pass
    return bl


def _public_tickers():
    """GERÇEK piyasanın 24s tickerları — auth gerektirmez.
    KRİTİK: testnet'te client.get_ticker() testnet'in kendi (minicik) işlem
    hacmini döndürür → $2M hacim filtresi her coini eler ve 'kaçırılan fırsat'
    analizi hiç çalışmaz. Fırsat taraması HER ZAMAN gerçek piyasaya bakmalı."""
    import urllib.request
    with urllib.request.urlopen(
            'https://api.binance.com/api/v3/ticker/24hr', timeout=15) as r:
        return json.loads(r.read())


def _missed_movers(client, cfg):
    """Son 24 saatte fırlayan ama botun almadığı coinler + engel teşhisi."""
    try:
        tickers = _public_tickers()
    except Exception as e:
        print(f'[Koç] Gerçek piyasa ticker hatası ({e}) — client fallback')
        try:
            tickers = client.get_ticker()
        except Exception as e2:
            print(f'[Koç] Ticker hatası: {e2}')
            return []

    movers = []
    for t in tickers:
        sym = t.get('symbol', '')
        if not sym.endswith('USDT') or sym in STABLES:
            continue
        try:
            chg = float(t.get('priceChangePercent', 0))
            vol = float(t.get('quoteVolume', 0))
            prc = float(t.get('lastPrice', 0))
        except (ValueError, TypeError):
            continue
        if chg >= MOVER_MIN_CHG and vol >= MOVER_MIN_VOL and prc > 0.005 \
                and not (0.85 <= prc <= 1.15):
            movers.append({'symbol': sym, 'chg24': round(chg, 1), 'vol24': vol})
    movers.sort(key=lambda x: x['chg24'], reverse=True)
    movers = movers[:10]
    if not movers:
        return []

    # Son 24 saatte bu coinlere alım yapıldı mı?
    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)
              ).strftime('%Y-%m-%d %H:%M:%S')
    bought = {t.get('symbol') for t in load_trades()
              if t.get('type') == 'buy' and t.get('time', '') >= cutoff}
    held = {s for s, p in load_positions().items() if p.get('qty', 0) > 0}

    blacklists  = _read_blacklists()
    max_chg     = float(cfg.get('breakout_max_chg_24h', 30.0))
    max_pos     = int(cfg.get('max_positions', 6))
    slots_full  = len(held) >= max_pos
    now         = time.time()

    missed = []
    for m in movers:
        sym = m['symbol']
        if sym in bought or sym in held:
            continue
        reasons = []
        if m['chg24'] > max_chg:
            reasons.append(f"24s +%{m['chg24']} > breakout_max_chg_24h({max_chg:.0f})")
        if blacklists.get(sym, 0) > now:
            kalan = (blacklists[sym] - now) / 3600
            reasons.append(f'blacklist ({kalan:.1f}s kaldı)')
        if slots_full:
            reasons.append(f'pozisyon slotları dolu ({len(held)}/{max_pos})')
        if cfg.get('hour_ban_enabled', True):
            reasons.append('gün içinde 13-20 TR yasağı vardı (BREAKOUT muaf)')
        if not reasons:
            reasons.append('skor/hacim-spike eşiğine takılmış olabilir')
        m['reasons'] = reasons
        missed.append(m)
    return missed


# ─── 3) DeepSeek ──────────────────────────────────────────────────────────────

def _current_params(cfg):
    out = {}
    for key, (lo, hi, default, desc) in PARAM_BOUNDS.items():
        out[key] = cfg.get(key, default)
    return out


def _build_prompt(perf, missed, params, equity, days):
    plines = [f"  {k} = {v}  (sınır: {PARAM_BOUNDS[k][0]}–{PARAM_BOUNDS[k][1]}, {PARAM_BOUNDS[k][3]})"
              for k, v in params.items()]
    if perf:
        alines = [f"  {fam}: {d['n']} işlem | kazanma %{d['winrate']} | "
                  f"net ${d['pnl']} | PF {d['pf']}" for fam, d in
                  sorted(perf.items(), key=lambda x: x[1]['pnl'])]
    else:
        alines = ['  (veri miladından bu yana kapanan işlem yok)']
    if missed:
        mlines = [f"  {m['symbol']} +%{m['chg24']}: {'; '.join(m['reasons'])}"
                  for m in missed]
    else:
        mlines = ['  (kaçırılan büyük fırsat tespit edilmedi)']

    return f"""Sen bir kripto spot alım-satım botunun STRATEJİ KOÇUSUN. Bot Binance'te
birden çok ajanla işlem yapıyor. Görevin: aşağıdaki verilerden ders çıkarıp
parametreleri kademeli olarak iyileştirmek. Hedef agresif kâr değil, İSTİKRARLI
küçük günlük kazanç (büyük kayıpları önle, kazanan işlemleri artır).

VERİ PENCERESI: son {days:.1f} gün (öncesi kirli veri, yok sayıldı)
TOPLAM SERMAYE: ${equity:.0f}

AJAN PERFORMANSI (kapanan işlemler):
{chr(10).join(alines)}

KAÇIRILAN FIRSATLAR (son 24s %15+ fırlayan, botun ALAMADIĞI coinler ve engel teşhisi):
{chr(10).join(mlines)}

MEVCUT PARAMETRELER:
{chr(10).join(plines)}

KURALLAR:
- En fazla {MAX_CHANGES_PER_RUN} parametre değiştir; küçük adımlar at (tek seferde
  bir eşiği en fazla ~%20 oynat). Değişiklik gerekmiyorsa hiç araç çağırma.
- 10'dan az işlem olan ajan hakkında kesin hüküm verme; önce veri biriksin.
- Filtreler art arda fırsat kaçırıyorsa GEVŞET; bir ajan net zarardaysa ve
  yeterli örneklem varsa o ajanın eşiğini SIKILAŞTIR.
- Cevabının metin kısmında 2-3 cümleyle ne öğrendiğini Türkçe özetle.
Gerekli görürsen set_param aracını çağır."""


def _call_deepseek(prompt, api_key):
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={'Authorization': f'Bearer {api_key}',
                     'Content-Type': 'application/json'},
            json={'model': 'deepseek-chat',
                  'messages': [{'role': 'user', 'content': prompt}],
                  'tools': TOOLS, 'tool_choice': 'auto',
                  'max_tokens': 1200, 'temperature': 0.2},
            timeout=60,
        )
        r.raise_for_status()
        msg = r.json()['choices'][0]['message']
        return {'content': (msg.get('content') or '').strip(),
                'tool_calls': msg.get('tool_calls') or []}
    except Exception as e:
        print(f'[Koç] DeepSeek hata: {e}')
        return None


def _apply_tool_calls(tool_calls, state):
    """set_param çağrılarını sınır kıskacıyla uygula. Dönen: değişiklik satırları."""
    results = []
    cfg = load_config()
    changed = False
    for tc in tool_calls[:MAX_CHANGES_PER_RUN]:
        try:
            if tc['function']['name'] != 'set_param':
                continue
            args = json.loads(tc['function']['arguments'])
            key  = args['key']
            if key not in PARAM_BOUNDS:
                results.append(f'❌ {key}: izin listesinde yok, reddedildi')
                continue
            lo, hi, default, _ = PARAM_BOUNDS[key]
            val = max(lo, min(hi, float(args['value'])))
            if key in ('max_positions', 'breakout_max_pos', 'hour_ban_enabled',
                       'breakout_fg_min', 'otonom_fg_min'):
                val = int(round(val))
            old = cfg.get(key, default)
            if old == val:
                continue
            cfg[key] = val
            changed = True
            reason = str(args.get('reason', ''))[:120]
            line = f'{key}: {old} → {val} ({reason})'
            results.append(f'✅ {line}')
            state.setdefault('history', []).append({
                'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'key': key, 'old': old, 'new': val, 'reason': reason,
            })
        except Exception as e:
            results.append(f'❌ Araç çağrısı işlenemedi: {e}')
    if changed:
        save_config(cfg)
        state['history'] = state.get('history', [])[-100:]
    return results


# ─── Ana Akış ─────────────────────────────────────────────────────────────────

def _ensure_epoch():
    """Veri miladı yoksa ŞİMDİ olarak kur — analiz temiz sayfayla başlar."""
    cfg = load_config()
    if not cfg.get('data_epoch'):
        cfg['data_epoch'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_config(cfg)
        send_telegram(
            '🧹 <b>Koç: Veri miladı kuruldu</b>\n'
            f'📅 {cfg["data_epoch"]}\n'
            'Bu tarihten önceki işlemler (test alımları, hatalı işlemler) '
            'öğrenme analizlerinde YOK SAYILACAK. Temiz sayfa açıldı.'
        )
    return cfg


def run_coach_review():
    """Tek tur Koç analizi. Telegram raporu + (key varsa) DeepSeek ayar turu."""
    state = _load_state()
    cfg   = _ensure_epoch()
    client = get_client()

    try:
        equity = get_total_equity(client)
    except Exception:
        equity = 0.0

    perf   = _perf_by_agent()
    missed = _missed_movers(client, cfg)
    params = _current_params(cfg)

    try:
        epoch_dt = datetime.datetime.strptime(cfg['data_epoch'], '%Y-%m-%d %H:%M:%S')
        days = max(0.04, (datetime.datetime.now() - epoch_dt).total_seconds() / 86400)
    except Exception:
        days = 1.0

    # ── Rapor (DeepSeek'ten bağımsız her zaman gider) ──
    lines = ['🎓 <b>KOÇ GÜNLÜK ANALİZ</b>', '━━━━━━━━━━━━━━',
             f'📅 Veri penceresi: {days:.1f} gün | 💰 Sermaye: ${equity:.0f}']
    if perf:
        lines.append('')
        lines.append('📊 <b>Ajan karnesi:</b>')
        for fam, d in sorted(perf.items(), key=lambda x: x[1]['pnl'], reverse=True):
            icon = '🟢' if d['pnl'] >= 0 else '🔴'
            lines.append(f"{icon} {fam}: {d['n']} işlem | %{d['winrate']} | ${d['pnl']} | PF {d['pf']}")
    else:
        lines.append('📊 Henüz kapanan işlem yok (milad sonrası).')
    if missed:
        lines.append('')
        lines.append('🚀 <b>Kaçırılan fırsatlar (24s):</b>')
        for m in missed[:5]:
            lines.append(f"• {m['symbol']} +%{m['chg24']} → {m['reasons'][0]}")

    api_key = cfg.get('deepseek_api_key', '')
    tool_results = []
    if api_key:
        resp = _call_deepseek(_build_prompt(perf, missed, params, equity, days), api_key)
        if resp:
            if resp.get('content'):
                lines += ['', f'🧠 <b>Koç dersi:</b> {resp["content"][:600]}']
            tool_results = _apply_tool_calls(resp.get('tool_calls', []), state)
        else:
            lines += ['', '⚠️ DeepSeek yanıt vermedi — bu tur ayar yapılmadı.']
    else:
        lines += ['', 'ℹ️ deepseek_api_key yok — rapor modunda (otomatik ayar kapalı).']

    if tool_results:
        lines += ['', '⚙️ <b>Parametre değişiklikleri:</b>'] + [f'  {r}' for r in tool_results]
    elif api_key:
        lines += ['', '⚙️ Bu tur parametre değişikliği yapılmadı.']

    send_telegram('\n'.join(lines))

    state['review_count'] = state.get('review_count', 0) + 1
    state['last_review']  = datetime.datetime.now().isoformat()
    _save_state(state)
    print(f'[Koç] Analiz #{state["review_count"]} tamamlandı '
          f'({len(tool_results)} değişiklik)')


# ─── Thread Yönetimi ──────────────────────────────────────────────────────────

_running = False
_thread  = None


def _loop():
    global _running
    # İlk analiz: başlangıçtan kısa süre sonra (kullanıcı sistemin çalıştığını görsün)
    end = time.time() + FIRST_RUN_DELAY_MIN * 60
    while _running and time.time() < end:
        time.sleep(15)
    while _running:
        cfg = load_config()
        if not cfg.get('coach_enabled', True):
            print('[Koç] coach_enabled=false — duruyorum')
            break
        try:
            run_coach_review()
        except Exception as e:
            print(f'[Koç] Analiz hatası: {e}')
            try:
                send_telegram(f'⚠️ Koç analiz hatası: {e}')
            except Exception:
                pass
        interval_h = float(cfg.get('coach_interval_hours', DEFAULT_INTERVAL_H))
        end = time.time() + interval_h * 3600
        while _running and time.time() < end:
            time.sleep(30)


def start_coach_agent():
    global _running, _thread
    if _running:
        return False
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()
    print('[Koç] Başladı')
    return True


def stop_coach_agent():
    global _running
    _running = False
    print('[Koç] Durduruldu')


def coach_agent_status():
    state = _load_state()
    return {
        'running':      _running,
        'review_count': state.get('review_count', 0),
        'last_review':  state.get('last_review', ''),
        'history':      state.get('history', [])[-20:],
    }


def trigger_coach_review():
    """Web/Telegram'dan manuel tetikleme — ayrı thread'de çalıştırır."""
    threading.Thread(target=run_coach_review, daemon=True).start()
    return True
