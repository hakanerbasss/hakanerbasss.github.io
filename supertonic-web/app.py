import os
import sys
import uuid
import asyncio
import subprocess
import json
import time
import re
import hashlib
import secrets
import random
from pathlib import Path
import shutil

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import traceback
import aiofiles
import httpx

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from supertonic import TTS
from deep_translator import GoogleTranslator
import whisper

import news_site
import ig_perf
from ig_analytics_full import fetch_full_analytics
from namaz_bildirim import start_namaz_scheduler
import xtts_clone

app = FastAPI()
app.include_router(news_site.router)

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_CONFIG   = Path("auth_config.json")
SESSIONS_FILE = Path("sessions.json")
_SESSION_TTL  = 7 * 24 * 3600  # 7 gün
_COOKIE       = "instube_session"


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _get_auth_cfg() -> dict:
    if not AUTH_CONFIG.exists():
        AUTH_CONFIG.write_text(json.dumps({"password_hash": _hash_pw("instube2026")}))
    return json.loads(AUTH_CONFIG.read_text())


def _load_sessions() -> dict:
    if SESSIONS_FILE.exists():
        try:
            data = json.loads(SESSIONS_FILE.read_text())
            now = time.time()
            return {t: exp for t, exp in data.items() if exp > now}
        except Exception:
            pass
    return {}


def _save_sessions(sessions: dict) -> None:
    try:
        SESSIONS_FILE.write_text(json.dumps(sessions))
    except Exception:
        pass


_sessions: dict = _load_sessions()  # restart'ta diskten yükle


def _valid_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if not exp or time.time() > exp:
        _sessions.pop(token, None)
        _save_sessions(_sessions)
        return False
    return True


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    host = (request.headers.get("host") or "").split(":")[0]
    # Login sayfası, statik dosyalar ve genel haber sitesi serbest (anonim erişim)
    if (path in ("/login", "/logout", "/ads.txt", "/robots.txt")
            or path.startswith("/static/")
            or path.startswith("/haberler")
            or path.startswith("/haber/")
            or path.startswith("/api/thumbnail/")
            or host == news_site.NEWS_SUBDOMAIN):
        return await call_next(request)
    # Localhost'tan gelen scheduler iç çağrıları serbest
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "::1"):
        return await call_next(request)
    token = request.cookies.get(_COOKIE)
    if not _valid_session(token):
        if path.startswith("/api/"):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


@app.get("/login")
async def login_page():
    return FileResponse("static/login.html")


@app.post("/login")
async def login(request: Request, response: Response):
    form = await request.form()
    password = form.get("password", "")
    cfg = _get_auth_cfg()
    if _hash_pw(password) != cfg.get("password_hash", ""):
        return FileResponse("static/login.html", status_code=401, headers={"X-Login-Error": "1"})
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + _SESSION_TTL
    _save_sessions(_sessions)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="lax", max_age=_SESSION_TTL)
    return resp


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(_COOKIE)
    _sessions.pop(token, None)
    _save_sessions(_sessions)
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(_COOKIE)
    return resp


@app.post("/api/auth/change-password")
async def change_password(request: Request):
    body = await request.json()
    old_pw = body.get("old_password", "")
    new_pw = body.get("new_password", "")
    if len(new_pw) < 6:
        raise HTTPException(400, "Şifre en az 6 karakter olmalı")
    cfg = _get_auth_cfg()
    if _hash_pw(old_pw) != cfg.get("password_hash", ""):
        raise HTTPException(403, "Mevcut şifre yanlış")
    cfg["password_hash"] = _hash_pw(new_pw)
    AUTH_CONFIG.write_text(json.dumps(cfg))
    return {"ok": True}
# ─────────────────────────────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "trace": traceback.format_exc()},
    )


def run_ffmpeg(cmd, timeout, retries=0, step=""):
    """ffmpeg çağrısını çalıştırır.

    subprocess'in varsayılan CalledProcessError mesajı yalnızca komutu yazar,
    ffmpeg'in asıl stderr çıktısını gizler — bu yüzden loglarda "neden" hiç
    görünmüyordu. Burada stderr'in son satırlarını hata mesajına ekliyoruz ve
    geçici (OOM/yük) hatalar için opsiyonel retry sağlıyoruz.
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        except subprocess.CalledProcessError as e:
            err = e.stderr or b""
            if isinstance(err, bytes):
                err = err.decode("utf-8", "ignore")
            err_tail = "\n".join(err.strip().splitlines()[-8:]) or "stderr boş"
            last_err = RuntimeError(
                f"ffmpeg {step} başarısız (exit {e.returncode}): {err_tail}"
            )
        except subprocess.TimeoutExpired:
            last_err = RuntimeError(
                f"ffmpeg {step} {timeout}sn içinde tamamlanamadı (timeout)"
            )
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    raise last_err


async def arun_ffmpeg(cmd, timeout, retries=0, step=""):
    """run_ffmpeg'in async sürümü — event loop'u bloke etmez."""
    return await asyncio.to_thread(run_ffmpeg, cmd, timeout, retries=retries, step=step)


OUTPUT_DIR = Path("outputs")
UPLOAD_DIR = Path("uploads")
COMEDY_UPLOAD_DIR = Path("uploads/comedy")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
COMEDY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

AVATAR_FILE = UPLOAD_DIR / "avatar_photo.jpg"
INFO_ENDCARD_FILE = UPLOAD_DIR / "info_endcard.jpg"
LONGCAT_SPACE = "https://victor-longcat-video-avatar-1-5.hf.space"

BANNED_TOPICS_FILE = Path("banned_topics.json")
CUSTOM_PROMPT_RULES_FILE = Path("custom_prompt_rules.json")


def get_custom_prompt_rules() -> str:
    if not CUSTOM_PROMPT_RULES_FILE.exists():
        return ""
    try:
        return json.loads(CUSTOM_PROMPT_RULES_FILE.read_text()).get("rules", "").strip()
    except Exception:
        return ""


def load_banned_topics() -> list[str]:
    if not BANNED_TOPICS_FILE.exists():
        return []
    try:
        data = json.loads(BANNED_TOPICS_FILE.read_text())
        return [t.strip().lower() for t in data if t.strip()]
    except Exception:
        return []


def save_banned_topics(topics: list[str]):
    BANNED_TOPICS_FILE.write_text(json.dumps(topics, ensure_ascii=False, indent=2))


def _is_banned_topic(title: str) -> bool:
    """Başlık yasaklı kelimelerden herhangi birini içeriyorsa True döner."""
    banned = load_banned_topics()
    if not banned:
        return False
    title_lower = title.lower()
    for kw in banned:
        if kw in title_lower:
            print(f"[BANNED] '{title[:60]}' yasaklı kelime içeriyor: '{kw}'", flush=True)
            return True
    return False

tts_model = None
whisper_model = None

LANG_MAP = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "ar": "Arabic",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
}

VOICES = ["M1", "M2", "M3", "F1", "F2", "F3"]

async def _synth_audio(text: str, lang: str, voice: str, speed: float, out_path: Path) -> float:
    """Ses sentezi. Türkçe+clone modu aktifse XTTS-v2, değilse Supertonic."""
    if lang == "tr" and get_ig_config().get("use_clone_voice", False) and xtts_clone.hazir_mi():
        return await xtts_clone.seslendir(
            _clean_tts_text(text, lang), str(out_path), language="tr", speed=speed
        )
    tts_obj = get_tts()
    style = tts_obj.get_voice_style(voice_name=voice)
    wav, dur = await asyncio.to_thread(tts_obj.synthesize,
        _clean_tts_text(text, lang), lang=lang, voice_style=style, total_steps=8, speed=speed)
    dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
    tts_obj.save_audio(wav, str(out_path))
    return dur_val


def _parse_llm_json(text: str) -> dict:
    """DeepSeek/LLM yanıtından JSON objesini güvenilir şekilde çıkar."""
    import re
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0]
    t = t.strip()
    start = t.find("{")
    end   = t.rfind("}") + 1
    if start >= 0 and end > start:
        t = t[start:end]
    # Trailing comma temizle
    t = re.sub(r",\s*([}\]])", r"\1", t)
    # String içindeki ham satır sonu karakterlerini temizle
    t = re.sub(r'(?<!\\)\n', ' ', t)
    t = re.sub(r'(?<!\\)\r', '', t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # Son çare: sadece geçerli JSON karakterlerini bırak
        t2 = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)
        return json.loads(t2)


def get_tts():
    global tts_model
    if tts_model is None:
        tts_model = TTS(auto_download=True)
    return tts_model


_TR_ONES = ['', 'bir', 'iki', 'üç', 'dört', 'beş', 'altı', 'yedi', 'sekiz', 'dokuz']
_TR_TENS = ['', 'on', 'yirmi', 'otuz', 'kırk', 'elli', 'altmış', 'yetmiş', 'seksen', 'doksan']


def _tr_num_to_words(n: int) -> str:
    """Tam sayıyı Türkçe sözcüklere çevirir. Örn: 1500 → bin beş yüz"""
    if n == 0:
        return 'sıfır'
    if n < 0:
        return 'eksi ' + _tr_num_to_words(-n)
    parts = []
    if n >= 1_000_000_000:
        b = n // 1_000_000_000; n %= 1_000_000_000
        parts.append(('bir' if b == 1 else _tr_num_to_words(b)) + ' milyar')
    if n >= 1_000_000:
        m = n // 1_000_000; n %= 1_000_000
        parts.append(('bir' if m == 1 else _tr_num_to_words(m)) + ' milyon')
    if n >= 1_000:
        t = n // 1_000; n %= 1_000
        parts.append(('' if t == 1 else _tr_num_to_words(t) + ' ') + 'bin')
    if n >= 100:
        h = n // 100; n %= 100
        parts.append(('' if h == 1 else _TR_ONES[h] + ' ') + 'yüz')
    if n >= 10:
        parts.append(_TR_TENS[n // 10]); n %= 10
    if n > 0:
        parts.append(_TR_ONES[n])
    return ' '.join(p.strip() for p in parts if p.strip())


# Sıra sayı eki her zaman sayının SON kelimesine eklenir (ör. "yüz yirmi üç" → "yüz
# yirmi üçüncü") ve Türkçe'de ünlü uyumu + ünsüz yumuşaması içerir (dört→dördüncü).
# Son kelime her zaman bu sabit listelerden biri olduğu için (birler/onlar/yüz/bin/
# milyon/milyar), tam algoritma yerine sonlu bir sözlük yeterli ve daha güvenilir.
_TR_ORDINAL_MAP = {
    'sıfır': 'sıfırıncı', 'bir': 'birinci', 'iki': 'ikinci', 'üç': 'üçüncü',
    'dört': 'dördüncü', 'beş': 'beşinci', 'altı': 'altıncı', 'yedi': 'yedinci',
    'sekiz': 'sekizinci', 'dokuz': 'dokuzuncu',
    'on': 'onuncu', 'yirmi': 'yirminci', 'otuz': 'otuzuncu', 'kırk': 'kırkıncı',
    'elli': 'ellinci', 'altmış': 'altmışıncı', 'yetmiş': 'yetmişinci',
    'seksen': 'sekseninci', 'doksan': 'doksanıncı',
    'yüz': 'yüzüncü', 'bin': 'bininci', 'milyon': 'milyonuncu', 'milyar': 'milyarıncı',
}


def _tr_ordinal_words(n: int) -> str:
    """Sıra sayı sözcüğü üretir. Örn: 13 → on üçüncü, 1 → birinci."""
    words = _tr_num_to_words(n).split(' ')
    words[-1] = _TR_ORDINAL_MAP.get(words[-1], words[-1] + 'ıncı')
    return ' '.join(words)


# Kaynak metinde sayı/birimden sonra kesme işaretiyle gelen hal ekleri (14:30'DA,
# 250 TL'YE, 2027'DE gibi) SİLİNMEMELİ — ek cümledeki iki sayıyı birbirinden ayıran
# tek şey, eksik olunca "on dört otuz dokuz" gibi anlamsız bitişik okuma oluyor.
# Sayı sözcüğünün SON kelimesi her zaman bu sabit listelerden biri olduğu için
# (birler/onlar/yüz/bin/milyon/milyar + enjekte ettiğimiz birim sözcükleri), genel
# bir ünlü-uyumu algoritması yerine sonlu bir sözlük kullanılıyor — Türkçe'de
# ünsüz yumuşaması (dört→dörde) bazı kelimelerde düzensiz, sözlük daha güvenilir.
_TR_DATIVE = {          # -a/-e/-ya/-ye ("...e/a", "'a kadar" gibi)
    'sıfır':'sıfıra','bir':'bire','iki':'ikiye','üç':'üçe','dört':'dörde','beş':'beşe',
    'altı':'altıya','yedi':'yediye','sekiz':'sekize','dokuz':'dokuza',
    'on':'ona','yirmi':'yirmiye','otuz':'otuza','kırk':'kırka','elli':'elliye',
    'altmış':'altmışa','yetmiş':'yetmişe','seksen':'seksene','doksan':'doksana',
    'yüz':'yüze','bin':'bine','milyon':'milyona','milyar':'milyara',
    'santigrat':'santigrada','derece':'dereceye','fahrenheit':'fahrenheite',
    'lira':'liraya','kilometre':'kilometreye','kilogram':'kilograma',
    'metrekare':'metrekareye','metreküp':'metreküpe',
    'dolar':'dolara','euro':'euroya','sterlin':'sterline','saat':'saate','nesil':'nesile',
    'gigabayt':'gigabayta','megabayt':'megabayta','kilobayt':'kilobayta','terabayt':'terabayta',
    'gigabit':'gigabite','megabit':'megabite','kilobit':'kilobite',
}
_TR_LOCATIVE = {        # -da/-de/-ta/-te ("...da/de")
    'sıfır':'sıfırda','bir':'birde','iki':'ikide','üç':'üçte','dört':'dörtte','beş':'beşte',
    'altı':'altıda','yedi':'yedide','sekiz':'sekizde','dokuz':'dokuzda',
    'on':'onda','yirmi':'yirmide','otuz':'otuzda','kırk':'kırkta','elli':'ellide',
    'altmış':'altmışta','yetmiş':'yetmişte','seksen':'seksende','doksan':'doksanda',
    'yüz':'yüzde','bin':'binde','milyon':'milyonda','milyar':'milyarda',
    'santigrat':'santigratta','derece':'derecede','fahrenheit':'fahrenheitte',
    'lira':'lirada','kilometre':'kilometrede','kilogram':'kilogramda',
    'metrekare':'metrekarede','metreküp':'metreküpte',
    'dolar':'dolarda','euro':'euroda','sterlin':'sterlinde','saat':'saatte','nesil':'nesilde',
    'gigabayt':'gigabaytta','megabayt':'megabaytta','kilobayt':'kilobaytta','terabayt':'terabaytta',
    'gigabit':'gigabitte','megabit':'megabitte','kilobit':'kilobitte',
}
_TR_ABLATIVE = {        # -dan/-den/-tan/-ten ("...dan/den")
    'sıfır':'sıfırdan','bir':'birden','iki':'ikiden','üç':'üçten','dört':'dörtten','beş':'beşten',
    'altı':'altıdan','yedi':'yediden','sekiz':'sekizden','dokuz':'dokuzdan',
    'on':'ondan','yirmi':'yirmiden','otuz':'otuzdan','kırk':'kırktan','elli':'elliden',
    'altmış':'altmıştan','yetmiş':'yetmişten','seksen':'seksenden','doksan':'doksandan',
    'yüz':'yüzden','bin':'binden','milyon':'milyondan','milyar':'milyardan',
    'santigrat':'santigrattan','derece':'dereceden','fahrenheit':'fahrenheitten',
    'lira':'liradan','kilometre':'kilometreden','kilogram':'kilogramdan',
    'metrekare':'metrekareden','metreküp':'metreküpten',
    'dolar':'dolardan','euro':'eurodan','sterlin':'sterlinden','saat':'saatten','nesil':'nesilden',
    'gigabayt':'gigabayttan','megabayt':'megabayttan','kilobayt':'kilobayttan','terabayt':'terabayttan',
    'gigabit':'gigabitten','megabit':'megabitten','kilobit':'kilobitten',
}
_TR_POSS_LOC = {        # "ayın 5'inde" → "ayın beşinde" (iyelik+bulunma birleşik eki)
    'sıfır':'sıfırında','bir':'birinde','iki':'ikisinde','üç':'üçünde','dört':'dördünde','beş':'beşinde',
    'altı':'altısında','yedi':'yedisinde','sekiz':'sekizinde','dokuz':'dokuzunda',
    'on':'onunda','yirmi':'yirmisinde','otuz':'otuzunda','kırk':'kırkında','elli':'ellisinde',
    'altmış':'altmışında','yetmiş':'yetmişinde','seksen':'sekseninde','doksan':'doksanında',
    'yüz':'yüzünde','bin':'bininde','milyon':'milyonunda','milyar':'milyarında',
}
_TR_GENITIVE = {        # "2026'nın ilk çeyreğinde" → "iki bin yirmi altının ilk çeyreğinde"
    'sıfır':'sıfırın','bir':'birin','iki':'ikinin','üç':'üçün','dört':'dördün','beş':'beşin',
    'altı':'altının','yedi':'yedinin','sekiz':'sekizin','dokuz':'dokuzun',
    'on':'onun','yirmi':'yirminin','otuz':'otuzun','kırk':'kırkın','elli':'ellinin',
    'altmış':'altmışın','yetmiş':'yetmişin','seksen':'sekseninin','doksan':'doksanın',
    'yüz':'yüzün','bin':'binin','milyon':'milyonun','milyar':'milyarın',
}


def _classify_tr_suffix(raw: str) -> str:
    """Kesme işaretinden sonraki ek harflerine bakıp ek TÜRÜNÜ tahmin eder."""
    s = raw.lower()
    if s.endswith('nde') or s.endswith('nda'):
        return 'possloc'
    if s.endswith('nin') or s.endswith('nın') or s.endswith('nun') or s.endswith('nün') \
       or s in ('in', 'ın', 'un', 'ün'):
        return 'genitive'  # 'nin' (ünlüyle biten kök, tampon n) veya 'in' (ünsüzle biten kök)
    if s.endswith('den') or s.endswith('dan') or s.endswith('ten') or s.endswith('tan'):
        return 'ablative'
    if s.endswith('de') or s.endswith('da') or s.endswith('te') or s.endswith('ta'):
        return 'locative'
    if s in ('a', 'e', 'ya', 'ye'):
        return 'dative'
    return ''


def _tr_attach_suffix(phrase: str, raw_suffix: str) -> str:
    """Dönüştürülmüş sayı ifadesinin (ör. 'otuz dört') SON kelimesine, orijinal
    kesme işaretli ekin türüne göre doğru Türkçe hal ekini bağlar. Tanınmayan/az
    rastlanan ek türlerinde (ör. '-lik', '-ini' iyelik-belirtme) güvenli şekilde
    eksiz bırakır — yanlış ek eklemek, hiç eklememekten daha kötü bir okuma
    hatasına yol açar."""
    if not raw_suffix:
        return phrase
    kind = _classify_tr_suffix(raw_suffix)
    table = {'dative': _TR_DATIVE, 'locative': _TR_LOCATIVE, 'ablative': _TR_ABLATIVE,
             'possloc': _TR_POSS_LOC, 'genitive': _TR_GENITIVE}.get(kind)
    if not table:
        return phrase
    words = phrase.split(' ')
    last = words[-1]
    if last in table:
        words[-1] = table[last]
        return ' '.join(words)
    return phrase


def _clean_tts_text(text: str, lang: str = "tr") -> str:
    """TTS'e gitmeden önce metni temizle — sayı/format hatalarını düzelt."""
    import re

    # Markdown kalıntılarını kaldır
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    if lang == "tr":
        # URL'leri kaldır (daha önce olmalı — rakam regex'lerinden önce)
        text = re.sub(r'https?://\S+', '', text)

        # Kurum/sınav kısaltmaları — DeepSeek promptunda 'bunları asla yazma,
        # tam adını yaz' kuralı zaten var ama LLM talimatlara her zaman uymuyor
        # (aynı 'rakam yazma' talimatının tutmaması gibi). Metin tarafında da
        # bir güvenlik ağı: kaçan kısaltmalar burada açılıyor. Büyük/küçük harf
        # duyarlı — bu kısaltmalar Türkçe metinde her zaman büyük harfle yazılır,
        # rastgele kelime çakışmasını önler.
        _TR_KISALTMA_ACILIM = {
            'TBMM': 'Türkiye Büyük Millet Meclisi',
            'YKS': 'Yükseköğretim Kurumları Sınavı',
            'LGS': 'Liselere Geçiş Sınavı',
            'ÖSS': 'Öğrenci Seçme Sınavı',
            'ÖSYM': 'Ölçme, Seçme ve Yerleştirme Merkezi',
            'SGK': 'Sosyal Güvenlik Kurumu',
            'ABD': 'Amerika Birleşik Devletleri',
            'AKP': 'Adalet ve Kalkınma Partisi',
            'CHP': 'Cumhuriyet Halk Partisi',
            'MHP': 'Milliyetçi Hareket Partisi',
            'TÜBİTAK': 'Türkiye Bilimsel ve Teknolojik Araştırma Kurumu',
            'MEB': 'Milli Eğitim Bakanlığı',
            'TÜİK': 'Türkiye İstatistik Kurumu',
            'TCMB': 'Türkiye Cumhuriyet Merkez Bankası',
            'BM': 'Birleşmiş Milletler',
            'AB': 'Avrupa Birliği',
        }
        # Açılımın SON kelimesi ünlüyle bittiği için hal eki tampon 'n' ister
        # (Kurumu'ndan, Meclisi'nde gibi) — genel güvenlik ağı sadece apostrofu
        # silip harfleri bitiştirdiği için tampon kayboluyordu ('Kurumudan').
        # Sayılardaki _tr_attach_suffix ile aynı mantık, açılımların son
        # kelimesine özel küçük bir sözlükle uygulanıyor.
        _TR_KISALTMA_SON_KELIME_EKI = {
            'Meclisi':    {'dative':'Meclisine','locative':'Meclisinde','ablative':'Meclisinden','genitive':'Meclisinin'},
            'Kurumu':     {'dative':'Kurumuna','locative':'Kurumunda','ablative':'Kurumundan','genitive':'Kurumunun'},
            'Devletleri': {'dative':'Devletlerine','locative':'Devletlerinde','ablative':'Devletlerinden','genitive':'Devletlerinin'},
            'Partisi':    {'dative':'Partisine','locative':'Partisinde','ablative':'Partisinden','genitive':'Partisinin'},
            'Bankası':    {'dative':'Bankasına','locative':'Bankasında','ablative':'Bankasından','genitive':'Bankasının'},
            'Milletler':  {'dative':'Milletlere','locative':'Milletlerde','ablative':'Milletlerden','genitive':'Milletlerin'},
            'Birliği':    {'dative':'Birliğine','locative':'Birliğinde','ablative':'Birliğinden','genitive':'Birliğinin'},
            'Sınavı':     {'dative':'Sınavına','locative':'Sınavında','ablative':'Sınavından','genitive':'Sınavının'},
            'Bakanlığı':  {'dative':'Bakanlığına','locative':'Bakanlığında','ablative':'Bakanlığından','genitive':'Bakanlığının'},
        }
        def _kisaltma_ek_bagla(acilim, raw_suffix):
            if not raw_suffix:
                return acilim
            kind = _classify_tr_suffix(raw_suffix)
            forms = _TR_KISALTMA_SON_KELIME_EKI.get(acilim.split(' ')[-1])
            if kind and forms and kind in forms:
                words = acilim.split(' ')
                words[-1] = forms[kind]
                return ' '.join(words)
            return acilim
        _EKYAK_ERKEN = r"(?:['’]([a-zçğıöşüA-ZÇĞİÖŞÜ]{1,4}))?"
        for _kis, _acilim in _TR_KISALTMA_ACILIM.items():
            def _repl(m, _ac=_acilim):
                return _kisaltma_ek_bagla(_ac, m.group(1) or '')
            # IGNORECASE: DeepSeek her zaman tam büyük harfle yazmıyor ('Yks',
            # 'yks' gibi karışık/küçük harfli varyantlar da kaçmasın diye.
            # Bu kısaltmaların hiçbiri gerçek Türkçe kelimeyle çakışmadığı için
            # (ab/bm/yks vb. tek başına anlamlı kelime değil) risksiz.
            text = re.sub(rf'\b{re.escape(_kis)}\b' + _EKYAK_ERKEN, _repl, text, flags=re.IGNORECASE)

        # Sayıya BİTİŞİK yazılan birim kısaltmalarının arasına boşluk sok
        # (5GB → 5 GB) — aşağıdaki birim regex'lerinin hepsi \b sınırına
        # dayanıyor, bitişik yazımda "5GB" tek kelime sayılıp hiç açılmıyordu.
        # NOT: bare 'G' (5G nesil göstergesi) BİLEREK bu listede yok — o özel
        # olarak bitişik kalmalı, aşağıda ayrıca ele alınıyor.
        _BITISIK_BIRIMLER = ['Gbps','Mbps','Kbps','GB','MB','KB','TB','TL',
                             'km/s','km²','km³','km','kg','cm²','cm³','cm','mm²','mm',
                             'TWh','GWh','MWh','kWh','Wh','TW','GW','MW','kW','ppm']
        for _birim in _BITISIK_BIRIMLER:
            text = re.sub(rf'(?<=\d)({re.escape(_birim)})\b', r' \1', text, flags=re.IGNORECASE)

        # Para birimleri: $50 → 50 dolar, €50 → 50 euro, £50 → 50 sterlin
        text = re.sub(r'\$\s*(\d[\d.,]*)', r'\1 dolar', text)
        text = re.sub(r'€\s*(\d[\d.,]*)', r'\1 euro', text)
        text = re.sub(r'£\s*(\d[\d.,]*)', r'\1 sterlin', text)

        # Saat aralığı: 14:00-16:00 → saat on dört - saat on altı. TEKİL saat
        # regex'inden ÖNCE işlenmeli, yoksa aradaki tire çıplak kalır
        # ("saat on dört -saat on altı" gibi bitişik/garip okuma).
        def _saat_phrase(h, mn):
            p = 'saat ' + _tr_num_to_words(h)
            if mn:
                p += ' ' + _tr_num_to_words(mn)
            return p
        def _saat_araligi(m):
            h1, mn1, h2, mn2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return _saat_phrase(h1, mn1) + ' - ' + _saat_phrase(h2, mn2)
        text = re.sub(r'\b(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})\b', _saat_araligi, text)

        # Saat: 14:30 → saat on dört otuz. Kaynak metinde önünde zaten "saat"
        # kelimesi varsa (ör. "saat 14:30'da") onu da yutuyoruz — yoksa "saat
        # saat on dört otuz" gibi tekrar oluyordu. Arkasındaki hal eki (14:30'DA)
        # doğru ünlü uyumuyla son kelimeye bağlanır — dakika sıfırsa (14:00'te
        # gibi tam saatlerde) sondaki boşluk _tr_attach_suffix'i şaşırtmasın
        # diye strip() ile temizlenir (son kelime 'sıfır'/saat sözü olsun).
        def _saat(m):
            h, mn = int(m.group(1)), int(m.group(2))
            phrase = _saat_phrase(h, mn)
            return _tr_attach_suffix(phrase, m.group(3) or '')
        text = re.sub(r"(?:\bsaat\s+)?\b(\d{1,2}):(\d{2})\b(?:['’]([a-zçğıöşüA-ZÇĞİÖŞÜ]{1,4}))?",
                      _saat, text, flags=re.IGNORECASE)

        # Tarih: 12.07.2026 veya 12/07/2026 → on iki temmuz iki bin yirmi altı
        _AYLAR = {1:'ocak',2:'şubat',3:'mart',4:'nisan',5:'mayıs',6:'haziran',
                  7:'temmuz',8:'ağustos',9:'eylül',10:'ekim',11:'kasım',12:'aralık'}
        def _tarih(m):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31 and y > 1900:
                return _tr_num_to_words(d) + ' ' + _AYLAR[mo] + ' ' + _tr_num_to_words(y)
            return m.group(0)
        text = re.sub(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b', _tarih, text)

        # On yıl (yüzyıl) eki: "1850'lerde" → "bin sekiz yüz elliler de" tipi
        # değil, TEK kelime "elliler" + varsa ikinci ek. ÖNCE işlenmeli —
        # genel _EKYAK yakalayıcısı en fazla 4 harf alıyor, 'lerde'/'larda'
        # (5 harf) buna sığmıyor ve "bin sekiz yüz ellie" gibi bozuk/anlamsız
        # bir bitişikliğe yol açıyordu (4 harf tüketilip 5.si dışarıda kalıyordu).
        # "ler"/"lar" kaynakta zaten doğru ünlü uyumuyla seçildiği için, arkasından
        # gelen ikinci eki (varsa) yeniden hesaplamadan olduğu gibi bitiştiriyoruz.
        def _yil_coğul(m):
            yil = int(m.group(1))
            coğul = m.group(2)
            ek = m.group(3) or ''
            words = _tr_num_to_words(yil).split(' ')
            words[-1] = words[-1] + coğul + ek
            return ' '.join(words)
        text = re.sub(r"\b(\d{4})['’](ler|lar)([a-zçğıöşü]{0,5})\b", _yil_coğul, text, flags=re.IGNORECASE)

        # Yüzde aralığı: %10-15 → yüzde on - on beş. TEKİL yüzde regex'inden
        # ÖNCE işlenmeli — yoksa ilk sayı %'den ayrı çevrilip aradaki tire
        # çıplak kalıyordu ("yüzde on-on beş" gibi bitişik okuma).
        text = re.sub(r'%\s*(\d+)-(\d+)',
                      lambda m: 'yüzde ' + _tr_num_to_words(int(m.group(1))) + ' - ' + _tr_num_to_words(int(m.group(2))),
                      text)

        # Yüzde: %85 → yüzde seksen beş, %13,52 → yüzde on üç virgül elli iki
        # ÖNCE işlenmeli — ondalık virgül regex'i "%13,52" içindeki "13,52"yi
        # kendi başına yakalayıp "%" işaretini boşta bırakıyordu.
        def _yuzde(m):
            out = 'yüzde ' + _tr_num_to_words(int(m.group(1)))
            if m.group(2):
                out += ' virgül ' + _tr_num_to_words(int(m.group(2)))
            return out
        text = re.sub(r'%\s*(\d+)(?:,(\d{1,2}))?', _yuzde, text)

        # Sıra sayılar: "13." (nokta + boşluk/son, arkasında rakam YOK) → "on üçüncü"
        # ÖNCE işlenmeli — aksi halde "13." önce "on üç." olur, sıra anlamı kaybolur.
        def _sira_sayi(m):
            return _tr_ordinal_words(int(m.group(1)))
        text = re.sub(r'\b(\d{1,4})\.(?=\s|$)', _sira_sayi, text)

        _EKYAK = r"(?:['’]([a-zçğıöşüA-ZÇĞİÖŞÜ]{1,4}))?"  # kesme işaretli ek — yakalanır, silinmez

        # Mobil nesil: 5G → beşinci nesil. Genel büyük-sayı dönüşümünden ÖNCE
        # işlenmeli — yoksa '5' sözcüğe çevrilir ama bitişik 'G' harfi öylece
        # kalır ('beşG' gibi tek garip token oluşur, TTS'i şaşırtır). Arkasındaki
        # ek de (5G'YE gibi) yakalanıp doğru bağlanır — yoksa güvenlik ağı sadece
        # apostrofu silip 'nesilye' gibi kuralsız bir bitişik bırakıyordu.
        _TR_NESIL = {1:'birinci',2:'ikinci',3:'üçüncü',4:'dördüncü',5:'beşinci',6:'altıncı'}
        def _nesil(m):
            n = int(m.group(1))
            phrase = _TR_NESIL.get(n, _tr_ordinal_words(n)) + ' nesil'
            return _tr_attach_suffix(phrase, m.group(2) or '')
        text = re.sub(r'\b([1-9])[Gg]\b' + _EKYAK, _nesil, text)

        # İki sayı arası tire: hem maç skoru (3-1) hem aralık (10-15 derece)
        # anlamına gelebilir — bağlamdan ayırt etmek güvenilir değil. İlk
        # denemede skora göre "e" hali eklemiştim ("ona on beş derece" gibi
        # aralıklarda anlamsız çıktı verdi). Güvenli ortak çözüm: ikisi de
        # doğal okunan düz yan yana biçim — "üç bir" (skor, doğru), "on on
        # beş" (aralık, "arasında" ile birlikte anlaşılır kalıyor).
        text = re.sub(r'\b(\d+)-(\d+)\b',
                      lambda m: _tr_num_to_words(int(m.group(1))) + ' ' + _tr_num_to_words(int(m.group(2))),
                      text)

        # Sıcaklık/derece — BÜYÜK SAYI'DAN ÖNCE işlenmeli, yoksa rakam zaten
        # sözcüğe çevrilmiş olur ve "\d+°C" deseni artık eşleşmez (35°C → "otuz
        # beş°C" kalır, °C hiç açılmaz). Ondalık sıcaklık da desteklenir (36,6°C).
        # Arkasındaki hal eki (38°C'YE) doğru ünlü uyumuyla bağlanır, silinmez.
        def _sicaklik(birim):
            def _f(m):
                whole = _tr_num_to_words(int(m.group(1)))
                if m.group(2):
                    whole += ' virgül ' + _tr_num_to_words(int(m.group(2)))
                return _tr_attach_suffix(whole + ' ' + birim, m.group(3) or '')
            return _f
        text = re.sub(r'(-?\d+)(?:[.,](\d{1,2}))?°C' + _EKYAK, _sicaklik('derece'), text)
        text = re.sub(r'(-?\d+)(?:[.,](\d{1,2}))?°F' + _EKYAK, _sicaklik('fahrenheit'), text)
        text = re.sub(r'(-?\d+)(?:[.,](\d{1,2}))?°' + _EKYAK, _sicaklik('derece'), text)
        # Eksi işaretini (sıcaklık dışı bağlamda da) sözcüğe çevir: -5 → eksi beş,
        # -3,5 → eksi üç virgül beş (ondalık kısmı da TEK regex'te yakalanmalı —
        # ayrı geçseydi ondalık virgül regex'i "-" den sonraki rakamı bulamazdı).
        def _eksi_sayi(m):
            out = 'eksi ' + _tr_num_to_words(int(m.group(1)))
            if m.group(2):
                out += ' virgül ' + _tr_num_to_words(int(m.group(2)))
            return _tr_attach_suffix(out, m.group(3) or '')
        text = re.sub(r'(?<![\w])-(\d+)(?:,(\d{1,2}))?(?!\d)' + _EKYAK, _eksi_sayi, text)

        # Ondalık kısım sözcüğe çevrilirken: 1-2 haneliyse tek sayı olarak
        # ("52" → "elli iki"), 3+ haneliyse hassasiyet kaybolmasın diye hane
        # hane okunur ("003" → "sıfır sıfır üç" — "üç" desek 0,003 ile 0,3
        # birbirine karışırdı, baştaki sıfırların anlamı kaybolurdu).
        def _tr_ondalik_kisim(frac: str) -> str:
            if len(frac) <= 2:
                return _tr_num_to_words(int(frac))
            return ' '.join(_tr_num_to_words(int(c)) for c in frac)

        # Ondalık sayı — ÖNCE binlik ayırıcıdan önce işlenmeli. NOKTA burada {1,2}
        # İLE SINIRLI KALMALI (virgül gibi {1,4}'e ÇIKARILMAMALI) — Türkçe'de
        # binlik ayıracı da NOKTA olduğu için ('2.500.000'), 3 haneli bir grup
        # gelince bunu ondalık sanıp 'iki nokta beş yüz' gibi tamamen yanlış
        # okuyordu (gerçek bug, canlıda yakalandı). {1,2} sınırı, 3 haneli
        # binlik gruplarının bu regex'e hiç takılmayıp aşağıdaki binlik ayırıcı
        # adımına düşmesini sağlayan örtük ayrım mekanizması — bilerek dar tutulur.
        # 3.5 → üç nokta beş
        def _ondalik_nokta(m):
            out = _tr_num_to_words(int(m.group(1))) + ' nokta ' + _tr_ondalik_kisim(m.group(2))
            return _tr_attach_suffix(out, m.group(3) or '')
        text = re.sub(r'\b(\d+)\.(\d{1,2})(?!\d)' + _EKYAK, _ondalik_nokta, text)
        # 3,5 → üç virgül beş
        def _ondalik_virgul(m):
            out = _tr_num_to_words(int(m.group(1))) + ' virgül ' + _tr_ondalik_kisim(m.group(2))
            return _tr_attach_suffix(out, m.group(3) or '')
        text = re.sub(r'\b(\d+),(\d{1,4})(?!\d)' + _EKYAK, _ondalik_virgul, text)

        # Binlik nokta ayırıcıyı kaldır: 1.500 → 1500
        text = re.sub(r'(\d)\.(\d{3})\b', r'\1\2', text)

        # Büyük sayıları sözcüğe çevir: TÜM rakamlar çevrilir (Supertonic hiçbir
        # rakamı — 1000 altı dahil — doğru okuyamıyor, eşik kaldırıldı). Arkasındaki
        # hal eki (2027'DE, 5'İNDE gibi) doğru ünlü uyumuyla bağlanır.
        def _buyuk_sayi(m):
            n = int(m.group(1).replace('.', ''))
            return _tr_attach_suffix(_tr_num_to_words(n), m.group(2) or '')
        text = re.sub(r'\b(\d[\d.]*)' + _EKYAK, _buyuk_sayi, text)

        # Kısaltmalar — rakam zaten yukarıda sözcüğe çevrildi, burada sadece birim
        # kısaltması açılıyor. Arkasındaki hal eki (TL'YE, m³'LÜK gibi) doğru ünlü
        # uyumuyla bağlanır (lira'ye değil liraya, metreküp'lük değil metreküpe vb.).
        def _kisaltma(kelime):
            def _f(m):
                return _tr_attach_suffix(kelime, m.group(1) or '')
            return _f
        text = re.sub(r'\bTL\b' + _EKYAK, _kisaltma('lira'), text)
        text = re.sub(r'\bkm/s\b' + _EKYAK, _kisaltma('kilometre saat'), text, flags=re.IGNORECASE)
        # ² / ³'lü birimler ÖNCE işlenmeli — yoksa \bkm\b gibi eksiz kalıplar
        # önce eşleşip "km²" içindeki "km"yi tek başına yer, "²" açılmadan kalır.
        text = re.sub(r'\bkm²\b' + _EKYAK, _kisaltma('kilometrekare'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bkm³\b' + _EKYAK, _kisaltma('kilometreküp'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bcm²\b' + _EKYAK, _kisaltma('santimetrekare'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bcm³\b' + _EKYAK, _kisaltma('santimetreküp'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bmm²\b' + _EKYAK, _kisaltma('milimetrekare'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bkm\b' + _EKYAK, _kisaltma('kilometre'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bcm\b' + _EKYAK, _kisaltma('santimetre'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bmm\b' + _EKYAK, _kisaltma('milimetre'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bkg\b' + _EKYAK, _kisaltma('kilogram'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bm²\b' + _EKYAK, _kisaltma('metrekare'), text)
        text = re.sub(r'\bm³\b' + _EKYAK, _kisaltma('metreküp'), text)

        # Veri birimleri — bps'li (hız) birimler ÖNCE işlenmeli, yoksa \bMB\b gibi
        # kısa kalıp "Mbps" içindeki "Mb"yi yanlışlıkla yer (sınır kontrolü çoğu
        # zaman engeller ama önce işlemek daha güvenli/açık).
        text = re.sub(r'\bGbps\b' + _EKYAK, _kisaltma('gigabit'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bMbps\b' + _EKYAK, _kisaltma('megabit'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bKbps\b' + _EKYAK, _kisaltma('kilobit'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bTB\b' + _EKYAK, _kisaltma('terabayt'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bGB\b' + _EKYAK, _kisaltma('gigabayt'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bMB\b' + _EKYAK, _kisaltma('megabayt'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bKB\b' + _EKYAK, _kisaltma('kilobayt'), text, flags=re.IGNORECASE)

        # Enerji birimleri (Wh ailesi) — karışık büyük/küçük harfli (MWh, kWh)
        # olduğu için ne birim kısaltma listesinde ne de harf-harf ayırma
        # düzeneğinde (o sadece TAMAMEN büyük harfli kısaltmaları yakalıyor)
        # yakalanıyordu, tamamen dokunulmadan kalıyordu. 'saat' zaten hal eki
        # sözlüklerinde olduğu için ek bağlama otomatik doğru çalışıyor
        # ('1.287 MWh'a' → '...megavat saate').
        text = re.sub(r'\bTWh\b' + _EKYAK, _kisaltma('teravat saat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bGWh\b' + _EKYAK, _kisaltma('gigavat saat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bMWh\b' + _EKYAK, _kisaltma('megavat saat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bkWh\b' + _EKYAK, _kisaltma('kilovat saat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bWh\b' + _EKYAK, _kisaltma('vat saat'), text)
        text = re.sub(r'\bTW\b' + _EKYAK, _kisaltma('teravat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bGW\b' + _EKYAK, _kisaltma('gigavat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bMW\b' + _EKYAK, _kisaltma('megavat'), text, flags=re.IGNORECASE)
        text = re.sub(r'\bkW\b' + _EKYAK, _kisaltma('kilovat'), text, flags=re.IGNORECASE)
        # ppm (milyonda parça) — küçük harfli olduğu için harf-harf ayırma
        # düzeneği de (büyük harf gerektiriyor) bunu yakalamıyordu.
        text = re.sub(r'\bppm\b' + _EKYAK, _kisaltma('milyonda bir'), text, flags=re.IGNORECASE)

        # Kısaltma sözlüğümüzde olmayan (ÇYDD, PKK, TRT, KHK gibi — sonsuz
        # sayıda olabilecek) büyük harfli kısaltmalar için son çare: harfleri
        # boşlukla ayır ki Supertonic her harfi ayrı ayrı Türkçe harf ismiyle
        # okusun ('Ç Y D D'), tek bitişik "kelime" gibi okuyup İngilizce
        # telaffuza kaçmasın. İSTİSNA: bazı kısaltmalar Türkçe'de tek kelime
        # gibi okunur (NATO → "nato", FETÖ → "fetö") — onları bölersek bozulur,
        # o yüzden ayrı bir listede tutulup dokunulmuyor.
        _TR_KISALTMA_KELIME_GIBI = {'NATO','FETÖ','UEFA','FIFA','AFAD','ASELSAN','TUSAŞ','ROKETSAN'}
        def _harf_harf(m):
            kelime = m.group(0)
            if kelime.upper() in _TR_KISALTMA_KELIME_GIBI:
                return kelime
            return ' '.join(kelime)
        text = re.sub(r'\b[A-ZÇĞİÖŞÜ]{2,6}\b', _harf_harf, text)

        # Son güvenlik ağı: sayı/birim dışındaki kelimelerde de (özel adlar,
        # "Meteoroloji'den" gibi) kesme işareti+ek kalıyordu — bunlar bizim sayı
        # sözlüğümüzde olmadığı için yukarıdaki _tr_attach_suffix hiç devreye
        # girmiyordu. ÇÖZÜM: eki SİLMEK değil, sadece kesme işaretini kaldırıp
        # ekin harflerini kelimeye BİTİŞİK bırakmak — Türkçe'de kesme işareti
        # zaten yalnızca yazım kuralı, telaffuzu etkilemiyor, bu yüzden
        # "Meteoroloji'den" → "Meteorolojiden" tamamen doğru ve ek korunmuş okunur.
        text = re.sub(r"(?<=\w)['’](?=[a-zçğıöşüA-ZÇĞİÖŞÜ]{1,4}\b)", '', text)

    # URL'leri kaldır (lang != tr için de)
    text = re.sub(r'https?://\S+', '', text)
    # Özel semboller
    text = re.sub(r'[#@|_~^\\<>{}[\]]', ' ', text)
    # Birden fazla boşluk → tek boşluk
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _format_hashtags(raw_tags: list, limit: int = 5) -> str:
    """Hashtag'leri boşlukla ayırır (virgül Instagram'da hatalı görünüyor), sayıyı sınırlar."""
    tags = []
    for t in raw_tags:
        t = t.lstrip("#").replace(" ", "").strip()
        if t and t not in tags:
            tags.append(t)
        if len(tags) >= limit:
            break
    return " ".join(f"#{t}" for t in tags)


def _smart_truncate(text: str, limit: int = 300) -> str:
    """Metni kelime sınırında keser, sadece gerçekten kesildiyse '...' ekler."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}..."


def get_whisper():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model


@app.get("/")
async def index(request: Request):
    host = (request.headers.get("host") or "").split(":")[0]
    if host == news_site.NEWS_SUBDOMAIN:
        return await news_site.haberler_list(request, sayfa=1)
    return FileResponse("static/index.html")


@app.get("/api/voices")
async def voices():
    return {"voices": VOICES, "languages": LANG_MAP}


@app.post("/api/synthesize")
async def synthesize(
    text: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
):
    if not text.strip():
        raise HTTPException(400, "Metin boş olamaz")
    if lang not in LANG_MAP:
        raise HTTPException(400, "Desteklenmeyen dil")
    if voice not in VOICES:
        raise HTTPException(400, "Geçersiz ses")

    out_file = OUTPUT_DIR / f"{uuid.uuid4()}.wav"

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    wav, duration = await asyncio.to_thread(tts.synthesize,
        _clean_tts_text(text, lang), lang=lang,
        voice_style=style, total_steps=8, speed=speed,
    )

    tts.save_audio(wav, str(out_file))

    dur = float(duration[0]) if hasattr(duration, '__getitem__') else float(duration)
    return {"file": f"/api/audio/{out_file.name}", "duration": round(dur, 2)}


@app.post("/api/translate")
async def translate_text(
    text: str = Form(...),
    source: str = Form("auto"),
    target: str = Form("tr"),
):
    if not text.strip():
        raise HTTPException(400, "Metin boş olamaz")

    translated = GoogleTranslator(source=source, target=target).translate(text)
    return {"translated": translated}


@app.post("/api/voice-video")
async def voice_video(
    file: UploadFile = File(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    translate_to: str = Form(""),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        raise HTTPException(400, "Desteklenmeyen video formatı")

    uid = uuid.uuid4().hex
    video_path = UPLOAD_DIR / f"{uid}{ext}"
    audio_extracted = UPLOAD_DIR / f"{uid}_audio.wav"
    tts_audio = OUTPUT_DIR / f"{uid}_tts.wav"
    output_video = OUTPUT_DIR / f"{uid}_voiced.mp4"

    async with aiofiles.open(video_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # videodan ses çıkar
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1",
         "-f", "wav", str(audio_extracted)],
        check=True, capture_output=True, timeout=180,
    )

    # transkript
    whisper_m = get_whisper()
    result = await asyncio.to_thread(whisper_m.transcribe, str(audio_extracted))
    transcript = result["text"]

    # çeviri istenmişse
    if translate_to and translate_to != lang:
        transcript = await asyncio.to_thread(
            GoogleTranslator(source="auto", target=translate_to).translate, transcript
        )
        lang = translate_to

    # TTS
    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)
    wav, _ = await asyncio.to_thread(tts.synthesize,
        _clean_tts_text(transcript, lang), lang=lang,
        voice_style=style, total_steps=8, speed=speed,
    )
    tts.save_audio(wav, str(tts_audio))

    # sesi videoyla birleştir
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(video_path), "-i", str(tts_audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-shortest", str(output_video)],
        check=True, capture_output=True, timeout=180,
    )

    return {
        "transcript": transcript,
        "video": f"/api/video/{output_video.name}",
        "audio": f"/api/audio/{tts_audio.name}",
    }


# ── Script hook stili A/B anahtarı ──────────────────────────────────────────
# "yeni" performans düşürürse tek tıkla "eski"ye dönülebilir (bkz. /api/hook-style)
HOOK_STYLE_CONFIG = Path("hook_style_config.json")

_HOOK_RULE_ESKI = (
    '- FIRST scene text MUST use a CURIOSITY-GAP hook — never state the answer directly in the first sentence. '
    'Create suspense or partial reveal. Examples: "Kimse beklemiyordu:", "Meğer...", "Az önce ortaya çıktı:", '
    '"Herkes bunu merak ediyordu — cevap şoke etti.", "Tarihin en büyük...", "Peki gerçekte ne oldu?". '
    'NEVER open with a plain news statement. The viewer must NEED to keep watching to get the answer. '
    'Do NOT repeat the same opener across videos.'
)

_HOOK_RULE_YENI = (
    '- FIRST scene text is the HOOK — the first 1-2 seconds decide if the viewer keeps watching or swipes away. '
    'It MUST follow ALL of these:\n'
    '  1) MAX 8-10 words, no filler, no throat-clearing (no "Bugün", "Az önce yaşanan bir olayda" style windups) '
    '— the hook itself must be the very first words spoken.\n'
    '  2) CURIOSITY-GAP — never state the answer/outcome in the first sentence. Create suspense or a partial '
    'reveal so the viewer NEEDS the next scene to find out. Examples: "Kimse beklemiyordu:", "Meğer...", '
    '"Az önce ortaya çıktı:", "Herkes bunu merak ediyordu — cevap şoke etti.", "Peki gerçekte ne oldu?". '
    'Do NOT repeat the same opener across videos.\n'
    '  3) PERSONAL-IMPACT framing whenever the topic allows it — make the viewer feel directly affected, not '
    'just an observer. Use angles like "seni ilgilendiriyor", "cebini/hayatını değiştirecek" over neutral '
    'third-person reporting. Topics with a direct personal-impact angle (money, rights, health, safety, '
    'prices, jobs) consistently outperform purely observational news — lean into the personal-impact angle. '
    'CRITICAL: NEVER invent scope words ("milyonlarca", "binlerce", "yüz binlerce") unless that exact '
    'number or scale appears verbatim in the news source. If the source says "bazı memurlar" you must '
    'write "bazı memurlar" — not "milyonlarca memur".\n'
    '  4) NEVER open with a plain, fully-informative news statement — the viewer must have zero reason to '
    'swipe away before scene 2.'
)


def get_hook_style() -> str:
    if HOOK_STYLE_CONFIG.exists():
        try:
            style = json.loads(HOOK_STYLE_CONFIG.read_text()).get("style", "yeni")
            if style in ("eski", "yeni"):
                return style
        except Exception:
            pass
    return "yeni"


def get_hook_rule() -> str:
    return _HOOK_RULE_YENI if get_hook_style() == "yeni" else _HOOK_RULE_ESKI


@app.get("/api/hook-style")
async def api_get_hook_style():
    return {"style": get_hook_style()}


@app.post("/api/hook-style")
async def api_set_hook_style(style: str = Form(...)):
    if style not in ("eski", "yeni"):
        raise HTTPException(400, "style 'eski' veya 'yeni' olmalı")
    HOOK_STYLE_CONFIG.write_text(json.dumps({"style": style}))
    return {"ok": True, "style": style}


@app.get("/api/custom-prompt-rules")
async def api_get_custom_rules():
    return {"rules": get_custom_prompt_rules()}


@app.post("/api/custom-prompt-rules")
async def api_set_custom_rules(rules: str = Form(...)):
    CUSTOM_PROMPT_RULES_FILE.write_text(
        json.dumps({"rules": rules.strip()}, ensure_ascii=False, indent=2)
    )
    return {"ok": True}


@app.get("/api/prompt-preview")
async def api_prompt_preview():
    scores = ig_perf.category_scores()
    perf_instr = ""
    try:
        perf_instr = ig_perf.build_instruction([])
    except Exception:
        pass
    return {
        "hook_style": get_hook_style(),
        "hook_rule": get_hook_rule(),
        "custom_rules": get_custom_prompt_rules(),
        "perf_instruction": perf_instr,
        "has_analytics": bool(scores),
        "category_scores": scores,
    }


# ── Kategori çeşitliliği takibi ─────────────────────────────────────────────
# Aynı kategori (ör. EKONOMİ) art arda tekrar etmesin diye son üretilenler izlenir
RECENT_CATEGORIES_FILE = Path("recent_categories.json")
_RECENT_WINDOW = 6       # son kaç video izlensin
_REPEAT_THRESHOLD = 3    # aynı kategori bu kadar veya fazla tekrar ederse uyar


def get_recent_categories() -> list[str]:
    if RECENT_CATEGORIES_FILE.exists():
        try:
            return json.loads(RECENT_CATEGORIES_FILE.read_text())[-_RECENT_WINDOW:]
        except Exception:
            pass
    return []


def add_recent_category(category: str):
    cats = get_recent_categories()
    cats.append(category)
    cats = cats[-_RECENT_WINDOW:]
    RECENT_CATEGORIES_FILE.write_text(json.dumps(cats, ensure_ascii=False))


def get_diversity_instruction() -> str:
    cats = get_recent_categories()
    if not cats:
        return ""
    from collections import Counter
    top_cat, count = Counter(cats).most_common(1)[0]
    if count >= _REPEAT_THRESHOLD:
        return (
            f"\nTOPIC DIVERSITY: Your last {len(cats)} videos were heavily {top_cat} "
            f"({count}/{len(cats)}). If the trending list has a topic from a DIFFERENT "
            f"category (economy/disaster/sports/world/tech/general), STRONGLY prefer that "
            f"one instead — do not pick another {top_cat} topic unless nothing else is available.\n"
        )
    return ""


async def _fetch_article_text(url: str, max_chars: int = 2000) -> str:
    """Haber URL'sine gidip tam makale metnini çeker. Başarısız olursa boş string döner."""
    if not url:
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0, read=12.0),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return ""
        try:
            import trafilatura
            text = trafilatura.extract(
                r.text,
                include_comments=False,
                include_tables=False,
                favor_recall=True,
            )
            if text and len(text) > 80:
                return text[:max_chars]
        except Exception:
            pass
        # Fallback: kaba HTML temizleme
        import re as _re
        clean = _re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", r.text, flags=_re.DOTALL | _re.IGNORECASE)
        clean = _re.sub(r"<[^>]+>", " ", clean)
        clean = _re.sub(r"\s+", " ", clean).strip()
        return clean[:max_chars] if len(clean) > 80 else ""
    except Exception:
        return ""


async def fetch_gnews_summary(query: str, lang: str = "tr", max_items: int = 3) -> dict:
    """Google News RSS'ten haber başlıkları + tam makale metinlerini çeker. Hata olursa {} döner."""
    import xml.etree.ElementTree as ET
    import re
    from urllib.parse import quote

    hl = "tr" if lang == "tr" else "en"
    gl = "TR" if lang == "tr" else "US"
    ceid = f"{gl}:{hl}"
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        root = ET.fromstring(r.text)
        channel = root.find("channel")
        if channel is None:
            return {}
        articles, sources = [], []
        for item in channel.findall("item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
            link = (item.findtext("link") or "").strip()
            src_el = item.find("source")
            src_name = (src_el.text or "").strip() if src_el is not None else ""
            if not src_name:
                dc = item.find("{http://purl.org/dc/elements/1.1/}creator")
                if dc is not None:
                    src_name = (dc.text or "").strip()
            if title:
                articles.append({"title": title, "desc": desc[:300], "source": src_name, "link": link})
                if src_name and src_name not in sources:
                    sources.append(src_name)
        if not articles:
            return {}

        # Tam makale metinlerini paralel çek
        texts = await asyncio.gather(
            *[_fetch_article_text(a["link"]) for a in articles],
            return_exceptions=True,
        )
        for i, txt in enumerate(texts):
            if isinstance(txt, str) and len(txt) > 80:
                articles[i]["full_text"] = txt

        has_full = any(a.get("full_text") for a in articles)

        context_lines = []
        for a in articles:
            header = f"KAYNAK: {a['title']}"
            if a["source"]:
                header += f" [{a['source']}]"
            body = a.get("full_text") or a["desc"]
            context_lines.append(f"{header}\n{body}")

        return {
            "found": True,
            "articles": articles,
            "sources": sources,
            "context_text": "\n\n---\n\n".join(context_lines),
            "has_full_text": has_full,
        }
    except Exception:
        return {}


async def _extract_verified_facts(client, article_text: str, lang: str = "tr") -> dict:
    """Ham makale metninden SADECE kaynakta yazan olguları çıkarır (ayrı ajan — yorum/tahmin katmaz).

    Senaryo yazan ajandan bilerek ayrı tutulur: aynı model hem serbest metni yorumlayıp hem de
    akıcı/viral bir senaryo yazınca dikkat dağılıyor ve eğitim verisinden detay sızdırıyor.
    Burada tek iş "kaynakta ne yazıyor" — yaratıcılık yok, düşük temperature.
    """
    if not article_text.strip():
        return {"facts": [], "sufficient": False}
    extract_prompt = (
        "You are a strict fact-checking extractor. Read the article text below and extract ONLY "
        "facts that are explicitly and literally stated in it. No inference, no assumption, "
        "no outside/general knowledge — even if it seems obviously true.\n\n"
        f"ARTICLE TEXT:\n{article_text}\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        "{\n"
        '  "facts": ["short atomic fact 1 (in ' + ("Turkish" if lang == "tr" else "English") + ')", "fact 2", "..."],\n'
        '  "names_with_titles": {"Full Name": "exact title/role as stated in the article, or empty string if none given"},\n'
        '  "numbers": ["exact number/percentage/count exactly as written in the article"],\n'
        '  "dates": ["exact date/time reference exactly as written in the article"],\n'
        '  "sufficient": true\n'
        "}\n\n"
        "RULES:\n"
        "- Every fact must trace to an exact sentence in the article above.\n"
        "- Do NOT add context from general/training knowledge, even obvious-seeming facts.\n"
        "- If the article implies someone's role/title has changed from what you'd expect, trust "
        "ONLY the article — never your training data.\n"
        "- If unsure whether something counts as a stated fact, leave it out.\n"
        '- Set "sufficient": true only if there are at least 4 solid, distinct facts — enough '
        "material for a natural ~45-55 second news narration without padding."
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0.1,
        )
        result = _parse_llm_json(resp.choices[0].message.content)
        result.setdefault("facts", [])
        result.setdefault("sufficient", len(result["facts"]) >= 4)
        return result
    except Exception as e:
        print(f"[fact-extract] hata: {e}", flush=True)
        return {"facts": [], "sufficient": False}


async def _verify_narration_facts(client, narration: str, facts_data: dict) -> list:
    """Üretilen senaryodaki iddiaları olgu listesiyle karşılaştırır — desteklenmeyenleri döner.

    Yazan ajandan ayrı bir üçüncü ajan: sadece karşılaştırma yapar, senaryo yazmaz.
    """
    if not facts_data.get("facts"):
        return []
    facts_list = "\n".join(f"- {f}" for f in facts_data["facts"])
    names = ", ".join(facts_data.get("names_with_titles", {}).keys())
    numbers = ", ".join(facts_data.get("numbers", []))
    dates = ", ".join(facts_data.get("dates", []))
    verify_prompt = (
        "You are a strict fact-checker. Compare the NARRATION below against the VERIFIED FACTS list. "
        "Find any specific claim in the narration — a name, number, date, title, or specific detail — "
        "that is NOT supported by the verified facts.\n\n"
        f"VERIFIED FACTS:\n{facts_list}\n"
        f"Known names: {names or '(none)'}\n"
        f"Known numbers: {numbers or '(none)'}\n"
        f"Known dates: {dates or '(none)'}\n\n"
        f"NARRATION TO CHECK:\n{narration}\n\n"
        "Return ONLY valid JSON, no markdown:\n"
        '{"unsupported_claims": ["claim text not backed by the facts above", "..."]}\n\n'
        "If every specific claim in the narration is backed by the facts list (generic storytelling "
        "phrasing with no new factual claims is fine), return an empty list."
    )
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": verify_prompt}],
            temperature=0.0,
        )
        result = _parse_llm_json(resp.choices[0].message.content)
        return result.get("unsupported_claims", []) or []
    except Exception as e:
        print(f"[verify] hata: {e}", flush=True)
        return []


# Kişisel ölüm/vefat/kaza haberleri — hem gurbetçi hem normal trend havuzunda
# ele alınır. ASAYİŞ kategorisi (cinayet, gözaltı, tutuklama vb.) ve SPOR kategorisi
# ig_perf.categorize() üzerinden ayrıca elenir — SPOR kesin/sert kural (kullanıcı isteği,
# ASAYİŞ gibi soft-score değil), burada sadece keyword listesi tekil ölüm/vefat vakalarını yakalar.
_LOW_VALUE_KW = ["öldü", "ölü bulundu", "vefat", "kaza yaptı", "hayatını kaybetti",
                 "cesedi bulundu", "facia", "boşandı", "evlilik teklifi", "aşk yaşıyor"]
_HARD_EXCLUDE_CATS = {"ASAYİŞ", "SPOR"}


def _filter_low_value_topics(titles: list) -> list:
    """Kişisel ölüm/vefat/dedikodu + ASAYİŞ (cinayet/gözaltı/skandal) + SPOR
    kategorisindeki başlıkları eler. Etkisiz/düşük değerli haberleri her havuzdan
    da tutarlı şekilde çıkarmak için kullanılır."""
    filtered = []
    for t in titles:
        low = t.lower()
        if any(kw in low for kw in _LOW_VALUE_KW):
            continue
        if ig_perf.categorize(t) in _HARD_EXCLUDE_CATS:
            continue
        filtered.append(t)
    return filtered


def _interleave_topics(a: list, b: list) -> list:
    """İki listeyi almaşık sıralar (a1,b1,a2,b2,...) — sonradan bir yerde [:N] ile
    kırpılsa bile her iki havuzdan da adil pay çıkar. Düz 'a + b' birleştirme
    kullanılsaydı b (gurbetçi) listesi hep sonda kalır, kırpma onu tamamen silerdi
    (tam olarak yaşanan hata buydu — trend 20 slotu doldurunca gurbetçi hiç görünmedi)."""
    out = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            out.append(a[i])
        if i < len(b):
            out.append(b[i])
    return list(dict.fromkeys(out))


def _dedupe_pool_against_recent(titles: list) -> list:
    """Havuzdan, son saatlerde zaten işlenmiş (Instagram'a atılmış) konularla anahtar
    kelime örtüşen başlıkları eler — _ig_same_topic_posted ile aynı mantık, ama
    üretim ÖNCESİ havuz/Telegram listesine uygulanır ki kullanıcı zaten yapılmış bir
    haberi tekrar seçip slotu boşa harcamasın."""
    fresh = []
    for t in titles:
        try:
            if _ig_same_topic_posted(t):
                continue
        except Exception:
            pass
        fresh.append(t)
    return fresh


async def fetch_gurbetci_topics(max_items: int = 8) -> list:
    """Gurbetçi/diaspora haberlerine özel Google News RSS sorgusu.

    pytrends'in Türkiye trend listesi yurt içi arama davranışını yansıtıyor —
    gurbetçi konuları orada nadiren organik çıkıyor. Bu, ayrı bir arz kanalı:
    manuel 'Trend + Gurbetçi' butonuyla kullanıcı havuzu inceleyip karar verir,
    otomatik akışa henüz bağlı değil.
    """
    import xml.etree.ElementTree as ET
    from urllib.parse import quote

    # Google News RSS boolean OR + tırnaklı ifadeleri güvenilir işlemiyor —
    # basit tekil sorgularla birden fazla istek atıp birleştirmek daha sağlam.
    # "when:2d" Google'ın kendi zaman filtresi — arama RSS'i varsayılan olarak alaka
    # düzeyine göre sıralıyor (tarihe göre değil), bu da dar sorgularda aynı yüksek
    # otoriteli makalelerin günlerce üstte kalmasına yol açıyordu. Ülke bazlı sorgular
    # da havuzu genişletiyor.
    queries = [
        "gurbetçi when:2d", "yurtdışındaki Türkler when:2d", "gurbetçilere when:2d",
        "Almanya'daki Türkler when:2d", "Hollanda'daki Türkler when:2d",
        "Fransa'daki Türkler when:2d", "Belçika'daki Türkler when:2d",
    ]
    titles = []
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            for q in queries:
                url = f"https://news.google.com/rss/search?q={quote(q)}&hl=tr&gl=TR&ceid=TR:tr"
                try:
                    r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code != 200:
                        print(f"[gurbetci-trends] '{q}' → HTTP {r.status_code}", flush=True)
                        continue
                    root = ET.fromstring(r.text)
                    channel = root.find("channel")
                    if channel is None:
                        continue
                    for item in channel.findall("item")[:max_items]:
                        t = (item.findtext("title") or "").strip()
                        if t and t not in titles:
                            titles.append(t)
                except Exception as qe:
                    print(f"[gurbetci-trends] '{q}' hata: {qe}", flush=True)

        # Kişisel ölüm/vefat/cinayet haberleri ele — "gurbetçi" kelimesi geçse bile
        # bunlar ASAYİŞ türü içerik, herkesi ilgilendiren pratik/politika haberi değil.
        filtered = _filter_low_value_topics(titles)
        dropped = len(titles) - len(filtered)
        if dropped:
            print(f"[gurbetci-trends] {dropped} kişisel/ölüm haberi elendi", flush=True)

        print(f"[gurbetci-trends] toplam {len(filtered)} başlık bulundu", flush=True)
        return filtered[:max_items]
    except Exception as e:
        print(f"[gurbetci-trends] genel hata: {e}", flush=True)
        return []


async def _trim_audio_for_longcat(src: Path, dst: Path, max_sec: int = 5) -> bool:
    """Sesi max_sec saniyeye kısalt (ZeroGPU GPU-time limiti için)."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-t", str(max_sec),
             "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", str(dst)],
            check=True, capture_output=True, timeout=30,
        )
        return True
    except Exception as e:
        print(f"[LONGCAT] Ses kısaltma hatası: {e}", flush=True)
        return False


async def _call_longcat_api(photo_path: Path, audio_path: Path, output_path: Path) -> bool:
    """Avatar fotoğrafı + ses → lip-synced video. HuggingFace LongCat Space'i kullanır."""
    try:
        timeout = httpx.Timeout(30.0, read=360.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as cli:
            # Gradio 5.x: /gradio_api/ prefix
            with open(photo_path, "rb") as fp, open(audio_path, "rb") as fa:
                up_r = await cli.post(
                    f"{LONGCAT_SPACE}/gradio_api/upload",
                    files=[
                        ("files", (photo_path.name, fp.read(), "image/jpeg")),
                        ("files", (audio_path.name, fa.read(), "audio/wav")),
                    ],
                )
            if up_r.status_code != 200:
                print(f"[LONGCAT] Upload failed: {up_r.status_code} {up_r.text[:200]}", flush=True)
                return False
            uploaded = up_r.json()
            img_ref = uploaded[0] if isinstance(uploaded[0], str) else uploaded[0].get("path", "")
            aud_ref = uploaded[1] if isinstance(uploaded[1], str) else uploaded[1].get("path", "")

            session_hash = uuid.uuid4().hex[:10]
            join_r = await cli.post(
                f"{LONGCAT_SPACE}/gradio_api/queue/join",
                json={
                    "data": [
                        {"path": img_ref, "meta": {"_type": "gradio.FileData"}},
                        {"path": aud_ref, "meta": {"_type": "gradio.FileData"}},
                        "A photorealistic person speaking naturally to the camera",
                        42,
                        False,
                    ],
                    "event_data": None,
                    "fn_index": 0,
                    "session_hash": session_hash,
                    "trigger_id": 0,
                },
            )
            if join_r.status_code != 200:
                print(f"[LONGCAT] Queue join failed: {join_r.status_code}", flush=True)
                return False

            deadline = time.time() + 360
            async with cli.stream(
                "GET",
                f"{LONGCAT_SPACE}/gradio_api/queue/data?session_hash={session_hash}",
                headers={"Accept": "text/event-stream"},
            ) as stream:
                async for raw_line in stream.aiter_lines():
                    if time.time() > deadline:
                        print("[LONGCAT] SSE timeout", flush=True)
                        return False
                    if not raw_line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(raw_line[5:].strip())
                    except Exception:
                        continue
                    msg = evt.get("msg", "")
                    if msg == "process_completed":
                        out = evt.get("output", {}).get("data", [])
                        if not out:
                            print("[LONGCAT] Empty output data", flush=True)
                            return False
                        video_info = out[0]
                        if isinstance(video_info, dict):
                            vpath = video_info.get("path") or video_info.get("url", "")
                        else:
                            vpath = str(video_info)
                        if not vpath:
                            return False
                        dl_url = vpath if vpath.startswith("http") else f"{LONGCAT_SPACE}/gradio_api/file={vpath}"
                        dl = await cli.get(dl_url)
                        if dl.status_code == 200:
                            output_path.write_bytes(dl.content)
                            print(f"[LONGCAT] Başarılı → {output_path.name}", flush=True)
                            return True
                        print(f"[LONGCAT] Download failed: {dl.status_code}", flush=True)
                        return False
                    elif msg == "process_errored":
                        print(f"[LONGCAT] Process errored: {evt.get('output', '')}", flush=True)
                        return False
        return False
    except Exception as e:
        print(f"[LONGCAT] API hatası: {e}", flush=True)
        return False


async def _overlay_avatar_on_video(main_video: Path, avatar_video: Path, output: Path) -> bool:
    """Avatar videosunu ana videonun sağ alt köşesine PIP olarak yerleştirir (loop destekli)."""
    try:
        # %22 genişlik, sağ alt köşe, 20px kenar + 80px taban boşluğu
        # stream_loop -1: avatar video kısa olsa bile ana video süresince tekrarlanır
        filter_complex = (
            "[1:v]scale=trunc(iw*0.22/2)*2:trunc(ih*0.22/2)*2[av];"
            "[0:v][av]overlay=main_w-overlay_w-20:main_h-overlay_h-80"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", str(main_video.absolute()),
            "-stream_loop", "-1", "-i", str(avatar_video.absolute()),
            "-filter_complex", filter_complex,
            "-map", "0:a",
            "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
            "-pix_fmt", "yuv420p", "-r", "30", "-bf", "0", "-g", "30",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart",
            "-shortest",
            str(output.absolute()),
        ]
        await arun_ffmpeg(cmd, timeout=300, step="avatar overlay")
        return True
    except Exception as e:
        print(f"[OVERLAY] Hata: {e}", flush=True)
        return False


async def _generate_shorts_core(
    topic: str,
    api_key: str,
    lang: str = "tr",
    voice: str = "M1",
    speed: float = 1.0,
    exclude_topics: str = "",
    region: str = "TR",
    use_video: str = "false",
    platform: str = "youtube",
    custom_image_paths: list = None,
    spiker_mode: bool = False,
    avatar_path: Path = None,
    info_format: str = None,
    cover_image_path: Path = None,
):
    import json
    import httpx
    from openai import OpenAI

    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    use_video_mode = use_video.lower() in ("true", "1", "yes")
    pexels_key = get_pexels_key()

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    lang_name = LANG_MAP.get(lang, "Turkish")
    data = None
    scenes = []
    gnews_data = {}

    if info_format:
        # BİLGİ SHORTS — eğitici/bilgilendirici format, trend/haber atlanır
        _format_hooks = {
            "biliyormuydunuz": "FIRST scene MUST start with 'Bunu biliyor muydunuz?' — open with a shocking or surprising fact that stops the scroll.",
            "aklinizda": "FIRST scene MUST start with 'Aklınızda bulunsun' — give a practical, life-saving tip the viewer can use today.",
            "30saniye": "FIRST scene MUST start with '30 saniyede öğrenin' — rapid-fire, one key fact per scene, punchy and fast.",
            "cogusinsan": "FIRST scene MUST start with 'Çoğu insan bunu bilmiyor' — revelation format, viewer feels they're learning an insider secret.",
        }
        format_rule = _format_hooks.get(info_format, _format_hooks["biliyormuydunuz"])
        info_prompt = f"""Create a YouTube Shorts informational/educational video in {lang_name}.

Topic: {topic}

Return ONLY valid JSON, no markdown:
{{
  "title": "catchy YouTube title (max 80 chars, in {lang_name})",
  "hashtags": ["Shorts", "bilgi", "keşfet", "topic", "tags"],
  "scenes": [
    {{
      "text": "narration text (1-2 short punchy sentences)",
      "keyword": "english search keyword for stock photo (2-3 words)"
    }}
  ]
}}

Rules:
- 5 to 7 scenes, total narration under 55 seconds
- {format_rule}
- NEVER use abbreviations; write full names for text-to-speech
- Turkish number format ONLY: comma (,) is the decimal separator, dot (.) is the thousands separator — NEVER write numbers in English format (e.g. "1,287" meaning one thousand two hundred eighty-seven). Write "1.287" or spell it out "bin iki yüz seksen yedi" instead — English-style thousands-commas break the TTS reading.
- NEVER reference real footage or photos in narration — storytelling and facts only
- LAST scene MUST end with (in {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!"
- hashtags: 10-15 tags. Always include "bilgi", "öğrendim", "keşfet", "viral", "Shorts". No # symbol, NO spaces within a tag.
- keyword: English, 2-3 words, visual and specific"""
        for attempt in range(3):
            _resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": info_prompt}],
                temperature=0.7,
            )
            try:
                data = _parse_llm_json(_resp.choices[0].message.content)
                break
            except Exception:
                if attempt == 2:
                    raise HTTPException(500, "DeepSeek geçerli JSON döndürmedi (3 deneme)")
        scenes = data["scenes"]
        # Son sahne CTA'sını zorla override — DeepSeek "haberler" yazmasın
        _info_cta = {
            "tr": {"youtube": "Beğenmek ve abone olmak için 2 saniye ver!", "instagram": "Takip et ve beğen! 2 saniye yeter!"},
            "en": {"youtube": "Like and subscribe! Just 2 seconds!", "instagram": "Follow and like! 2 seconds is all it takes!"},
        }
        if scenes:
            scenes[-1]["text"] = _info_cta.get(lang, _info_cta["tr"]).get(platform, "Beğenmek ve abone olmak için 2 saniye ver!")

    else:
        # HABER SHORTS — mevcut trend/haber akışı
        trend_data = get_trends(region_code=region.upper(), lang=lang)

        # TR için: normal trend + gurbetçi havuzunu birleştirip aynı filtreden geçir
        # (ölüm/vefat/dedikodu + ASAYİŞ kategorisi elenir) — Telegram seçim listesiyle
        # aynı havuz, artık otomatik seçimde de kullanılıyor. Konu zaten belirtilmişse
        # (manuel/Telegram'dan zorunlu konu) bu havuz kullanılmayacağı için atlanır.
        if lang == "tr" and not topic.strip():
            try:
                gurbetci_topics = await fetch_gurbetci_topics()
                merged = _filter_low_value_topics(trend_data.get("topics", []))
                merged = _interleave_topics(merged, gurbetci_topics)
                merged = _dedupe_pool_against_recent(merged)
                if merged:
                    trend_data["topics"] = merged
            except Exception as _ge:
                print(f"[combined-pool] otomatik akışta birleşik havuz kullanılamadı: {_ge}", flush=True)

        trend_topics = ", ".join(trend_data["topics"][:30])
        yt_tags = ", ".join(trend_data.get("yt_trending_tags", [])[:10])
        trend_tags = ", ".join(trend_data["hashtags"][:10])

        exclude_instruction = ""
        if exclude_topics.strip():
            exclude_instruction = f"\nIMPORTANT - Do NOT cover these topics (already posted today):\n{exclude_topics}\nPick a DIFFERENT topic from the trending list.\n"

        # ── Hesap performans verisi: kategori skorları + tekrar kısıtları ────────
        perf_instruction = ""
        if lang == "tr" and not topic.strip():
            try:
                perf_instruction = ig_perf.build_instruction(get_ig_only_tr_used_topics())
            except Exception as _pe:
                print(f"[ig_perf] yönlendirme üretilemedi: {_pe}", flush=True)

        # ── Google News doğrulama: gerçek haber detaylarını çek ──────────────────
        gnews_data = {}
        search_query = topic.strip()
        if not search_query:
            try:
                sel_prompt = (
                    f"From this list of trending topics, pick ONE to make a breaking news Short video about. "
                    f"The list is already sorted by popularity — prefer topics near the top. "
                    f"Return ONLY the topic name, nothing else.\n\nTopics: {trend_topics}"
                    + (f"\n\nAvoid (already posted today): {exclude_topics}" if exclude_topics.strip() else "")
                    + perf_instruction
                )
                sel_resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": sel_prompt}],
                    temperature=0.3,
                    max_tokens=60,
                )
                search_query = sel_resp.choices[0].message.content.strip().split("\n")[0]
            except Exception:
                search_query = trend_data["topics"][0] if trend_data["topics"] else ""
        if search_query:
            gnews_data = await fetch_gnews_summary(search_query, lang)

        # ── Olgu çıkarma: ayrı bir ajan, sadece "kaynakta ne yazıyor" işiyle uğraşır ──
        # (Senaryo yazan ajandan bilerek ayrı — aynı model hem yorumlayıp hem yaratıcı
        #  yazınca dikkat dağılıyor, eğitim verisinden detay sızdırıyor.)
        facts_data = {}
        if gnews_data.get("found") and gnews_data.get("context_text"):
            facts_data = await _extract_verified_facts(client, gnews_data["context_text"], lang)

        news_context_instruction = ""
        if facts_data.get("facts"):
            facts_list = "\n".join(f"- {f}" for f in facts_data["facts"])
            names_map = facts_data.get("names_with_titles") or {}
            names_block = "\n".join(
                f"- {n}: {t or '(unvan belirtilmemiş — sadece adını kullan)'}"
                for n, t in names_map.items()
            )
            numbers_block = ", ".join(facts_data.get("numbers", [])) or "yok"
            dates_block = ", ".join(facts_data.get("dates", [])) or "yok"
            thin_note = (
                "\nNOT: Olgu sayısı az. YİNE DE video en az 45 saniye olmalı — yeni bilgi "
                "UYDURMADAN, elindeki olguları derinleştirerek doldur (örn. bu olgu kimi nasıl "
                "etkiler, ne zaman geçerli olur, neden önemli — olgunun kendisinden çıkan doğal "
                "açılımlar, yeni iddia değil). Kısa kesip atlamak yerine var olan olguyu iyi anlat.\n"
                if not facts_data.get("sufficient") else ""
            )
            news_context_instruction = (
                f"\n\nDOĞRULANMIŞ OLGULAR (ayrı bir olgu-çıkarma ajanı tarafından kaynaktan çıkarıldı) — "
                f"Senaryo YALNIZCA bu listeye dayanmalı:\n{facts_list}\n"
                + (f"\nİSİMLER VE UNVANLAR (yalnızca bunları kullan):\n{names_block}\n" if names_block else "")
                + f"\nGeçerli rakamlar: {numbers_block}\n"
                f"Geçerli tarihler: {dates_block}\n"
                f"{thin_note}"
                f"MUTLAK KURALLAR — İhlali yasaktır:\n"
                f"- Yukarıdaki listede OLMAYAN hiçbir isim, rakam, tarih, yüzde, unvan kullanma. Bilmiyorsan söyleme, atla.\n"
                f"- Eğitim verinle tahmin yürütme — güncel değil. Sadece yukarıdaki olgu listesini kullan.\n"
                f"- Listede 'bazı kişiler' varsa sen 'milyonlarca kişi' diyemezsin.\n"
                f"- Listede rakam yoksa rakam uyduramazsın.\n"
                f"- Birinin unvanı listede yoksa sadece adını kullan, unvan takma.\n"
            )
        # ─────────────────────────────────────────────────────────────────────────

        if topic.strip():
            topic_instruction = (
                f"Make a Short video ONLY about this specific topic: {topic}\n"
                f"IMPORTANT: Cover ONLY this topic in depth. Do NOT include or mention other news stories."
            )
        elif lang == "en":
            topic_instruction = (
                f"Choose ONE of these TODAY'S trending news topics for a US/English-speaking audience:\n{trend_topics}\n"
                f"PRIORITY ORDER: 1) Trump or US President news  2) US politics / Congress / White House  "
                f"3) Major US foreign policy (wars, sanctions, NATO)  4) Breaking global news that impacts the US  "
                f"5) Any other trending topic.\n"
                f"Always pick the HIGHEST priority category available in the list above."
            )
        else:
            topic_instruction = (
                f"Choose ONE of these TODAY'S trending topics and make a short breaking-news video:\n{trend_topics}\n"
                f"\nSTEP 1 — HOOK SCORE (do this mentally before choosing):\n"
                f"Score each headline 1-10 on hook strength:\n"
                f"  +3 if it directly affects the viewer's wallet, safety, or daily life\n"
                f"  +2 if it triggers curiosity or surprise ('how is that possible?')\n"
                f"  +2 if there's a clear human story or victim/winner\n"
                f"  +1 if it's time-sensitive / just happened\n"
                f"  +1 if it has a specific number or contrast in the headline\n"
                f"  -3 if it's vague, abstract, or institutional (e.g. 'committee meets', 'statement issued')\n"
                f"Eliminate any topic scoring below 7. If all score below 7, keep the top 2 and continue.\n"
                f"\nSTEP 2 — PICK from the remaining topics:\n"
                f"Pick whichever topic is most compelling and timely. Prefer topics that directly affect "
                f"people's daily lives (safety, wallet, health, rights) — but do not force a category; "
                f"a genuinely viral story beats a forced angle every time.\n"
                f"{get_diversity_instruction()}{perf_instruction}"
            )
        yt_tag_instruction = f"\nYouTube TR trending hashtags RIGHT NOW (include relevant ones): {yt_tags}" if yt_tags else ""
        _cr = get_custom_prompt_rules()
        _custom_block = ("- CUSTOM RULES (highest priority — always follow these):\n" +
                         "\n".join("  " + ln for ln in _cr.splitlines())) if _cr else ""
        prompt = f"""Create a YouTube Shorts video.
Narration language: {lang_name}
{topic_instruction}
{exclude_instruction}{news_context_instruction}Suggested hashtags: {trend_tags}{yt_tag_instruction}

Return ONLY valid JSON, no markdown, no explanation:
{{
  "title": "catchy YouTube title for this video (max 80 chars, in {lang_name})",
  "hashtags": ["Shorts", "topic", "specific", "tags", "no", "hash", "symbol"],
  "scenes": [
    {{
      "text": "narration for this scene (1-2 short sentences)",
      "keyword": "english search keyword for stock photo (2-3 words, specific and visual)"
    }}
  ]
}}

Rules:
- 5 to 7 scenes
- In scene text: NEVER use abbreviations (e.g. YKS, ÖSYM, TBMM, ABD, AKP, CHP). Always write the full name so text-to-speech reads correctly. Example: write "Yükseköğretim Kurumları Sınavı" not "YKS", "Amerika Birleşik Devletleri" not "ABD".
- Turkish number format ONLY: comma (,) is the decimal separator, dot (.) is the thousands separator — NEVER write numbers in English format (e.g. "1,287" meaning one thousand two hundred eighty-seven). Write "1.287" or spell it out "bin iki yüz seksen yedi" instead — English-style thousands-commas break the TTS reading.
- NEVER use phrases that imply real footage or real photos exist (e.g. "İşte görüntüler", "İşte o anlar", "kameralar görüntüledi", "işte o fotoğraflar", "görüntüler ortaya çıktı", "here is the footage"). Visuals are illustrative stock photos — narration must describe events in storytelling form, never reference visuals.
- POLITICAL TITLES: Your training data is outdated. NEVER assume someone still holds a position from your training. Use ONLY the title given in the news context above. If no title is given, use only the person's name. Known outdated facts to avoid: Assad is no longer Syria's president (fled Dec 2024), Biden is no longer US president.
- NO FABRICATED NUMBERS OR SCOPE: NEVER write "milyonlarca", "binlerce", "yüz binlerce", or any specific number/count/percentage UNLESS it appears word-for-word in the news source provided above. If the source does not mention a number, do NOT invent one. Use the exact scope from the source (e.g. if source says "bazı çalışanlar", write "bazı çalışanlar" — never upgrade it to "milyonlarca çalışan"). Inventing numbers is disinformation and causes legal risk.
- TITLE SCOPE MUST MATCH THE SOURCE TOO — this is NOT just a narration rule: the "title" field gets the SAME scrutiny as scene text. If the source says only SOME workers/positions/groups are affected (e.g. "bazı memur kadroları", "bazı unvanlar"), the title must NOT generalize to the whole group (e.g. do NOT write "MEMURLARA Ek Tazminat" if it's only a subset — write "Bazı Memurlara..." or name the specific group). A catchy title is fine; an overclaimed scope is not — viewers who don't qualify will call it a lie in the comments.
- NO SENSATIONALISM BEYOND SOURCE: Do not use words like "şoke eden", "bomba", "skandal", "rezalet", "inanılmaz" unless the source itself uses comparable language. Stick to facts as stated in the source.
- NO EMPTY PROMISES: NEVER write a sentence that promises information without immediately delivering it in the same or next sentence — e.g. "detaylar açıklandı", "işte merak edilenler", "peki bakalım neler var" followed by ending the video without saying what those details/answers actually are. Every scene must contain a real, concrete piece of information from the facts list. If you don't have enough facts to fill a promised detail, do NOT tease it — cut that sentence entirely instead. Ending a video on an unfulfilled setup reads as clickbait and destroys trust, even if no fact was technically wrong.
{get_hook_rule()}
- LAST scene text MUST end with this exact call to action (translated naturally to {lang_name}): "{'Takip etmek ve beğenmek için 2 saniye ver!' if platform == 'instagram' else 'Beğenmek, abone olmak ve yorum yapmak için 2 saniye ver!'}" — make it feel urgent and personal, not generic.
- keyword: English, 2-3 words, visual and specific (e.g. "mountain sunset", "busy city street")
- Total narration between 45 and 55 seconds — NEVER shorter than 45 seconds. If the facts feel thin, elaborate naturally on the facts you have (implications, who it affects, timing) instead of cutting the video short or inventing new details.
- hashtags: 10-15 tags — FIRST 5 MUST be specific to this video's topic/people/places (e.g. if video is about Instagram algorithm: "instagram", "algoritma", "mosseri", "reels", "sosyalmedya"). Then add: "sondakika", "gündem", "keşfet", "haberler", "viral". ALWAYS include "Shorts" as the last tag. No # symbol, NO spaces within a tag.
{_custom_block}"""

        for attempt in range(3):
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            try:
                data = _parse_llm_json(response.choices[0].message.content)
                break
            except Exception:
                if attempt == 2:
                    raise HTTPException(500, "DeepSeek geçerli JSON döndürmedi (3 deneme)")

        scenes = data["scenes"]

        # ── Üçüncü ajan: senaryodaki iddiaları olgu listesiyle karşılaştırır ──
        # Desteklenmeyen bir iddia bulunursa, o iddiayı göstererek yeniden yazdırır (maks 2 deneme).
        if facts_data.get("facts"):
            for _verify_attempt in range(2):
                full_narration = " ".join(s.get("text", "") for s in scenes)
                unsupported = await _verify_narration_facts(client, full_narration, facts_data)
                if not unsupported:
                    break
                print(f"[verify] desteklenmeyen iddialar bulundu, yeniden yazdırılıyor: {unsupported}", flush=True)
                correction_prompt = prompt + (
                    "\n\nDÜZELTME GEREKLİ — bir önceki taslağında şu iddialar olgu listesinde YOKTU. "
                    "Bunları TAMAMEN KALDIR veya olgu listesindeki karşılığıyla değiştir. Başka hiçbir "
                    "yeni detay ekleme:\n" + "\n".join(f"- {c}" for c in unsupported)
                )
                try:
                    _fix_resp = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": correction_prompt}],
                        temperature=0.5,
                    )
                    _fixed = _parse_llm_json(_fix_resp.choices[0].message.content)
                    data = _fixed
                    scenes = data["scenes"]
                except Exception as _fix_e:
                    print(f"[verify] düzeltme denemesi başarısız: {_fix_e}", flush=True)
                    break

        if lang == "tr":
            try:
                add_recent_category(news_site.guess_category(data.get("title", ""))[0])
            except Exception:
                pass

        # Son sahne TTS metnini platforma göre sabit CTA ile değiştir (haber shorts)
        if scenes:
            _cta = {
                "tr": {
                    "youtube": "Bu haberi beğen, kanala abone ol ve bir yorum bırak! İki saniye yeterli!",
                    "instagram": "Takip et ve beğen! Her haberi ilk sen gör! İki saniye yeterli!",
                },
                "en": {
                    "youtube": "Like, subscribe and drop a comment! Just 2 seconds!",
                    "instagram": "Follow and like! Be the first to see every update!",
                },
            }
            _lang_cta = _cta.get(lang, _cta["tr"])
            scenes[-1]["text"] = _lang_cta.get(platform, _lang_cta["youtube"])

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    audio_files = []
    png_files = []
    durations = []
    visual_warnings: set = set()
    scene_raw_videos = []  # video modunda her sahne için ham video yolu (None = foto kullan)

    for i, scene in enumerate(scenes):
        audio_path = scene_dir / f"audio_{i}.wav"
        dur_val = await _synth_audio(scene["text"], lang, voice, speed, audio_path)
        audio_files.append(audio_path)
        durations.append(dur_val)

        # Son sahne: sabit belmolysoft end card — Pexels'e gitme
        is_last_scene = (i == len(scenes) - 1)
        png_path = scene_dir / f"scene_{i}.jpg"
        scene_raw_video = None  # video modunda indirilen ham video

        if is_last_scene:
            endcard = Path("static/endcard_tr.jpg")
            if info_format and INFO_ENDCARD_FILE.exists():
                import shutil as _sh
                _sh.copy2(str(INFO_ENDCARD_FILE), str(png_path))
                photo_saved, visual_err = True, ""
            elif endcard.exists() and not info_format:
                import shutil as _sh
                _sh.copy2(str(endcard), str(png_path))
                photo_saved, visual_err = True, ""
            else:
                # Endcard yok — son sahne için Pexels'tan fotoğraf çek
                photo_saved, visual_err = fetch_scene_visual("social media news channel", "portrait", pexels_key, png_path)
        else:
            keyword = scene.get("keyword", topic)
            if i == 0 and cover_image_path and Path(cover_image_path).exists():
                try:
                    import shutil as _sh
                    _sh.copy2(str(cover_image_path), str(png_path))
                    photo_saved, visual_err = True, ""
                except Exception:
                    photo_saved, visual_err = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)
            elif custom_image_paths:
                # Kullanıcının kendi yüklediği görseller (ör. uygulama ekran görüntüleri)
                try:
                    import shutil as _sh
                    src_img = custom_image_paths[i % len(custom_image_paths)]
                    _sh.copy2(str(src_img), str(png_path))
                    photo_saved, visual_err = True, ""
                except Exception:
                    photo_saved, visual_err = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)
            # Video modu: önce Pexels video dene, başarısız olursa görsele düş
            # İlk sahne (i==0) her zaman görsel — banner overlay için PNG şart
            elif use_video_mode and pexels_key and i > 0:
                vid_ok, vid_result = await asyncio.to_thread(
                    fetch_pexels_video, keyword, pexels_key,
                    scene_dir / f"rawvid_{i}.mp4", durations[i]
                )
                if vid_ok:
                    scene_raw_video = Path(vid_result)
                    photo_saved, visual_err = True, ""  # video var, PNG fallback gerekmez
                else:
                    visual_warnings.add(f"video→fotoğraf: {vid_result}")
                    photo_saved, visual_err = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)
            else:
                # Görsel hiyerarşisi: DALL-E → Wikimedia Commons → Pexels
                photo_saved, visual_err = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)
            if not photo_saved and visual_err:
                visual_warnings.add(visual_err)

        scene_raw_videos.append(scene_raw_video)

        # Fallback: koyu arka plan
        if not photo_saved:
            try:
                from PIL import Image as PILImage
                img = PILImage.new("RGB", (1080, 1920), color=(20, 20, 30))
                img.save(str(png_path), "JPEG", quality=92)
            except Exception:
                await asyncio.to_thread(subprocess.run,
                    ["ffmpeg", "-y", "-f", "lavfi",
                     "-i", "color=black:size=1080x1920:rate=1",
                     "-frames:v", "1", str(png_path)],
                    capture_output=True, timeout=90,
                )

        png_files.append(png_path)

    # İlk sahneye haber overlay ekle — Bilgi Shorts modunda atla
    if png_files and not info_format:
        try:
            first_title = data.get("title", topic or scenes[0]["text"][:60])
            overlay_first_scene_banner(png_files[0], first_title, lang=lang)
        except Exception:
            pass

    # Son sahneye platform bandı ekle — endcard varsa overlay ekleme (görsel zaten tasarımlı)
    endcard_used = (Path("static/endcard_tr.jpg").exists() and not info_format) or (info_format and INFO_ENDCARD_FILE.exists())
    if png_files and not endcard_used:
        try:
            if platform == "instagram":
                overlay_ig_follow_banner(png_files[-1])
            else:
                overlay_like_subscribe_banner(png_files[-1])
        except Exception:
            pass

    # Mevcut font bul
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    # Her sahne için video klibi oluştur (fotoğraf + metin overlay)
    clip_files = []
    for i, (png, dur, scene) in enumerate(zip(png_files, durations, scenes)):
        clip_path = scene_dir / f"clip_{i}.mp4"
        is_last = (i == len(scenes) - 1)

        # Son sahne (endcard): metin overlay ekleme — endcard zaten tasarımlı
        if is_last and endcard_used:
            try:
                await asyncio.to_thread(subprocess.run,
                    ["ffmpeg", "-y",
                     "-loop", "1", "-i", str(png),
                     "-t", str(dur),
                     "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                     "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
                    check=True, capture_output=True, timeout=90,
                )
            except Exception as fe:
                raise RuntimeError(f"ffmpeg endcard scene failed: {fe}")
            clip_files.append(clip_path)
            continue

        # Metni dosyaya yaz — özel karakter sorununu çözer
        words = scene["text"].split()
        lines, line = [], []
        for w in words:
            if len(" ".join(line + [w])) > 38:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        wrapped_text = "\n".join(lines)

        text_file = scene_dir / f"text_{i}.txt"
        text_file.write_text(wrapped_text, encoding="utf-8")

        drawtext = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"drawtext=textfile={text_file.absolute()}"
            f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
            f":box=1:boxcolor=black@0.55:boxborderw=18"
        )
        if font_path:
            drawtext += f":fontfile={font_path}"

        # Video modu: ham video varsa ondan klip oluştur
        raw_vid = scene_raw_videos[i] if i < len(scene_raw_videos) else None
        if raw_vid and raw_vid.exists():
            vid_clip_ok = await _create_clip_from_video(raw_vid, float(dur), clip_path, text_file, font_path)
            if vid_clip_ok:
                clip_files.append(clip_path)
                continue
            # Video clip başarısız → png yoksa Pexels'tan fotoğraf çek
            if not png.exists():
                fb_keyword = scene.get("keyword", topic)
                fetch_scene_visual(fb_keyword, "portrait", pexels_key, png)

        # Ken Burns efekti dene — başarısız olursa statik fallback
        kb_ok = await _try_ken_burns_clip(png, float(dur), clip_path, text_file, font_path)
        if not kb_ok:
            try:
                result = await asyncio.to_thread(subprocess.run,
                    ["ffmpeg", "-y",
                     "-loop", "1", "-i", str(png),
                     "-t", str(dur),
                     "-vf", drawtext,
                     "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
                    capture_output=True, timeout=90,
                )
                if result.returncode != 0:
                    await asyncio.to_thread(subprocess.run,
                        ["ffmpeg", "-y",
                         "-loop", "1", "-i", str(png),
                         "-t", str(dur),
                         "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                         "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
                        check=True, capture_output=True, timeout=90,
                    )
            except Exception as fe:
                raise RuntimeError(f"ffmpeg scene {i} failed: {fe}")
        clip_files.append(clip_path)

    # Ses dosyalarını birleştir
    audio_list_file = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list_file, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    # -c copy yerine yeniden encode: sahnelerin TTS çıktısı farklı örnekleme
    # hızı/kanal ile gelirse concat copy sessizce bozuk akış üretip sonraki
    # mux'taki -map 1:a:0'ı düşürüyordu. pcm ile akış tek tip olur.
    await arun_ffmpeg(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list_file),
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", str(combined_audio)],
        timeout=120, step="ses birleştirme"
    )

    # Video kliplerini birleştir
    clip_list_file = scene_dir / "clip_list.txt"
    with open(clip_list_file, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")

    slideshow = scene_dir / "slideshow.mp4"
    await arun_ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list_file.absolute()),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-r", "30", "-vsync", "cfr", "-pix_fmt", "yuv420p",
        str(slideshow.absolute())
    ], timeout=600, step="slideshow")

    # Ses ekle — YouTube + Instagram uyumlu encode
    output_file = OUTPUT_DIR / f"{uid}_shorts.mp4"
    disclaimer_file = scene_dir / "disclaimer.txt"
    disclaimer_file.write_text(
        "Gorseller temsilidir. Gercek kisi veya mekanla ilgili degildir.",
        encoding="utf-8"
    )
    disclaimer_filter = (
        f"drawtext=textfile={disclaimer_file.absolute()}"
        f":fontsize=20:fontcolor=white@0.9"
        f":box=1:boxcolor=black@0.55:boxborderw=6"
        f":x=(w-text_w)/2:y=h-th-12"
    )
    if font_path:
        disclaimer_filter += f":fontfile={font_path}"
    await arun_ffmpeg([
        "ffmpeg", "-y", "-i", str(slideshow.absolute()), "-i", str(combined_audio.absolute()),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", disclaimer_filter,
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr",
        "-bf", "0", "-g", "30",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest", str(output_file.absolute())
    ], timeout=600, retries=1, step="ses+video mux")

    full_script = " ".join(s["text"] for s in scenes)
    generated_title = data.get("title", topic or scenes[0]["text"][:60])

    # Videoya özel hashtag'ler (DeepSeek'ten) + genel engagement tag'leri
    raw_tags = data.get("hashtags", [])
    if raw_tags:
        tag_limit = 15 if info_format else 5
        video_tags = _format_hashtags(raw_tags, limit=tag_limit)
    else:
        if info_format:
            video_tags = "#bilgi #Shorts #keşfet #öğren #viral"
        else:
            # Fallback: trend hashtag'leri + başlık kelimelerinden üret
            title_tags = [w.lower() for w in generated_title.split()[:3] if len(w) > 3]
            video_tags = _format_hashtags(["Shorts"] + title_tags + trend_data["hashtags"][1:6], limit=5)

    # Thumbnail — overlay'li ilk sahneyi kopyala (ayrıca create_thumbnail gerekmez)
    thumb_path = None
    try:
        thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
        shutil.copy2(str(png_files[0]), str(thumb_out))
        thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

    # Spiker Modu: avatar fotoğrafı varsa LongCat API ile lip-sync video oluştur
    if spiker_mode and avatar_path and Path(avatar_path).exists():
        try:
            print(f"[SPIKER] LongCat API çağrısı başlıyor…", flush=True)
            # ZeroGPU GPU-time limiti: sesi 9 saniyeye kısalt, overlay'de loop ile tüm videoya yay
            spiker_audio = OUTPUT_DIR / f"{uid}_spiker_audio.wav"
            trim_ok = await _trim_audio_for_longcat(combined_audio, spiker_audio, max_sec=5)
            if not trim_ok:
                shutil.copy2(str(combined_audio.absolute()), str(spiker_audio))
            avatar_video_path = OUTPUT_DIR / f"{uid}_avatar.mp4"
            lc_ok = await _call_longcat_api(Path(avatar_path), spiker_audio, avatar_video_path)
            if lc_ok and avatar_video_path.exists():
                spiker_output = OUTPUT_DIR / f"{uid}_spiker_shorts.mp4"
                ov_ok = await _overlay_avatar_on_video(output_file, avatar_video_path, spiker_output)
                if ov_ok and spiker_output.exists():
                    output_file.unlink(missing_ok=True)
                    spiker_output.rename(output_file)
                    print(f"[SPIKER] Avatar overlay tamamlandı", flush=True)
                else:
                    print("[SPIKER] Overlay başarısız, orijinal video korunuyor", flush=True)
            else:
                print("[SPIKER] LongCat başarısız, orijinal video korunuyor", flush=True)
            for tmp in (spiker_audio, avatar_video_path):
                tmp.unlink(missing_ok=True)
        except Exception as _sp_e:
            print(f"[SPIKER] Hata: {_sp_e}", flush=True)

    # Outro template ekle (uploads/outro_template.mp4 varsa)
    if OUTRO_TEMPLATE.exists():
        try:
            _outro_final = OUTPUT_DIR / f"{uid}_with_outro.mp4"
            if await _append_outro_template(output_file, _outro_final) and _outro_final.exists():
                output_file.unlink(missing_ok=True)
                _outro_final.rename(output_file)
                print("[OUTRO] Template outro eklendi", flush=True)
        except Exception as _outro_e:
            print(f"[OUTRO] Hata: {_outro_e}", flush=True)

    # Geçici dosyaları temizle (disk dolmaması için)
    shutil.rmtree(scene_dir, ignore_errors=True)

    # Kullanılan konuyu kaydet — scheduler aynı haberi tekrar seçmesin
    add_shorts_used_topic(generated_title)

    sources = gnews_data.get("sources", [])
    source_text = ("Kaynak: " + ", ".join(sources)) if sources else ""

    # Açıklama metni — Bilgi Shorts için eğitim odaklı, haber için haber odaklı
    ig_caption_desc = ""
    try:
        cap_lang_note = "Türkçe" if lang == "tr" else "English"
        if info_format:
            cap_prompt = (
                f"Aşağıdaki eğitici/bilgilendirici kısa video için YouTube açıklama metni yaz.\n"
                f"Dil: {cap_lang_note}\n"
                f"Başlık: {generated_title}\n"
                f"\nVideo içeriği:\n{full_script}\n"
                + """
Kurallar:
- 2-3 paragraf, toplamda 600-1000 karakter
- Videoda anlatılan bilgileri özetle, izleyiciye fayda hissettir
- Merak uyandıran, sade ve akıcı bir dil kullan
- Emoji yok, hashtag yok, başlık tekrarlama
- Son cümle: "Beğenin ve abone olun, her hafta yeni bilgiler paylaşıyorum!"
- Sadece açıklama paragraflarını döndür
"""
            )
        else:
            cap_context = gnews_data.get("context_text", "") if gnews_data.get("found") else ""
            cap_prompt = (
                f"Aşağıdaki haber için Instagram açıklama metni yaz.\n"
                f"Dil: {cap_lang_note}\n"
                f"Başlık: {generated_title}\n"
                f"\nVideo senaryosu (kısa özet):\n{full_script}\n"
                + (f"\nGüncel haber kaynakları:\n{cap_context}\n" if cap_context else "")
                + """
Kurallar:
- 3-4 paragraf, toplamda 900-1400 karakter
- Haberin tüm önemli detaylarını ver: kim, ne, nerede, ne zaman, neden
- Sadece doğrulanmış bilgileri kullan; spekülasyon yapma
- Haber dili: net, akıcı, merak uyandıran ama sensasyonel değil
- Kişi adlarını, yerleri ve rakamları değiştirme
- "..." ile KESME — her cümle tam bitişin
- Emoji yok, hashtag yok, başlık tekrarlama
- Sadece açıklama paragraflarını döndür
"""
            )
        cap_resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": cap_prompt}],
            temperature=0.4,
            max_tokens=700,
        )
        ig_caption_desc = cap_resp.choices[0].message.content.strip()
    except Exception as _cap_e:
        print(f"[CAPTION-GEN] Açıklama üretilemedi: {_cap_e}", flush=True)
        ig_caption_desc = full_script

    return {
        "video": f"/api/video/{output_file.name}",
        "thumbnail": thumb_path,
        "script": full_script,
        "title": generated_title,
        "scene_count": len(scenes),
        "suggested_tags": video_tags,
        "suggested_description": ig_caption_desc,
        "visual_warning": " | ".join(sorted(visual_warnings)) if visual_warnings else "",
        "source_text": source_text,
    }


@app.post("/api/generate-shorts")
async def generate_shorts(
    topic: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    exclude_topics: str = Form(""),
    region: str = Form("TR"),
    use_video: str = Form("false"),
    platform: str = Form("youtube"),
):
    return await _generate_shorts_core(topic, api_key, lang, voice, speed, exclude_topics, region, use_video, platform)


MANUAL_SHORTS_LOG = Path("manual_shorts_log.json")
_manual_shorts_lock = False
MANUAL_LV_LOG = Path("manual_lv_log.json")
LV_JOB_FILE   = Path("lv_job.json")
_manual_lv_lock = False


def _save_manual_shorts_log(status: str, result: dict = None, error: str = "", started_at: float = None):
    existing = {}
    if MANUAL_SHORTS_LOG.exists():
        try:
            existing = json.loads(MANUAL_SHORTS_LOG.read_text())
        except Exception:
            pass
    entry = {
        "status": status,
        "started_at": started_at if started_at is not None else existing.get("started_at", time.time()),
        "result": result,
        "error": error,
        "ts": time.time(),
    }
    MANUAL_SHORTS_LOG.write_text(json.dumps(entry, ensure_ascii=False))


def _save_manual_lv_log(status: str, result: dict = None, error: str = "", started_at: float = None):
    existing = {}
    if MANUAL_LV_LOG.exists():
        try:
            existing = json.loads(MANUAL_LV_LOG.read_text())
        except Exception:
            pass
    entry = {
        "status": status,
        "started_at": started_at if started_at is not None else existing.get("started_at", time.time()),
        "result": result,
        "error": error,
        "ts": time.time(),
    }
    MANUAL_LV_LOG.write_text(json.dumps(entry, ensure_ascii=False))


async def _shorts_job_runner(topic, api_key, lang, voice, speed, exclude_topics, region, use_video, platform, custom_image_paths=None, spiker_mode=False, avatar_path=None, info_format=None, cover_image_path=None):
    global _manual_shorts_lock
    try:
        result = await _generate_shorts_core(topic, api_key, lang, voice, speed, exclude_topics, region, use_video, platform, custom_image_paths, spiker_mode=spiker_mode, avatar_path=avatar_path, info_format=info_format, cover_image_path=cover_image_path)
        _save_manual_shorts_log("done", result=result)
        video_file = OUTPUT_DIR / result["video"].split("/")[-1]
        await send_telegram_video(
            video_file,
            result.get("title", topic or "Manuel Shorts"),
            result.get("suggested_description", ""),
            result.get("suggested_tags", ""),
        )
    except Exception as e:
        _save_manual_shorts_log("error", error=str(e))
    finally:
        _manual_shorts_lock = False
        for p in (custom_image_paths or []):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass
        if cover_image_path:
            try:
                Path(cover_image_path).unlink(missing_ok=True)
            except Exception:
                pass


@app.post("/api/generate-shorts-async")
async def generate_shorts_async_endpoint(
    topic: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    exclude_topics: str = Form(""),
    region: str = Form("TR"),
    use_video: str = Form("false"),
    platform: str = Form("youtube"),
    custom_images: list[UploadFile] = File(default=[]),
    spiker_mode: str = Form("false"),
    avatar_image: UploadFile = File(default=None),
):
    global _manual_shorts_lock
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")
    if _manual_shorts_lock:
        raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")

    custom_image_paths = []
    for i, img in enumerate(custom_images):
        if not img.filename:
            continue
        data = await img.read()
        dest = UPLOAD_DIR / f"customimg_{uuid.uuid4().hex}_{i}.jpg"
        if _save_as_jpeg(data, dest):
            custom_image_paths.append(dest)

    use_spiker = spiker_mode.lower() in ("true", "1", "yes")
    saved_avatar_path = None
    if use_spiker and avatar_image and avatar_image.filename:
        av_data = await avatar_image.read()
        av_dest = UPLOAD_DIR / f"avatar_{uuid.uuid4().hex}.jpg"
        if _save_as_jpeg(av_data, av_dest):
            saved_avatar_path = av_dest
            shutil.copy2(str(av_dest), str(AVATAR_FILE))
        else:
            use_spiker = False
    elif use_spiker and AVATAR_FILE.exists():
        saved_avatar_path = AVATAR_FILE

    _manual_shorts_lock = True
    started_at = time.time()
    _save_manual_shorts_log("running", started_at=started_at)
    asyncio.create_task(_shorts_job_runner(topic, api_key, lang, voice, speed, exclude_topics, region, use_video, platform, custom_image_paths, spiker_mode=use_spiker, avatar_path=saved_avatar_path))
    return {"ok": True}


@app.post("/api/generate-info-shorts-async")
async def generate_info_shorts_async(
    topic: str = Form(...),
    info_format: str = Form("biliyormuydunuz"),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    use_video: str = Form("false"),
    platform: str = Form("youtube"),
    cover_image: UploadFile = File(None),
):
    global _manual_shorts_lock
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")
    if not topic.strip():
        raise HTTPException(400, "Konu boş olamaz")
    if _manual_shorts_lock:
        raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")

    saved_cover = None
    if cover_image and cover_image.filename:
        data = await cover_image.read()
        dest = UPLOAD_DIR / f"cover_{uuid.uuid4().hex}.jpg"
        if _save_as_jpeg(data, dest):
            saved_cover = dest

    _manual_shorts_lock = True
    started_at = time.time()
    _save_manual_shorts_log("running", started_at=started_at)
    asyncio.create_task(_shorts_job_runner(
        topic, api_key, lang, voice, speed, "", "TR", use_video, platform,
        spiker_mode=False, avatar_path=None, info_format=info_format,
        cover_image_path=saved_cover,
    ))
    return {"ok": True}


@app.get("/api/avatar-status")
async def get_avatar_status():
    if AVATAR_FILE.exists():
        return {"has_avatar": True, "path": f"/api/avatar-photo"}
    return {"has_avatar": False}


@app.get("/api/settings/banned-topics")
async def get_banned_topics():
    return {"topics": load_banned_topics()}


@app.post("/api/settings/banned-topics")
async def set_banned_topics(request: Request):
    body = await request.json()
    topics = [t.strip().lower() for t in body.get("topics", []) if t.strip()]
    save_banned_topics(topics)
    return {"ok": True, "count": len(topics)}


@app.get("/api/manual-shorts/status")
async def get_manual_shorts_status():
    if not MANUAL_SHORTS_LOG.exists():
        return {"status": "idle"}
    try:
        data = json.loads(MANUAL_SHORTS_LOG.read_text())
    except Exception:
        return {"status": "idle"}
    if data.get("status") == "running":
        elapsed = int(time.time() - data.get("started_at", time.time()))
        if elapsed > 45 * 60:  # 45 dakika aşıldıysa takılmış demek
            data["status"] = "error"
            data["error"] = f"Zaman aşımı ({elapsed // 60} dakika). Sıfırlayıp tekrar deneyin."
    data["elapsed"] = int(time.time() - data.get("started_at", time.time()))
    return data


@app.post("/api/manual-shorts/reset")
async def reset_manual_shorts():
    global _manual_shorts_lock
    _manual_shorts_lock = False
    if MANUAL_SHORTS_LOG.exists():
        MANUAL_SHORTS_LOG.unlink(missing_ok=True)
    return {"ok": True}


from trends import get_trends

THUMB_DIR = Path("thumbnails")
THUMB_DIR.mkdir(exist_ok=True)


def create_thumbnail(photo_bytes: bytes, title: str, out_path: Path, size=(1280, 720), lang="tr", news_style=True):
    """Haber kanalı stili thumbnail: koyu fotoğraf + sarı bantlar. news_style=False → SON DAKİKA ve bantlar olmadan belgesel stili."""
    from PIL import Image, ImageDraw, ImageFont
    import io, textwrap

    W, H = size
    is_portrait = H > W

    # Arka plan fotoğrafı
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    img = img.resize(size, Image.LANCZOS)

    # Koyu overlay
    overlay = Image.new("RGBA", size, (0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    def load_font(size):
        if font_path:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def text_w(draw, text, font):
        try:
            return draw.textlength(text, font=font)
        except AttributeError:
            return font.getlength(text)

    YELLOW = (255, 208, 0)
    RED    = (213, 0, 0)
    BLACK  = (17, 17, 17)
    WHITE  = (255, 255, 255)

    badge_text = "SON DAKİKA" if lang == "tr" else "BREAKING NEWS"

    if is_portrait:
        # ── Portrait (Shorts 1080×1920) ──
        # Başlığı 3 parçaya böl: ilk kısa kelime(ler) / orta / son kısa kelime(ler)
        words = title.upper().split()
        if len(words) <= 2:
            part_a, part_b, part_c = title.upper(), "", ""
        elif len(words) <= 4:
            mid = len(words) // 2
            part_a = " ".join(words[:mid])
            part_b = " ".join(words[mid:])
            part_c = ""
        else:
            part_a = " ".join(words[:2])
            part_b = " ".join(words[2:-2])
            part_c = " ".join(words[-2:])

        cat_text = "GÜNDEM" if lang == "tr" else "BREAKING"
        cat_fs   = int(H * 0.028)
        big_fs   = int(H * 0.072)
        mid_fs   = int(H * 0.042)
        sml_fs   = int(H * 0.032)
        badge_fs = int(H * 0.038)
        pad      = int(W * 0.05)

        cat_font   = load_font(cat_fs)
        big_font   = load_font(big_fs)
        mid_font   = load_font(mid_fs)
        sml_font   = load_font(sml_fs)
        badge_font = load_font(badge_fs)

        y = int(H * 0.09)

        # ① Kategori bandı
        band1_h = cat_fs + int(H * 0.025)
        draw.rectangle([(0, y), (W, y + band1_h)], fill=YELLOW)
        draw.rectangle([(0, y), (W, y + 3)], fill=BLACK)
        draw.rectangle([(0, y + band1_h - 3), (W, y + band1_h)], fill=BLACK)
        # ok dekorasyonları
        draw.text((pad, y + (band1_h - cat_fs) // 2), "»»", font=cat_font, fill=BLACK)
        cw = text_w(draw, cat_text, cat_font)
        draw.text(((W - cw) / 2, y + (band1_h - cat_fs) // 2), cat_text, font=cat_font, fill=BLACK)
        draw.text((W - pad - text_w(draw, "««", cat_font), y + (band1_h - cat_fs) // 2), "««", font=cat_font, fill=BLACK)
        y += band1_h + int(H * 0.018)

        # ② Büyük sarı bant — part_a
        if part_a:
            lines_a = textwrap.wrap(part_a, width=10)[:2]
            band2_h = len(lines_a) * (big_fs + 10) + int(H * 0.022)
            draw.rectangle([(pad // 2, y), (W - pad // 2, y + band2_h)], fill=YELLOW)
            draw.rectangle([(pad // 2, y), (W - pad // 2, y + 3)], fill=BLACK)
            draw.rectangle([(pad // 2, y + band2_h - 3), (W - pad // 2, y + band2_h)], fill=BLACK)
            ty = y + int(H * 0.011)
            for ln in lines_a:
                lw = text_w(draw, ln, big_font)
                draw.text(((W - lw) / 2, ty), ln, font=big_font, fill=BLACK)
                ty += big_fs + 10
            y += band2_h + int(H * 0.022)

        # ③ Orta satır — sarı yazı koyu zeminde
        if part_b:
            lines_b = textwrap.wrap(part_b, width=16)[:3]
            for ln in lines_b:
                lw = text_w(draw, ln, mid_font)
                draw.text(((W - lw) / 2, y), ln, font=mid_font, fill=YELLOW)
                y += mid_fs + int(H * 0.012)
            # ince ayraç çizgisi
            draw.rectangle([(W // 4, y), (3 * W // 4, y + 3)], fill=YELLOW)
            y += int(H * 0.022)

        # ④ İkinci büyük sarı bant — part_c
        if part_c:
            lines_c = textwrap.wrap(part_c, width=10)[:2]
            band4_h = len(lines_c) * (big_fs + 10) + int(H * 0.022)
            draw.rectangle([(pad // 2, y), (W - pad // 2, y + band4_h)], fill=YELLOW)
            draw.rectangle([(pad // 2, y), (W - pad // 2, y + 3)], fill=BLACK)
            draw.rectangle([(pad // 2, y + band4_h - 3), (W - pad // 2, y + band4_h)], fill=BLACK)
            ty = y + int(H * 0.011)
            for ln in lines_c:
                lw = text_w(draw, ln, big_font)
                draw.text(((W - lw) / 2, ty), ln, font=big_font, fill=BLACK)
                ty += big_fs + 10
            y += band4_h + int(H * 0.018)

        # ⑤ SON DAKİKA kırmızı bant — alt
        if news_style:
            badge_h = badge_fs + int(H * 0.028)
            by = H - badge_h - int(H * 0.04)
            draw.rectangle([(0, by), (W, by + badge_h)], fill=RED)
            draw.rectangle([(0, by), (W, by + 5)], fill=(255, 23, 68))
            draw.rectangle([(0, by), (8, by + badge_h)], fill=(255, 23, 68))
            draw.rectangle([(W - 8, by), (W, by + badge_h)], fill=(255, 23, 68))
            bw = text_w(draw, badge_text, badge_font)
            draw.text(((W - bw) / 2, by + (badge_h - badge_fs) // 2), badge_text, font=badge_font, fill=WHITE)

    else:
        # ── Landscape (uzun video 1280×720) ──
        words = title.upper().split()
        part_a = " ".join(words[:3]) if len(words) > 3 else title.upper()
        part_b = " ".join(words[3:]) if len(words) > 3 else ""

        big_fs   = int(H * 0.10)
        mid_fs   = int(H * 0.06)
        badge_fs = int(H * 0.055)
        pad      = int(W * 0.04)
        band_h   = int(H * 0.18)

        big_font   = load_font(big_fs)
        mid_font   = load_font(mid_fs)
        badge_font = load_font(badge_fs)

        y = int(H * 0.12)

        # Büyük sarı bant
        draw.rectangle([(0, y), (W, y + band_h)], fill=YELLOW)
        draw.rectangle([(0, y), (W, y + 4)], fill=BLACK)
        draw.rectangle([(0, y + band_h - 4), (W, y + band_h)], fill=BLACK)
        lines_a = textwrap.wrap(part_a, width=20)[:2]
        ty = y + (band_h - len(lines_a) * (big_fs + 6)) // 2
        for ln in lines_a:
            lw = text_w(draw, ln, big_font)
            draw.text(((W - lw) / 2, ty), ln, font=big_font, fill=BLACK)
            ty += big_fs + 6
        y += band_h + int(H * 0.04)

        # Orta sarı yazı
        if part_b:
            lines_b = textwrap.wrap(part_b, width=28)[:2]
            for ln in lines_b:
                lw = text_w(draw, ln, mid_font)
                draw.text(((W - lw) / 2, y), ln, font=mid_font, fill=YELLOW)
                y += mid_fs + int(H * 0.015)

        # SON DAKİKA
        if news_style:
            badge_band = badge_fs + int(H * 0.04)
            by = H - badge_band - int(H * 0.03)
            draw.rectangle([(0, by), (W, by + badge_band)], fill=RED)
            draw.rectangle([(0, by), (W, by + 4)], fill=(255, 23, 68))
            draw.rectangle([(0, by), (8, by + badge_band)], fill=(255, 23, 68))
            draw.rectangle([(W - 8, by), (W, by + badge_band)], fill=(255, 23, 68))
            bw = text_w(draw, badge_text, badge_font)
            draw.text(((W - bw) / 2, by + (badge_band - badge_fs) // 2), badge_text, font=badge_font, fill=WHITE)

    img.save(str(out_path), "JPEG", quality=92)
    return out_path


def overlay_ig_follow_banner(photo_path: Path) -> None:
    """Son sahne fotoğrafına koyu şeffaf alt bant + ❤️ Beğen  👤 Takip Et yazar (Instagram)."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.open(photo_path).convert("RGBA")
    img = img.resize((W, H), Image.LANCZOS)

    BAND_H = 260
    band = Image.new("RGBA", (W, BAND_H), (10, 10, 10, 210))
    img.paste(band, (0, H - BAND_H), band)

    draw = ImageDraw.Draw(img)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    try:
        font_big   = ImageFont.truetype(font_path, 90) if font_path else ImageFont.load_default()
        font_small = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()
    except Exception:
        font_big = font_small = ImageFont.load_default()

    PINK   = (225, 48, 108)
    WHITE  = (255, 255, 255)
    YELLOW = (255, 208, 0)

    lx = W // 4
    draw.text((lx, H - BAND_H + 28),  "❤️",       font=font_big,   anchor="mt", fill=WHITE)
    draw.text((lx, H - BAND_H + 128), "Beğen",    font=font_small, anchor="mt", fill=YELLOW)

    sep_x = W // 2
    draw.line([(sep_x, H - BAND_H + 20), (sep_x, H - 20)], fill=(80, 80, 80), width=2)

    rx = W * 3 // 4
    draw.text((rx, H - BAND_H + 28),  "👤",        font=font_big,   anchor="mt", fill=WHITE)
    draw.text((rx, H - BAND_H + 128), "Takip Et", font=font_small, anchor="mt", fill=PINK)

    img.convert("RGB").save(str(photo_path), "JPEG", quality=92)


def overlay_like_subscribe_banner(photo_path: Path) -> None:
    """Son sahne fotoğrafına koyu şeffaf alt bant + 👍 Beğen  🔔 Abone Ol yazar."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    img = Image.open(photo_path).convert("RGBA")
    img = img.resize((W, H), Image.LANCZOS)

    BAND_H = 260
    band = Image.new("RGBA", (W, BAND_H), (10, 10, 10, 210))
    img.paste(band, (0, H - BAND_H), band)

    draw = ImageDraw.Draw(img)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    try:
        font_big  = ImageFont.truetype(font_path, 90) if font_path else ImageFont.load_default()
        font_small = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()
    except Exception:
        font_big = font_small = ImageFont.load_default()

    RED    = (255, 0, 0)
    WHITE  = (255, 255, 255)
    YELLOW = (255, 208, 0)

    # Sol yarı — 👍 Beğen
    lx = W // 4
    draw.text((lx, H - BAND_H + 28), "👍", font=font_big,  anchor="mt", fill=WHITE)
    draw.text((lx, H - BAND_H + 128), "Beğen",   font=font_small, anchor="mt", fill=YELLOW)

    # Dikey ayraç
    sep_x = W // 2
    draw.line([(sep_x, H - BAND_H + 20), (sep_x, H - 20)], fill=(80, 80, 80), width=2)

    # Sağ yarı — 🔔 Abone Ol
    rx = W * 3 // 4
    draw.text((rx, H - BAND_H + 28), "🔔", font=font_big,  anchor="mt", fill=WHITE)
    draw.text((rx, H - BAND_H + 128), "Abone Ol", font=font_small, anchor="mt", fill=RED)

    img.convert("RGB").save(str(photo_path), "JPEG", quality=92)


OUTRO_TEMPLATE = UPLOAD_DIR / "outro_template.mp4"


def create_animated_outro_video(
    avatar_file,
    ig_handle: str,
    output_path: Path,
    platform: str = "instagram",
    duration_sec: float = 3.5,
    fps: int = 30,
) -> bool:
    """Artık kullanılmıyor — template sistemi kullanılıyor."""
    return False
    import tempfile, math, random
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1080, 1920
    total_frames = int(duration_sec * fps)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    fp = next((f for f in font_candidates if Path(f).exists()), None)

    def lf(size):
        if fp:
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def eout(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 1 - (1 - t) ** 3

    def eio(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return 3 * t * t - 2 * t * t * t

    # Avatar daire hazırlama
    AVSIZE = 320
    avatar_img = None
    if avatar_file and Path(avatar_file).exists():
        try:
            av = Image.open(avatar_file).convert("RGBA").resize((AVSIZE, AVSIZE), Image.LANCZOS)
            mask = Image.new("L", (AVSIZE, AVSIZE), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, AVSIZE, AVSIZE], fill=255)
            av.putalpha(mask)
            avatar_img = av
        except Exception:
            pass

    # Platform renkler
    if platform == "instagram":
        cta_color = (225, 48, 108)    # Instagram pembe
        cta_icon = "👤"
        cta_label = "Takip Et"
        bottom_text = "❤️  Beğen ve Paylaş"
    else:
        cta_color = (255, 0, 0)       # YouTube kırmızı
        cta_icon = "🔴"
        cta_label = "Abone Ol"
        bottom_text = "🔔  Bildirimleri Aç"

    # Sabit parıltı noktaları (deterministic, random seed)
    rng = random.Random(42)
    sparkles = [(rng.randint(40, W - 40), rng.randint(100, H - 100), rng.random()) for _ in range(35)]

    cy_mid = H // 2 - 80   # dikey merkez

    with tempfile.TemporaryDirectory() as tmpdir:
        for fi in range(total_frames):
            t = fi / max(total_frames - 1, 1)

            bg = Image.new("RGBA", (W, H), (5, 5, 16, 255))
            draw = ImageDraw.Draw(bg)

            # ── Animasyonlu radyal glow ──
            glow_r = int(460 + 55 * math.sin(t * math.tau))
            for gr in range(glow_r, 0, -20):
                a = int(22 * (gr / glow_r))
                draw.ellipse([W // 2 - gr, cy_mid - gr, W // 2 + gr, cy_mid + gr],
                             fill=(18, 36, 90, a))

            # ── Parıltı noktaları ──
            for sx, sy, sp in sparkles:
                sa = int(160 * abs(math.sin((t * 2.5 + sp) * math.tau)))
                sr = rng.randint(2, 5) if sa > 60 else 2
                draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255, sa))

            # ── 1. Üst yazı: "Daha Fazlası İçin" (0 → 0.35s, slide-up + fade) ──
            lbl_e = eout(t / 0.3)
            if lbl_e > 0:
                lbl_a = int(255 * lbl_e)
                lbl_offset = int(55 * (1 - lbl_e))
                lbl_font = lf(58)
                lbl_text = "Daha Fazlası İçin"
                bb = draw.textbbox((0, 0), lbl_text, font=lbl_font)
                lw = bb[2] - bb[0]
                ll = Image.new("RGBA", (W, 90), (0, 0, 0, 0))
                ImageDraw.Draw(ll).text(
                    (W // 2 - lw // 2, 0), lbl_text, font=lbl_font,
                    fill=(200, 205, 230, lbl_a)
                )
                bg.alpha_composite(ll, (0, cy_mid - 400 + lbl_offset))

            # ── 2. Avatar yüzük + görsel (0.2 → 0.7s, scale-in) ──
            av_e = eout((t - 0.18) / 0.42)
            av_cx, av_cy = W // 2, cy_mid - 20

            if av_e > 0:
                av_a = int(255 * av_e)
                scale_r = int((AVSIZE // 2 + 14) * av_e)

                # Dış halkalar (glow ring)
                ring_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                rd = ImageDraw.Draw(ring_layer)
                # İç halka — beyaz
                rd.ellipse([av_cx - scale_r, av_cy - scale_r,
                            av_cx + scale_r, av_cy + scale_r],
                           fill=(255, 255, 255, av_a))
                # İkinci halka — platform rengi, daha büyük, şeffaf
                ring2_r = scale_r + 12
                rd.ellipse([av_cx - ring2_r, av_cy - ring2_r,
                            av_cx + ring2_r, av_cy + ring2_r],
                           fill=(*cta_color, int(av_a * 0.35)))
                bg.alpha_composite(ring_layer)

                # Avatar veya placeholder
                av_final_r = int(AVSIZE // 2 * av_e)
                if av_final_r > 2:
                    if avatar_img:
                        av_scaled = avatar_img.resize((av_final_r * 2, av_final_r * 2), Image.LANCZOS)
                        if av_a < 255:
                            r2, g2, b2, alpha2 = av_scaled.split()
                            alpha2 = alpha2.point(lambda x: int(x * av_a / 255))
                            av_scaled = Image.merge("RGBA", (r2, g2, b2, alpha2))
                        bg.alpha_composite(av_scaled, (av_cx - av_final_r, av_cy - av_final_r))
                    else:
                        ph = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                        ImageDraw.Draw(ph).ellipse(
                            [av_cx - av_final_r, av_cy - av_final_r,
                             av_cx + av_final_r, av_cy + av_final_r],
                            fill=(40, 60, 120, av_a)
                        )
                        bg.alpha_composite(ph)

            # ── 3. Kullanıcı adı (0.55 → 0.8s, fade-in) ──
            usr_e = eout((t - 0.52) / 0.25)
            if usr_e > 0 and ig_handle:
                usr_a = int(255 * usr_e)
                usr_font = lf(54)
                utext = f"@{ig_handle.lstrip('@')}"
                bb = draw.textbbox((0, 0), utext, font=usr_font)
                uw = bb[2] - bb[0]
                ul = Image.new("RGBA", (W, 72), (0, 0, 0, 0))
                ImageDraw.Draw(ul).text(
                    (W // 2 - uw // 2, 0), utext, font=usr_font,
                    fill=(255, 255, 255, usr_a)
                )
                bg.alpha_composite(ul, (0, av_cy + AVSIZE // 2 + 22))

            # ── 4. CTA butonu (0.68 → 1.0s, slide-up + scale) ──
            btn_e = eout((t - 0.65) / 0.3)
            BTN_W, BTN_H = 440, 108
            btn_cy_final = av_cy + AVSIZE // 2 + (110 if ig_handle else 60)
            btn_cy = int(btn_cy_final + 200 * (1 - btn_e))
            btn_a = int(255 * btn_e)

            if btn_e > 0:
                # Nabız efekti (2s'den sonra)
                pulse = 1.0 + 0.04 * math.sin((t - 1.8) * 6.0 * math.pi) if t > 1.8 else 1.0
                pb_w = int(BTN_W * pulse)
                pb_h = int(BTN_H * pulse)
                bx0 = W // 2 - pb_w // 2
                by0 = btn_cy - pb_h // 2
                btn_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                _draw_rounded_rect(
                    ImageDraw.Draw(btn_layer),
                    [bx0, by0, bx0 + pb_w, by0 + pb_h],
                    pb_h // 2,
                    (*cta_color, btn_a)
                )
                btn_font = lf(56)
                btext = f"{cta_icon}  {cta_label}"
                bbd = ImageDraw.Draw(btn_layer).textbbox((0, 0), btext, font=btn_font)
                btw = bbd[2] - bbd[0]
                bth = bbd[3] - bbd[1]
                ImageDraw.Draw(btn_layer).text(
                    (W // 2 - btw // 2, btn_cy - bth // 2 - bbd[1]),
                    btext, font=btn_font,
                    fill=(255, 255, 255, btn_a)
                )
                bg.alpha_composite(btn_layer)

            # ── 5. Alt metin (0.9 → 1.0s, fade-in) ──
            bot_e = eout((t - 0.88) / 0.18)
            if bot_e > 0:
                bot_a = int(200 * bot_e)
                bot_font = lf(46)
                bb = draw.textbbox((0, 0), bottom_text, font=bot_font)
                bw = bb[2] - bb[0]
                bot_l = Image.new("RGBA", (W, 66), (0, 0, 0, 0))
                ImageDraw.Draw(bot_l).text(
                    (W // 2 - bw // 2, 0), bottom_text, font=bot_font,
                    fill=(255, 215, 60, bot_a)
                )
                bg.alpha_composite(bot_l, (0, btn_cy_final + BTN_H // 2 + 30))

            frame_path = Path(tmpdir) / f"frame_{fi:05d}.png"
            bg.convert("RGB").save(str(frame_path))

        try:
            r = subprocess.run([
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(Path(tmpdir) / "frame_%05d.png"),
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-r", str(fps),
                str(output_path)
            ], capture_output=True, timeout=180)
            return r.returncode == 0 and output_path.exists()
        except Exception as e:
            print(f"[OUTRO] ffmpeg encode hata: {e}", flush=True)
            return False


async def _append_outro_template(main_video: Path, final_output: Path) -> bool:
    """uploads/outro_template.mp4 varsa ana videoya yapıştır."""
    if not OUTRO_TEMPLATE.exists():
        return False
    import tempfile as _tf
    try:
        with _tf.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write(f"file '{main_video.absolute()}'\n")
            f.write(f"file '{OUTRO_TEMPLATE.absolute()}'\n")
            concat_list = f.name
        await arun_ffmpeg([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr", "-bf", "0", "-g", "30",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
            "-movflags", "+faststart",
            str(final_output.absolute())
        ], timeout=300, step="outro-concat")
        Path(concat_list).unlink(missing_ok=True)
        return final_output.exists()
    except Exception as e:
        print(f"[OUTRO] concat hata: {e}", flush=True)
        return False


def overlay_first_scene_banner(photo_path: Path, title: str, lang: str = "tr") -> None:
    """İlk sahne fotoğrafına haber overlay: bantsız büyük sarı yazılar + dar eğik SON DAKİKA."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    W, H = 1080, 1920
    img = Image.open(photo_path).convert("RGB")
    img = img.resize((W, H), Image.LANCZOS)

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    fp = next((f for f in font_candidates if Path(f).exists()), None)

    def lf(sz):
        if fp:
            try:
                return ImageFont.truetype(fp, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    def tw(text, font):
        try:
            return draw.textlength(text, font=font)
        except AttributeError:
            return font.getlength(text)

    def shadow_text(cx, y, text, font, fill):
        w = int(tw(text, font)); x = cx - w // 2
        for dx, dy in [(5, 5), (4, 4), (3, 3)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=fill)

    def fit_font(text, start_sz, max_w):
        sz = start_sz
        while sz > 40:
            f = lf(sz)
            if tw(text, f) <= max_w:
                return f, sz
            sz -= 10
        return lf(sz), sz

    # Başlık anahtar kelimesinden kategori rengi tespiti
    _tl = title.lower()
    _CATS = [
        (["ekonomi","borsa","döviz","faiz","enflasyon","dolar","euro","piyasa","merkez ban","bütçe","liret"],
         (30, 130, 220), "EKONOMİ"),
        (["deprem","sel","yangın","afet","fırtına","kasırga","tsunami","volkan","heyelan"],
         (230, 105, 0), "AFET"),
        (["futbol","basketbol","spor","şampiyona","lig","maç","gol","transfer","milli takım","teniz","formula"],
         (0, 170, 55), "SPOR"),
        (["dünya","nato","avrupa","ukrayna","rusya","gazze","suriye","savaş","uluslararası","filistin","İsrail"],
         (140, 50, 215), "DÜNYA"),
        (["teknoloji","yapay zeka","nasa","uzay","bilim","robot","chatgpt","iphone","android","yapay","ai"],
         (0, 175, 195), "TEKNOLOJİ"),
    ]
    _accent = (255, 208, 0)
    cat_text = "GÜNDEM" if lang == "tr" else "BREAKING"
    _band_txt_dark = True
    for _kws, _color, _label in _CATS:
        if any(k in _tl for k in _kws):
            _accent = _color
            cat_text = _label
            _band_txt_dark = False
            break
    BAND_COLOR = _accent          # bant arka planı → kategori rengi
    YELLOW     = (255, 208, 0)    # başlık metni her zaman sarı (okunabilirlik)
    RED    = (213,   0,   0)
    BLACK  = ( 17,  17,  17)
    WHITE  = (255, 255, 255)
    BAND_TXT = BLACK if _band_txt_dark else WHITE
    CX     = W // 2
    badge_text = "SON DAKİKA" if lang == "tr" else "BREAKING NEWS"

    # Başlığı 3 parçaya böl
    words = title.upper().split()
    if len(words) <= 2:
        part_a, part_b, part_c = " ".join(words), "", ""
    elif len(words) <= 4:
        m = len(words) // 2
        part_a = " ".join(words[:m])
        part_b = " ".join(words[m:])
        part_c = ""
    else:
        part_a = " ".join(words[:2])
        part_b = " ".join(words[2:-2])
        part_c = " ".join(words[-2:])

    # ① Üst kategori bandı — renk kategoriye göre değişir, başlık metni her zaman sarı
    y1, h1 = 150, 120
    draw.rectangle([(0, y1), (W, y1 + h1)], fill=BAND_COLOR)
    draw.rectangle([(0, y1), (W, y1 + 7)], fill=BLACK)
    draw.rectangle([(0, y1 + h1 - 7), (W, y1 + h1)], fill=BLACK)
    cf = lf(52); af = lf(62)
    draw.text((60, y1 + (h1 - 52) // 2), "»»", font=af, fill=BAND_TXT)
    cw = tw(cat_text, cf)
    draw.text((CX - cw // 2, y1 + (h1 - 52) // 2), cat_text, font=cf, fill=BAND_TXT)
    draw.text((W - 60 - int(tw("««", af)), y1 + (h1 - 52) // 2), "««", font=af, fill=BAND_TXT)

    # ② part_a — bantsız büyük sarı yazı
    if part_a:
        a_font, a_sz = fit_font(part_a, 190, W - 120)
        shadow_text(CX, 330, part_a, a_font, YELLOW)

    # ③ part_b — koyu eğik arka plan + sarı yazı (bant değil)
    if part_b:
        b_font, b_sz = fit_font(part_b, 88, W - 100)
        b_w = int(tw(part_b, b_font))
        bx1 = CX - b_w // 2 - 50; bx2 = CX + b_w // 2 + 50
        by  = 580; bh = b_sz + 40; sk = 20
        poly = [(bx1 + sk, by), (bx2 + sk, by), (bx2 - sk, by + bh), (bx1 - sk, by + bh)]
        acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(acc).polygon(poly, fill=(10, 10, 10, 185))
        img = Image.alpha_composite(img.convert("RGBA"), acc).convert("RGB")
        draw = ImageDraw.Draw(img)
        shadow_text(CX, by + 18, part_b, b_font, YELLOW)

    # ④ part_c — bantsız büyük sarı yazı
    if part_c:
        c_font, c_sz = fit_font(part_c, 190, W - 120)
        y_c = 750 if part_b else 600
        shadow_text(CX, y_c, part_c, c_font, YELLOW)

    # ⑤ SON DAKİKA — dar eğik kırmızı badge (tam genişlik değil)
    bdf = lf(80); bt = badge_text; btw = int(tw(bt, bdf))
    bw2 = btw + 130; bx_b = CX - bw2 // 2; byy = 1050; bhh = 140; sk2 = 28
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([(CX - 360, byy + 60), (CX + 360, byy + 240)], fill=(255, 30, 40, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)
    rp = [(bx_b + sk2, byy), (bx_b + bw2 + sk2, byy), (bx_b + bw2 - sk2, byy + bhh), (bx_b - sk2, byy + bhh)]
    rib = Image.new("RGBA", (W, H), (0, 0, 0, 0)); rd = ImageDraw.Draw(rib)
    rd.polygon(rp, fill=(213, 0, 0, 255))
    rd.polygon([(bx_b + sk2, byy), (bx_b + bw2 + sk2, byy),
                (bx_b + bw2 + sk2 - 6, byy + 10), (bx_b + sk2 - 6, byy + 10)], fill=(255, 40, 60, 255))
    img = Image.alpha_composite(img.convert("RGBA"), rib).convert("RGB")
    draw = ImageDraw.Draw(img)
    shadow_text(CX, byy + (bhh - 80) // 2, bt, bdf, WHITE)

    img.save(str(photo_path), "JPEG", quality=92)


def prepend_thumbnail_intro(thumb_path: Path, video_path: Path, duration: int = 2, size: tuple = (1080, 1920)) -> Path:
    """Thumbnail görüntüsünü intro klibe çevirip videonun başına ekler."""
    import shutil, tempfile
    W, H = size
    tmp = Path(tempfile.mkdtemp())
    intro_clip = tmp / "intro.mp4"
    intro_list = tmp / "list.txt"
    final_path = video_path.with_name(video_path.stem + "_wi.mp4")
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(thumb_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100",
            str(intro_clip),
        ], check=True, capture_output=True, timeout=120)
        with open(intro_list, "w") as f:
            f.write(f"file '{intro_clip.absolute()}'\n")
            f.write(f"file '{video_path.absolute()}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(intro_list),
            "-c", "copy", str(final_path),
        ], check=True, capture_output=True, timeout=120)
        video_path.unlink(missing_ok=True)
        return final_path
    except Exception:
        return video_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_THUMB_TEMPLATES = {
    "breaking": {
        "band_grad": ((184, 0, 0), (255, 30, 30)),
        "sayi_color": (255, 212, 0),
        "ana_color": (255, 255, 255),
        "accent_fill": (255, 212, 0),
        "accent_text": (0, 0, 0),
        "detay_color": (255, 255, 255),
        "alarm_border": (255, 0, 0),
        "alarm_label": {"tr": "ACİL GELİŞME", "en": "BREAKING UPDATE"},
        "alarm_label_color": (255, 64, 64),
    },
    "tech": {
        "band_grad": ((0, 50, 160), (0, 180, 255)),
        "sayi_color": (0, 220, 255),
        "ana_color": (255, 255, 255),
        "accent_fill": (0, 150, 255),
        "accent_text": (255, 255, 255),
        "detay_color": (0, 220, 255),
        "alarm_border": (0, 180, 255),
        "alarm_label": {"tr": "YENİ GELİŞME", "en": "TECH UPDATE"},
        "alarm_label_color": (0, 200, 255),
    },
    "economy": {
        "band_grad": ((0, 90, 20), (0, 210, 80)),
        "sayi_color": (0, 255, 120),
        "ana_color": (255, 255, 255),
        "accent_fill": (0, 200, 80),
        "accent_text": (0, 0, 0),
        "detay_color": (0, 255, 120),
        "alarm_border": (0, 200, 80),
        "alarm_label": {"tr": "PİYASA HABERİ", "en": "MARKET NEWS"},
        "alarm_label_color": (0, 230, 100),
    },
    "shock": {
        "band_grad": ((110, 0, 180), (220, 0, 255)),
        "sayi_color": (255, 100, 0),
        "ana_color": (255, 255, 255),
        "accent_fill": (180, 0, 220),
        "accent_text": (255, 255, 255),
        "detay_color": (255, 120, 0),
        "alarm_border": (200, 0, 240),
        "alarm_label": {"tr": "İNANILMAZ!", "en": "UNBELIEVABLE!"},
        "alarm_label_color": (255, 80, 255),
    },
}


def create_shorts_thumbnail(thumb_vars: dict, out_path: Path, size=(1080, 1920), lang="tr"):
    """ChatGPT SVG breaking-news tasarımını PIL ile render eder. 4 renk şablonu döner."""
    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    W, H = size
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    def load_font(sz):
        if font_path:
            try:
                return ImageFont.truetype(font_path, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    def center_text(text, font, cy, fill, shadow_fill=None):
        bb = draw.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x = (W - tw) // 2
        y = cy - th // 2
        if shadow_fill:
            draw.text((x + 5, y + 8), text, font=font, fill=shadow_fill)
        draw.text((x, y), text, font=font, fill=fill)

    def rrect(x1, y1, x2, y2, r, fill, outline=None, width=0):
        try:
            if outline:
                draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=r, fill=fill, outline=outline, width=width)
            else:
                draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=r, fill=fill)
        except (AttributeError, TypeError):
            draw.rectangle([(x1, y1), (x2, y2)], fill=fill, outline=outline, width=width)

    # Şablon seç
    tpl_key = thumb_vars.get("template", "breaking")
    if tpl_key not in _THUMB_TEMPLATES:
        tpl_key = "breaking"
    tpl = _THUMB_TEMPLATES[tpl_key]

    # SVG 1080x1920 — aynı boyut, scale=1
    def s(v): return int(v * H / 1920)

    # ── Dekoratif ince şeritler ──
    draw.rectangle([(0, s(128)), (W, s(153))], fill=(17, 17, 17))
    draw.rectangle([(0, s(1755)), (W, s(1780))], fill=(17, 17, 17))

    # ── Üst gradient bant ──
    c1, c2 = tpl["band_grad"]
    bx1, by1, bx2, by2 = s(80), s(80), s(80) + s(920), s(80) + s(130)
    for xi in range(bx1, bx2):
        t = (xi - bx1) / max(bx2 - bx1, 1)
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        draw.line([(xi, by1), (xi, by2)], fill=col)
    ust = thumb_vars.get("ust_bant", "SON DAKİKA" if lang == "tr" else "BREAKING NEWS")
    center_text(ust, load_font(s(82)), (by1 + by2) // 2, (255, 255, 255))

    # ── Büyük sayı / kelime ──
    sayi = str(thumb_vars.get("sayi", ""))
    if sayi:
        center_text(sayi, load_font(s(420)), s(520), tpl["sayi_color"], shadow_fill=(20, 20, 20))

    # ── Ana başlık ──
    ana = thumb_vars.get("ana_baslik", "")
    if ana:
        center_text(ana, load_font(s(130)), s(860), tpl["ana_color"])

    # ── Accent rounded rect + yazı ──
    yr1, yr2 = s(1030), s(1150)
    xr1, xr2 = s(120), s(960)
    rrect(xr1, yr1, xr2, yr2, s(14), tpl["accent_fill"])
    alt = thumb_vars.get("alt_baslik", "")
    if alt:
        alt_font = load_font(s(72))
        bb = draw.textbbox((0, 0), alt, font=alt_font)
        alt_sz = s(72)
        while bb[2] - bb[0] > (xr2 - xr1) - s(40) and alt_sz > s(36):
            alt_sz -= 4
            alt_font = load_font(alt_sz)
            bb = draw.textbbox((0, 0), alt, font=alt_font)
        center_text(alt, alt_font, (yr1 + yr2) // 2, tpl["accent_text"])

    # ── Detay metni ──
    detay = thumb_vars.get("detay", "")
    if detay:
        center_text(detay, load_font(s(95)), s(1285), tpl["detay_color"])

    # ── Alarm kutusu ──
    ab_x1, ab_x2 = s(90), s(990)
    ab_y1, ab_y2 = s(1450), s(1660)
    rrect(ab_x1, ab_y1, ab_x2, ab_y2, s(22), (17, 17, 17), outline=tpl["alarm_border"], width=s(8))

    acil = tpl["alarm_label"].get(lang, tpl["alarm_label"].get("tr", "ACİL GELİŞME"))
    center_text(acil, load_font(s(55)), s(1510), tpl["alarm_label_color"])

    ek = thumb_vars.get("ek_bilgi", "")
    if ek:
        ek_lines = textwrap.wrap(ek, width=20)[:2]
        ek_y = s(1570)
        for ln in ek_lines:
            lf = load_font(s(60) if len(ek_lines) > 1 else s(72))
            bb = draw.textbbox((0, 0), ln, font=lf)
            draw.text(((W - (bb[2]-bb[0])) // 2, ek_y), ln, font=lf, fill=(255, 255, 255))
            ek_y += s(72)

    # ── Brand bar ──
    draw.rectangle([(0, s(1810)), (W, H)], fill=(5, 5, 5))
    center_text("BELMOLYSOFT NEWS", load_font(s(46)), s(1855), (119, 119, 119))

    img.save(str(out_path), "JPEG", quality=92)
    return out_path


def overlay_lv_title_banner(photo_path: Path, title: str) -> None:
    """Landscape (1920x1080) ilk sahne için başlık banner'ı."""
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        img = PILImage.open(str(photo_path)).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        ]
        fp = next((f for f in font_candidates if Path(f).exists()), None)
        font_big = ImageFont.truetype(fp, 56) if fp else ImageFont.load_default()
        font_sm = ImageFont.truetype(fp, 32) if fp else ImageFont.load_default()
        # Üst koyu bant
        overlay = PILImage.new("RGBA", (1920, 200), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (1920, 200)], fill=(10, 10, 20, 210))
        img.paste(PILImage.new("RGB", (1920, 200), (10, 10, 20)),
                  (0, 0), mask=overlay.split()[3])
        # Başlık (max 2 satır) — belgesel modda SON DAKİKA rozeti yok
        words = title.split()
        line1, line2 = [], []
        for w in words:
            if draw.textlength(" ".join(line1 + [w]), font=font_big) < 1700:
                line1.append(w)
            else:
                line2.append(w)
        draw.text((40, 20), " ".join(line1), fill=(255, 220, 0), font=font_big,
                  stroke_width=2, stroke_fill=(0, 0, 0))
        if line2:
            draw.text((40, 90), " ".join(line2[:8]), fill=(255, 220, 0), font=font_big,
                      stroke_width=2, stroke_fill=(0, 0, 0))
        img.save(str(photo_path), "JPEG", quality=90)
    except Exception:
        pass


def overlay_lv_subscribe_banner(photo_path: Path) -> None:
    """Landscape (1920x1080) son sahne için abone ol banner'ı."""
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        img = PILImage.open(str(photo_path)).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        fp = next((f for f in font_candidates if Path(f).exists()), None)
        font = ImageFont.truetype(fp, 58) if fp else ImageFont.load_default()
        # Alt koyu bant
        overlay = PILImage.new("RGBA", (1920, 160), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (1920, 160)], fill=(10, 10, 20, 220))
        img.paste(PILImage.new("RGB", (1920, 160), (10, 10, 20)),
                  (0, 920), mask=overlay.split()[3])
        text = "👍  Beğen         🔔  Abone Ol"
        tw = draw.textlength(text, font=font)
        draw.text(((1920 - tw) // 2, 940), text, fill=(255, 255, 255), font=font,
                  stroke_width=2, stroke_fill=(0, 0, 0))
        img.save(str(photo_path), "JPEG", quality=90)
    except Exception:
        pass


async def _generate_long_video_core(topic: str, api_key: str, lang: str, voice: str, speed: float, duration_min: int, use_video: str = "false") -> dict:
    import json as _json
    from openai import OpenAI

    use_video_mode = use_video == "true"
    pexels_key = get_pexels_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    lang_name = LANG_MAP.get(lang, "Turkish")
    scene_count = max(6, duration_min * 2)

    prompt = f"""Create a detailed educational/documentary YouTube video about: {topic}
Narration language: {lang_name}
Target duration: {duration_min} minutes ({scene_count} scenes)

Return ONLY valid JSON, no markdown:
{{
  "title": "engaging YouTube title (max 80 chars, in {lang_name})",
  "description": "detailed video description (3-4 sentences, in {lang_name})",
  "hashtags": ["relevant", "hashtag", "words", "no", "hash", "symbol"],
  "scenes": [
    {{
      "text": "narration for this scene (2-3 rich, detailed sentences with facts and context, max 30 seconds when spoken)",
      "keyword": "english search keyword for stock photo (2-3 words)"
    }}
  ]
}}

Rules:
- Exactly {scene_count} scenes
- In scene text: NEVER use abbreviations (e.g. YKS, ÖSYM, TBMM, ABD, AKP, CHP, TÜBİTAK). Always write the full name so text-to-speech reads correctly.
- Turkish number format ONLY: comma (,) is the decimal separator, dot (.) is the thousands separator — NEVER write numbers in English format (e.g. "1,287" meaning one thousand two hundred eighty-seven, or "1.2" when you mean "one point two" is fine but "1,287" as a thousands-grouped count is NOT). Write "1.287" for the thousands case or spell it out "bin iki yüz seksen yedi" — English-style thousands-commas break the TTS reading and can be misread as a decimal.
- NEVER use phrases that imply real footage or real photos exist (e.g. "İşte görüntüler", "İşte o anlar", "kameralar görüntüledi", "işte o fotoğraflar", "görüntüler ortaya çıktı", "here is the footage"). Visuals are illustrative stock photos — narration must describe events in storytelling form, never reference visuals.
- FIRST scene text MUST use a CURIOSITY-GAP hook — never state the answer directly. Create suspense, ask a question, or give a partial reveal. Examples: "Kimse beklemiyordu:", "Meğer...", "Az önce ortaya çıktı:", "Cevap herkesi şoke etti.", "Peki gerçekte ne oldu?", "Tarihin en büyük...". The viewer MUST feel compelled to keep watching. NEVER open with a plain news statement. Vary the opener every video.
- LAST scene text MUST end with (translated naturally to {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!" — urgent and personal, not generic.
- Each scene: 2-3 sentences packed with facts, context and detail — NOT simple or vague
- Cover the topic thoroughly: introduction, key facts, interesting details, historical context, conclusion
- hashtags: 8-12 relevant tags mixing {lang_name} and English terms, ALWAYS include "Shorts", "belgesel", "eğitim", "keşfet" — then add topic-specific tags. No # symbol, NO spaces within a tag (e.g. "yapayZeka" not "yapay zeka")
- keyword: English, specific and visual"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4000,
    )

    data = _parse_llm_json(response.choices[0].message.content)
    scenes = data["scenes"]

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    audio_files = []
    clip_files = []
    durations = []

    for i, scene in enumerate(scenes):
        wav, dur = await asyncio.to_thread(tts.synthesize,
            _clean_tts_text(scene["text"], lang), lang=lang,
            voice_style=style, total_steps=8, speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        img_path = scene_dir / f"scene_{i}.jpg"
        raw_vid = None

        # İlk sahne (i==0) her zaman görsel — banner için; diğerleri video modunda olabilir
        if use_video_mode and pexels_key and i > 0:
            vid_ok, vid_result = await asyncio.to_thread(
                fetch_pexels_video, scene.get("keyword", topic), pexels_key,
                scene_dir / f"rawvid_{i}.mp4", dur_val,
            )
            if vid_ok:
                raw_vid = Path(vid_result)
                photo_saved = True
            else:
                photo_saved = fetch_scene_visual(scene.get("keyword", topic), "landscape", pexels_key, img_path)
        else:
            photo_saved = fetch_scene_visual(scene.get("keyword", topic), "landscape", pexels_key, img_path)

        if not photo_saved and not raw_vid:
            await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "color=black:size=1920x1080:rate=1",
                 "-frames:v", "1", str(img_path)],
                capture_output=True, timeout=90,
            )

        # Banner overlay'leri (sadece görsel sahnesinde çalışır)
        if img_path.exists():
            if i == 0:
                overlay_lv_title_banner(img_path, data.get("title", topic))
            elif i == len(scenes) - 1:
                overlay_lv_subscribe_banner(img_path)

        # Clip oluştur (yatay 1920x1080)
        clip_path = scene_dir / f"clip_{i}.mp4"
        words = scene["text"].split()
        lines, line = [], []
        for w in words:
            if len(" ".join(line + [w])) > 70:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        text_file = scene_dir / f"text_{i}.txt"
        text_file.write_text("\n".join(lines), encoding="utf-8")

        drawtext = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"drawtext=textfile={text_file.absolute()}"
            f":fontsize=36:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-80:line_spacing=10"
            f":box=1:boxcolor=black@0.6:boxborderw=16"
        )
        if font_path:
            drawtext += f":fontfile={font_path}"

        if raw_vid:
            await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-i", str(raw_vid),
                 "-t", str(dur_val),
                 "-vf", drawtext,
                 "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                 "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, timeout=180,
            )
        else:
            await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
                 "-t", str(dur_val),
                 "-vf", drawtext,
                 "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                 "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, timeout=180,
            )
        clip_files.append(clip_path)

    # Sesleri birleştir
    audio_list = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True, timeout=180,
    )

    # Klipleri birleştir
    clip_list = scene_dir / "clip_list.txt"
    merged = scene_dir / "merged.mp4"
    with open(clip_list, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(merged)],
        check=True, capture_output=True, timeout=180,
    )

    # Ses ekle + disclaimer overlay
    output_file = OUTPUT_DIR / f"{uid}_long.mp4"
    lv_disclaimer_file = scene_dir / "disclaimer.txt"
    lv_disclaimer_file.write_text(
        "Gorseller temsilidir. Gercek kisi veya mekanla ilgili degildir.",
        encoding="utf-8"
    )
    lv_disclaimer_filter = (
        f"drawtext=textfile={lv_disclaimer_file.absolute()}"
        f":fontsize=20:fontcolor=white@0.9"
        f":box=1:boxcolor=black@0.55:boxborderw=6"
        f":x=(w-text_w)/2:y=h-th-12"
    )
    if font_path:
        lv_disclaimer_filter += f":fontfile={font_path}"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-vf", lv_disclaimer_filter,
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", str(output_file)],
        check=True, capture_output=True, timeout=300,
    )

    full_script = " ".join(s["text"] for s in scenes)
    total_dur = round(sum(durations), 1)
    lv_title = data.get("title", topic)

    raw_tags = data.get("hashtags", [])
    suggested_tags = _format_hashtags(raw_tags, limit=5)
    if not suggested_tags:
        suggested_tags = _format_hashtags([topic.split()[0], "belgesel", "eğitim", "keşfet", "teknoloji"], limit=5)

    thumb_path = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), lv_title, thumb_out, size=(1280, 720), lang=lang, news_style=False)
            thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

    shutil.rmtree(scene_dir, ignore_errors=True)

    return {
        "video": f"/api/video/{output_file.name}",
        "thumbnail": thumb_path,
        "title": lv_title,
        "description": data.get("description", ""),
        "suggested_tags": suggested_tags,
        "script": full_script,
        "duration_sec": total_dur,
        "scene_count": len(scenes),
    }


async def _long_video_runner(topic, api_key, lang, voice, speed, duration_min, use_video):
    global _manual_lv_lock
    try:
        result = await _generate_long_video_core(topic, api_key, lang, voice, speed, duration_min, use_video)
        _save_manual_lv_log("done", result=result)
        # Send to Telegram automatically
        video_file = OUTPUT_DIR / result["video"].split("/")[-1]
        await send_telegram_video(
            video_file,
            result.get("title", topic),
            result.get("description", ""),
            result.get("suggested_tags", ""),
        )
    except Exception as e:
        _save_manual_lv_log("error", error=str(e))
    finally:
        _manual_lv_lock = False


@app.post("/api/generate-long-video")
async def generate_long_video(
    topic: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    duration_min: int = Form(3),
    use_video: str = Form("false"),
):
    if not topic.strip():
        raise HTTPException(400, "Konu boş olamaz")
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")
    # Zaten çalışan worker var mı kontrol et (PID dosyası)
    if MANUAL_LV_LOG.exists():
        try:
            existing = json.loads(MANUAL_LV_LOG.read_text())
            if existing.get("status") == "running":
                pid = existing.get("pid")
                if pid:
                    import os as _os
                    try:
                        os.kill(int(pid), 0)
                        raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")
                    except OSError:
                        pass  # process ölmüş, yenisini başlat
                else:
                    raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")
        except HTTPException:
            raise
        except Exception:
            pass

    started_at = time.time()
    job = {
        "topic": topic, "api_key": api_key, "lang": lang,
        "voice": voice, "speed": speed, "duration_min": duration_min,
        "use_video": use_video, "started_at": started_at,
    }
    LV_JOB_FILE.write_text(json.dumps(job, ensure_ascii=False))

    worker_path = Path(__file__).parent / "lv_worker.py"
    proc = subprocess.Popen(
        [sys.executable, str(worker_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=open(Path(__file__).parent / "lv_worker.log", "a"),
        cwd=str(Path(__file__).parent),
    )
    _save_manual_lv_log("running", started_at=started_at)
    # PID'i log'a kaydet (canlı kontrol için)
    try:
        existing = json.loads(MANUAL_LV_LOG.read_text())
        existing["pid"] = proc.pid
        MANUAL_LV_LOG.write_text(json.dumps(existing, ensure_ascii=False))
    except Exception:
        pass

    return {"ok": True}


@app.post("/api/generate-long-video-from-script")
async def generate_long_video_from_script(
    script_file: UploadFile = File(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    use_video: str = Form("false"),
):
    content = await script_file.read()
    try:
        script_text = content.decode("utf-8")
    except UnicodeDecodeError:
        script_text = content.decode("latin-1", errors="replace")

    if not script_text.strip():
        raise HTTPException(400, "Dosya boş")
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    if MANUAL_LV_LOG.exists():
        try:
            existing = json.loads(MANUAL_LV_LOG.read_text())
            if existing.get("status") == "running":
                pid = existing.get("pid")
                if pid:
                    try:
                        os.kill(int(pid), 0)
                        raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")
                    except OSError:
                        pass
                else:
                    raise HTTPException(409, "Üretim devam ediyor, lütfen bekleyin")
        except HTTPException:
            raise
        except Exception:
            pass

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    lang_name = LANG_MAP.get(lang, "Turkish")

    parse_prompt = f"""Below is a script text in {lang_name}. Parse it into scenes for a YouTube video narration.

SCRIPT:
{script_text[:8000]}

Return ONLY valid JSON, no markdown:
{{
  "title": "engaging YouTube title based on the script (max 80 chars, in {lang_name})",
  "description": "detailed video description (3-4 sentences, in {lang_name})",
  "hashtags": ["relevant", "hashtag", "words", "no", "hash", "symbol"],
  "scenes": [
    {{
      "text": "narration text for this scene (copy exact words from script, 2-4 sentences per scene)",
      "keyword": "english search keyword for stock photo (2-3 words)"
    }}
  ]
}}

Rules:
- Split the script naturally into logical scenes of 2-4 sentences each
- Copy the script's narration text exactly — do NOT paraphrase or summarize
- Generate an appropriate English image search keyword for each scene
- hashtags: 8-12 relevant tags. No # symbol, NO spaces within a tag.
- NEVER use abbreviations in scene text; always write the full name for text-to-speech
- If the uploaded script contains numbers in English format (comma as thousands separator, e.g. "1,287"), convert them to Turkish format ("1.287") or spell them out — Turkish uses comma ONLY as the decimal separator, English-style thousands-commas break the TTS reading"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": parse_prompt}],
        temperature=0.3,
        max_tokens=8000,
    )
    data = _parse_llm_json(response.choices[0].message.content)
    if not data.get("scenes"):
        raise HTTPException(500, "Senaryo sahnelere ayrılamadı")

    started_at = time.time()
    job = {
        "topic": data.get("title", script_file.filename or "Senaryo"),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "hashtags": data.get("hashtags", []),
        "scenes": data["scenes"],
        "api_key": api_key,
        "lang": lang,
        "voice": voice,
        "speed": speed,
        "duration_min": max(3, len(data["scenes"]) // 2),
        "use_video": use_video,
        "started_at": started_at,
    }
    LV_JOB_FILE.write_text(json.dumps(job, ensure_ascii=False))

    worker_path = Path(__file__).parent / "lv_worker.py"
    proc = subprocess.Popen(
        [sys.executable, str(worker_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=open(Path(__file__).parent / "lv_worker.log", "a"),
        cwd=str(Path(__file__).parent),
    )
    _save_manual_lv_log("running", started_at=started_at)
    try:
        existing = json.loads(MANUAL_LV_LOG.read_text())
        existing["pid"] = proc.pid
        MANUAL_LV_LOG.write_text(json.dumps(existing, ensure_ascii=False))
    except Exception:
        pass

    return {"ok": True, "scenes": len(data["scenes"]), "title": data.get("title", "")}


@app.get("/api/manual-lv/status")
async def get_manual_lv_status():
    if not MANUAL_LV_LOG.exists():
        return {"status": "idle"}
    try:
        data = json.loads(MANUAL_LV_LOG.read_text())
    except Exception:
        return {"status": "idle"}
    # "running" ama process ölmüş veya zaman aşımı → error olarak göster
    if data.get("status") == "running":
        elapsed = int(time.time() - data.get("started_at", time.time()))
        if elapsed > 90 * 60:  # 90 dakika aşıldıysa
            data["status"] = "error"
            data["error"] = f"Zaman aşımı ({elapsed // 60} dakika). Sıfırlayıp tekrar deneyin."
        else:
            pid = data.get("pid")
            if pid:
                alive = False
                try:
                    os.kill(int(pid), 0)
                    alive = True
                except OSError:
                    alive = False
                if not alive:
                    data["status"] = "error"
                    data["error"] = "Worker process durdu (muhtemelen restart sonrası). Yeniden üretebilirsiniz."
    data["elapsed"] = int(time.time() - data.get("started_at", time.time()))
    return data


@app.post("/api/manual-lv/reset")
async def reset_manual_lv():
    """Takılı kalan üretimi sıfırla."""
    if MANUAL_LV_LOG.exists():
        try:
            data = json.loads(MANUAL_LV_LOG.read_text())
            pid = data.get("pid")
            if pid:
                try:
                    import signal
                    os.kill(int(pid), signal.SIGTERM)
                except OSError:
                    pass
        except Exception:
            pass
        MANUAL_LV_LOG.unlink(missing_ok=True)
    if LV_JOB_FILE.exists():
        LV_JOB_FILE.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/info-shorts-trend")
async def info_shorts_trend(
    category: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    info_format: str = Form("biliyormuydunuz"),
):
    """Bilgi Shorts için seçilen kategori ve formata uygun konu öner."""
    from openai import OpenAI
    from datetime import datetime
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")
    if not category.strip():
        raise HTTPException(400, "Kategori boş olamaz")
    lang_name = LANG_MAP.get(lang, "Turkish")
    today = datetime.now().strftime("%d.%m.%Y")
    format_labels = {
        "biliyormuydunuz": "Bunu biliyor muydunuz? (shocking fact)",
        "aklinizda": "Aklınızda bulunsun (practical tip)",
        "30saniye": "30 saniyede öğren (quick explainer)",
        "cogusinsan": "Çoğu insan bilmiyor (insider secret)",
    }
    fmt_label = format_labels.get(info_format, format_labels["biliyormuydunuz"])
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = f"""Today is {today}. You are helping create a YouTube Shorts informational video in {lang_name}.

Category: {category}
Format style: {fmt_label}

Suggest ONE compelling short video topic (45-60 seconds) that:
- Fits the format style perfectly
- Is surprising, useful, or counterintuitive — something that makes people say "I didn't know that!"
- Targets general audience aged 35-65
- Is specific (not "health tips" but "Why you should never drink coffee before 10am")

Return ONLY a JSON object, no markdown:
{{"topic": "the specific topic in {lang_name}", "hook": "one sentence that captures the hook in {lang_name}"}}"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=200,
        )
        data = _parse_llm_json(resp.choices[0].message.content)
        return {"topic": data.get("topic", ""), "hook": data.get("hook", "")}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/lv-category-trend")
async def lv_category_trend(
    category: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
):
    """Seçilen kategori için günün trend konusunu bul."""
    from openai import OpenAI
    from datetime import datetime
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")
    if not category.strip():
        raise HTTPException(400, "Kategori boş olamaz")
    lang_name = LANG_MAP.get(lang, "Turkish")
    today = datetime.now().strftime("%d.%m.%Y")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = f"""Today is {today}. You are helping create a YouTube documentary video in {lang_name}.

Category: {category}

Suggest ONE compelling documentary topic in this category that:
- Is currently relevant or timeless/fascinating
- Works great as a 5-10 minute educational documentary
- Has a curiosity-gap angle (e.g. "How did X really happen?", "The secret behind Y", "Why Z changed everything")
- Is specific, not generic

Return ONLY a JSON object, no markdown:
{{"topic": "the specific topic in {lang_name}", "hook": "one sentence curiosity-gap description in {lang_name}"}}"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=200,
        )
        data = _parse_llm_json(resp.choices[0].message.content)
        return {"topic": data.get("topic", ""), "hook": data.get("hook", "")}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/generate-trend-long-video")
async def generate_trend_long_video(
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    region: str = Form("TR"),
):
    from openai import OpenAI
    from datetime import datetime

    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    pexels_key = get_pexels_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    lang_name = LANG_MAP.get(lang, "Turkish")

    trend_data = get_trends(region_code=region, lang=lang)
    trend_pool = trend_data["topics"]
    if lang == "tr":
        trend_pool = _filter_low_value_topics(trend_pool) or trend_pool
    topics_list = trend_pool[:6]
    topics_str = "\n".join(f"- {t}" for t in topics_list)
    yt_tags_lv = ", ".join(trend_data.get("yt_trending_tags", [])[:12])
    today = datetime.now().strftime("%d.%m.%Y")

    prompt = f"""Create a news roundup YouTube video covering today's trending topics in {lang_name}.
Date: {today}

Trending topics:
{topics_str}

YouTube TR trending hashtags RIGHT NOW (use relevant ones in your hashtags list): {yt_tags_lv}

Create a news digest with one segment per topic. Each segment has 2 scenes.

Return ONLY valid JSON, no markdown:
{{
  "title": "news roundup title in {lang_name} (mention date or 'günün haberleri', max 80 chars)",
  "description": "video description mentioning all topics (3-4 sentences, in {lang_name})",
  "hashtags": ["relevant", "tags", "for", "news", "no", "hash", "symbol"],
  "segments": [
    {{
      "topic": "short topic title (in {lang_name})",
      "scenes": [
        {{"text": "opening sentence for this news story (1-2 sentences with key facts)", "keyword": "english keyword for photo (2-3 words)"}},
        {{"text": "follow-up with more detail (1-2 sentences)", "keyword": "english keyword for photo (2-3 words)"}}
      ]
    }}
  ]
}}

Rules:
- One segment per trending topic ({len(topics_list)} segments total, {len(topics_list)*2} scenes)
- In scene text: NEVER use abbreviations (e.g. YKS, ÖSYM, TBMM, ABD, AKP, CHP). Always write the full name so text-to-speech reads correctly.
- Turkish number format ONLY: comma (,) is the decimal separator, dot (.) is the thousands separator — NEVER write numbers in English format (e.g. "1,287" meaning one thousand two hundred eighty-seven). Write "1.287" or spell it out "bin iki yüz seksen yedi" instead — English-style thousands-commas break the TTS reading.
- NEVER use phrases that imply real footage or real photos exist (e.g. "İşte görüntüler", "İşte o anlar", "kameralar görüntüledi", "işte o fotoğraflar", "görüntüler ortaya çıktı", "here is the footage"). Visuals are illustrative stock photos — narration must describe events in storytelling form, never reference visuals.
- VERY FIRST scene MUST use a CURIOSITY-GAP hook — never state the answer directly. Withhold the key fact, create suspense or partial reveal. Examples: "Kimse beklemiyordu:", "Meğer...", "Az önce ortaya çıktı:", "Peki gerçekte ne oldu?", "Cevap herkesi şoke etti.", "Tarihin en büyük...". The viewer MUST feel compelled to keep watching. Critical for retention — never open with a plain news headline.
- VERY LAST scene MUST end with (translated naturally to {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!" — urgent and personal, not generic.
- Each segment: exactly 2 scenes, informative and engaging
- hashtags: 10-15 tags mixing {lang_name} and English, ALWAYS include "Shorts", "sondakika", "gündem", "keşfet", "haberler", "güncel" — then add topic-specific tags. No # symbol, NO spaces within a tag (e.g. "sondakika" not "son dakika")
- keyword: English, 2-3 words, visual and specific"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4000,
    )

    data = _parse_llm_json(response.choices[0].message.content)
    scenes = []
    for seg in data.get("segments", []):
        for sc in seg.get("scenes", []):
            scenes.append(sc)

    if not scenes:
        raise HTTPException(500, "Video sahneleri üretilemedi")

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    audio_files = []
    clip_files = []
    durations = []

    for i, scene in enumerate(scenes):
        wav, dur = await asyncio.to_thread(tts.synthesize,
            _clean_tts_text(scene["text"], lang), lang=lang,
            voice_style=style, total_steps=8, speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        img_path = scene_dir / f"scene_{i}.jpg"
        kw = scene.get("keyword", "breaking news")
        photo_saved = fetch_scene_visual(kw, "landscape", pexels_key, img_path)

        if not photo_saved:
            await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "color=black:size=1920x1080:rate=1",
                 "-frames:v", "1", str(img_path)],
                capture_output=True, timeout=90,
            )

        clip_path = scene_dir / f"clip_{i}.mp4"
        words = scene["text"].split()
        lines, line = [], []
        for w in words:
            if len(" ".join(line + [w])) > 70:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        text_file = scene_dir / f"text_{i}.txt"
        text_file.write_text("\n".join(lines), encoding="utf-8")

        drawtext = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"drawtext=textfile={text_file.absolute()}"
            f":fontsize=36:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-80:line_spacing=10"
            f":box=1:boxcolor=black@0.6:boxborderw=16"
        )
        if font_path:
            drawtext += f":fontfile={font_path}"

        await asyncio.to_thread(subprocess.run,
            ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
             "-t", str(dur_val),
             "-vf", drawtext,
             "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", str(clip_path)],
            check=True, capture_output=True, timeout=180,
        )
        clip_files.append(clip_path)

    audio_list = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True, timeout=180,
    )

    clip_list = scene_dir / "clip_list.txt"
    merged = scene_dir / "merged.mp4"
    with open(clip_list, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(merged)],
        check=True, capture_output=True, timeout=180,
    )

    output_file = OUTPUT_DIR / f"{uid}_tnlv.mp4"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", str(output_file)],
        check=True, capture_output=True, timeout=120,
    )

    full_script = " ".join(s["text"] for s in scenes)
    total_dur = round(sum(durations), 1)
    tnlv_title = data.get("title", f"Günün Trend Haberleri - {today}")

    raw_tags = data.get("hashtags", [])
    suggested_tags = _format_hashtags(raw_tags, limit=5)
    if not suggested_tags:
        suggested_tags = _format_hashtags(["gündem", "haberler", "trendler", "güncel", "viral"], limit=5)

    thumb_path = None
    thumb_out = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), tnlv_title, thumb_out, size=(1280, 720), lang=lang, news_style=False)
            thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

    shutil.rmtree(scene_dir, ignore_errors=True)

    return {
        "video": f"/api/video/{output_file.name}",
        "thumbnail": thumb_path,
        "title": tnlv_title,
        "description": data.get("description", ""),
        "suggested_tags": suggested_tags,
        "script": full_script,
        "duration_sec": total_dur,
        "scene_count": len(scenes),
        "topics": topics_list,
    }


CONFIG_FILE = Path("yt_config.json")
TOKEN_FILE = Path("yt_token.json")
TOKEN_FILE_EN = Path("yt_token_en.json")
PEXELS_CONFIG = Path("pexels_config.json")
DS_CONFIG = Path("deepseek_config.json")
OPENAI_CONFIG = Path("openai_config.json")
IG_CONFIG = Path("ig_config.json")
IG_LOG = Path("ig_log.json")
IG_RECENT_FILE = Path("ig_recent_posts.json")  # duplicate prevention
IG_PENDING_FILE = Path("ig_pending.json")       # doğrulama bekleyen postlar
IG_FAILED_FILE = Path("ig_failed_uploads.json") # başarısız yüklemeler kuyruğu

TELEGRAM_CONFIG = Path("telegram_config.json")


def get_telegram_config() -> dict:
    if TELEGRAM_CONFIG.exists():
        try:
            return json.loads(TELEGRAM_CONFIG.read_text())
        except Exception:
            pass
    return {}


async def send_telegram_alert(source: str, message: str) -> None:
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        return
    import datetime, html as _html
    ts = datetime.datetime.now().strftime("%d %B %Y %H:%M")
    text = (
        f"🚨 <b>Supertonic Hata</b>\n─────────────────\n"
        f"📌 Kaynak: {_html.escape(source)}\n"
        f"❌ {_html.escape(str(message))}\n"
        f"🕐 {ts}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
    except Exception:
        pass


def _fire_telegram(source: str, message: str) -> None:
    """Sync context'ten Telegram alert gönder (event loop'a task ekler)."""
    try:
        loop = asyncio.get_running_loop()  # Python 3.10+ uyumlu
        loop.create_task(send_telegram_alert(source, message))
    except RuntimeError:
        pass  # event loop çalışmıyor
    except Exception:
        pass


async def send_telegram_plain(text: str) -> bool:
    """Ham metin gönder (uyarı formatı olmadan) — konu seçim listesi/onay mesajları için."""
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            return r.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM] send_telegram_plain hata: {e}", flush=True)
        return False


async def _telegram_mark_offset_to_latest() -> int:
    """Şu ana kadarki tüm mesajları 'okunmuş' işaretler (offset'i son update_id+1'e çeker).
    Liste gönderilmeden ÖNCE çağrılır ki eski/bekleyen mesajlar cevap sanılmasın."""
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    if not token:
        return 0
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"timeout": 0})
            if r.status_code != 200:
                return 0
            results = r.json().get("result", [])
            if not results:
                return 0
            max_id = max(u["update_id"] for u in results)
            # offset'i ilerletmek için bir kez daha çağır (Telegram offset=X → X'e kadarki mesajları siler)
            await client.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": max_id + 1, "timeout": 0})
            return max_id + 1
    except Exception as e:
        print(f"[TELEGRAM] offset temizleme hatası: {e}", flush=True)
        return 0


_TELEGRAM_CANCEL_KELIMELERI = {"cancel", "c", "iptal", "i", "no", "hayır", "hayir"}


async def wait_for_telegram_numeric_reply(offset: int, max_choice: int, timeout_sec: int = 300, poll_sec: int = 8) -> int | str | None:
    """offset'ten itibaren gelen mesajlarda 1..max_choice aralığında bir sayı arar.
    Bulursa sayıyı, 'cancel'/'c'/'iptal'/'i' yazılırsa 'CANCEL' sabitini,
    timeout dolarsa None döner."""
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    expected_chat_id = cfg.get("chat_id", "").strip()
    if not token:
        return None
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=poll_sec + 5) as client:
                remaining = max(1, int(deadline - time.time()))
                r = await client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": min(poll_sec, remaining)},
                )
            if r.status_code == 200:
                results = r.json().get("result", [])
                for u in results:
                    offset = max(offset, u["update_id"] + 1)
                    msg = u.get("message") or {}
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = (msg.get("text") or "").strip()
                    if expected_chat_id and chat_id != expected_chat_id:
                        continue
                    if text.lower() in _TELEGRAM_CANCEL_KELIMELERI:
                        return "CANCEL"
                    if text.isdigit():
                        n = int(text)
                        if 1 <= n <= max_choice:
                            return n
        except Exception as e:
            print(f"[TELEGRAM] cevap bekleme hatası: {e}", flush=True)
            await asyncio.sleep(poll_sec)
    return None


async def send_telegram_video(video_path: Path, title: str, description: str, tags: str) -> None:
    """Üretilen videoyu Telegram'a gönder."""
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        print("[TELEGRAM] Bot token veya chat_id eksik — gönderim atlandı", flush=True)
        return
    if not video_path.exists():
        print(f"[TELEGRAM] Video dosyası bulunamadı: {video_path}", flush=True)
        return
    import html as _html
    # Description'dan hashtag satırlarını temizle (sadece metin kalsın)
    clean_desc = ""
    if description:
        lines = [ln for ln in description.splitlines() if not ln.strip().startswith("#")]
        clean_desc = " ".join(lines).strip()[:400]

    # Tagleri parse et: virgül/boşluk ayır, YouTube olanlari at, Instagram ekle
    yt_remove = {"shorts", "youtubeshorts", "youtube", "ytshorts", "youtubevideos", "youtubetr", "yttr"}
    ig_base   = ["#reels", "#keşfet", "#instareels"]
    filtered  = []
    for t in tags.replace(",", " ").split():
        clean = t.lstrip("#").lower().strip()
        if clean and clean not in yt_remove:
            filtered.append(f"#{clean}" if not t.startswith("#") else f"#{t.lstrip('#')}")
    for ig in ig_base:
        if ig not in filtered:
            filtered.append(ig)
    ig_tags_str = " ".join(filtered[:30])  # Instagram max 30 hashtag

    caption_parts = []
    if title:
        caption_parts.append(f"<b>{_html.escape(title)}</b>")
    if clean_desc:
        caption_parts.append(_html.escape(clean_desc))
    if ig_tags_str:
        caption_parts.append(_html.escape(ig_tags_str))
    caption = "\n\n".join(caption_parts)[:1024]
    try:
        print(f"[TELEGRAM] Gönderiliyor: {video_path.name} ({video_path.stat().st_size // 1024}KB)", flush=True)
        async with httpx.AsyncClient(timeout=300) as client:
            with open(video_path, "rb") as vf:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": "true"},
                    files={"video": (video_path.name, vf, "video/mp4")},
                )
        if resp.status_code == 200:
            print("[TELEGRAM] Gönderim başarılı", flush=True)
        else:
            print(f"[TELEGRAM] Hata {resp.status_code}: {resp.text[:300]}", flush=True)
    except Exception as e:
        print(f"[TELEGRAM] Exception: {e}", flush=True)


_generation_lock = None


def _get_gen_lock() -> asyncio.Lock:
    """Tüm video üretim job'ları için ortak sıra kilidi."""
    global _generation_lock
    if _generation_lock is None:
        _generation_lock = asyncio.Lock()
    return _generation_lock


SCHED_CONFIG = Path("scheduler_config.json")
SCHED_LOG = Path("scheduler_log.json")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def get_pexels_key():
    if PEXELS_CONFIG.exists():
        return json.loads(PEXELS_CONFIG.read_text()).get("api_key", "")
    return ""


def get_openai_key():
    if OPENAI_CONFIG.exists():
        return json.loads(OPENAI_CONFIG.read_text()).get("api_key", "")
    return ""


def get_ig_config() -> dict:
    if IG_CONFIG.exists():
        return json.loads(IG_CONFIG.read_text())
    return {}


_IG_DEDUP_HOURS = 24  # aynı başlık bu süreden önce atıldıysa tekrar atma — haberler günlük/saatlik yenilendiği için 1 gün yeterli

_TR_STOP_WORDS = {
    # Bağlaçlar / edatlar
    "ile", "bir", "bu", "şu", "ne", "ki", "son", "için", "gibi",
    "kadar", "daha", "çok", "var", "yok", "ama", "veya", "ayrı",
    "aynı", "oldu", "olan", "eden", "etti", "etdi", "konusu",
    "haberi", "haber", "dakika", "acil", "işte", "birer", "fakat",
    "vurdu", "geldi", "çıktı", "atıldı", "yapıldı", "alındı",
    # Çok genel ülke / şehir / kurum adları — tek başına ayırt edici değil
    "nato", "ankara", "istanbul", "türkiye", "türk", "türkiye",
    "trump", "erdoğan", "biden", "rusya", "ruslar", "ukrayna",
    "israil", "filistin", "iran", "irak", "suriye", "mısır",
    "avrupa", "amerika", "almanya", "fransa", "ingiltere",
    "tbmm", "meclis", "hükümet", "cumhurbaskani", "basbakan",
    "zirvesi", "toplantı", "zirve", "açıklama", "açıkladı",
    "bakanlığı", "bakanlık", "başkanlık", "basın",
}


def _extract_topic_keywords(title: str) -> set:
    """Başlıktan olay/kişi/kurum gibi anlamlı kelimeleri çıkarır (≥4 harf)."""
    cleaned = re.sub(r"[^a-züğışöçA-ZÜĞİŞÖÇ\s]", " ", title.lower())
    return {w for w in cleaned.split() if len(w) >= 4 and w not in _TR_STOP_WORDS}


def _ig_recently_posted(title: str) -> bool:
    """Aynı başlık son _IG_DEDUP_HOURS saat içinde Instagram'a atıldıysa True döner."""
    if not IG_RECENT_FILE.exists():
        return False
    try:
        records = json.loads(IG_RECENT_FILE.read_text())
        cutoff = time.time() - _IG_DEDUP_HOURS * 3600
        title_lower = title.strip().lower()[:80]
        return any(
            r.get("title", "").lower()[:80] == title_lower and r.get("ts", 0) > cutoff
            for r in records
        )
    except Exception:
        return False


def _ig_same_topic_posted(title: str) -> bool:
    """Aynı konuyu (3+ ortak özgün anahtar kelime) 8 saat içinde attıysa True döner."""
    if not IG_RECENT_FILE.exists():
        return False
    try:
        records = json.loads(IG_RECENT_FILE.read_text())
        cutoff = time.time() - 8 * 3600  # 12h → 8h: günde 12 slotluk yoğun programda havuz erken tükeniyordu
        new_kw = _extract_topic_keywords(title)
        if len(new_kw) < 2:
            return False
        for r in records:
            if r.get("ts", 0) <= cutoff:
                continue
            past_kw = _extract_topic_keywords(r.get("title", ""))
            common = new_kw & past_kw
            if len(common) >= 3:  # 2 → 3: genel kelime çakışmalarını engelle
                print(f"[DEDUP-TOPIC] ENGELLENDI '{title[:60]}' ← çakışan: '{r.get('title','')[:60]}' | ortak: {common}", flush=True)
                return True
        return False
    except Exception:
        return False


def _ig_mark_posted(title: str) -> None:
    """Başlığı IG son-gönderi listesine ekle, 30 günden eski kayıtları temizle."""
    try:
        records = json.loads(IG_RECENT_FILE.read_text()) if IG_RECENT_FILE.exists() else []
        cutoff = time.time() - 30 * 24 * 3600
        records = [r for r in records if r.get("ts", 0) > cutoff]
        records.append({"ts": time.time(), "title": title.strip()[:120]})
        IG_RECENT_FILE.write_text(json.dumps(records))
    except Exception:
        pass


def _ig_mark_pending(title: str) -> None:
    """Başlığı 'doğrulama bekliyor' listesine ekle (2 saatlik geçerlilik)."""
    try:
        records = json.loads(IG_PENDING_FILE.read_text()) if IG_PENDING_FILE.exists() else []
        cutoff = time.time() - 2 * 3600
        records = [r for r in records if r.get("ts", 0) > cutoff]
        title_lower = title.strip().lower()[:80]
        if not any(r.get("title", "").lower()[:80] == title_lower for r in records):
            records.append({"ts": time.time(), "title": title.strip()[:120]})
        IG_PENDING_FILE.write_text(json.dumps(records))
    except Exception:
        pass


def _ig_remove_pending(title: str) -> None:
    """Başlığı pending listesinden çıkar."""
    try:
        if not IG_PENDING_FILE.exists():
            return
        records = json.loads(IG_PENDING_FILE.read_text())
        title_lower = title.strip().lower()[:80]
        records = [r for r in records if r.get("title", "").lower()[:80] != title_lower]
        IG_PENDING_FILE.write_text(json.dumps(records))
    except Exception:
        pass


def _ig_is_pending(title: str) -> bool:
    """Başlık hâlâ doğrulama bekliyorsa True döner."""
    try:
        if not IG_PENDING_FILE.exists():
            return False
        records = json.loads(IG_PENDING_FILE.read_text())
        cutoff = time.time() - 2 * 3600
        title_lower = title.strip().lower()[:80]
        return any(r.get("title", "").lower()[:80] == title_lower and r.get("ts", 0) > cutoff for r in records)
    except Exception:
        return False


def _load_failed_ig_uploads() -> list:
    if IG_FAILED_FILE.exists():
        try:
            return json.loads(IG_FAILED_FILE.read_text())
        except Exception:
            pass
    return []


def _save_failed_ig_upload(filename: str, title: str, caption: str, error: str = "") -> None:
    items = _load_failed_ig_uploads()
    items = [x for x in items if x.get("filename") != filename]  # duplicate önle
    items.append({"filename": filename, "title": title, "caption": caption, "error": error, "ts": time.time()})
    IG_FAILED_FILE.write_text(json.dumps(items, ensure_ascii=False))


def _remove_failed_ig_upload(filename: str) -> None:
    items = [x for x in _load_failed_ig_uploads() if x.get("filename") != filename]
    IG_FAILED_FILE.write_text(json.dumps(items, ensure_ascii=False))


def _is_non_retriable_meta_error(text: str) -> bool:
    """Meta'nın kendisi 'retriable': false dediği hatalar (örn. RequestRateLimitedError) —
    bunlar geçici sunucu sorunu değil, hesap/uygulama seviyesinde bir API çağrı limiti.
    Tekrar denemek sadece zaman kaybı, limit süresi dolmadan aynı sonucu verir."""
    return '"retriable":false' in text or '"retriable": false' in text


async def post_reel_to_instagram(video_path: Path, caption: str, ig_user_id: str, access_token: str) -> tuple[str | None, str]:
    """Instagram Reels yükle (resumable upload — HTTPS gerekmez). (media_id, error) döner."""
    graph = "https://graph.facebook.com/v21.0"
    try:
        video_bytes = video_path.read_bytes()
        video_size = len(video_bytes)

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Resumable upload session başlat
            r1 = await client.post(
                f"{graph}/{ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": access_token,
                },
            )
            if r1.status_code != 200:
                return None, f"session create failed: {r1.status_code} {r1.text[:300]}"
            j1 = r1.json()
            media_id = j1.get("id")
            upload_uri = j1.get("uri")
            if not media_id or not upload_uri:
                return None, f"no id/uri: {r1.text[:300]}"

            # Instagram container'ın hazır olması için bekle
            await asyncio.sleep(12)

            # 2. Video bytes'ı yükle — 4 deneme, artan bekleme
            r2 = None
            upload_ok = False
            for attempt in range(4):
                r2 = await client.post(
                    upload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(video_size),
                        "Content-Type": "video/mp4",
                    },
                    content=video_bytes,
                    timeout=180,
                )
                if r2.status_code in (200, 201):
                    upload_ok = True
                    break
                # "not in the status to upload" → ilk deneme aslında geçmiş olabilir,
                # container PROCESSING/FINISHED state'e girmiştir — retry yerine status kontrol et
                if r2.status_code == 400 and "not in the status" in r2.text:
                    try:
                        chk = await client.get(
                            f"{graph}/{media_id}",
                            params={"fields": "status_code", "access_token": access_token},
                            timeout=15,
                        )
                        if chk.status_code == 200 and chk.json().get("status_code") in ("FINISHED", "IN_PROGRESS"):
                            upload_ok = True
                            break
                    except Exception:
                        pass
                # Rate limit gibi "retriable: false" hatalarda 4 kez boşuna denemenin
                # anlamı yok — Meta'nın kendisi tekrar denemenin işe yaramayacağını söylüyor.
                if _is_non_retriable_meta_error(r2.text):
                    return None, f"upload failed (non-retriable, muhtemelen rate limit): {r2.status_code} {r2.text[:300]}"
                if attempt < 3:
                    await asyncio.sleep(15 * (attempt + 1))  # 15s, 30s, 45s
            if not upload_ok:
                return None, f"upload failed: {r2.status_code} {r2.text[:300]}"

            # 3. İşlenme tamamlanana kadar bekle (maks ~5 dakika) — artan aralıklarla
            # sorgula (10s'den başlayıp 20s'ye çıkar): sabit 10s×30 yerine ~16-17 çağrıya
            # düşürüyor, günde 12 slotluk yoğun programda Meta API çağrı hacmini azaltır.
            elapsed = 0
            poll_interval = 10
            while elapsed < 300:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                r3 = await client.get(
                    f"{graph}/{media_id}",
                    params={"fields": "status_code,status", "access_token": access_token},
                    timeout=15,
                )
                if r3.status_code == 200:
                    st = r3.json()
                    code = st.get("status_code", "")
                    if code == "FINISHED":
                        break
                    if code == "ERROR":
                        return None, f"processing error: {st.get('status', '')}"
                poll_interval = min(poll_interval + 2, 20)

            # 4. Yayınla — Meta'nın geçici (is_transient) sunucu hatalarına karşı birkaç kez dene
            r4 = None
            for pub_attempt in range(3):
                r4 = await client.post(
                    f"{graph}/{ig_user_id}/media_publish",
                    params={"creation_id": media_id, "access_token": access_token},
                    timeout=30,
                )
                if r4.status_code == 200:
                    pub_id = r4.json().get("id")
                    if pub_id:
                        return pub_id, ""
                    return None, f"publish 200 but no id in response: {r4.text[:200]}"
                if _is_non_retriable_meta_error(r4.text):
                    return None, f"publish failed (non-retriable, muhtemelen rate limit): {r4.status_code} {r4.text[:200]}"
                is_transient = r4.status_code >= 500 or '"is_transient":true' in r4.text
                if is_transient and pub_attempt < 2:
                    await asyncio.sleep(10 * (pub_attempt + 1))  # 10s, 20s
                    continue
                break
            return None, f"publish failed: {r4.status_code} {r4.text[:200]}"
    except Exception as e:
        return None, str(e)


async def post_story_to_instagram(video_path: Path, ig_user_id: str, access_token: str) -> tuple[bool, str]:
    """Instagram Story olarak video yayınla (resumable upload)."""
    graph = "https://graph.facebook.com/v21.0"
    try:
        video_bytes = video_path.read_bytes()
        video_size = len(video_bytes)

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Resumable session (REELS + is_stories=true — VIDEO deprecated)
            r1 = await client.post(
                f"{graph}/{ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "is_stories": "true",
                    "access_token": access_token,
                },
            )
            if r1.status_code != 200:
                return False, f"session create failed: {r1.status_code} {r1.text[:300]}"
            j1 = r1.json()
            media_id = j1.get("id")
            upload_uri = j1.get("uri")
            if not media_id or not upload_uri:
                return False, f"no uri: {r1.text[:300]}"

            # Instagram container'ın hazır olması için bekle
            await asyncio.sleep(3)

            # 2. Video bytes yükle — 3 deneme
            r2 = None
            for attempt in range(3):
                r2 = await client.post(
                    upload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(video_size),
                        "Content-Type": "video/mp4",
                    },
                    content=video_bytes,
                    timeout=180,
                )
                if r2.status_code in (200, 201):
                    break
                if attempt < 2:
                    await asyncio.sleep(8)
            if r2 is None or r2.status_code not in (200, 201):
                return False, f"upload failed: {r2.status_code} {r2.text[:200]}"

            # 3. İşlenme bekle
            for _ in range(18):
                await asyncio.sleep(10)
                r3 = await client.get(
                    f"{graph}/{media_id}",
                    params={"fields": "status_code", "access_token": access_token},
                    timeout=15,
                )
                if r3.status_code == 200:
                    code = r3.json().get("status_code", "")
                    if code == "FINISHED":
                        break
                    if code == "ERROR":
                        return False, f"processing error"

            # 4. Yayınla
            r4 = await client.post(
                f"{graph}/{ig_user_id}/media_publish",
                params={"creation_id": media_id, "access_token": access_token},
                timeout=30,
            )
            if r4.status_code == 200:
                return True, ""
            return False, f"publish failed: {r4.status_code} {r4.text[:200]}"
    except Exception as e:
        return False, str(e)


async def _verify_reel_published(reel_id: str, title: str, video_path: str, caption: str, ig_cfg: dict, source: str, attempt: int = 1, description: str = "", thumbnail: str = ""):
    """Post'tan 5 dk sonra Instagram API ile reel'i doğrular. Bulunamazsa yeniden dener (maks 3)."""
    await asyncio.sleep(300)  # 5 dakika bekle

    graph = "https://graph.facebook.com/v21.0"
    ig_token = ig_cfg["access_token"]
    ig_user_id = ig_cfg["ig_user_id"]
    confirmed = False
    post_ts = time.time() - 300  # post yaklaşık 5 dk önce yapıldı

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Yöntem 1: reel_id ile doğrudan kontrol
            r1 = await client.get(
                f"{graph}/{reel_id}",
                params={"fields": "id,timestamp", "access_token": ig_token},
            )
            if r1.status_code == 200 and "id" in r1.json():
                confirmed = True

            # Yöntem 2: reel_id bulunamazsa son medya listesine bak
            if not confirmed:
                r2 = await client.get(
                    f"{graph}/{ig_user_id}/media",
                    params={"fields": "id,timestamp", "limit": 5, "access_token": ig_token},
                )
                if r2.status_code == 200:
                    for m in r2.json().get("data", []):
                        ts_str = m.get("timestamp", "")
                        if ts_str:
                            try:
                                import calendar
                                t = calendar.timegm(time.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S"))
                                if t >= post_ts - 60:  # post zamanından sonra yayınlanmış
                                    confirmed = True
                                    break
                            except Exception:
                                pass
    except Exception:
        pass

    if confirmed:
        _ig_mark_posted(title)
        _ig_remove_pending(title)
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[DOĞRULANDI:{source}] {title[:60]}"}))
        try:
            permalink = ""
            async with httpx.AsyncClient(timeout=15) as client:
                rp = await client.get(
                    f"{graph}/{reel_id}",
                    params={"fields": "permalink", "access_token": ig_token},
                )
                if rp.status_code == 200:
                    permalink = rp.json().get("permalink", "")
            news_site.add_article(title=title, description=description, thumbnail=thumbnail, ig_permalink=permalink)
        except Exception:
            pass
        return

    # Her iki yöntem de bulamadı — gerçekten yüklenmemiş
    if attempt < 3:
        vpath = Path(video_path)
        if vpath.exists():
            reel_id2, reel_err = await post_reel_to_instagram(vpath, caption, ig_user_id, ig_token)
            if reel_id2:
                IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[YENİDEN:{source}] Deneme {attempt + 1}: {title[:60]}"}))
                asyncio.create_task(_verify_reel_published(reel_id2, title, video_path, caption, ig_cfg, source, attempt + 1, description, thumbnail))
            else:
                err_msg = reel_err or "Bilinmeyen hata (boş yanıt)"
                await send_telegram_alert(f"IG Yeniden Deneme [{source}]", f"Deneme {attempt + 1} başarısız: {err_msg}\n{title[:60]}")
                if attempt + 1 >= 3:
                    _ig_remove_pending(title)
        else:
            await send_telegram_alert(f"IG Doğrulama [{source}]", f"Video dosyası bulunamadı:\n{title[:60]}")
            _ig_remove_pending(title)
    else:
        await send_telegram_alert(f"IG Kalıcı Hata [{source}]", f"3 denemede Instagram'a yüklenemedi:\n{title[:60]}")
        _ig_remove_pending(title)


def _fetch_wikimedia_image(keyword: str, width: int = 1920) -> bytes | None:
    """Wikimedia Commons'dan CC lisanslı görsel çeker."""
    try:
        r = httpx.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": keyword,
                "gsrnamespace": "6",
                "gsrlimit": "5",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": str(width),
                "format": "json",
            },
            timeout=10,
            headers={"User-Agent": "SupertonicBot/1.0"},
        )
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            mime = info.get("mime", "")
            if not mime.startswith("image/"):
                continue
            url = info.get("thumburl") or info.get("url", "")
            if url:
                return httpx.get(url, timeout=15).content
    except Exception:
        pass
    return None


def _generate_dalle_image(keyword: str, orientation: str, openai_key: str) -> bytes | None:
    """gpt-image-1-mini ile sahne görseli üretir."""
    import base64
    try:
        from openai import OpenAI as _OAI
        client = _OAI(api_key=openai_key)
        size = "1024x1536" if orientation == "portrait" else "1536x1024"
        resp = client.images.generate(
            model="gpt-image-1-mini",
            prompt=(
                f"Professional high-quality documentary-style photo of {keyword}, "
                "realistic, cinematic lighting, no text, no watermarks, no logos"
            ),
            size=size,
            n=1,
        )
        b64 = resp.data[0].b64_json
        if b64:
            return base64.b64decode(b64)
        # Fallback: url varsa indir
        url = getattr(resp.data[0], "url", None)
        if url:
            return httpx.get(url, timeout=30).content
    except Exception:
        pass
    return None


def _save_as_jpeg(data: bytes, img_path: Path) -> bool:
    """Herhangi bir görsel formatını (SVG hariç) JPEG olarak kaydeder."""
    from PIL import Image
    import io
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.save(str(img_path), "JPEG", quality=92)
        return True
    except Exception:
        return False


async def _try_ken_burns_clip(
    img_path: Path, dur: float, clip_path: Path,
    text_file=None, font_path: str = None,
) -> bool:
    """Ken Burns zoom efektiyle klip oluşturmayı dene. Başarısız olursa False döner."""
    frames = max(1, int(dur * 30))
    zoom_expr = f"'min(1+0.12*on/{frames},1.12)'"
    zoompan = (
        f"scale=1296:2304:force_original_aspect_ratio=increase,"
        f"crop=1296:2304,"
        f"zoompan=z={zoom_expr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s=1080x1920:fps=30"
    )
    if text_file and Path(text_file).exists():
        dt = (
            f"drawtext=textfile={Path(text_file).absolute()}"
            f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
            f":box=1:boxcolor=black@0.55:boxborderw=18"
        )
        if font_path:
            dt += f":fontfile={font_path}"
        vf = zoompan + "," + dt
    else:
        vf = zoompan
    try:
        result = await asyncio.to_thread(subprocess.run,
            ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
             "-t", str(dur), "-vf", vf,
             "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-pix_fmt", "yuv420p", str(clip_path)],
            capture_output=True, timeout=90,
        )
        return result.returncode == 0 and clip_path.exists() and clip_path.stat().st_size > 0
    except Exception:
        return False


def fetch_scene_visual(keyword: str, orientation: str, pexels_key: str, img_path: Path) -> tuple[bool, str]:
    """
    Görsel hiyerarşisi: DALL-E → Pexels → Wikimedia Commons (son çare).
    Wikimedia bir ansiklopedi görsel deposu — soyut anahtar kelimeler için harita/logo/
    diyagram gibi boşluklu, alakasız sonuçlar dönebiliyor. Pexels gerçek stok fotoğraf
    kaynağı olduğu için önceliklendirildi.
    (başarı: True,"") | (başarısız: False, "hata nedeni")
    """
    import sys
    size_key = "portrait" if orientation == "portrait" else "large2x"

    openai_key = get_openai_key()
    if openai_key:
        data = _generate_dalle_image(keyword, orientation, openai_key)
        if data and _save_as_jpeg(data, img_path):
            return True, ""

    pexels_err = ""
    if pexels_key:
        try:
            resp = httpx.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "orientation": orientation, "per_page": 3},
                headers={"Authorization": pexels_key},
                timeout=10,
            )
            if resp.status_code == 401:
                print(f"[GÖRSEL] Pexels key geçersiz (401): '{keyword}'", file=sys.stderr)
                _fire_telegram("Pexels", "API key geçersiz (401) — yeni key gerekiyor")
                pexels_err = "Pexels 401 key geçersiz"
            elif resp.status_code == 429:
                print(f"[GÖRSEL] Pexels kota doldu (429): '{keyword}'", file=sys.stderr)
                _fire_telegram("Pexels", "Aylık kota doldu (429) — limit: 20.000 istek/ay")
                pexels_err = "Pexels 429 kota doldu"
            else:
                photos = resp.json().get("photos", [])
                if photos:
                    img_url = photos[0]["src"].get(size_key) or photos[0]["src"]["large"]
                    data = httpx.get(img_url, timeout=15).content
                    if _save_as_jpeg(data, img_path):
                        return True, ""
                else:
                    print(f"[GÖRSEL] Pexels sonuç yok: '{keyword}'", file=sys.stderr)
                    pexels_err = "Pexels sonuç yok"
        except Exception as e:
            print(f"[GÖRSEL] Pexels hata: '{keyword}' {e}", file=sys.stderr)
            pexels_err = f"Pexels hata: {e}"
    else:
        pexels_err = "Pexels key yok"

    width = 1080 if orientation == "portrait" else 1920
    data = _fetch_wikimedia_image(keyword, width=width)
    if data and _save_as_jpeg(data, img_path):
        return True, ""

    print(f"[GÖRSEL] Tüm kaynaklar başarısız — siyah kare: '{keyword}' ({pexels_err})", file=sys.stderr)
    return False, f"tüm kaynaklar başarısız ({pexels_err})"


def fetch_pexels_video(keyword: str, pexels_key: str, raw_path: Path, min_duration: float) -> tuple[bool, str]:
    """Pexels'tan portrait video klip indir. (True, raw_path_str) | (False, hata)"""
    if not pexels_key:
        return False, "Pexels key yok"
    try:
        resp = httpx.get(
            "https://api.pexels.com/videos/search",
            params={"query": keyword, "orientation": "portrait", "per_page": 5, "size": "medium"},
            headers={"Authorization": pexels_key},
            timeout=15,
        )
        if resp.status_code != 200:
            return False, f"Pexels video HTTP {resp.status_code}"
        videos = resp.json().get("videos", [])
        if not videos:
            return False, "Pexels video sonuç yok"

        # Yeterince uzun video tercih et
        suitable = [v for v in videos if v.get("duration", 0) >= max(min_duration - 1, 2)]
        video = (suitable or videos)[0]

        # Portrait (h > w) dosyayı tercih et, yoksa en yüksek çözünürlüklü
        vfiles = video.get("video_files", [])
        portrait = [f for f in vfiles if f.get("height", 0) > f.get("width", 0)]
        candidates = portrait or vfiles
        if not candidates:
            return False, "Video dosyası yok"
        best = max(candidates, key=lambda f: f.get("width", 0) * f.get("height", 0))
        url = best.get("link", "")
        if not url:
            return False, "Video URL yok"

        content = httpx.get(url, timeout=60, follow_redirects=True).content
        raw_path.write_bytes(content)
        return True, str(raw_path)
    except Exception as e:
        return False, f"Pexels video hata: {e}"


async def _create_clip_from_video(raw_vid: Path, dur: float, clip_path: Path, text_file: Path, font_path: str | None) -> bool:
    """Video klipten sahne oluştur: trim + scale 1080x1920 + metin overlay."""
    drawtext = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"drawtext=textfile={text_file.absolute()}"
        f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
        f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
        f":box=1:boxcolor=black@0.55:boxborderw=18"
    )
    if font_path:
        drawtext += f":fontfile={font_path}"
    try:
        result = await asyncio.to_thread(subprocess.run,
            ["ffmpeg", "-y", "-i", str(raw_vid),
             "-t", str(dur),
             "-vf", drawtext,
             "-r", "30", "-vsync", "cfr", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-an", str(clip_path)],
            capture_output=True, timeout=120,
        )
        return result.returncode == 0
    except Exception:
        return False


@app.post("/api/pexels/config")
async def save_pexels_config(api_key: str = Form(...)):
    PEXELS_CONFIG.write_text(json.dumps({"api_key": api_key}))
    return {"ok": True}


@app.get("/api/pexels/config")
async def get_pexels_config():
    return {"configured": bool(get_pexels_key())}


@app.get("/api/openai/config")
async def get_openai_config():
    key = get_openai_key()
    return {"configured": bool(key), "key_preview": (key[:8] + "...") if key else ""}

@app.post("/api/openai/config")
async def set_openai_config(api_key: str = Form(...)):
    OPENAI_CONFIG.write_text(json.dumps({"api_key": api_key}, ensure_ascii=False))
    return {"ok": True}


@app.get("/api/instagram/config")
async def get_instagram_config():
    cfg = get_ig_config()
    user_id = cfg.get("ig_user_id", "")
    token = cfg.get("access_token", "")
    return {
        "configured": bool(user_id and token),
        "ig_user_id": user_id,
        "token_preview": (token[:10] + "...") if token else "",
        "post_reels": cfg.get("post_reels", True),
        "post_story": cfg.get("post_story", True),
    }


@app.post("/api/instagram/config")
async def set_instagram_config(
    ig_user_id: str = Form(""),
    access_token: str = Form(""),
    post_reels: str = Form("true"),
    post_story: str = Form("false"),
):
    existing = get_ig_config()
    uid = ig_user_id.strip() or existing.get("ig_user_id", "")
    tok = access_token.strip() or existing.get("access_token", "")
    if not uid or not tok:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Kullanıcı ID ve Access Token gerekli")
    cfg = {
        "ig_user_id": uid,
        "access_token": tok,
        "post_reels": post_reels == "true",
        "post_story": post_story == "true",
        "ig_handle": existing.get("ig_handle", ""),
    }
    IG_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False))
    return {"ok": True}


@app.get("/api/instagram/log")
async def get_instagram_log():
    if IG_LOG.exists():
        return json.loads(IG_LOG.read_text())
    return {"ts": None, "msg": "Henüz Instagram gönderisi yapılmadı"}


@app.post("/api/instagram/test")
async def test_instagram():
    """Kayıtlı token ile Instagram bağlantısını test eder."""
    cfg = get_ig_config()
    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        return {"ok": False, "error": "Instagram yapılandırması eksik"}
    ig_user_id = cfg["ig_user_id"]
    access_token = cfg["access_token"]
    graph = "https://graph.facebook.com/v21.0"
    try:
        r = httpx.get(
            f"{graph}/{ig_user_id}",
            params={"fields": "id,username,name,biography", "access_token": access_token},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json()
            return {"ok": True, "username": d.get("username") or d.get("name"), "id": d.get("id")}
        return {"ok": False, "error": f"{r.status_code}: {r.text[:800]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/instagram/analytics")
async def instagram_analytics(limit: int = 15):
    """Son Reels + hesap özeti. limit: kaç gönderi çekilsin."""
    cfg = get_ig_config()
    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        raise HTTPException(400, "Instagram yapılandırması eksik")
    uid   = cfg["ig_user_id"]
    token = cfg["access_token"]
    graph = "https://graph.facebook.com/v21.0"

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Profil
        r_profile = await client.get(f"{graph}/{uid}", params={
            "fields": "username,followers_count,media_count,biography",
            "access_token": token,
        })
        if r_profile.status_code != 200:
            raise HTTPException(502, f"Profil alınamadı: {r_profile.text[:200]}")
        profile = r_profile.json()

        # 2. Son gönderiler — views Reels'te doğrudan media object'ten geliyor
        r_media = await client.get(f"{graph}/{uid}/media", params={
            "fields": "id,caption,media_type,timestamp,like_count,comments_count,thumbnail_url,media_url,permalink,views",
            "limit": limit,
            "access_token": token,
        })
        if r_media.status_code != 200:
            raise HTTPException(502, f"Medya alınamadı: {r_media.text[:200]}")
        media_list = r_media.json().get("data", [])

        # 3. Her gönderi için insights
        posts = []
        for m in media_list:
            is_video = m.get("media_type") in ("VIDEO", "REEL")
            # plays metriği 21 Nisan 2025'te kaldırıldı, yeni adı views
            insight_metrics = "views,reach,likes,comments,shares,saved" if is_video else "impressions,reach,likes,comments,saved"
            r_ins = await client.get(f"{graph}/{m['id']}/insights", params={
                "metric": insight_metrics,
                "period": "lifetime",
                "access_token": token,
            })
            insights = {}
            if r_ins.status_code == 200:
                for item in r_ins.json().get("data", []):
                    if "total_value" in item:
                        val = item["total_value"].get("value", 0)
                    elif "values" in item:
                        val = item["values"][0].get("value", 0) if item["values"] else 0
                    else:
                        val = item.get("value", 0)
                    insights[item["name"]] = val or 0
            media_views = m.get("views") or insights.get("views") or 0
            posts.append({
                "id":          m["id"],
                "type":        m.get("media_type", ""),
                "caption":     (m.get("caption") or "")[:80],
                "timestamp":   m.get("timestamp", ""),
                "thumb":       m.get("thumbnail_url") or m.get("media_url") or "",
                "permalink":   m.get("permalink", ""),
                "likes":       m.get("like_count", 0),
                "comments":    m.get("comments_count", 0),
                "views":       media_views,
                "plays":       media_views,
                "reach":       insights.get("reach", 0),
                "shares":      insights.get("shares", 0),
                "saved":       insights.get("saved", 0),
                "impressions": insights.get("impressions", 0),
            })

    return {
        "profile":   profile,
        "posts":     posts,
    }


@app.get("/api/instagram/analytics/full")
async def instagram_analytics_full(force: bool = False):
    """Tüm Instagram verileri: tüm postlar, demografi, saat haritası, günlük takipçi."""
    cfg = get_ig_config()
    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        raise HTTPException(400, "Instagram yapılandırması eksik")
    try:
        data = await fetch_full_analytics(cfg["ig_user_id"], cfg["access_token"], force=force)
        return data
    except Exception as e:
        raise HTTPException(502, str(e))


def load_yt_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


@app.get("/api/trends")
async def trends_endpoint(region: str = "TR", lang: str = "tr"):
    yt_client = None
    if TOKEN_FILE.exists():
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request as GRequest
            from googleapiclient.discovery import build
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(GRequest())
                TOKEN_FILE.write_text(creds.to_json())
            yt_client = build("youtube", "v3", credentials=creds)
        except Exception:
            pass
    data = get_trends(youtube_client=yt_client, region_code=region, lang=lang)
    return data


@app.post("/api/trends/refresh")
async def trends_refresh():
    from trends import CACHE_FILE
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    return await trends_endpoint()


@app.post("/api/trends/refresh-with-gurbetci")
async def trends_refresh_with_gurbetci():
    """Manuel inceleme için: normal trend listesi + ayrı gurbetçi RSS havuzu.
    Otomatik akışa bağlı değil — sadece Shorts Manuel panelinde gösterilir."""
    base = await trends_refresh()
    gurbetci_topics = await fetch_gurbetci_topics()
    return {**base, "gurbetci_topics": gurbetci_topics}


@app.post("/api/trends/refresh-combined")
async def trends_refresh_combined():
    """Manuel inceleme için: normal trend + gurbetçi havuzlarını AYNI filtreden
    geçirip (ölüm/vefat/dedikodu + ASAYİŞ kategorisi + son işlenenler elenir) tek
    listede birleştirir. Bu fonksiyonun mantığı (interleave + filtre) otomatik
    akışta (_generate_shorts_core) ve Telegram konu seçiminde de aynen kullanılıyor —
    üçü farklı yerlerde ayrı ayrı yazıldığı için bir ara birbirinden sapmıştı
    (gurbetçi listenin sonuna eklenip [:N] kesmesiyle siliniyordu), artık hepsi
    aynı _interleave_topics() ile adil sıralanıyor."""
    base = await trends_refresh()
    gurbetci_topics = await fetch_gurbetci_topics()
    trend_topics_filtered = _filter_low_value_topics(base.get("topics", []))
    dropped = len(base.get("topics", [])) - len(trend_topics_filtered)
    if dropped:
        print(f"[combined-trends] normal trend havuzundan {dropped} düşük değerli haber elendi", flush=True)
    combined = _interleave_topics(trend_topics_filtered, gurbetci_topics)
    combined = _dedupe_pool_against_recent(combined)
    return {**base, "gurbetci_topics": gurbetci_topics, "combined_topics": combined}


@app.post("/api/yt/config")
async def save_yt_config(client_id: str = Form(...), client_secret: str = Form(...)):
    CONFIG_FILE.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))
    return {"ok": True}


@app.get("/api/yt/config")
async def get_yt_config():
    cfg = load_yt_config()
    return {"configured": bool(cfg), "authorized": TOKEN_FILE.exists()}


VERIFIER_FILE = Path("yt_verifier.txt")
VERIFIER_FILE_EN = Path("yt_verifier_en.txt")


def _build_flow(cfg, redirect_uri):
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(
        {"web": {"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token",
                 "redirect_uris": [redirect_uri]}},
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


@app.get("/auth/youtube")
async def youtube_auth(request: Request):
    import secrets, hashlib, base64
    cfg = load_yt_config()
    if not cfg:
        raise HTTPException(400, "Önce client_id ve client_secret girin")
    redirect_uri = str(request.base_url) + "auth/youtube/callback"
    flow = _build_flow(cfg, redirect_uri)

    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    VERIFIER_FILE.write_text(code_verifier)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return RedirectResponse(auth_url)


@app.get("/auth/youtube/callback")
async def youtube_callback(request: Request, code: str):
    cfg = load_yt_config()
    redirect_uri = str(request.base_url) + "auth/youtube/callback"
    flow = _build_flow(cfg, redirect_uri)
    code_verifier = VERIFIER_FILE.read_text() if VERIFIER_FILE.exists() else None
    flow.fetch_token(code=code, code_verifier=code_verifier)
    TOKEN_FILE.write_text(flow.credentials.to_json())
    return RedirectResponse("/?yt=ok")


@app.get("/auth/youtube/en")
async def youtube_auth_en(request: Request):
    import secrets, hashlib, base64
    cfg = load_yt_config()
    if not cfg:
        raise HTTPException(400, "Önce client_id ve client_secret girin")
    redirect_uri = str(request.base_url) + "auth/youtube/en/callback"
    flow = _build_flow(cfg, redirect_uri)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    VERIFIER_FILE_EN.write_text(code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return RedirectResponse(auth_url)


@app.get("/auth/youtube/en/callback")
async def youtube_callback_en(request: Request, code: str):
    cfg = load_yt_config()
    redirect_uri = str(request.base_url) + "auth/youtube/en/callback"
    flow = _build_flow(cfg, redirect_uri)
    code_verifier = VERIFIER_FILE_EN.read_text() if VERIFIER_FILE_EN.exists() else None
    flow.fetch_token(code=code, code_verifier=code_verifier)
    TOKEN_FILE_EN.write_text(flow.credentials.to_json())
    return RedirectResponse("/?yt_en=ok")


@app.get("/api/yt/en/config")
async def get_yt_en_config():
    return {"authorized": TOKEN_FILE_EN.exists()}


@app.get("/api/yt/analytics")
async def get_yt_analytics(days: int = 28, channel: str = "tr"):
    """YouTube Analytics API — genişletilmiş kanal raporu."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import datetime

    tok = TOKEN_FILE_EN if channel == "en" else TOKEN_FILE
    if not tok.exists():
        raise HTTPException(401, "YouTube hesabı bağlı değil")

    creds_data = json.loads(tok.read_text())
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            import google.auth.transport.requests
            creds.refresh(google.auth.transport.requests.Request())
            tok.write_text(creds.to_json())
        except Exception as ref_err:
            if "invalid_grant" in str(ref_err).lower() or "token has been expired" in str(ref_err).lower():
                tok.unlink(missing_ok=True)
                raise HTTPException(401, "token_expired")
            raise HTTPException(401, str(ref_err))

    end_date   = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days - 1)
    sd, ed     = str(start_date), str(end_date)

    def safe_query(**kw):
        try:
            return analytics.reports().query(**kw).execute()
        except Exception:
            return {}

    try:
        analytics = build("youtubeAnalytics", "v2", credentials=creds)
        yt        = build("youtube", "v3", credentials=creds)

        # ── Günlük: views, watch, subs kazanılan/kaybedilen, likes, comments, shares
        daily = safe_query(
            ids="channel==MINE", startDate=sd, endDate=ed,
            metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares",
            dimensions="day", sort="day",
        )

        # ── Top 15 video: views, watch, avg view duration, avg view %, likes
        top_videos = safe_query(
            ids="channel==MINE", startDate=sd, endDate=ed,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes",
            dimensions="video", sort="-views", maxResults=15,
        )

        # ── Trafik kaynağı
        traffic = safe_query(
            ids="channel==MINE", startDate=sd, endDate=ed,
            metrics="views", dimensions="insightTrafficSourceType", sort="-views",
        )

        # ── Cihaz türü
        devices = safe_query(
            ids="channel==MINE", startDate=sd, endDate=ed,
            metrics="views", dimensions="deviceType", sort="-views",
        )

        # ── Top 10 ülke
        countries = safe_query(
            ids="channel==MINE", startDate=sd, endDate=ed,
            metrics="views,estimatedMinutesWatched", dimensions="country", sort="-views", maxResults=10,
        )

        # ── Kanal abone sayısı
        ch_resp = yt.channels().list(part="statistics", mine=True).execute()
        ch_stats = {}
        if ch_resp.get("items"):
            s = ch_resp["items"][0]["statistics"]
            ch_stats = {
                "subscriber_count": int(s.get("subscriberCount", 0)),
                "total_views": int(s.get("viewCount", 0)),
                "video_count": int(s.get("videoCount", 0)),
            }

        # ── Video başlıkları
        video_ids = [row[0] for row in top_videos.get("rows", [])]
        video_titles = {}
        if video_ids:
            vr = yt.videos().list(part="snippet", id=",".join(video_ids)).execute()
            for item in vr.get("items", []):
                video_titles[item["id"]] = item["snippet"]["title"]

        # ── Özet toplamlar
        rows_d = daily.get("rows", [])
        total_views     = sum(r[1] for r in rows_d)
        total_watch_min = sum(r[2] for r in rows_d)
        total_subs_g    = sum(r[3] for r in rows_d)
        total_subs_l    = sum(r[4] for r in rows_d)
        total_likes     = sum(r[5] for r in rows_d)
        total_comments  = sum(r[6] for r in rows_d)
        total_shares    = sum(r[7] for r in rows_d)

        traffic_map = {
            "ADVERTISING": "Reklam", "ANNOTATION": "Açıklama", "BROWSE": "Gözat / Ana Sayfa",
            "CHANNEL": "Kanal Sayfası", "END_SCREEN": "Bitiş Ekranı", "EXT_URL": "Harici URL",
            "NO_LINK_EMBEDDED": "Yerleşik Player", "NO_LINK_OTHER": "Diğer",
            "NOTIFICATION": "Bildirim", "PLAYLIST": "Oynatma Listesi",
            "PROMOTED": "Tanıtılan Video", "RELATED_VIDEO": "Önerilen Video",
            "SEARCH": "YouTube Arama", "YT_SEARCH": "YouTube Arama",
            "SHORTS": "Shorts Feed", "SUBSCRIBER": "Aboneler",
            "YT_CHANNEL": "YT Kanal Sayfası", "YT_OTHER_PAGE": "Diğer YT Sayfası",
            "SOUND_PAGE": "Ses/Müzik Sayfası", "HASHTAG": "Hashtag Sayfası",
            "CAMPAIGN_CARD": "Kampanya", "VIDEO_REMIXES": "Video Remix",
        }

        return {
            "channel": ch_stats,
            "summary": {
                "views": int(total_views),
                "watch_hours": round(total_watch_min / 60, 1),
                "subs_gained": int(total_subs_g),
                "subs_lost": int(total_subs_l),
                "subs_net": int(total_subs_g - total_subs_l),
                "likes": int(total_likes),
                "comments": int(total_comments),
                "shares": int(total_shares),
                "period_days": days,
            },
            "daily": [
                {
                    "date": r[0], "views": int(r[1]), "watch_min": int(r[2]),
                    "subs_gained": int(r[3]), "subs_lost": int(r[4]),
                    "likes": int(r[5]), "comments": int(r[6]), "shares": int(r[7]),
                }
                for r in rows_d
            ],
            "top_videos": [
                {
                    "id": r[0],
                    "title": video_titles.get(r[0], r[0]),
                    "views": int(r[1]),
                    "watch_min": int(r[2]),
                    "avg_view_sec": int(r[3]),
                    "avg_view_pct": round(float(r[4]), 1),
                    "likes": int(r[5]),
                }
                for r in top_videos.get("rows", [])
            ],
            "traffic": [
                {"source": traffic_map.get(r[0], r[0]), "views": int(r[1])}
                for r in traffic.get("rows", [])
            ],
            "devices": [
                {"device": r[0].replace("_", " ").title(), "views": int(r[1])}
                for r in devices.get("rows", [])
            ],
            "countries": [
                {"country": r[0], "views": int(r[1]), "watch_min": int(r[2])}
                for r in countries.get("rows", [])
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/yt/upload")
async def upload_youtube(
    filename: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy: str = Form("public"),
    category_id: str = Form("25"),
    age_restricted: str = Form("false"),
    thumbnail_filename: str = Form(""),
    channel: str = Form("tr"),
):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_file = TOKEN_FILE_EN if channel == "en" else TOKEN_FILE
    if not token_file.exists():
        raise HTTPException(401, "YouTube hesabı bağlı değil")

    video_path = OUTPUT_DIR / filename
    if not video_path.exists():
        raise HTTPException(404, "Video bulunamadı")

    # Sosyal medya footer — tüm videolara eklenir
    if channel == "en":
        social_footer = (
            "\n\n📺 Subscribe for daily documentaries!\n"
            "📸 Instagram: https://www.instagram.com/hakanerbasss/\n"
            "\n#documentary #education #history #science #shorts"
        )
    else:
        social_footer = (
            "\n\n📺 Abone olmayı unutma!\n"
            "📸 Instagram: https://www.instagram.com/hakanerbasss/\n"
            "\n#gündem #haber #shorts #keşfet #viral"
        )
    description = (description or "").strip() + social_footer

    from google.auth.transport.requests import Request as GRequest
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GRequest())
            token_file.write_text(creds.to_json())
        except Exception as ref_err:
            if "invalid_grant" in str(ref_err).lower() or "token has been expired" in str(ref_err).lower():
                token_file.unlink(missing_ok=True)
                raise HTTPException(401, "token_expired")
            raise HTTPException(401, str(ref_err))
    youtube = build("youtube", "v3", credentials=creds)

    # Tag listesi — virgül veya boşluk ayırıcı kabul et
    tag_list = [t.lstrip("#").strip() for t in re.split(r"[\s,]+", tags) if t.strip().lstrip("#")]
    if "Shorts" not in tag_list:
        tag_list.insert(0, "Shorts")

    # Hashtagleri description'a ekle (YouTube'da tıklanabilir gösterir)
    hashtag_str = " ".join(
        f"#{t}" if not t.startswith("#") else t
        for t in tag_list
    )
    full_description = f"{description}\n\n{hashtag_str}".strip() if description else hashtag_str

    yt_title = title

    body = {
        "snippet": {
            "title": yt_title[:100],
            "description": full_description[:5000],
            "tags": tag_list[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            **({"selfDeclaredMadeForKids": False} if age_restricted == "true" else {"selfDeclaredMadeForKids": False}),
        },
    }
    if age_restricted == "true":
        body["ageGating"] = {"restricted": True}

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = req.next_chunk()

    video_id = response["id"]

    # Thumbnail yükle
    if thumbnail_filename:
        thumb_path = THUMB_DIR / thumbnail_filename
        if thumb_path.exists():
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
                ).execute()
            except Exception:
                pass

    return {"youtube_id": video_id, "url": f"https://youtu.be/{video_id}"}


@app.get("/api/thumbnail/{filename}")
async def get_thumbnail(filename: str):
    path = THUMB_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Thumbnail bulunamadı")
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/avatar-photo")
async def get_avatar_photo():
    if not AVATAR_FILE.exists():
        raise HTTPException(404, "Avatar fotoğrafı yüklenmedi")
    return FileResponse(str(AVATAR_FILE), media_type="image/jpeg")


@app.get("/api/info-endcard/status")
async def info_endcard_status():
    if INFO_ENDCARD_FILE.exists():
        return {"has_endcard": True, "path": "/api/info-endcard/photo"}
    return {"has_endcard": False}


@app.post("/api/info-endcard/upload")
async def info_endcard_upload(file: UploadFile = File(...)):
    data = await file.read()
    if not _save_as_jpeg(data, INFO_ENDCARD_FILE):
        raise HTTPException(400, "Geçersiz görsel dosyası")
    return {"ok": True, "path": "/api/info-endcard/photo"}


@app.delete("/api/info-endcard")
async def info_endcard_delete():
    INFO_ENDCARD_FILE.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/info-endcard/photo")
async def info_endcard_photo():
    if not INFO_ENDCARD_FILE.exists():
        raise HTTPException(404, "Kapanış görseli yüklenmedi")
    return FileResponse(str(INFO_ENDCARD_FILE), media_type="image/jpeg")


@app.get("/api/outro-template/status")
async def outro_template_status():
    if OUTRO_TEMPLATE.exists():
        size_mb = round(OUTRO_TEMPLATE.stat().st_size / 1024 / 1024, 1)
        return {"has_template": True, "size_mb": size_mb}
    return {"has_template": False}


@app.post("/api/outro-template/upload")
async def outro_template_upload(file: UploadFile = File(...)):
    data = await file.read()
    OUTRO_TEMPLATE.write_bytes(data)
    size_mb = round(len(data) / 1024 / 1024, 1)
    return {"ok": True, "size_mb": size_mb}


@app.delete("/api/outro-template")
async def outro_template_delete():
    OUTRO_TEMPLATE.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Dosya bulunamadı")
    return FileResponse(str(path), media_type="audio/wav")


@app.get("/api/video/{filename}")
async def get_video(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Dosya bulunamadı")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/api/comedy/photo/{session_id}/{filename}")
async def get_comedy_photo(session_id: str, filename: str):
    path = COMEDY_UPLOAD_DIR / session_id / filename
    if not path.exists():
        raise HTTPException(404, "Fotoğraf bulunamadı")
    return FileResponse(str(path))


# ── DeepSeek server-side config ──────────────────────────────────────────────

def get_deepseek_key():
    if DS_CONFIG.exists():
        return json.loads(DS_CONFIG.read_text()).get("api_key", "")
    return ""


@app.post("/api/deepseek/config")
async def save_deepseek_config(api_key: str = Form(...)):
    DS_CONFIG.write_text(json.dumps({"api_key": api_key}))
    return {"ok": True}


@app.get("/api/deepseek/config")
async def get_deepseek_config():
    return {"configured": bool(get_deepseek_key())}


# ── Scheduler ─────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")


LV_SCHED_CONFIG = Path("lv_scheduler_config.json")
LV_SCHED_LOG    = Path("lv_scheduler_log.json")


def load_lv_sched_config():
    if LV_SCHED_CONFIG.exists():
        return json.loads(LV_SCHED_CONFIG.read_text())
    return {
        "enabled": False,
        "time": "10:00",
        "categories": "teknoloji, bilim, tarih, uzay, doğa, yapay zeka",
        "duration_min": 5,
        "lang": "tr",
        "voice": "F1",
    }


def save_lv_sched_log(status: str, message: str, url: str = ""):
    LV_SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("LV Uzun Video", message)


SHORTS_DAILY_TOPICS = Path("shorts_daily_topics.json")
LV_EN_TOPICS = Path("lv_en_topics.json")


def get_lv_en_used_topics() -> list[str]:
    from datetime import date
    today = str(date.today())
    if LV_EN_TOPICS.exists():
        data = json.loads(LV_EN_TOPICS.read_text())
        if data.get("date") == today:
            return data.get("topics", [])
    return []


def add_lv_en_used_topic(title: str):
    from datetime import date
    today = str(date.today())
    topics = get_lv_en_used_topics()
    if title not in topics:
        topics.append(title)
    LV_EN_TOPICS.write_text(json.dumps({"date": today, "topics": topics}, ensure_ascii=False))


def get_shorts_used_topics() -> list[str]:
    from datetime import date
    today = str(date.today())
    if SHORTS_DAILY_TOPICS.exists():
        data = json.loads(SHORTS_DAILY_TOPICS.read_text())
        if data.get("date") == today:
            return data.get("topics", [])
    return []


def add_shorts_used_topic(title: str):
    from datetime import date
    today = str(date.today())
    topics = get_shorts_used_topics()
    if title not in topics:
        topics.append(title)
    SHORTS_DAILY_TOPICS.write_text(json.dumps({"date": today, "topics": topics}, ensure_ascii=False))


_TR_SHORTS_WEEKLY_SCHEDULE = {
    "mon": ["09:22", "14:38", "20:07"],
    "tue": ["09:15", "14:45", "20:15"],
    "wed": ["09:28", "14:32", "20:22"],
    "thu": ["09:18", "14:40", "20:35"],
    "fri": ["09:12", "14:35", "20:28"],
    "sat": ["10:45", "19:15"],
    "sun": ["11:30", "20:00"],
}


def load_sched_config():
    if SCHED_CONFIG.exists():
        cfg = json.loads(SCHED_CONFIG.read_text())
        if "weekly" not in cfg:
            cfg["weekly"] = _TR_SHORTS_WEEKLY_SCHEDULE
        return cfg
    return {"enabled": False, "voice": "F1", "weekly": _TR_SHORTS_WEEKLY_SCHEDULE}


def save_sched_log(status: str, message: str, url: str = ""):
    SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("TR Shorts", message)


async def auto_shorts_job():
    lock = _get_gen_lock()
    if lock.locked():
        save_sched_log("running", "⏳ Üretim kuyruğa alındı, bekleniyor...")
    await lock.acquire()
    save_sched_log("running", "Video üretiliyor…")
    try:
        api_key = get_deepseek_key()
        if not api_key:
            save_sched_log("error", "DeepSeek API key sunucuda kayıtlı değil")
            return
        if not TOKEN_FILE.exists():
            save_sched_log("error", "YouTube hesabı bağlı değil")
            return

        shorts_cfg = load_sched_config()
        s_lang  = shorts_cfg.get("lang", "tr")
        s_voice = shorts_cfg.get("voice", "F1")

        used_topics = get_shorts_used_topics()
        banned = load_banned_topics()
        banned_str = " | ".join(banned) if banned else ""
        exclude_str = " | ".join(used_topics) if used_topics else ""
        if banned_str:
            exclude_str = f"{exclude_str} | YASAKLI KONULAR (kesinlikle yapma): {banned_str}" if exclude_str else f"YASAKLI KONULAR (kesinlikle yapma): {banned_str}"

        async with httpx.AsyncClient(timeout=900) as client:
            _MAX_DEDUP_RETRY = 3
            d = None
            for _attempt in range(_MAX_DEDUP_RETRY):
                # 1. Video üret (trend haberden)
                r = await client.post(
                    "http://localhost:8001/api/generate-shorts",
                    data={"topic": "", "api_key": api_key, "lang": s_lang, "voice": s_voice,
                          "speed": "1.0", "exclude_topics": exclude_str},
                )
                if r.status_code != 200:
                    save_sched_log("error", f"Video üretilemedi: {r.text[:800]}")
                    return
                d = r.json()
                gen_title = d.get("title", "")

                # Banned topic kontrolü
                if _is_banned_topic(gen_title):
                    print(f"[BANNED-RETRY {_attempt+1}/{_MAX_DEDUP_RETRY}] Yasaklı konu: '{gen_title[:60]}'", flush=True)
                    if _attempt < _MAX_DEDUP_RETRY - 1:
                        continue
                    else:
                        save_sched_log("error", f"Yasaklı konu: {_MAX_DEDUP_RETRY} denemede uygun konu bulunamadı")
                        return

                # Dedup: video üretildi ama Instagram'a zaten atılmış konu mu?
                if _ig_recently_posted(gen_title) or _ig_same_topic_posted(gen_title):
                    print(f"[DEDUP-RETRY {_attempt+1}/{_MAX_DEDUP_RETRY}] ENGELLENDI: '{gen_title[:60]}' — exclude'a eklendi", flush=True)
                    exclude_str = f"{exclude_str} | {gen_title}" if exclude_str else gen_title
                    if _attempt < _MAX_DEDUP_RETRY - 1:
                        continue  # yeniden dene
                    else:
                        save_sched_log("error", f"Dedup: {_MAX_DEDUP_RETRY} denemede farklı konu bulunamadı, saat dilimi atlandı. Denenenler: {exclude_str[:200]}")
                        return

                # Dedup geçti — bu konuyu kullanıyoruz
                break

            if d is None:
                return

            add_shorts_used_topic(d.get("title", ""))

            filename = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            # 2. YouTube'a yükle
            r2 = await client.post(
                "http://localhost:8001/api/yt/upload",
                data={
                    "filename": filename,
                    "title": d.get("title", "Gündem Shorts"),
                    "description": d.get("suggested_description", ""),
                    "tags": d.get("suggested_tags", "#Shorts, #gündem, #viral, #keşfet"),
                    "privacy": "public",
                    "category_id": "25",
                    "age_restricted": "false",
                    "thumbnail_filename": thumbnail,
                },
                timeout=600,
            )
            if r2.status_code != 200:
                save_sched_log("error", f"YouTube yüklenemedi: {r2.text[:300]}")
                return

            result = r2.json()
            vw = d.get("visual_warning", "")
            log_title = d.get("title", "") + (f" ⚠️ Görsel: {vw}" if vw else "")
            save_sched_log("success", log_title, result.get("url", ""))

            # 3. Instagram'a gönder — arka planda, job'u bloke etmez
            ig_cfg = get_ig_config()
            ig_any = ig_cfg.get("post_reels", True) or ig_cfg.get("post_story", False)
            if ig_any and ig_cfg.get("ig_user_id") and ig_cfg.get("access_token"):
                asyncio.create_task(_post_to_instagram_bg(
                    filename=filename,
                    title=d.get("title", ""),
                    suggested_tags=d.get("suggested_tags", "#Shorts #gündem"),
                    ig_cfg=ig_cfg,
                    description=d.get("suggested_description", ""),
                    thumbnail=thumbnail,
                    source="TR-Shorts",
                    source_text=d.get("source_text", ""),
                ))

    except Exception as e:
        save_sched_log("error", f"{e}")
    finally:
        lock.release()


async def _post_to_instagram_bg(filename: str, title: str, suggested_tags: str, ig_cfg: dict, source: str = "", description: str = "", thumbnail: str = "", source_text: str = "") -> tuple[bool, str]:
    """Instagram gönderisi. (ok, err) döner — True/ok sadece upload başlatıldığında."""
    ig_user_id = ig_cfg["ig_user_id"]
    ig_token = ig_cfg["access_token"]
    _POWER_TAGS = ["sondakika", "haberler", "gündem", "keşfet", "türkiye", "viral"]
    existing_lower = suggested_tags.lower()
    extra = " ".join(f"#{t}" for t in _POWER_TAGS if t not in existing_lower)
    full_tags = f"{suggested_tags} {extra}".strip() if extra else suggested_tags
    desc_excerpt = _smart_truncate(description, limit=1800) if description else ""
    parts = [title]
    if desc_excerpt:
        parts.append(desc_excerpt)
    if source_text:
        parts.append(source_text)
    parts.append("Siz ne düşünüyorsunuz? 👇")
    parts.append("⚠️ Haberin doğruluğunu kendi kaynaklarınızdan teyit ediniz.")
    parts.append("🔗 Tüm haberler için link bio'da")
    parts.append(full_tags)
    caption = "\n\n".join(parts)
    # Instagram caption limiti 2200 karakter — güvenli taraf
    if len(caption) > 2180:
        caption = caption[:2177] + "..."

    # Aynı başlık daha önce atıldıysa veya doğrulama bekliyorsa atla — ama kuyruğa
    # düşür, kullanıcı gerçekten farklı bir haber olduğunu düşünürse zorla gönderebilsin
    if _ig_recently_posted(title) or _ig_is_pending(title) or _ig_same_topic_posted(title):
        err = "dedup: zaten atıldı veya bekliyor"
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[DEDUP:{source}] Zaten atıldı/bekliyor, atlanıyor: {title[:60]}"}))
        _save_failed_ig_upload(filename, title, caption, err)
        return False, err

    ig_log = ""
    upload_ok = False

    if ig_cfg.get("post_reels", True):
        video_file = OUTPUT_DIR / filename
        # Pending işaretle — 5 dk doğrulama penceresi boyunca dedup koruması
        _ig_mark_pending(title)
        reel_id, reel_err = await post_reel_to_instagram(video_file, caption, ig_user_id, ig_token)
        if reel_err:
            ig_log = f"Reels hatası: {reel_err}"
            IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": ig_log}))
            await send_telegram_alert(f"Instagram Reels [{source}]", reel_err)
            _ig_remove_pending(title)
            # Başarısız yüklemeyi kuyruğa al — kullanıcı manuel olarak yeniden deneyebilir
            _save_failed_ig_upload(filename, title, caption, reel_err)
            return False, reel_err
        else:
            ig_log = f"Reels yüklendi, doğrulama bekleniyor: {reel_id}"
            IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": ig_log}))
            asyncio.create_task(_verify_reel_published(reel_id, title, str(video_file), caption, ig_cfg, source, 1, description, thumbnail))
            upload_ok = True

    if ig_cfg.get("post_story", False):  # varsayılan False — REELS+is_stories grid'e de düşer
        video_file2 = OUTPUT_DIR / filename
        ok, story_err = await post_story_to_instagram(video_file2, ig_user_id, ig_token)
        story_log = "Story yüklendi" if ok else f"Story hatası: {story_err}"
        combined = f"{ig_log} | {story_log}" if ig_log else story_log
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": combined}))
        if story_err:
            await send_telegram_alert(f"Instagram Story [{source}]", story_err)

    return upload_ok, ""


def _rebuild_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("auto_"):
            job.remove()
    cfg = load_sched_config()
    if not cfg.get("enabled"):
        return
    for day, times in cfg.get("weekly", _TR_SHORTS_WEEKLY_SCHEDULE).items():
        for t in times:
            try:
                hour, minute = t.split(":")
                scheduler.add_job(
                    auto_shorts_job,
                    CronTrigger(day_of_week=day, hour=int(hour), minute=int(minute), timezone="Europe/Istanbul"),
                    id=f"auto_{day}_{t.replace(':', '')}",
                    replace_existing=True,
                    max_instances=1,
                )
            except Exception:
                pass


async def auto_long_video_job():
    lock = _get_gen_lock()
    if lock.locked():
        save_lv_sched_log("running", "⏳ Üretim kuyruğa alındı, bekleniyor...")
    await lock.acquire()
    try:
        save_lv_sched_log("running", "Konu seçiliyor…")
        api_key = get_deepseek_key()
        if not api_key:
            save_lv_sched_log("error", "DeepSeek API key sunucuda kayıtlı değil")
            return
        if not TOKEN_FILE.exists():
            save_lv_sched_log("error", "YouTube hesabı bağlı değil")
            return

        cfg = load_lv_sched_config()
        categories = cfg.get("categories", "teknoloji, bilim, tarih, uzay")
        duration_min = cfg.get("duration_min", 5)
        lang = cfg.get("lang", "tr")
        voice = cfg.get("voice", "F1")
        lang_name = LANG_MAP.get(lang, "Turkish")

        # 1. DeepSeek'e konu seçtir
        from openai import OpenAI
        ds = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        topic_resp = ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"""Pick ONE specific, interesting and educational documentary topic in {lang_name}.
Categories to choose from: {categories}
Return ONLY valid JSON: {{"topic": "specific topic in {lang_name}"}}
Make it specific and fascinating — NOT generic. Examples:
- "Kuantum Dolanıklığı Nasıl Çalışır ve Neden Önemlidir?"
- "James Webb Uzay Teleskobu İlk Bir Yılda Neler Keşfetti?"
- "GPT-4 ve Büyük Dil Modelleri Nasıl Eğitilir?"
- "İklim Değişikliğinin Okyanuslar Üzerindeki Gizli Etkileri"
Pick something different and interesting each time."""}],
            temperature=0.95,
        )
        topic = _parse_llm_json(topic_resp.choices[0].message.content).get(
            "topic", categories.split(",")[0].strip()
        )

        save_lv_sched_log("running", f"Video üretiliyor: {topic}")

        # 2. Uzun video üret + YouTube'a yükle
        timeout = httpx.Timeout(connect=30, read=1800, write=60, pool=30)
        async with httpx.AsyncClient(timeout=timeout) as hc:
            r = await hc.post(
                "http://localhost:8001/api/generate-long-video",
                data={"topic": topic, "api_key": api_key, "lang": lang,
                      "voice": voice, "speed": "1.0", "duration_min": str(duration_min)},
            )
            if r.status_code != 200:
                save_lv_sched_log("error", f"Video üretilemedi: {r.text[:800]}")
                return
            d = r.json()

            filename  = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            r2 = await hc.post(
                "http://localhost:8001/api/yt/upload",
                data={
                    "filename": filename,
                    "title": d.get("title", topic),
                    "description": d.get("description", ""),
                    "tags": d.get("suggested_tags", f"#belgesel, #eğitim, #teknoloji, #keşfet"),
                    "privacy": "public",
                    "category_id": "28",
                    "age_restricted": "false",
                    "thumbnail_filename": thumbnail,
                },
                timeout=600,
            )
            if r2.status_code != 200:
                save_lv_sched_log("error", f"YouTube yüklenemedi: {r2.text[:300]}")
                return

            save_lv_sched_log("success", d.get("title", topic), r2.json().get("url", ""))

    except Exception as e:
        save_lv_sched_log("error", str(e))
    finally:
        lock.release()


def _rebuild_lv_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("lv_") and not job.id.startswith("lv_en_"):
            job.remove()
    cfg = load_lv_sched_config()
    if not cfg.get("enabled"):
        return
    t = cfg.get("time", "10:00")
    try:
        hour, minute = t.strip().split(":")
        scheduler.add_job(
            auto_long_video_job,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="lv_daily",
            replace_existing=True,
            max_instances=1,
        )
    except Exception:
        pass


LV_EN_SCHED_CONFIG = Path("lv_en_scheduler_config.json")
LV_EN_SCHED_LOG    = Path("lv_en_scheduler_log.json")


def load_lv_en_sched_config():
    if LV_EN_SCHED_CONFIG.exists():
        return json.loads(LV_EN_SCHED_CONFIG.read_text())
    return {
        "enabled": False,
        "time": "14:00",
        "categories": "history, science, space, technology, nature, ancient civilizations, physics",
        "duration_min": 5,
        "voice": "M1",
    }


def save_lv_en_sched_log(status: str, message: str, url: str = ""):
    LV_EN_SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("EN Uzun Video", message)


async def auto_lv_en_job():
    lock = _get_gen_lock()
    if lock.locked():
        save_lv_en_sched_log("running", "⏳ Generation queued, waiting...")
    await lock.acquire()
    try:
        save_lv_en_sched_log("running", "Topic selecting…")
        api_key = get_deepseek_key()
        if not api_key:
            save_lv_en_sched_log("error", "DeepSeek API key not configured on server")
            return
        if not TOKEN_FILE_EN.exists():
            save_lv_en_sched_log("error", "EN YouTube channel not connected")
            return

        cfg = load_lv_en_sched_config()
        categories = cfg.get("categories", "history, science, space, technology")
        duration_min = cfg.get("duration_min", 5)
        voice = cfg.get("voice", "M1")

        from openai import OpenAI
        ds = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        used_topics = get_lv_en_used_topics()
        exclude_block = (
            f"\nDo NOT pick any of these already-covered topics:\n" + "\n".join(f"- {t}" for t in used_topics) + "\n"
        ) if used_topics else ""
        topic_resp = ds.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"""Pick ONE specific, fascinating and educational documentary topic in English.
Categories to choose from: {categories}
{exclude_block}Return ONLY valid JSON: {{"topic": "specific topic in English"}}
Make it specific and fascinating — NOT generic. Examples:
- "How the Roman Colosseum Was Built and What Happened Inside"
- "The Science Behind Black Holes: What Happens If You Fall In?"
- "The Real Story of the Library of Alexandria and Its Destruction"
- "How Quantum Entanglement Could Change Communication Forever"
Pick something DIFFERENT and interesting each time."""}],
            temperature=0.95,
        )
        topic = _parse_llm_json(topic_resp.choices[0].message.content).get(
            "topic", categories.split(",")[0].strip()
        )

        save_lv_en_sched_log("running", f"Generating: {topic}")

        timeout = httpx.Timeout(connect=30, read=1800, write=60, pool=30)
        async with httpx.AsyncClient(timeout=timeout) as hc:
            r = await hc.post(
                "http://localhost:8001/api/generate-long-video",
                data={"topic": topic, "api_key": api_key, "lang": "en",
                      "voice": voice, "speed": "1.0", "duration_min": str(duration_min)},
            )
            if r.status_code != 200:
                save_lv_en_sched_log("error", f"Video failed: {r.text[:800]}")
                return
            d = r.json()

            filename  = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            r2 = await hc.post(
                "http://localhost:8001/api/yt/upload",
                data={
                    "filename": filename,
                    "title": d.get("title", topic),
                    "description": d.get("description", ""),
                    "tags": d.get("suggested_tags", "#documentary, #education, #science, #history"),
                    "privacy": "public",
                    "category_id": "27",
                    "age_restricted": "false",
                    "thumbnail_filename": thumbnail,
                    "channel": "en",
                },
                timeout=600,
            )
            if r2.status_code != 200:
                save_lv_en_sched_log("error", f"Upload failed: {r2.text[:300]}")
                return

            title = d.get("title", topic)
            add_lv_en_used_topic(title)
            save_lv_en_sched_log("success", title, r2.json().get("url", ""))

    except Exception as e:
        save_lv_en_sched_log("error", str(e))
    finally:
        lock.release()


def _rebuild_lv_en_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("lv_en_"):
            job.remove()
    cfg = load_lv_en_sched_config()
    if not cfg.get("enabled"):
        return
    t = cfg.get("time", "14:00")
    try:
        hour, minute = t.strip().split(":")
        scheduler.add_job(
            auto_lv_en_job,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="lv_en_daily",
            replace_existing=True,
            max_instances=1,
        )
    except Exception:
        pass


EN_SHORTS_SCHED_CONFIG  = Path("en_shorts_scheduler_config.json")
EN_SHORTS_SCHED_LOG     = Path("en_shorts_scheduler_log.json")
EN_SHORTS_DAILY_TOPICS  = Path("en_shorts_daily_topics.json")


_EN_SHORTS_WEEKLY_SCHEDULE = {
    "mon": ["10:22", "15:38", "21:07"],
    "tue": ["10:15", "15:45", "21:15"],
    "wed": ["10:28", "15:32", "21:22"],
    "thu": ["10:18", "15:40", "21:35"],
    "fri": ["10:12", "15:25", "21:28"],
    "sat": ["11:45", "20:15"],
    "sun": ["12:30", "21:00"],
}


def load_en_shorts_sched_config():
    if EN_SHORTS_SCHED_CONFIG.exists():
        cfg = json.loads(EN_SHORTS_SCHED_CONFIG.read_text())
        if "weekly" not in cfg:
            cfg["weekly"] = _EN_SHORTS_WEEKLY_SCHEDULE
        return cfg
    return {"enabled": False, "voice": "M1", "ig_enabled": False, "weekly": _EN_SHORTS_WEEKLY_SCHEDULE}


def save_en_shorts_sched_log(status: str, message: str, url: str = ""):
    EN_SHORTS_SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("EN Shorts", message)


def get_en_shorts_used_topics() -> list[str]:
    from datetime import date
    today = str(date.today())
    if EN_SHORTS_DAILY_TOPICS.exists():
        data = json.loads(EN_SHORTS_DAILY_TOPICS.read_text())
        if data.get("date") == today:
            return data.get("topics", [])
    return []


def add_en_shorts_used_topic(title: str):
    from datetime import date
    today = str(date.today())
    topics = get_en_shorts_used_topics()
    if title not in topics:
        topics.append(title)
    EN_SHORTS_DAILY_TOPICS.write_text(json.dumps({"date": today, "topics": topics}, ensure_ascii=False))


async def auto_en_shorts_job():
    lock = _get_gen_lock()
    if lock.locked():
        save_en_shorts_sched_log("running", "⏳ Generation queued, waiting...")
    await lock.acquire()
    try:
        save_en_shorts_sched_log("running", "Generating EN short…")
        api_key = get_deepseek_key()
        if not api_key:
            save_en_shorts_sched_log("error", "DeepSeek API key not configured on server")
            return
        if not TOKEN_FILE_EN.exists():
            save_en_shorts_sched_log("error", "EN YouTube channel not connected")
            return

        cfg = load_en_shorts_sched_config()
        s_voice = cfg.get("voice", "M1")

        used_topics = get_en_shorts_used_topics()
        exclude_str = " | ".join(used_topics) if used_topics else ""

        async with httpx.AsyncClient(timeout=900) as client:
            r = await client.post(
                "http://localhost:8001/api/generate-shorts",
                data={
                    "topic": "",
                    "api_key": api_key,
                    "lang": "en",
                    "voice": s_voice,
                    "speed": "1.0",
                    "exclude_topics": exclude_str,
                    "region": "US",
                },
            )
            if r.status_code != 200:
                save_en_shorts_sched_log("error", f"Video failed: {r.text[:800]}")
                return
            d = r.json()
            add_en_shorts_used_topic(d.get("title", ""))

            filename = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            r2 = await client.post(
                "http://localhost:8001/api/yt/upload",
                data={
                    "filename": filename,
                    "title": d.get("title", "Breaking News Short"),
                    "description": d.get("suggested_description", ""),
                    "tags": d.get("suggested_tags", "#Shorts #news #viral #trending"),
                    "privacy": "public",
                    "category_id": "25",
                    "age_restricted": "false",
                    "thumbnail_filename": thumbnail,
                    "channel": "en",
                },
                timeout=600,
            )
            if r2.status_code != 200:
                save_en_shorts_sched_log("error", f"Upload failed: {r2.text[:300]}")
                return

            result = r2.json()
            ig_enabled = bool(cfg.get("ig_enabled", False))
            save_en_shorts_sched_log("success", d.get("title", "") + f" [IG={'AÇIK' if ig_enabled else 'KAPALI'}]", result.get("url", ""))
            if ig_enabled:
                ig_cfg = get_ig_config()
                ig_any = ig_cfg.get("post_reels", True) or ig_cfg.get("post_story", False)
                if ig_any and ig_cfg.get("ig_user_id") and ig_cfg.get("access_token"):
                    asyncio.create_task(_post_to_instagram_bg(
                        filename=filename,
                        title=d.get("title", ""),
                        suggested_tags=d.get("suggested_tags", "#Shorts #news"),
                        ig_cfg=ig_cfg,
                        source="EN-Shorts",
                    ))

    except Exception as e:
        save_en_shorts_sched_log("error", str(e))
    finally:
        lock.release()


def _rebuild_en_shorts_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("en_shorts_"):
            job.remove()
    cfg = load_en_shorts_sched_config()
    if not cfg.get("enabled"):
        return
    for day, times in cfg.get("weekly", _EN_SHORTS_WEEKLY_SCHEDULE).items():
        for t in times:
            try:
                hour, minute = t.split(":")
                scheduler.add_job(
                    auto_en_shorts_job,
                    CronTrigger(day_of_week=day, hour=int(hour), minute=int(minute), timezone="Europe/Istanbul"),
                    id=f"en_shorts_{day}_{t.replace(':', '')}",
                    replace_existing=True,
                    max_instances=1,
                )
            except Exception:
                pass


TNLV_SCHED_CONFIG = Path("tnlv_scheduler_config.json")
TNLV_SCHED_LOG    = Path("tnlv_scheduler_log.json")


def load_tnlv_sched_config():
    if TNLV_SCHED_CONFIG.exists():
        return json.loads(TNLV_SCHED_CONFIG.read_text())
    return {
        "enabled": False,
        "times": ["08:00", "20:00"],
        "lang": "tr",
        "voice": "F1",
    }


def save_tnlv_sched_log(status: str, message: str, url: str = ""):
    TNLV_SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("TNLV Shorts", message)


async def auto_tnlv_job():
    lock = _get_gen_lock()
    if lock.locked():
        save_tnlv_sched_log("running", "⏳ Üretim kuyruğa alındı, bekleniyor...")
    await lock.acquire()
    try:
        save_tnlv_sched_log("running", "Trend haberleri getiriliyor…")
        api_key = get_deepseek_key()
        if not api_key:
            save_tnlv_sched_log("error", "DeepSeek API key sunucuda kayıtlı değil")
            return
        if not TOKEN_FILE.exists():
            save_tnlv_sched_log("error", "YouTube hesabı bağlı değil")
            return

        cfg = load_tnlv_sched_config()
        lang  = cfg.get("lang", "tr")
        voice = cfg.get("voice", "F1")

        timeout = httpx.Timeout(connect=30, read=1800, write=60, pool=30)
        async with httpx.AsyncClient(timeout=timeout) as hc:
            r = await hc.post(
                "http://localhost:8001/api/generate-trend-long-video",
                data={"api_key": api_key, "lang": lang, "voice": voice, "speed": "1.0", "region": "TR"},
            )
            if r.status_code != 200:
                save_tnlv_sched_log("error", f"Video üretilemedi: {r.text[:800]}")
                return
            d = r.json()

            filename  = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            r2 = await hc.post(
                "http://localhost:8001/api/yt/upload",
                data={
                    "filename": filename,
                    "title": d.get("title", "Günün Trend Haberleri"),
                    "description": d.get("description", ""),
                    "tags": d.get("suggested_tags", "#gündem, #haberler, #trendler, #viral"),
                    "privacy": "public",
                    "category_id": "25",
                    "age_restricted": "false",
                    "thumbnail_filename": thumbnail,
                },
                timeout=600,
            )
            if r2.status_code != 200:
                save_tnlv_sched_log("error", f"YouTube yüklenemedi: {r2.text[:300]}")
                return

            save_tnlv_sched_log("success", d.get("title", "Günün Trend Haberleri"), r2.json().get("url", ""))

    except Exception as e:
        save_tnlv_sched_log("error", str(e))
    finally:
        lock.release()


def _rebuild_tnlv_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("tnlv_"):
            job.remove()
    cfg = load_tnlv_sched_config()
    if not cfg.get("enabled"):
        return
    for t in cfg.get("times", []):
        try:
            hour, minute = t.strip().split(":")
            scheduler.add_job(
                auto_tnlv_job,
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f"tnlv_{t.replace(':', '')}",
                replace_existing=True,
                max_instances=1,
            )
        except Exception:
            pass


# ── TR Instagram-Only Scheduler ─────────────────────────────────────────────
IG_ONLY_TR_SCHED_CONFIG = Path("ig_only_tr_sched_config.json")
IG_ONLY_TR_SCHED_LOG    = Path("ig_only_tr_sched_log.json")
IG_ONLY_TR_DAILY_TOPICS = Path("ig_only_tr_daily_topics.json")


def load_ig_only_tr_config():
    if IG_ONLY_TR_SCHED_CONFIG.exists():
        cfg = json.loads(IG_ONLY_TR_SCHED_CONFIG.read_text())
        if "weekly" not in cfg or cfg.get("sched_v") != _IG_SCHED_VERSION:
            # Eski schedule → veriye göre ayarlanmış yeni schedule'a geç
            cfg["weekly"] = _IG_WEEKLY_SCHEDULE
            cfg["sched_v"] = _IG_SCHED_VERSION
            IG_ONLY_TR_SCHED_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False))
        return cfg
    return {"enabled": False, "voice": "F1", "weekly": _IG_WEEKLY_SCHEDULE, "sched_v": _IG_SCHED_VERSION}


def save_ig_only_tr_log(status: str, message: str):
    IG_ONLY_TR_SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("TR Instagram-Only", message)


def get_ig_only_tr_used_topics() -> list[str]:
    today = time.strftime("%Y-%m-%d")
    if IG_ONLY_TR_DAILY_TOPICS.exists():
        data = json.loads(IG_ONLY_TR_DAILY_TOPICS.read_text())
        if data.get("date") == today:
            return data.get("topics", [])
    return []


def add_ig_only_tr_used_topic(title: str):
    today = time.strftime("%Y-%m-%d")
    topics = get_ig_only_tr_used_topics()
    topics.append(title.strip()[:120])
    IG_ONLY_TR_DAILY_TOPICS.write_text(json.dumps({"date": today, "topics": topics}, ensure_ascii=False))


async def auto_ig_only_tr_job(force_telegram_pick: bool = False):
    try:
        api_key = get_deepseek_key()
        if not api_key:
            save_ig_only_tr_log("error", "DeepSeek API key kayıtlı değil")
            return
        ig_cfg = get_ig_config()
        if not ig_cfg.get("ig_user_id") or not ig_cfg.get("access_token"):
            save_ig_only_tr_log("error", "Instagram yapılandırılmamış")
            return

        cfg = load_ig_only_tr_config()
        s_voice = cfg.get("voice", "F1")
        video_mode = cfg.get("video_mode", "off")
        use_video_val = "true" if (video_mode == "random" and random.random() < 0.40) else "false"
        used_topics = get_ig_only_tr_used_topics()
        banned = load_banned_topics()
        banned_str = " | ".join(banned) if banned else ""
        exclude_str = " | ".join(used_topics) if used_topics else ""
        if banned_str:
            exclude_str = f"{exclude_str} | YASAKLI KONULAR (kesinlikle yapma): {banned_str}" if exclude_str else f"YASAKLI KONULAR (kesinlikle yapma): {banned_str}"

        # ── Telegram'dan manuel konu seçimi (switch açıksa) ──────────────────────
        # Kullanıcı 5 dakika içinde numarayla cevap verirse o haberi zorla, vermezse
        # eskisi gibi DeepSeek otomatik seçsin.
        forced_topic = ""
        if cfg.get("telegram_topic_pick") or force_telegram_pick:
            try:
                trend_data = get_trends(region_code="TR", lang="tr")
                gurbetci_topics = await fetch_gurbetci_topics()
                pool = _filter_low_value_topics(trend_data.get("topics", []))
                pool = _interleave_topics(pool, gurbetci_topics)
                pool = _dedupe_pool_against_recent(pool)[:30]
                if pool:
                    offset = await _telegram_mark_offset_to_latest()
                    numbered = "\n\n".join(f"{i+1}. {t}" for i, t in enumerate(pool))
                    sent = await send_telegram_plain(
                        f"📰 TR Instagram-Only — 5 dakika içinde numara yaz, o haberi yapayım.\n"
                        f"Uygun haber yoksa 'iptal' veya 'c' yaz, bu saat dilimi hiç paylaşılmasın.\n"
                        f"Cevap gelmezse otomatik seçeceğim.\n\n{numbered}"
                    )
                    if sent:
                        save_ig_only_tr_log("running", "📰 Telegram'a haber listesi gönderildi, cevap bekleniyor (5 dk)...")
                        choice = await wait_for_telegram_numeric_reply(offset, len(pool), timeout_sec=300)
                        if choice == "CANCEL":
                            await send_telegram_plain("🚫 İptal edildi, bu saat diliminde paylaşım yapılmayacak.")
                            save_ig_only_tr_log("success", "Telegram'dan iptal edildi — uygun haber yok, bu saat dilimi atlandı")
                            return
                        elif choice:
                            forced_topic = pool[choice - 1]
                            await send_telegram_plain(f"✅ Seçildi: {forced_topic}\nÜretiliyor…")
                            save_ig_only_tr_log("running", f"Telegram'dan seçildi: {forced_topic[:80]}")
                        else:
                            await send_telegram_plain("⏱️ Cevap gelmedi, otomatik seçiliyor…")
                            save_ig_only_tr_log("running", "Telegram cevabı gelmedi, otomatik seçime devam ediliyor...")
            except Exception as te:
                print(f"[TELEGRAM-PICK] hata: {te}", flush=True)
        # ───────────────────────────────────────────────────────────────────────

        # Kullanıcı Telegram'dan belirli bir haber seçtiyse tekrar denemenin anlamı
        # yok (aynı konu tekrar denenirse yine aynı sonucu verir) — tek deneme yapılır.
        _MAX_DEDUP_RETRY = 1 if forced_topic else 3

        # Kilit sadece gerçek üretim aşamasında tutulur — Telegram cevabı beklerken
        # (yukarıda, kilitsiz) diğer zamanlanmış işler 5 dakika boyunca kuyrukta
        # bekletilmesin diye kilit alımı buraya, üretimin hemen öncesine taşındı.
        lock = _get_gen_lock()
        if lock.locked():
            save_ig_only_tr_log("running", "⏳ Üretim kuyruğa alındı, bekleniyor...")
        await lock.acquire()
        try:
            gen_msg = f"Video üretiliyor: {forced_topic[:100]}" if forced_topic else "Video üretiliyor…"
            save_ig_only_tr_log("running", gen_msg)
            d = None
            async with httpx.AsyncClient(timeout=900) as client:
                for _attempt in range(_MAX_DEDUP_RETRY):
                    r = await client.post(
                        "http://localhost:8001/api/generate-shorts",
                        data={"topic": forced_topic, "api_key": api_key, "lang": "tr", "voice": s_voice,
                              "speed": "1.0", "exclude_topics": exclude_str, "region": "TR",
                              "platform": "instagram", "use_video": use_video_val},
                    )
                    if r.status_code != 200:
                        save_ig_only_tr_log("error", f"Video üretilemedi: {r.text[:800]}")
                        return
                    d = r.json()
                    gen_title = d.get("title", "")
                    save_ig_only_tr_log("running", f"Üretildi, Instagram'a yükleniyor: {gen_title[:100]}")

                    # Banned topic kontrolü
                    if _is_banned_topic(gen_title):
                        print(f"[BANNED-RETRY {_attempt+1}/{_MAX_DEDUP_RETRY}] Yasaklı konu: '{gen_title[:60]}'", flush=True)
                        if _attempt < _MAX_DEDUP_RETRY - 1:
                            continue
                        else:
                            save_ig_only_tr_log("error", f"Yasaklı konu: {_MAX_DEDUP_RETRY} denemede uygun konu bulunamadı")
                            return

                    # Dedup: video üretilmeden önce Instagram konu kontrolü
                    if _ig_recently_posted(gen_title) or _ig_same_topic_posted(gen_title):
                        print(f"[DEDUP-RETRY {_attempt+1}/{_MAX_DEDUP_RETRY}] ENGELLENDI: '{gen_title[:60]}' — exclude'a eklendi", flush=True)
                        exclude_str = f"{exclude_str} | {gen_title}" if exclude_str else gen_title
                        if _attempt < _MAX_DEDUP_RETRY - 1:
                            continue
                        else:
                            save_ig_only_tr_log("error", f"Dedup: {_MAX_DEDUP_RETRY} denemede farklı konu bulunamadı, saat dilimi atlandı. Denenenler: {exclude_str[:200]}")
                            return

                    # Kategori tekrar/tavan kontrolü — son denemede ihlale rağmen paylaşılır
                    # (slot boş kalmasın; trend listesi o gün tek konuya kilitlenmiş olabilir)
                    cat_ok, cat_reason = ig_perf.check_hard_rules(gen_title, get_ig_only_tr_used_topics())
                    if not cat_ok:
                        if _attempt < _MAX_DEDUP_RETRY - 1:
                            print(f"[CAT-RETRY {_attempt+1}/{_MAX_DEDUP_RETRY}] {cat_reason}: '{gen_title[:60]}' — farklı kategori istenecek", flush=True)
                            exclude_str = f"{exclude_str} | {gen_title}" if exclude_str else gen_title
                            continue
                        else:
                            print(f"[CAT-WARN] {cat_reason} ama son deneme — yine de paylaşılıyor: '{gen_title[:60]}'", flush=True)
                    break  # dedup + kategori geçti

            if d is None:
                return

            add_ig_only_tr_used_topic(d.get("title", ""))
            filename = d["video"].split("/").pop()
            thumbnail = (d.get("thumbnail") or "").split("/").pop()

            # Sadece Instagram — YouTube'a gönderilmez
            ig_cfg["post_reels"] = True
            vw = d.get("visual_warning", "")
            log_title = d.get("title", "") + (f" ⚠️ {vw}" if vw else "")

            ig_ok, ig_err = await _post_to_instagram_bg(
                filename=filename,
                title=d.get("title", ""),
                suggested_tags=d.get("suggested_tags", "#Shorts #gündem"),
                ig_cfg=ig_cfg,
                description=d.get("suggested_description", ""),
                thumbnail=thumbnail,
                source="IG-Only-TR",
                source_text=d.get("source_text", ""),
            )
            if ig_ok:
                save_ig_only_tr_log("success", log_title)
            else:
                save_ig_only_tr_log("error", f"Instagram gönderilemedi: {ig_err}")
        finally:
            lock.release()

    except Exception as e:
        save_ig_only_tr_log("error", str(e))


# v3 — 292 postluk analitik verisine göre (12.07.2026):
# 09:00–15:00 altın pencere (ort. 4.415 izlenme, 10:00'da 5.727 + 37.6 paylaşım),
# 06:00–09:00 ölü bölge (ort. 1.040), 22:00 civarı iyi (2.923).
# Slotlar sabah yerine öğlen penceresine yığıldı; 18:40 tek akşam + 22:00 korundu.
_IG_SCHED_VERSION = 3
_IG_WEEKLY_SCHEDULE = {
    "mon": ["09:00", "09:50", "10:40", "11:30", "12:20", "13:10", "14:05", "15:00", "16:00", "17:05", "18:40", "22:00"],
    "tue": ["09:05", "09:55", "10:45", "11:35", "12:25", "13:15", "14:10", "15:05", "16:05", "17:10", "18:45", "22:05"],
    "wed": ["09:10", "10:00", "10:50", "11:40", "12:30", "13:20", "14:15", "15:10", "16:10", "17:15", "18:50", "22:10"],
    "thu": ["09:00", "09:52", "10:42", "11:32", "12:22", "13:12", "14:07", "15:02", "16:02", "17:07", "18:42", "22:02"],
    "fri": ["09:05", "09:57", "10:47", "11:37", "12:27", "13:17", "14:12", "15:07", "16:07", "17:12", "18:47", "22:07"],
    "sat": ["09:30", "10:30", "11:30", "12:30", "13:45", "15:00", "16:30", "22:00"],
    "sun": ["09:35", "10:35", "11:35", "12:35", "13:50", "15:05", "16:35", "22:05"],
}


def _rebuild_ig_only_tr_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("ig_only_tr_"):
            job.remove()
    cfg = load_ig_only_tr_config()
    if not cfg.get("enabled"):
        return
    for day, times in cfg.get("weekly", _IG_WEEKLY_SCHEDULE).items():
        for t in times:
            try:
                hour, minute = t.split(":")
                scheduler.add_job(
                    auto_ig_only_tr_job,
                    CronTrigger(day_of_week=day, hour=int(hour), minute=int(minute), timezone="Europe/Istanbul"),
                    id=f"ig_only_tr_{day}_{t.replace(':', '')}",
                    replace_existing=True,
                    max_instances=1,
                )
            except Exception:
                pass


@app.get("/api/ig-only-tr/config")
async def get_ig_only_tr_sched_config():
    cfg = load_ig_only_tr_config()
    log = {}
    if IG_ONLY_TR_SCHED_LOG.exists():
        log = json.loads(IG_ONLY_TR_SCHED_LOG.read_text())
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("ig_only_tr_")]
    next_run = min((j.next_run_time for j in jobs if j.next_run_time), default=None)
    return {**cfg, "log": log, "next_run": next_run.isoformat() if next_run else None}


@app.post("/api/ig-only-tr/config")
async def save_ig_only_tr_sched_config(
    enabled: str = Form("false"),
    voice: str = Form("F1"),
    video_mode: str = Form("off"),
    telegram_topic_pick: str = Form("false"),
    mon: str = Form(""),
    tue: str = Form(""),
    wed: str = Form(""),
    thu: str = Form(""),
    fri: str = Form(""),
    sat: str = Form(""),
    sun: str = Form(""),
):
    weekly = {}
    for day, val in [("mon",mon),("tue",tue),("wed",wed),("thu",thu),("fri",fri),("sat",sat),("sun",sun)]:
        weekly[day] = [t.strip() for t in val.split(",") if t.strip()]
    # sched_v damgalanır ki kullanıcının elle kaydettiği saatler migration'da ezilmesin
    cfg = {"enabled": enabled == "true", "voice": voice,
           "video_mode": video_mode if video_mode in ("off", "random") else "off",
           "telegram_topic_pick": telegram_topic_pick == "true",
           "weekly": weekly, "sched_v": _IG_SCHED_VERSION}
    IG_ONLY_TR_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_ig_only_tr_scheduler()
    return {"ok": True}


@app.post("/api/ig-only-tr/run-now")
async def run_ig_only_tr_now():
    asyncio.create_task(auto_ig_only_tr_job())
    return {"ok": True}


@app.post("/api/ig-only-tr/run-now-telegram")
async def run_ig_only_tr_now_telegram():
    """Test için: switch'in kayıtlı durumuna dokunmadan, sadece bu çalıştırmada
    Telegram'dan konu seçimini zorlar. Saat ayarlamaya gerek kalmadan denemek için."""
    asyncio.create_task(auto_ig_only_tr_job(force_telegram_pick=True))
    return {"ok": True}


@app.get("/api/ig/failed-uploads")
async def get_ig_failed_uploads():
    return {"items": _load_failed_ig_uploads()}


@app.post("/api/ig/retry-upload")
async def retry_ig_upload(filename: str = Form(...)):
    ig_cfg = get_ig_config()
    if not ig_cfg.get("ig_user_id") or not ig_cfg.get("access_token"):
        raise HTTPException(400, "Instagram yapılandırılmamış")
    items = _load_failed_ig_uploads()
    item = next((x for x in items if x.get("filename") == filename), None)
    if not item:
        raise HTTPException(404, "Kayıt bulunamadı")
    video_file = OUTPUT_DIR / filename
    if not video_file.exists():
        raise HTTPException(404, "Video dosyası bulunamadı")
    reel_id, reel_err = await post_reel_to_instagram(
        video_file, item["caption"], ig_cfg["ig_user_id"], ig_cfg["access_token"]
    )
    if reel_err:
        # Hata mesajını güncelle ama listeden çıkarma
        updated = [{**x, "error": reel_err, "ts": time.time()} if x.get("filename") == filename else x for x in items]
        IG_FAILED_FILE.write_text(json.dumps(updated, ensure_ascii=False))
        raise HTTPException(500, reel_err)
    _remove_failed_ig_upload(filename)
    asyncio.create_task(_verify_reel_published(reel_id, item["title"], str(video_file), item["caption"], ig_cfg, "manual-retry"))
    return {"ok": True, "reel_id": reel_id}


@app.delete("/api/ig/failed-upload/{filename}")
async def delete_ig_failed_upload(filename: str):
    _remove_failed_ig_upload(filename)
    video_file = OUTPUT_DIR / filename
    if video_file.exists():
        video_file.unlink()
    return {"ok": True}


# ── Biriken video dosyaları — otomatik temizlik çalışmazsa manuel yedek ────────

@app.get("/api/output-videos")
async def list_output_videos():
    failed_filenames = {x.get("filename") for x in _load_failed_ig_uploads()}
    now = time.time()
    items = []
    for f in OUTPUT_DIR.iterdir():
        if not f.is_file():
            continue
        st = f.stat()
        items.append({
            "filename": f.name,
            "size_mb": round(st.st_size / (1024 * 1024), 2),
            "age_hours": round((now - st.st_mtime) / 3600, 1),
            "pending": f.name in failed_filenames,
        })
    items.sort(key=lambda x: x["age_hours"], reverse=True)
    return {"items": items, "total_mb": round(sum(i["size_mb"] for i in items), 2), "count": len(items)}


@app.delete("/api/output-videos/{filename}")
async def delete_output_video(filename: str):
    video_file = OUTPUT_DIR / Path(filename).name
    if video_file.exists():
        video_file.unlink()
    _remove_failed_ig_upload(Path(filename).name)
    return {"ok": True}


@app.post("/api/output-videos/bulk-delete")
async def bulk_delete_output_videos(filenames: str = Form("")):
    deleted = 0
    for name in [n.strip() for n in filenames.split(",") if n.strip()]:
        vf = OUTPUT_DIR / Path(name).name
        if vf.exists():
            vf.unlink()
            deleted += 1
        _remove_failed_ig_upload(Path(name).name)
    return {"ok": True, "deleted": deleted}


# ── Startup / Shutdown ────────────────────────────────────────────────────────
_SERVICE_STARTED_AT: float = 0.0

_RESCUE_MAP = None  # startup sonrası doldurulur


async def _rescue_interrupted_jobs_task():
    """Scheduler ayağa kalktıktan 5 sn sonra yarım kalan job'ları yeniden başlatır."""
    await asyncio.sleep(5)
    cutoff = time.time() - 2 * 3600
    for log_file, job_fn, label in _RESCUE_MAP:
        if not log_file.exists():
            continue
        try:
            data = json.loads(log_file.read_text())
            if data.get("status") != "running":
                continue
            job_ts = data.get("ts", 0)
            if job_ts < cutoff:
                # 2 saatten eski — sadece log'u düzelt, yeniden başlatma
                log_file.write_text(json.dumps(
                    {"status": "error", "message": "Servis yeniden başlatıldı, job kesildi", "ts": time.time()},
                    ensure_ascii=False,
                ))
            else:
                # 2 saat içindeydi — log'u güncelle + otomatik yeniden kuyruğa al
                log_file.write_text(json.dumps(
                    {"status": "error",
                     "message": f"⚠️ Servis yeniden başlatıldı — {label} otomatik yeniden sıraya alındı",
                     "ts": time.time()},
                    ensure_ascii=False,
                ))
                asyncio.create_task(job_fn())
        except Exception:
            pass


_VIDEO_RETENTION_DAYS = 3      # başarıyla paylaşılan / ilgisiz videolar bu kadar gün sonra silinir
_FAILED_UPLOAD_EXPIRY_DAYS = 7  # bekleyen yüklemeler bu kadar gün çözülmezse otomatik iptal edilir (haber bayatlar)


def _cleanup_old_media():
    """OUTPUT_DIR'daki eski video dosyalarını temizler — diskin dolmasını önler.
    Thumbnail'lere dokunmaz (haber sitesi kalıcı olarak kullanıyor)."""
    now = time.time()
    failed = _load_failed_ig_uploads()
    failed_filenames = {x.get("filename") for x in failed}

    # 7 günden eski bekleyen yüklemeleri otomatik iptal et (haber bayatladı)
    still_pending = []
    for item in failed:
        if now - item.get("ts", 0) > _FAILED_UPLOAD_EXPIRY_DAYS * 86400:
            vf = OUTPUT_DIR / item.get("filename", "")
            if vf.exists():
                vf.unlink()
            failed_filenames.discard(item.get("filename"))
        else:
            still_pending.append(item)
    if len(still_pending) != len(failed):
        IG_FAILED_FILE.write_text(json.dumps(still_pending, ensure_ascii=False))

    # OUTPUT_DIR'daki eski video dosyalarını sil (hâlâ bekleyen yükleme kuyruğunda olanlar hariç)
    try:
        for f in OUTPUT_DIR.iterdir():
            if not f.is_file() or f.name in failed_filenames:
                continue
            if now - f.stat().st_mtime > _VIDEO_RETENTION_DAYS * 86400:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass

    # THUMB_DIR'daki eski thumbnail'leri sil — haber sitesi DB'sinde olanlar korunur
    try:
        news_thumbs = set()
        try:
            import sqlite3 as _sq
            _db = Path("haberler.db")
            if _db.exists():
                with _sq.connect(str(_db)) as _c:
                    for (tn,) in _c.execute("SELECT thumbnail FROM articles WHERE thumbnail != ''"):
                        news_thumbs.add(tn)
        except Exception:
            pass
        for f in THUMB_DIR.iterdir():
            if not f.is_file() or f.name in news_thumbs:
                continue
            if now - f.stat().st_mtime > 7 * 86400:
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass


async def _refresh_ig_analytics_cache():
    """Gece 05:15'te analitik cache'i yeniler — ig_perf skorlaması hep taze veriyle çalışsın.
    İlk sabah postu 09:00'da olduğundan skorlar güne hazır olur."""
    try:
        cfg = get_ig_config()
        if not cfg.get("ig_user_id") or not cfg.get("access_token"):
            return
        data = await fetch_full_analytics(cfg["ig_user_id"], cfg["access_token"], force=True)
        print(f"[ig_perf] analitik cache yenilendi: {data.get('total_posts', 0)} post", flush=True)
    except Exception as e:
        print(f"[ig_perf] analitik cache yenileme hatası: {e}", flush=True)


@app.on_event("startup")
async def startup_event():
    global _SERVICE_STARTED_AT, _RESCUE_MAP
    _SERVICE_STARTED_AT = time.time()

    _RESCUE_MAP = [
        (SCHED_LOG,            auto_shorts_job,       "TR Shorts"),
        (LV_SCHED_LOG,         auto_long_video_job,   "TR Uzun Video"),
        (LV_EN_SCHED_LOG,      auto_lv_en_job,        "EN Uzun Video"),
        (EN_SHORTS_SCHED_LOG,  auto_en_shorts_job,    "EN Shorts"),
        (TNLV_SCHED_LOG,       auto_tnlv_job,         "TNLV Video"),
        (IG_ONLY_TR_SCHED_LOG, auto_ig_only_tr_job,   "TR Instagram-Only"),
    ]

    scheduler.start()
    _rebuild_scheduler()
    _rebuild_lv_scheduler()
    _rebuild_lv_en_scheduler()
    _rebuild_en_shorts_scheduler()
    _rebuild_tnlv_scheduler()
    _rebuild_ig_only_tr_scheduler()
    scheduler.add_job(
        _cleanup_old_media, CronTrigger(hour=4, minute=30, timezone="Europe/Istanbul"),
        id="cleanup_old_media", replace_existing=True,
    )
    scheduler.add_job(
        _refresh_ig_analytics_cache, CronTrigger(hour=5, minute=15, timezone="Europe/Istanbul"),
        id="refresh_ig_analytics", replace_existing=True,
    )

    start_namaz_scheduler(scheduler)

    asyncio.create_task(_rescue_interrupted_jobs_task())


@app.post("/api/namaz/register-city")
async def namaz_register_city(request: Request):
    """Uygulama açılışında aktif şehri kaydeder. namaz_bildirim.py bu listeyi okur."""
    body = await request.json()
    city    = str(body.get("city", "")).strip()
    country = str(body.get("country", "Turkey")).strip()
    if not city:
        raise HTTPException(status_code=400, detail="city required")
    cities_file = Path("namaz_cities.json")
    cities: list = json.loads(cities_file.read_text()) if cities_file.exists() else []
    key = f"{city.lower()}_{country.lower()}"
    if not any(c.get("key") == key for c in cities):
        cities.append({"key": key, "city": city, "country": country})
        cities_file.write_text(json.dumps(cities, ensure_ascii=False, indent=2))
    return {"ok": True}


@app.get("/api/status/service-start")
async def get_service_start():
    return {"ts": _SERVICE_STARTED_AT}


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown(wait=False)


@app.get("/api/scheduler/config")
async def get_scheduler_config():
    cfg = load_sched_config()
    log = {}
    if SCHED_LOG.exists():
        log = json.loads(SCHED_LOG.read_text())
    jobs = scheduler.get_jobs()
    next_run = None
    if jobs:
        nxt = [j.next_run_time for j in jobs if j.next_run_time]
        if nxt:
            next_run = min(nxt).strftime("%d.%m.%Y %H:%M")
    return {**cfg, "log": log, "next_run": next_run}


@app.post("/api/scheduler/config")
async def save_scheduler_config(
    enabled: str = Form("false"),
    lang: str = Form("tr"),
    voice: str = Form("F1"),
    mon: str = Form(""),
    tue: str = Form(""),
    wed: str = Form(""),
    thu: str = Form(""),
    fri: str = Form(""),
    sat: str = Form(""),
    sun: str = Form(""),
):
    weekly = {}
    for day, val in [("mon",mon),("tue",tue),("wed",wed),("thu",thu),("fri",fri),("sat",sat),("sun",sun)]:
        weekly[day] = [t.strip() for t in val.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "lang": lang, "voice": voice, "weekly": weekly}
    SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_scheduler()
    return cfg


@app.post("/api/scheduler/run-now")
async def run_scheduler_now():
    asyncio.create_task(auto_shorts_job())
    return {"ok": True}


@app.get("/api/lv-scheduler/config")
async def get_lv_scheduler_config():
    cfg = load_lv_sched_config()
    log = {}
    if LV_SCHED_LOG.exists():
        log = json.loads(LV_SCHED_LOG.read_text())
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("lv_") and not j.id.startswith("lv_en_")]
    next_run = None
    if jobs and jobs[0].next_run_time:
        next_run = jobs[0].next_run_time.strftime("%d.%m.%Y %H:%M")
    return {**cfg, "log": log, "next_run": next_run}


@app.post("/api/lv-scheduler/config")
async def save_lv_scheduler_config(
    enabled: str = Form("false"),
    time: str = Form("10:00"),
    categories: str = Form("teknoloji, bilim, tarih, uzay, doğa, yapay zeka"),
    duration_min: str = Form("5"),
    lang: str = Form("tr"),
    voice: str = Form("F1"),
):
    cfg = {
        "enabled": enabled == "true",
        "time": time.strip(),
        "categories": categories,
        "duration_min": int(duration_min),
        "lang": lang,
        "voice": voice,
    }
    LV_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_lv_scheduler()
    return cfg


@app.post("/api/lv-scheduler/run-now")
async def run_lv_now():
    asyncio.create_task(auto_long_video_job())
    return {"ok": True}


@app.get("/api/lv-en-scheduler/config")
async def get_lv_en_scheduler_config():
    cfg = load_lv_en_sched_config()
    log = {}
    if LV_EN_SCHED_LOG.exists():
        log = json.loads(LV_EN_SCHED_LOG.read_text())
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("lv_en_")]
    next_run = None
    if jobs and jobs[0].next_run_time:
        next_run = jobs[0].next_run_time.strftime("%d.%m.%Y %H:%M")
    return {**cfg, "log": log, "next_run": next_run}


@app.post("/api/lv-en-scheduler/config")
async def save_lv_en_scheduler_config(
    enabled: str = Form("false"),
    time: str = Form("14:00"),
    categories: str = Form("history, science, space, technology, nature"),
    duration_min: str = Form("5"),
    voice: str = Form("M1"),
):
    cfg = {
        "enabled": enabled == "true",
        "time": time.strip(),
        "categories": categories,
        "duration_min": int(duration_min),
        "voice": voice,
    }
    LV_EN_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_lv_en_scheduler()
    return cfg


@app.post("/api/lv-en-scheduler/run-now")
async def run_lv_en_now():
    asyncio.create_task(auto_lv_en_job())
    return {"ok": True}


@app.get("/api/en-shorts-scheduler/config")
async def get_en_shorts_scheduler_config():
    cfg = load_en_shorts_sched_config()
    log = {}
    if EN_SHORTS_SCHED_LOG.exists():
        log = json.loads(EN_SHORTS_SCHED_LOG.read_text())
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("en_shorts_")]
    next_run = None
    if jobs:
        nxt = [j.next_run_time for j in jobs if j.next_run_time]
        if nxt:
            next_run = min(nxt).strftime("%d.%m.%Y %H:%M")
    return {**cfg, "log": log, "next_run": next_run}


@app.post("/api/en-shorts-scheduler/config")
async def save_en_shorts_scheduler_config(
    enabled: str = Form("false"),
    voice: str = Form("M1"),
    ig_enabled: str = Form("false"),
    mon: str = Form(""),
    tue: str = Form(""),
    wed: str = Form(""),
    thu: str = Form(""),
    fri: str = Form(""),
    sat: str = Form(""),
    sun: str = Form(""),
):
    weekly = {}
    for day, val in [("mon",mon),("tue",tue),("wed",wed),("thu",thu),("fri",fri),("sat",sat),("sun",sun)]:
        weekly[day] = [t.strip() for t in val.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "voice": voice, "ig_enabled": ig_enabled == "true", "weekly": weekly}
    EN_SHORTS_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_en_shorts_scheduler()
    return cfg


@app.post("/api/en-shorts-scheduler/run-now")
async def run_en_shorts_now():
    asyncio.create_task(auto_en_shorts_job())
    return {"ok": True}


@app.get("/api/tnlv-scheduler/config")
async def get_tnlv_scheduler_config():
    cfg = load_tnlv_sched_config()
    log = {}
    if TNLV_SCHED_LOG.exists():
        log = json.loads(TNLV_SCHED_LOG.read_text())
    jobs = [j for j in scheduler.get_jobs() if j.id.startswith("tnlv_")]
    next_run = None
    if jobs:
        nxt = [j.next_run_time for j in jobs if j.next_run_time]
        if nxt:
            next_run = min(nxt).strftime("%d.%m.%Y %H:%M")
    return {**cfg, "log": log, "next_run": next_run}


@app.post("/api/tnlv-scheduler/config")
async def save_tnlv_scheduler_config(
    enabled: str = Form("false"),
    times: str = Form("08:00,20:00"),
    lang: str = Form("tr"),
    voice: str = Form("F1"),
):
    time_list = [t.strip() for t in times.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "times": time_list, "lang": lang, "voice": voice}
    TNLV_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_tnlv_scheduler()
    return cfg


@app.post("/api/tnlv-scheduler/run-now")
async def run_tnlv_now():
    asyncio.create_task(auto_tnlv_job())
    return {"ok": True}


@app.get("/api/telegram/config")
async def get_telegram_cfg():
    cfg = get_telegram_config()
    return {"bot_token": cfg.get("bot_token", ""), "chat_id": cfg.get("chat_id", "")}


@app.post("/api/telegram/config")
async def save_telegram_cfg(
    bot_token: str = Form(""),
    chat_id: str = Form(""),
):
    cfg = {"bot_token": bot_token.strip(), "chat_id": chat_id.strip()}
    TELEGRAM_CONFIG.write_text(json.dumps(cfg))
    return {"ok": True}


@app.post("/api/telegram/test")
async def test_telegram():
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "Bot token veya Chat ID eksik")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "✅ Supertonic bağlantısı başarılı! Bildirimler aktif.", "parse_mode": "Markdown"},
            )
        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "error": r.text[:800]}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/stop-all")
async def stop_all_jobs():
    """Tüm çalışan FFmpeg proseslerini öldür ve log'ları sıfırla."""
    import signal

    # FFmpeg proseslerini öldür
    killed = 0
    try:
        result = await asyncio.to_thread(subprocess.run, ["pgrep", "-x", "ffmpeg"], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                import os
                os.kill(int(pid), signal.SIGKILL)
                killed += 1
            except Exception:
                pass
    except Exception:
        pass

    # Tüm log dosyalarını "durduruldu" olarak sıfırla
    stop_payload = json.dumps({"status": "error", "message": "Kullanıcı tarafından durduruldu", "url": "", "ts": time.time()})
    for log_file in [SCHED_LOG, LV_SCHED_LOG, LV_EN_SCHED_LOG, EN_SHORTS_SCHED_LOG, TNLV_SCHED_LOG, IG_ONLY_TR_SCHED_LOG]:
        try:
            log_file.write_text(stop_payload)
        except Exception:
            pass

    return {"ok": True, "killed_ffmpeg": killed}



# ──────────────────────────────────────────────────────────────────────────────
# KOMİK HABER — fotoğraftan video oluştur
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/comedy/upload")
async def comedy_upload_photos(files: list[UploadFile] = File(...)):
    """Komik haber için fotoğraf yükle. Yükleme sırasına göre 1.jpg, 2.jpg... olarak kaydeder."""
    if not files:
        raise HTTPException(400, "Fotoğraf yüklenmedi")
    session_id = uuid.uuid4().hex[:8]
    session_dir = COMEDY_UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, f in enumerate(files, start=1):
        ext = Path(f.filename).suffix.lower() or ".jpg"
        dest = session_dir / f"{i}{ext}"
        dest.write_bytes(await f.read())
        saved.append(dest.name)
    return {"session_id": session_id, "photos": saved, "count": len(saved)}


@app.post("/api/comedy/create")
async def comedy_create_video(request: Request):
    """
    Fotoğraflardan komik haber videosu oluştur.
    Body: {
      "session_id": "abc12345",
      "scenes": [{"photo": "1.jpg", "text": "Alt yazı...", "tts": "Seslendir..."}],
      "voice": "M3",
      "title": "Video başlığı"
    }
    """
    body = await request.json()
    session_id = body.get("session_id", "")
    scenes = body.get("scenes", [])
    voice = body.get("voice", "M3")

    if not session_id or not scenes:
        raise HTTPException(400, "session_id ve scenes gerekli")

    session_dir = COMEDY_UPLOAD_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(404, f"Session bulunamadı: {session_id}")

    uid = uuid.uuid4().hex[:8]
    work_dir = COMEDY_UPLOAD_DIR / f"work_{uid}"
    work_dir.mkdir(parents=True, exist_ok=True)

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((fp for fp in font_candidates if Path(fp).exists()), None)

    audio_files = []
    clip_files = []

    from PIL import Image

    for i, scene in enumerate(scenes):
        photo_name = scene.get("photo", "")
        text = scene.get("text", "")
        tts_text = _clean_tts_text(scene.get("tts", text), "tr")

        photo_src = session_dir / photo_name
        if not photo_src.exists():
            raise HTTPException(404, f"Fotoğraf bulunamadı: {photo_name}")

        # Fotoğrafı 1080x1920 dikey formata crop/resize
        img = Image.open(photo_src).convert("RGB")
        src_ratio = img.width / img.height
        tgt_ratio = 1080 / 1920
        if src_ratio > tgt_ratio:
            new_h = 1920
            new_w = int(new_h * src_ratio)
        else:
            new_w = 1080
            new_h = int(new_w / src_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - 1080) // 2
        top = (new_h - 1920) // 2
        img = img.crop((left, top, left + 1080, top + 1920))
        png_path = work_dir / f"scene_{i}.jpg"
        img.save(str(png_path), "JPEG", quality=90)

        # TTS
        wav, duration = await asyncio.to_thread(tts.synthesize,
            tts_text, lang="tr", voice_style=style, total_steps=8, speed=1.0,
        )
        audio_path = work_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        dur = float(duration[0]) if hasattr(duration, '__getitem__') else float(duration)
        audio_files.append((audio_path, dur))

        # Alt yazı dosyası
        words = text.split()
        lines, line = [], []
        for w in words:
            if len(" ".join(line + [w])) > 38:
                lines.append(" ".join(line))
                line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        text_file = work_dir / f"text_{i}.txt"
        text_file.write_text("\n".join(lines), encoding="utf-8")

        clip_path = work_dir / f"clip_{i}.mp4"
        kb_ok = await _try_ken_burns_clip(png_path, dur, clip_path, text_file, font_path)
        if not kb_ok:
            drawtext = (
                f"scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,"
                f"drawtext=textfile={text_file.absolute()}"
                f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
                f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
                f":box=1:boxcolor=black@0.55:boxborderw=18"
            )
            if font_path:
                drawtext += f":fontfile={font_path}"
            r = await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-loop", "1", "-i", str(png_path),
                 "-t", str(dur), "-vf", drawtext,
                 "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
                capture_output=True, timeout=90,
            )
            if r.returncode != 0:
                await asyncio.to_thread(subprocess.run,
                    ["ffmpeg", "-y", "-loop", "1", "-i", str(png_path),
                     "-t", str(dur), "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                     "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
                    check=True, capture_output=True, timeout=90,
                )
        clip_files.append(clip_path)

    # Ses birleştir
    audio_list_file = work_dir / "audio_list.txt"
    combined_audio = work_dir / "combined.wav"
    with open(audio_list_file, "w") as f:
        for af, _ in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list_file), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True, timeout=120,
    )

    # Video kliplerini birleştir
    clip_list_file = work_dir / "clip_list.txt"
    with open(clip_list_file, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")
    slideshow = work_dir / "slideshow.mp4"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list_file.absolute()),
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
         "-r", "30", "-vsync", "cfr", "-pix_fmt", "yuv420p",
         str(slideshow.absolute())],
        check=True, capture_output=True, timeout=300,
    )

    # Final encode
    output_file = OUTPUT_DIR / f"{uid}_comedy.mp4"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(slideshow.absolute()), "-i", str(combined_audio.absolute()),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
         "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr", "-bf", "0", "-g", "30",
         "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k",
         "-movflags", "+faststart", "-shortest", str(output_file.absolute())],
        check=True, capture_output=True, timeout=300,
    )

    # Meta kaydet (Instagram gönderimi için)
    (session_dir / "video_meta.json").write_text(json.dumps({
        "video_file": output_file.name,
        "uid": uid,
        "title": body.get("title", ""),
        "ts": time.time(),
    }))

    shutil.rmtree(work_dir, ignore_errors=True)

    return {
        "ok": True,
        "video": f"/api/video/{output_file.name}",
        "session_id": session_id,
        "uid": uid,
    }


@app.post("/api/shorts/send-instagram")
async def shorts_send_instagram(request: Request):
    """Manuel üretilen shorts videosunu Instagram Reels olarak gönder."""
    body = await request.json()
    filename = body.get("filename", "").strip()
    title = body.get("title", "").strip()
    tags = body.get("tags", "").strip()
    description = body.get("description", "").strip()

    if not filename:
        raise HTTPException(400, "filename gerekli")

    output_file = OUTPUT_DIR / filename
    if not output_file.exists():
        raise HTTPException(404, "Video bulunamadı")

    cfg = get_ig_config()
    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        raise HTTPException(400, "Instagram konfigürasyonu eksik — Ayarlar'dan yapılandır")

    _POWER_TAGS = ["sondakika", "haberler", "gündem", "keşfet", "türkiye", "viral"]
    existing_lower = tags.lower()
    extra = " ".join(f"#{t}" for t in _POWER_TAGS if t not in existing_lower)
    full_tags = f"{tags} {extra}".strip() if extra else tags
    desc_excerpt = _smart_truncate(description, limit=1800) if description else ""
    if title and desc_excerpt:
        caption = f"{title}\n\n{desc_excerpt}\n\nSiz ne düşünüyorsunuz? 👇\n\n{full_tags}"
    elif title:
        caption = f"{title}\n\nSiz ne düşünüyorsunuz? 👇\n\n{full_tags}"
    else:
        caption = full_tags

    media_id, err = await post_reel_to_instagram(
        output_file, caption, cfg["ig_user_id"], cfg["access_token"]
    )
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "media_id": media_id}


@app.post("/api/comedy/send-instagram")
async def comedy_send_instagram(request: Request):
    """Oluşturulan komik haber videosunu Instagram Reels olarak gönder."""
    body = await request.json()
    uid = body.get("uid", "")
    caption = body.get("caption", "").strip() or "😄 #komedi #günlük #yaşam"

    if not uid:
        raise HTTPException(400, "uid gerekli")

    output_file = OUTPUT_DIR / f"{uid}_comedy.mp4"
    if not output_file.exists():
        raise HTTPException(404, "Video bulunamadı")

    cfg = get_ig_config()
    if not cfg.get("ig_user_id") or not cfg.get("access_token"):
        raise HTTPException(400, "Instagram konfigürasyonu eksik — Ayarlar'dan yapılandır")

    media_id, err = await post_reel_to_instagram(
        output_file, caption, cfg["ig_user_id"], cfg["access_token"]
    )
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "media_id": media_id}



# ──────────────────────────────────────────────────────────────────────────────
# YEDEKLEME — config dosyalarını ZIP indir / geri yükle
# ──────────────────────────────────────────────────────────────────────────────

_BACKUP_FILES = [
    TOKEN_FILE,
    PEXELS_CONFIG,
    DS_CONFIG,
    OPENAI_CONFIG,
    IG_CONFIG,
    IG_RECENT_FILE,
    TELEGRAM_CONFIG,
    SCHED_CONFIG,
    LV_SCHED_CONFIG,
    LV_EN_SCHED_CONFIG,
    EN_SHORTS_SCHED_CONFIG,
    TNLV_SCHED_CONFIG,
    IG_ONLY_TR_SCHED_CONFIG,
    IG_ONLY_TR_SCHED_LOG,
    IG_ONLY_TR_DAILY_TOPICS,
    HOOK_STYLE_CONFIG,
    RECENT_CATEGORIES_FILE,
    news_site.DB_PATH,
]


# ── Ses Klonu (XTTS-v2) ──────────────────────────────────────────────────────

@app.get("/api/tts/clone-status")
async def tts_clone_status():
    cfg = get_ig_config()
    return {
        "has_reference": xtts_clone.hazir_mi(),
        "use_clone": cfg.get("use_clone_voice", False),
        "ref_path": str(xtts_clone.ref_audio_path()) if xtts_clone.hazir_mi() else None,
    }


@app.post("/api/tts/upload-reference")
async def tts_upload_reference(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "Dosya seçilmedi")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".wav", ".mp3", ".m4a", ".ogg", ".flac"):
        raise HTTPException(400, "Desteklenen formatlar: wav, mp3, m4a, ogg, flac")
    dest = xtts_clone.ref_audio_path()
    tmp = dest.with_suffix(".tmp")
    async with aiofiles.open(tmp, "wb") as f:
        content = await file.read()
        await f.write(content)
    # Gürültü temizleme + normalize + WAV dönüşümü (tüm formatlar için)
    noise_filter = "anlmdn=s=7:p=0.002:r=0.002:m=15,highpass=f=100,lowpass=f=8000,loudnorm"
    cmd = ["ffmpeg", "-y", "-i", str(tmp), "-af", noise_filter, "-ar", "22050", "-ac", "1", str(dest)]
    r = subprocess.run(cmd, capture_output=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise HTTPException(500, f"FFmpeg dönüşüm hatası: {r.stderr.decode()[:200]}")
    return {"ok": True, "path": str(dest), "size_kb": round(dest.stat().st_size / 1024)}


@app.post("/api/tts/toggle-clone")
async def tts_toggle_clone(enabled: bool = Form(...)):
    cfg = get_ig_config()
    cfg["use_clone_voice"] = enabled
    IG_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False))
    return {"use_clone": enabled}


@app.post("/api/tts/test-clone")
async def tts_test_clone(text: str = Form("Merhaba, bu benim klonlanmış sesim. Türkçe haber sunuyorum.")):
    if not xtts_clone.hazir_mi():
        raise HTTPException(400, "Referans ses yok — önce referans_sesim.wav yükle")
    out = Path("/tmp") / f"clone_test_{uuid.uuid4().hex[:8]}.wav"
    try:
        dur = await xtts_clone.seslendir(text, str(out), language="tr")
    except Exception as e:
        raise HTTPException(500, str(e))
    return FileResponse(str(out), media_type="audio/wav",
                        filename="clone_test.wav",
                        headers={"X-Duration": str(round(dur, 2))})


# ─────────────────────────────────────────────────────────────────────────────

def _write_simple_backup_zip(zf) -> None:
    """Sadece config/token dosyaları — Telegram için küçük boyutlu yedek."""
    for p in _BACKUP_FILES:
        if p.exists():
            zf.write(str(p), p.name)


def _write_full_backup_zip(zf) -> None:
    """Config + haber veritabanı + tüm thumbnail arşivi — tam yedek."""
    _write_simple_backup_zip(zf)
    if THUMB_DIR.exists():
        for f in THUMB_DIR.iterdir():
            if f.is_file():
                zf.write(str(f), f"thumbnails/{f.name}")


@app.get("/api/backup/download")
async def backup_download():
    """Tüm config dosyalarını, haber veritabanını ve thumbnail arşivini ZIP olarak indir."""
    import zipfile, io, datetime
    buf = io.BytesIO()
    today = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_full_backup_zip(zf)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=supertonic_backup_{today}.zip"},
    )


@app.post("/api/backup/send-telegram")
async def backup_send_telegram():
    """Backup ZIP'i Telegram botuna gönder."""
    import zipfile, io, datetime
    cfg = get_telegram_config()
    token = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        raise HTTPException(400, "Telegram bot token veya chat_id ayarlı değil")
    buf = io.BytesIO()
    today = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    fname = f"supertonic_backup_{today}.zip"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_simple_backup_zip(zf)
    buf.seek(0)
    data = buf.read()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id, "caption": f"📦 Supertonic Yedek — {today}"},
                files={"document": (fname, data, "application/zip")},
            )
        if resp.status_code == 200:
            return {"ok": True, "filename": fname}
        else:
            raise HTTPException(500, f"Telegram hatası: {resp.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/backup/restore")
async def backup_restore(file: UploadFile = File(...)):
    """Yedek ZIP dosyasından config dosyalarını geri yükle."""
    import zipfile, io
    if not file.filename.endswith(".zip"):
        raise HTTPException(400, "ZIP dosyası gerekli")
    content = await file.read()
    restored, skipped = [], []
    allowed = {p.name for p in _BACKUP_FILES}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for name in zf.namelist():
            if name.startswith("thumbnails/") and not name.endswith("/"):
                dest = THUMB_DIR / Path(name).name
                dest.write_bytes(zf.read(name))
                restored.append(name)
            elif name in allowed:
                Path(name).write_bytes(zf.read(name))
                restored.append(name)
            else:
                skipped.append(name)
    return {"ok": True, "restored": restored, "skipped": skipped}


@app.get("/ads.txt", response_class=PlainTextResponse)
async def ads_txt():
    return "google.com, pub-7820582813827252, DIRECT, f08c47fec0942fa0\n"

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
