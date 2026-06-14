"""
Evolution Engine — Strateji Evrimi
────────────────────────────────────────────────────────────────────────────
Canlı organizma modeli: Bot kendi scoring fonksiyonunu yazar, test eder,
gerekirse değiştirir.

Döngü:
  1. Coach: Otonom'un WR < %40, 10+ işlem → evrim tetiklenir
  2. DeepSeek mevcut _score() kodu + trade geçmişi alır → yeni score() yazar
  3. Challenger 24 saat GÖLGE modda çalışır:
     - Piyasayı izler, sinyal üretir
     - GERÇEK ALIM YAPMAZ — "bu fiyata girseydin ne olurdu?" kaydeder
     - 4 saat sonra fiyat kontrol edilir: kazandı mı kaybetti mi?
  4. 24 saat sonra karşılaştır: challenger gölge WR vs mevcut Otonom WR
  5. Challenger %5+ daha iyiyse → aktif strateji olur (promote)
  6. Kötüyse → farklı yaklaşım dene (max 3 deneme)
  7. 3 deneme de başarısızsa → mevcut korunur, 72 saat beklenir

Versiyon geçmişi: evolution_state.json — her versiyon arşivlenir, SİLİNMEZ.
Gölge sinyaller: shadow_results.json — ne zaman, hangi coin, hangi fiyat.
"""

import json, os, time, datetime, math, traceback
import requests
from bot import send_telegram, load_config

STATE_FILE   = 'evolution_state.json'
SHADOW_FILE  = 'shadow_results.json'
DEEPSEEK_API = 'https://api.deepseek.com/v1/chat/completions'

MIN_TRADES_TO_EVOLVE = 10      # evrim tetiklenmesi için minimum işlem sayısı
POOR_WR_THRESHOLD    = 40.0    # WR bu değerin altında ise evrim başlar (%)
SHADOW_HOURS         = 24      # challenger gölge test süresi (saat)
SHADOW_SIGNALS_MIN   = 5       # en az bu kadar değerlendirilmiş gölge sinyal gerekli
EVAL_HOLD_HOURS      = 4       # gölge sinyali X saat sonra değerlendirilir
MAX_ATTEMPTS         = 3       # bir ajan için max challenger denemesi
IMPROVEMENT_MARGIN   = 5.0     # challenger en az bu kadar (WR%) daha iyi olmalı
EXHAUSTED_COOLDOWN_H = 72      # tüm denemeler başarısız → bu kadar bekle

# Sandbox: sadece güvenli built-in'ler. os, sys, open, exec, eval YASAK.
_SAFE_BUILTINS = {
    'abs': abs, 'all': all, 'any': any, 'bool': bool, 'dict': dict,
    'enumerate': enumerate, 'float': float, 'int': int, 'isinstance': isinstance,
    'len': len, 'list': list, 'max': max, 'min': min, 'print': print,
    'range': range, 'round': round, 'set': set, 'sorted': sorted,
    'sum': sum, 'tuple': tuple, 'zip': zip, 'math': math,
}

# ─── State yönetimi ──────────────────────────────────────────────────────────

def _load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {'agents': {}}

def _save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f'[Evrim] state kayıt hatası: {e}')

def _load_shadow():
    try:
        with open(SHADOW_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_shadow(data):
    try:
        with open(SHADOW_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f'[Evrim] shadow kayıt hatası: {e}')

# ─── Mevcut strateji kodu okuma ───────────────────────────────────────────────

def _get_current_score_code():
    """autonomous_agent.py'dan _score() fonksiyonunu oku ve döndür."""
    try:
        fname = 'autonomous_agent.py'
        if not os.path.exists(fname):
            fname = os.path.join(os.path.dirname(__file__), 'autonomous_agent.py')
        with open(fname, encoding='utf-8') as f:
            src = f.read()
        start = src.find('\ndef _score(')
        if start == -1:
            return '[_score() bulunamadı]'
        # Bir sonraki top-level tanıma kadar al
        for marker in ['\ndef ', '\nclass ']:
            end = src.find(marker, start + 10)
            if end > start:
                break
        else:
            end = len(src)
        return src[start:end].strip()
    except Exception as e:
        return f'[kaynak okunamadı: {e}]'

# ─── Sandbox ─────────────────────────────────────────────────────────────────

def _sandbox_exec(code_str):
    """
    Strateji kodunu güvenli ortamda çalıştır.
    Başarılıysa 'score' fonksiyonunu, hata varsa None döndürür.
    """
    try:
        import numpy as np
        import statistics as _stat

        # Yalnızca güvenli modüllere izin veren import fonksiyonu
        _ALLOWED_MODS = {'numpy', 'np', 'math', 'statistics', 'collections'}
        def _safe_import(name, *args, **kwargs):
            base = name.split('.')[0]
            if base not in _ALLOWED_MODS:
                raise ImportError(f"'{name}' modülüne izin yok (sandbox)")
            return __import__(name, *args, **kwargs)

        namespace = {
            '__builtins__': {**_SAFE_BUILTINS, '__import__': _safe_import},
            'np': np, 'numpy': np, 'math': math, 'statistics': _stat,
        }
        exec(compile(code_str, '<evolution_strategy>', 'exec'), namespace)
        fn = namespace.get('score')
        if not callable(fn):
            print('[Evrim] Kod "score" fonksiyonu içermiyor')
            return None
        return fn
    except Exception as e:
        print(f'[Evrim] Sandbox exec hatası: {e}')
        return None

def _validate_fn(fn):
    """Fonksiyonu dummy verilerle test et — 0-10 arası sayısal değer döndürmeli."""
    try:
        import numpy as np
        n = 60
        c = list(np.cumsum(np.random.randn(n) * 0.005) + 1.0)
        h = [v * 1.005 for v in c]
        l = [v * 0.995 for v in c]
        v = [1_000_000.0] * n
        btc = list(np.cumsum(np.random.randn(n) * 50) + 65_000)
        result = fn(c, h, l, v, btc, 55,
                    {'vol_ratio': 1.8, 'rsi1h': 52.0, 'rsi15m': 48.0,
                     'adx': 26.0, 'regime': 'BULL'})
        # numpy float64, float32 vb. dahil tüm sayısal tipler kabul
        try:
            val = float(result)
        except (TypeError, ValueError):
            print(f'[Evrim] Sonuç float\'a çevrilemiyor: {result!r} ({type(result).__name__})')
            return False
        ok = 0.0 <= val <= 10.0
        if not ok:
            print(f'[Evrim] Sonuç 0-10 aralığı dışında: {val}')
        return ok
    except Exception as e:
        print(f'[Evrim] Fonksiyon doğrulama hatası: {e}')
        return False

# ─── Gölge (shadow) sinyal sistemi ───────────────────────────────────────────

def shadow_log(agent_name, symbol, entry_price, score_val, version):
    """Gölge sinyal kaydet — GERÇEK ALIM YOK."""
    shadow = _load_shadow()
    signals = shadow.setdefault(agent_name, [])
    eval_due = (datetime.datetime.now() +
                datetime.timedelta(hours=EVAL_HOLD_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    signals.append({
        'time':     datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'symbol':   symbol,
        'entry':    entry_price,
        'score':    round(float(score_val), 2),
        'version':  version,
        'eval_due': eval_due,
        'result':   None,   # sonradan fiyat kontrol edilince doldurulur
    })
    shadow[agent_name] = signals[-500:]
    _save_shadow(shadow)

def shadow_evaluate(agent_name, get_price_fn):
    """
    Süresi dolan gölge sinyalleri sonuçlandır.
    get_price_fn: symbol → float (fiyat)
    """
    shadow = _load_shadow()
    signals = shadow.get(agent_name, [])
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    changed = False
    for sig in signals:
        if sig.get('result') is not None:
            continue
        if sig.get('eval_due', '') > now:
            continue
        try:
            price = get_price_fn(sig['symbol'])
            if price and price > 0:
                pct = (price - sig['entry']) / sig['entry'] * 100
                sig['result'] = round(pct, 2)
                changed = True
        except Exception:
            pass
    if changed:
        shadow[agent_name] = signals
        _save_shadow(shadow)

def shadow_stats(agent_name, version=None):
    """Gölge sinyal istatistiklerini döndür."""
    shadow = _load_shadow()
    sigs = [s for s in shadow.get(agent_name, [])
            if s.get('result') is not None
            and (version is None or s.get('version') == version)]
    if not sigs:
        return None
    wins  = sum(1 for s in sigs if s['result'] > 0)
    total = len(sigs)
    return {
        'wins':    wins,
        'total':   total,
        'wr':      round(wins / total * 100, 1),
        'avg_pct': round(sum(s['result'] for s in sigs) / total, 2),
    }

# ─── DeepSeek strateji üretimi ────────────────────────────────────────────────

_SYSTEM_PROMPT = """Sen bir kripto alım stratejisi mühendisisin.
Görev: Verilen mevcut strateji + performans verilerine dayanarak daha iyi bir 'score()' fonksiyonu yaz.

KESİNLİKLE bu imzayı kullan:

def score(closes, highs, lows, volumes, btc_closes, fg_value, extra):
    '''
    closes:    son N kapanış fiyatı (liste, en yeni sonda)
    highs:     yüksekler
    lows:      düşükler
    volumes:   USDT cinsinden hacimler
    btc_closes: BTC kapanışları (piyasa yönü için)
    fg_value:  Fear & Greed Index (0-100)
    extra:     dict {
        'vol_ratio': float,   # mevcut hacim / 21g ortalama
        'rsi1h':     float,   # 1 saatlik RSI
        'rsi15m':    float,   # 15 dakikalık RSI
        'adx':       float,   # trend gücü
        'regime':    str,     # 'BULL' / 'SIDEWAYS' / 'BEAR'
    }
    Döndür: 0.0 - 10.0 arası float (yüksek = güçlü AL sinyali)
    '''
    ...

KATİ KURALLAR:
- Sadece standart Python + numpy (np olarak hazır) + math kullan
- os, sys, open, requests, eval, exec, __import__ YASAK
- Fonksiyon DIŞINDA hiçbir kod yazma
- MUTLAKA 0-10 arası float döndür; hata ihtimaline karşı try/except ekle
- Mevcut stratejiden FARKLI bir mantık kullan — kopyalama yok
- Açıklama satırı ekle (neden bu yaklaşım?)
"""

def _generate_strategy(agent_name, current_code, perf_data, attempt, prev_failures):
    """DeepSeek'ten yeni strateji kodu üret."""
    cfg = load_config()
    key = cfg.get('deepseek_api_key', '')
    if not key:
        print('[Evrim] deepseek_api_key yok')
        return None

    wins  = perf_data.get('wins', 0)
    total = perf_data.get('total', 1)
    wr    = wins / total * 100 if total > 0 else 0
    pnl   = perf_data.get('pnl', 0.0)

    fail_note = ''
    if prev_failures:
        fail_note = '\n\nÖNCEKİ BAŞARISIZ DENEMELER:\n'
        for i, f in enumerate(prev_failures, 1):
            fail_note += f'  {i}. {f}\n'
        fail_note += '\nBu sefer TAMAMEN FARKLI bir yaklaşım dene — öncekilerden hiçbirini tekrarlama.'

    user_msg = (
        f'Ajan: {agent_name}\n'
        f'Son {total} işlem: %{wr:.1f} kazanma oranı, ${pnl:.2f} toplam PnL\n'
        f'HEDEF: En az %55 kazanma oranı\n\n'
        f'MEVCUT ÇALIŞAN STRATEJİ:\n```python\n{current_code}\n```'
        f'{fail_note}\n\n'
        f'Deneme #{attempt}: Yeni ve farklı bir score() fonksiyonu yaz.\n'
        f'Sadece fonksiyon kodunu ver, başka hiçbir şey ekleme.'
    )

    try:
        r = requests.post(
            DEEPSEEK_API,
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user',   'content': user_msg},
                ],
                'temperature': min(0.6 + (attempt - 1) * 0.2, 1.3),
                'max_tokens': 2500,
            },
            timeout=90,
        )
        if not r.ok:
            print(f'[Evrim] DeepSeek HTTP {r.status_code}')
            return None

        content = r.json()['choices'][0]['message']['content']

        # Kod bloğu ayıkla
        for marker in ['```python', '```']:
            if marker in content:
                content = content.split(marker)[1].split('```')[0].strip()
                break

        return content.strip() or None

    except Exception as e:
        print(f'[Evrim] DeepSeek hata: {e}')
        return None

# ─── Challenger yönetimi ─────────────────────────────────────────────────────

def get_challenger_fn(agent_name):
    """
    Aktif challenger fonksiyonunu döndür.
    Çağrı: autonomous_agent._scanner_loop() → gölge değerlendirme için.
    Döner: (fn, version) veya (None, None)
    """
    state = _load_state()
    ag = state.get('agents', {}).get(agent_name, {})
    ch = ag.get('challenger')
    if not ch:
        return None, None
    ver = ch.get('version')
    for v in ag.get('versions', []):
        if v['version'] == ver:
            fn = _sandbox_exec(v['code'])
            return fn, ver
    return None, None

def get_active_fn(agent_name):
    """
    Terfi etmiş (promoted) strateji fonksiyonunu döndür.
    None → varsayılan _score() kullanılır.
    """
    state = _load_state()
    ag = state.get('agents', {}).get(agent_name, {})
    ver = ag.get('active_version', 0)
    if ver == 0:
        return None
    for v in ag.get('versions', []):
        if v['version'] == ver and v.get('status') == 'active':
            return _sandbox_exec(v['code'])
    return None

# ─── Ana evrim döngüsü ────────────────────────────────────────────────────────

def run_evolution(agent_name, perf_data):
    """
    Coach tarafından çağrılır. Tüm evrim mantığını yönetir.

    agent_name: 'OTONOM'
    perf_data:  {'wins': int, 'total': int, 'pnl': float}

    Döner: 'skip' | 'started' | 'waiting' | 'promoted' | 'retrying' | 'exhausted'
    """
    total = perf_data.get('total', 0)
    wins  = perf_data.get('wins', 0)
    wr    = wins / total * 100 if total > 0 else 100.0

    if total < MIN_TRADES_TO_EVOLVE:
        return 'skip'
    if wr >= POOR_WR_THRESHOLD:
        return 'skip'

    state = _load_state()
    ag = state['agents'].setdefault(agent_name, {
        'active_version': 0,
        'versions':       [],
        'challenger':     None,
        'attempts':       0,
        'status':         'idle',
        'failures':       [],
        'exhausted_until': '',
    })

    # Tüm denemeler tükendiyse cooldown kontrol et
    if ag.get('status') == 'exhausted':
        until = ag.get('exhausted_until', '')
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if until > now:
            return 'skip'
        else:
            # Cooldown bitti — sıfırla
            ag['status']    = 'idle'
            ag['attempts']  = 0
            ag['failures']  = []
            ag['challenger'] = None

    # ── Mevcut challenger varsa değerlendir ─────────────────────────────────
    if ag.get('challenger'):
        ch     = ag['challenger']
        ch_ver = ch['version']

        # Süre doldu mu?
        try:
            started_dt = datetime.datetime.strptime(ch['started'], '%Y-%m-%d %H:%M:%S')
            elapsed_h  = (datetime.datetime.now() - started_dt).total_seconds() / 3600
        except Exception:
            elapsed_h = 999

        stats = shadow_stats(agent_name, version=ch_ver)
        n = stats['total'] if stats else 0

        # Yeterli süre ve sinyal: değerlendir
        if elapsed_h >= SHADOW_HOURS or n >= SHADOW_SIGNALS_MIN * 3:
            if stats and n >= SHADOW_SIGNALS_MIN:
                ch_wr = stats['wr']
                if ch_wr > wr + IMPROVEMENT_MARGIN:
                    # ── TERFI ───────────────────────────────────────────────
                    _promote(state, agent_name, ch_ver, stats)
                    send_telegram(
                        f'🧬 <b>Evrim: Yeni Strateji Aktif!</b>\n'
                        f'━━━━━━━━━━━━━━\n'
                        f'🤖 Ajan: {agent_name}\n'
                        f'📈 Eski WR: %{wr:.1f} → Yeni gölge WR: %{ch_wr:.1f}\n'
                        f'🔢 Versiyon: v{ch_ver} — {n} gölge sinyal\n'
                        f'📦 Eski strateji arşivde korunuyor.'
                    )
                    return 'promoted'
                else:
                    # Başarısız — yeni deneme
                    note = (f'v{ch_ver}: gölge WR=%{ch_wr:.1f}, '
                            f'gereken=%{wr + IMPROVEMENT_MARGIN:.1f}')
                    ag.setdefault('failures', []).append(note)
                    ag['challenger'] = None
                    ag['attempts']   = ag.get('attempts', 0) + 1
                    _save_state(state)

                    if ag['attempts'] >= MAX_ATTEMPTS:
                        ag['status'] = 'exhausted'
                        until = (datetime.datetime.now() +
                                 datetime.timedelta(hours=EXHAUSTED_COOLDOWN_H)
                                 ).strftime('%Y-%m-%d %H:%M:%S')
                        ag['exhausted_until'] = until
                        _save_state(state)
                        send_telegram(
                            f'🧬 <b>Evrim: {MAX_ATTEMPTS} Deneme Tükendi</b>\n'
                            f'🤖 {agent_name} — mevcut strateji korunuyor\n'
                            f'⏰ {EXHAUSTED_COOLDOWN_H} saat sonra yeniden denenecek'
                        )
                        return 'exhausted'

                    # Tekrar challenger üret
                    _launch_challenger(state, agent_name, perf_data)
                    return 'retrying'
            else:
                # Yeterli gölge sinyal yok — bekle
                return 'waiting'
        else:
            return 'waiting'

    # ── Yeni evrim döngüsü başlat ────────────────────────────────────────────
    ag['attempts'] = 0
    ag['failures'] = []
    ag['status']   = 'evolving'
    _save_state(state)
    _launch_challenger(state, agent_name, perf_data)
    return 'started'


def _launch_challenger(state, agent_name, perf_data):
    """DeepSeek'ten yeni strateji al, test et, challenger olarak kaydet."""
    ag      = state['agents'][agent_name]
    attempt = ag.get('attempts', 0) + 1
    prev_f  = ag.get('failures', [])

    send_telegram(
        f'🧬 <b>Evrim — {agent_name} (Deneme {attempt}/{MAX_ATTEMPTS})</b>\n'
        f'DeepSeek yeni scoring stratejisi yazıyor...'
    )

    current_code = _get_current_score_code()
    code = _generate_strategy(agent_name, current_code, perf_data, attempt, prev_f)

    if not code:
        send_telegram(f'🧬 ⚠️ {agent_name}: DeepSeek yanıt vermedi')
        return

    fn = _sandbox_exec(code)
    if not fn or not _validate_fn(fn):
        send_telegram(
            f'🧬 ⚠️ {agent_name}: Üretilen kod sandbox/doğrulama testini geçemedi\n'
            f'Kod boyutu: {len(code)} karakter'
        )
        return

    ver = len(ag.get('versions', [])) + 1
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    ag.setdefault('versions', []).append({
        'version': ver,
        'created': now,
        'code':    code,
        'status':  'challenger',
    })
    ag['challenger'] = {'version': ver, 'started': now}
    _save_state(state)

    send_telegram(
        f'🧬 <b>Challenger v{ver} Aktif</b>\n'
        f'━━━━━━━━━━━━━━\n'
        f'🤖 Ajan: {agent_name}\n'
        f'👻 Mod: Gölge — GERÇEK ALIM YOK\n'
        f'⏰ Test süresi: {SHADOW_HOURS} saat\n'
        f'📊 Değerlendirme: {EVAL_HOLD_HOURS} saatlik simüle tutma\n'
        f'📝 Kod: {len(code)} karakter\n'
        f'🎯 Terfi için: mevcut WR + %{IMPROVEMENT_MARGIN:.0f} gerekli'
    )


def _promote(state, agent_name, version, shadow_stats_data):
    """Challenger'ı aktif strateji yap, eskisini arşivle."""
    ag = state['agents'][agent_name]
    for v in ag.get('versions', []):
        if v['version'] == version:
            v['status']       = 'active'
            v['shadow_stats'] = shadow_stats_data
        elif v.get('status') == 'active':
            v['status'] = 'archived'
    ag['active_version'] = version
    ag['challenger']     = None
    ag['status']         = 'idle'
    ag['attempts']       = 0
    _save_state(state)


# ─── Durum sorgusu ────────────────────────────────────────────────────────────

def evolution_status():
    """Web/Telegram için durum özeti."""
    state = _load_state()
    out = {}
    for name, ag in state.get('agents', {}).items():
        sh = shadow_stats(name)
        ch = ag.get('challenger')
        out[name] = {
            'status':         ag.get('status', 'idle'),
            'active_version': ag.get('active_version', 0),
            'challenger':     ch,
            'versions':       len(ag.get('versions', [])),
            'shadow':         sh,
            'attempts':       ag.get('attempts', 0),
        }
    return out
