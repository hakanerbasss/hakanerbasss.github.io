import os
import uuid
import asyncio
import subprocess
import json
import time
import re
import hashlib
import secrets
from pathlib import Path
import shutil

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import traceback
import aiofiles
import httpx

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from supertonic import TTS
from deep_translator import GoogleTranslator
import whisper

app = FastAPI()

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_CONFIG = Path("auth_config.json")
_sessions: dict = {}  # token -> expiry (time.time() + 24h)
_SESSION_TTL = 24 * 3600
_COOKIE = "instube_session"


def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def _get_auth_cfg() -> dict:
    if not AUTH_CONFIG.exists():
        AUTH_CONFIG.write_text(json.dumps({"password_hash": _hash_pw("instube2026")}))
    return json.loads(AUTH_CONFIG.read_text())


def _valid_session(token: str | None) -> bool:
    if not token:
        return False
    exp = _sessions.get(token)
    if not exp or time.time() > exp:
        _sessions.pop(token, None)
        return False
    return True


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Login sayfası ve statik dosyalar serbest
    if path in ("/login", "/logout") or path.startswith("/static/"):
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
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="lax", max_age=_SESSION_TTL)
    return resp


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get(_COOKIE)
    _sessions.pop(token, None)
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


def _clean_tts_text(text: str, lang: str = "tr") -> str:
    """TTS'e gitmeden önce metni temizle — imla/format hatalarını düzelt."""
    import re
    # Markdown kalıntılarını kaldır
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    if lang == "tr":
        # 1.500 → 1500
        text = re.sub(r'(\d)\.(\d{3})\b', r'\1\2', text)
        # %85 → yüzde 85
        text = re.sub(r'%\s*(\d+)', r'yüzde \1', text)
        # 32° → 32 derece
        text = re.sub(r'(\d+)°', r'\1 derece', text)

    # URL'leri kaldır
    text = re.sub(r'https?://\S+', '', text)
    # Özel semboller
    text = re.sub(r'[#@|_~^\\<>{}[\]]', ' ', text)
    # Birden fazla boşluk → tek boşluk
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_whisper():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model


@app.get("/")
async def index():
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

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    wav, duration = await asyncio.to_thread(tts.synthesize,
        _clean_tts_text(text, lang), lang=lang,
        voice_style=style, total_steps=8, speed=speed,
    )

    out_file = OUTPUT_DIR / f"{uuid.uuid4()}.wav"
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
):
    import json
    import httpx
    from openai import OpenAI

    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    use_video_mode = use_video.lower() in ("true", "1", "yes")
    pexels_key = get_pexels_key()

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Trend verileri al
    trend_data = get_trends(region_code=region.upper(), lang=lang)
    trend_topics = ", ".join(trend_data["topics"][:12])
    yt_tags = ", ".join(trend_data.get("yt_trending_tags", [])[:10])
    trend_tags = ", ".join(trend_data["hashtags"][:10])

    lang_name = LANG_MAP.get(lang, "Turkish")
    exclude_instruction = ""
    if exclude_topics.strip():
        exclude_instruction = f"\nIMPORTANT - Do NOT cover these topics (already posted today):\n{exclude_topics}\nPick a DIFFERENT topic from the trending list.\n"
    if topic.strip():
        topic_instruction = (
            f"Topic: {topic}\n"
            f"Use these TODAY'S real trending news to make the content timely and relevant:\n{trend_topics}"
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
            f"Choose ONE of these TODAY'S trending news and make a Short about it:\n{trend_topics}"
        )
    yt_tag_instruction = f"\nYouTube TR trending hashtags RIGHT NOW (include relevant ones): {yt_tags}" if yt_tags else ""
    prompt = f"""Create a YouTube Shorts video.
Narration language: {lang_name}
{topic_instruction}
{exclude_instruction}Suggested hashtags: {trend_tags}{yt_tag_instruction}

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
- NEVER use phrases that imply real footage or real photos exist (e.g. "İşte görüntüler", "İşte o anlar", "kameralar görüntüledi", "işte o fotoğraflar", "görüntüler ortaya çıktı", "here is the footage"). Visuals are illustrative stock photos — narration must describe events in storytelling form, never reference visuals.
- FIRST scene text MUST use a CURIOSITY-GAP hook — never state the answer directly in the first sentence. Create suspense or partial reveal. Examples: "Kimse beklemiyordu:", "Meğer...", "Az önce ortaya çıktı:", "Herkes bunu merak ediyordu — cevap şoke etti.", "Tarihin en büyük...", "Peki gerçekte ne oldu?". NEVER open with a plain news statement. The viewer must NEED to keep watching to get the answer. Do NOT repeat the same opener across videos.
- LAST scene text MUST end with this exact call to action (translated naturally to {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!" — make it feel urgent and personal, not generic.
- keyword: English, 2-3 words, visual and specific (e.g. "mountain sunset", "busy city street")
- Total narration under 55 seconds
- hashtags: 8-12 tags specific to THIS video's topic (mix of {lang_name} and English), ALWAYS include "Shorts", "sondakika", "gündem", "keşfet", "haberler" — then add topic-specific tags. No # symbol, NO spaces within a tag (e.g. "sondakika" not "son dakika", "breaking news" → "breakingnews")
"""

    data = None
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

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    audio_files = []
    png_files = []
    durations = []
    visual_warnings: set = set()
    scene_raw_videos = []  # video modunda her sahne için ham video yolu (None = foto kullan)

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

        # Son sahne: sabit belmolysoft end card — Pexels'e gitme
        is_last_scene = (i == len(scenes) - 1)
        png_path = scene_dir / f"scene_{i}.jpg"
        scene_raw_video = None  # video modunda indirilen ham video

        if is_last_scene:
            endcard = Path("static/endcard_tr.jpg")
            if endcard.exists():
                import shutil as _sh
                _sh.copy2(str(endcard), str(png_path))
                photo_saved, visual_err = True, ""
            else:
                photo_saved, visual_err = False, "endcard yok"
        else:
            keyword = scene.get("keyword", topic)
            # Video modu: önce Pexels video dene, başarısız olursa görsele düş
            if use_video_mode and pexels_key:
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

    # İlk sahneye haber overlay ekle
    if png_files:
        try:
            first_title = data.get("title", topic or scenes[0]["text"][:60])
            overlay_first_scene_banner(png_files[0], first_title, lang=lang)
        except Exception:
            pass

    # Son sahneye beğen/abone ol bandı ekle (endcard kullanılıyorsa atlıyoruz — zaten içinde var)
    endcard_used = Path("static/endcard_tr.jpg").exists()
    if png_files and not endcard_used:
        try:
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
            # Başarısız → foto fallback'e düş

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
    await arun_ffmpeg([
        "ffmpeg", "-y", "-i", str(slideshow.absolute()), "-i", str(combined_audio.absolute()),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest", str(output_file.absolute())
    ], timeout=600, retries=1, step="ses+video mux")

    full_script = " ".join(s["text"] for s in scenes)
    generated_title = data.get("title", topic or scenes[0]["text"][:60])

    # Videoya özel hashtag'ler (DeepSeek'ten) + genel engagement tag'leri
    raw_tags = data.get("hashtags", [])
    if raw_tags:
        video_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:12] if t.strip())
    else:
        # Fallback: trend hashtag'leri + başlık kelimelerinden üret
        title_tags = [f"#{w.lower()}" for w in generated_title.split()[:3] if len(w) > 3]
        video_tags = ", ".join(["#Shorts"] + title_tags + trend_data["hashtags"][1:6])

    # Thumbnail — overlay'li ilk sahneyi kopyala (ayrıca create_thumbnail gerekmez)
    thumb_path = None
    try:
        thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
        shutil.copy2(str(png_files[0]), str(thumb_out))
        thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

    # Geçici dosyaları temizle (disk dolmaması için)
    shutil.rmtree(scene_dir, ignore_errors=True)

    # Kullanılan konuyu kaydet — scheduler aynı haberi tekrar seçmesin
    add_shorts_used_topic(generated_title)

    return {
        "video": f"/api/video/{output_file.name}",
        "thumbnail": thumb_path,
        "script": full_script,
        "title": generated_title,
        "scene_count": len(scenes),
        "suggested_tags": video_tags,
        "suggested_description": f"{full_script[:200]}...\n\n{video_tags.replace(', ', ' ')}",
        "visual_warning": " | ".join(sorted(visual_warnings)) if visual_warnings else "",
    }


from trends import get_trends

THUMB_DIR = Path("thumbnails")
THUMB_DIR.mkdir(exist_ok=True)


def create_thumbnail(photo_bytes: bytes, title: str, out_path: Path, size=(1280, 720), lang="tr"):
    """Haber kanalı stili thumbnail: koyu fotoğraf + sarı bantlar + SON DAKİKA."""
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

    YELLOW = (255, 208,   0)
    RED    = (213,   0,   0)
    BLACK  = ( 17,  17,  17)
    WHITE  = (255, 255, 255)
    CX     = W // 2

    cat_text   = "GÜNDEM"     if lang == "tr" else "BREAKING"
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

    # ① Üst kategori bandı — tek tam genişlik sarı bant
    y1, h1 = 150, 120
    draw.rectangle([(0, y1), (W, y1 + h1)], fill=YELLOW)
    draw.rectangle([(0, y1), (W, y1 + 7)], fill=BLACK)
    draw.rectangle([(0, y1 + h1 - 7), (W, y1 + h1)], fill=BLACK)
    cf = lf(52); af = lf(62)
    draw.text((60, y1 + (h1 - 52) // 2), "»»", font=af, fill=BLACK)
    cw = tw(cat_text, cf)
    draw.text((CX - cw // 2, y1 + (h1 - 52) // 2), cat_text, font=cf, fill=BLACK)
    draw.text((W - 60 - int(tw("««", af)), y1 + (h1 - 52) // 2), "««", font=af, fill=BLACK)

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


@app.post("/api/generate-long-video")
async def generate_long_video(
    topic: str = Form(...),
    api_key: str = Form(...),
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    speed: float = Form(1.0),
    duration_min: int = Form(3),
):
    import json
    import httpx
    from openai import OpenAI

    if not topic.strip():
        raise HTTPException(400, "Konu boş olamaz")
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

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
        # TTS
        wav, dur = await asyncio.to_thread(tts.synthesize,
            _clean_tts_text(scene["text"], lang), lang=lang,
            voice_style=style, total_steps=8, speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        # Görsel hiyerarşisi: DALL-E → Wikimedia Commons → Pexels
        img_path = scene_dir / f"scene_{i}.jpg"
        photo_saved = fetch_scene_visual(scene.get("keyword", topic), "landscape", pexels_key, img_path)

        if not photo_saved:
            await asyncio.to_thread(subprocess.run,
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "color=black:size=1920x1080:rate=1",
                 "-frames:v", "1", str(img_path)],
                capture_output=True, timeout=90,
            )

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

    # Ses ekle
    output_file = OUTPUT_DIR / f"{uid}_long.mp4"
    await asyncio.to_thread(subprocess.run,
        ["ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)],
        check=True, capture_output=True, timeout=120,
    )

    full_script = " ".join(s["text"] for s in scenes)
    total_dur = round(sum(durations), 1)
    lv_title = data.get("title", topic)

    # Hashtag'leri oluştur
    raw_tags = data.get("hashtags", [])
    suggested_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:12] if t)
    if not suggested_tags:
        suggested_tags = f"#{topic.split()[0]}, #belgesel, #eğitim, #keşfet, #teknoloji"

    # Thumbnail
    thumb_path = None
    thumb_out = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), lv_title, thumb_out, size=(1280, 720), lang=lang)
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
    topics_list = trend_data["topics"][:6]
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
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)],
        check=True, capture_output=True, timeout=120,
    )

    full_script = " ".join(s["text"] for s in scenes)
    total_dur = round(sum(durations), 1)
    tnlv_title = data.get("title", f"Günün Trend Haberleri - {today}")

    raw_tags = data.get("hashtags", [])
    suggested_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:15] if t)
    if not suggested_tags:
        suggested_tags = "#gündem, #haberler, #trendler, #güncel, #viral"

    thumb_path = None
    thumb_out = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), tnlv_title, thumb_out, size=(1280, 720), lang=lang)
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
    import datetime
    ts = datetime.datetime.now().strftime("%d %B %Y %H:%M")
    text = f"🚨 *Supertonic Hata*\n─────────────────\n📌 Kaynak: {source}\n❌ {message}\n🕐 {ts}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
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


_IG_DEDUP_HOURS = 4  # aynı başlık bu süreden önce atıldıysa tekrar atma


def _ig_recently_posted(title: str) -> bool:
    """Aynı başlık daha önce Instagram'a atıldıysa True döner (süre sınırı yok)."""
    if not IG_RECENT_FILE.exists():
        return False
    try:
        records = json.loads(IG_RECENT_FILE.read_text())
        title_lower = title.strip().lower()[:80]
        return any(r.get("title", "").lower()[:80] == title_lower for r in records)
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
                    break
                if attempt < 3:
                    await asyncio.sleep(15 * (attempt + 1))  # 15s, 30s, 45s
            if r2 is None or r2.status_code not in (200, 201):
                return None, f"upload failed: {r2.status_code} {r2.text[:300]}"

            # 3. İşlenme tamamlanana kadar bekle (maks 5 dakika)
            for _ in range(30):
                await asyncio.sleep(10)
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

            # 4. Yayınla
            r4 = await client.post(
                f"{graph}/{ig_user_id}/media_publish",
                params={"creation_id": media_id, "access_token": access_token},
                timeout=30,
            )
            if r4.status_code == 200:
                return r4.json().get("id"), ""
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


async def _verify_reel_published(reel_id: str, title: str, video_path: str, caption: str, ig_cfg: dict, source: str, attempt: int = 1):
    """Post'tan 5 dk sonra Instagram API ile reel'i doğrular. Bulunamazsa yeniden dener (maks 3)."""
    await asyncio.sleep(300)  # 5 dakika bekle

    graph = "https://graph.facebook.com/v21.0"
    ig_token = ig_cfg["access_token"]
    ig_user_id = ig_cfg["ig_user_id"]
    confirmed = False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{graph}/{reel_id}",
                params={"fields": "id,timestamp,permalink", "access_token": ig_token},
            )
        confirmed = r.status_code == 200 and "id" in r.json()
    except Exception:
        pass

    if confirmed:
        _ig_mark_posted(title)
        _ig_remove_pending(title)
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[DOĞRULANDI:{source}] {title[:60]}"}))
        return

    # Doğrulanamadı
    if attempt < 3:
        vpath = Path(video_path)
        if vpath.exists():
            reel_id2, reel_err = await post_reel_to_instagram(vpath, caption, ig_user_id, ig_token)
            if reel_id2:
                IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[YENİDEN:{source}] Deneme {attempt + 1}: {title[:60]}"}))
                asyncio.create_task(_verify_reel_published(reel_id2, title, video_path, caption, ig_cfg, source, attempt + 1))
            else:
                await send_telegram_alert(f"IG Yeniden Deneme [{source}]", f"Deneme {attempt + 1} başarısız: {reel_err}\n{title[:60]}")
                if attempt + 1 >= 3:
                    _ig_remove_pending(title)
        else:
            await send_telegram_alert(f"IG Doğrulama [{source}]", f"Video dosyası bulunamadı, yeniden denenemedi:\n{title[:60]}")
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
    Görsel hiyerarşisi: DALL-E → Wikimedia Commons → Pexels.
    (başarı: True,"") | (başarısız: False, "hata nedeni")
    """
    import sys
    width = 1080 if orientation == "portrait" else 1920
    size_key = "portrait" if orientation == "portrait" else "large2x"

    openai_key = get_openai_key()
    if openai_key:
        data = _generate_dalle_image(keyword, orientation, openai_key)
        if data and _save_as_jpeg(data, img_path):
            return True, ""

    data = _fetch_wikimedia_image(keyword, width=width)
    if data and _save_as_jpeg(data, img_path):
        return True, ""

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
                return False, "Pexels 401 key geçersiz"
            if resp.status_code == 429:
                print(f"[GÖRSEL] Pexels kota doldu (429): '{keyword}'", file=sys.stderr)
                _fire_telegram("Pexels", "Aylık kota doldu (429) — limit: 20.000 istek/ay")
                return False, "Pexels 429 kota doldu"
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"].get(size_key) or photos[0]["src"]["large"]
                data = httpx.get(img_url, timeout=15).content
                if _save_as_jpeg(data, img_path):
                    return True, ""
            else:
                print(f"[GÖRSEL] Pexels sonuç yok: '{keyword}' HTTP={resp.status_code}", file=sys.stderr)
                return False, f"Pexels sonuç yok ({resp.status_code})"
        except Exception as e:
            print(f"[GÖRSEL] Pexels hata: '{keyword}' {e}", file=sys.stderr)
            return False, f"Pexels hata: {e}"
    else:
        print(f"[GÖRSEL] Pexels key yok, Wikimedia de bulunamadı: '{keyword}'", file=sys.stderr)
        return False, "Pexels key yok"

    print(f"[GÖRSEL] Tüm kaynaklar başarısız — siyah kare: '{keyword}'", file=sys.stderr)
    return False, "tüm kaynaklar başarısız"


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
             "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)],
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


def load_sched_config():
    if SCHED_CONFIG.exists():
        return json.loads(SCHED_CONFIG.read_text())
    return {"enabled": False, "times": ["07:00", "10:00", "13:00", "17:00", "21:00"]}


def save_sched_log(status: str, message: str, url: str = ""):
    SCHED_LOG.write_text(json.dumps(
        {"status": status, "message": message, "url": url, "ts": time.time()},
        ensure_ascii=False,
    ))
    if status == "error":
        _fire_telegram("TR Shorts", message)


_shorts_job_lock = False

async def auto_shorts_job():
    global _shorts_job_lock
    if _shorts_job_lock:
        save_sched_log("error", "Önceki job hâlâ çalışıyor, bu istek atlandı")
        return
    _shorts_job_lock = True
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
        exclude_str = " | ".join(used_topics) if used_topics else ""

        async with httpx.AsyncClient(timeout=900) as client:
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
                    source="TR-Shorts",
                ))

    except Exception as e:
        save_sched_log("error", f"{e}")
        await send_telegram_alert("TR Shorts", str(e))
    finally:
        _shorts_job_lock = False


async def _post_to_instagram_bg(filename: str, title: str, suggested_tags: str, ig_cfg: dict, source: str = ""):
    """Instagram gönderisi arka planda çalışır — scheduler'ı bloke etmez."""
    # Aynı başlık daha önce atıldıysa veya doğrulama bekliyorsa atla
    if _ig_recently_posted(title) or _ig_is_pending(title):
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": f"[DEDUP:{source}] Zaten atıldı/bekliyor, atlanıyor: {title[:60]}"}))
        return

    ig_user_id = ig_cfg["ig_user_id"]
    ig_token = ig_cfg["access_token"]
    _POWER_TAGS = ["sondakika", "haberler", "gündem", "keşfet", "türkiye", "viral"]
    existing_lower = suggested_tags.lower()
    extra = " ".join(f"#{t}" for t in _POWER_TAGS if t not in existing_lower)
    full_tags = f"{suggested_tags} {extra}".strip() if extra else suggested_tags
    caption = f"{title}\n\nSiz ne düşünüyorsunuz? 👇\n\n{full_tags}"
    ig_log = ""

    if ig_cfg.get("post_reels", True):
        video_file = OUTPUT_DIR / filename
        # Pending işaretle — 5 dk doğrulama penceresi boyunca dedup koruması
        _ig_mark_pending(title)
        reel_id, reel_err = await post_reel_to_instagram(video_file, caption, ig_user_id, ig_token)
        if reel_err:
            ig_log = f"Reels hatası: {reel_err}"
            IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": ig_log}))
            await send_telegram_alert(f"Instagram Reels [{source}]", reel_err)
            _ig_remove_pending(title)  # başarısız oldu, bir sonraki çalışmada yeniden denenebilsin
        else:
            ig_log = f"Reels yüklendi, doğrulama bekleniyor: {reel_id}"
            IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": ig_log}))
            asyncio.create_task(_verify_reel_published(reel_id, title, str(video_file), caption, ig_cfg, source))

    if ig_cfg.get("post_story", False):  # varsayılan False — REELS+is_stories grid'e de düşer
        video_file2 = OUTPUT_DIR / filename
        ok, story_err = await post_story_to_instagram(video_file2, ig_user_id, ig_token)
        story_log = "Story yüklendi" if ok else f"Story hatası: {story_err}"
        combined = f"{ig_log} | {story_log}" if ig_log else story_log
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": combined}))
        if story_err:
            await send_telegram_alert(f"Instagram Story [{source}]", story_err)


def _rebuild_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("auto_"):
            job.remove()
    cfg = load_sched_config()
    if not cfg.get("enabled"):
        return
    for t in cfg.get("times", []):
        try:
            hour, minute = t.strip().split(":")
            scheduler.add_job(
                auto_shorts_job,
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f"auto_{t.replace(':', '')}",
                replace_existing=True,
                max_instances=1,
            )
        except Exception:
            pass


async def auto_long_video_job():
    save_lv_sched_log("running", "Konu seçiliyor…")
    try:
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
        await send_telegram_alert("TR Uzun Video", str(e))


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
    save_lv_en_sched_log("running", "Topic selecting…")
    try:
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
        await send_telegram_alert("EN Uzun Video", str(e))


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


def load_en_shorts_sched_config():
    if EN_SHORTS_SCHED_CONFIG.exists():
        return json.loads(EN_SHORTS_SCHED_CONFIG.read_text())
    return {"enabled": False, "times": ["08:00", "14:00", "20:00"], "voice": "M1", "ig_enabled": False}


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
    save_en_shorts_sched_log("running", "Generating EN short…")
    try:
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
        await send_telegram_alert("EN Shorts", str(e))


def _rebuild_en_shorts_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("en_shorts_"):
            job.remove()
    cfg = load_en_shorts_sched_config()
    if not cfg.get("enabled"):
        return
    for t in cfg.get("times", []):
        try:
            hour, minute = t.strip().split(":")
            scheduler.add_job(
                auto_en_shorts_job,
                CronTrigger(hour=int(hour), minute=int(minute)),
                id=f"en_shorts_{t.replace(':', '')}",
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
    save_tnlv_sched_log("running", "Trend haberleri getiriliyor…")
    try:
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
        await send_telegram_alert("TNLV Video", str(e))


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
        return json.loads(IG_ONLY_TR_SCHED_CONFIG.read_text())
    return {"enabled": False, "times": ["09:00", "14:00", "19:00", "22:00"], "voice": "F1"}


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


_ig_only_tr_job_lock = False


async def auto_ig_only_tr_job():
    global _ig_only_tr_job_lock
    if _ig_only_tr_job_lock:
        save_ig_only_tr_log("error", "Önceki job hâlâ çalışıyor, atlandı")
        return
    _ig_only_tr_job_lock = True
    save_ig_only_tr_log("running", "Video üretiliyor…")
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
        used_topics = get_ig_only_tr_used_topics()
        exclude_str = " | ".join(used_topics) if used_topics else ""

        async with httpx.AsyncClient(timeout=900) as client:
            r = await client.post(
                "http://localhost:8001/api/generate-shorts",
                data={"topic": "", "api_key": api_key, "lang": "tr", "voice": s_voice,
                      "speed": "1.0", "exclude_topics": exclude_str, "region": "TR"},
            )
            if r.status_code != 200:
                save_ig_only_tr_log("error", f"Video üretilemedi: {r.text[:800]}")
                return
            d = r.json()
            add_ig_only_tr_used_topic(d.get("title", ""))
            filename = d["video"].split("/").pop()

        # Sadece Instagram — YouTube'a gönderilmez
        ig_cfg["post_reels"] = True
        vw = d.get("visual_warning", "")
        log_title = d.get("title", "") + (f" ⚠️ {vw}" if vw else "")

        await _post_to_instagram_bg(
            filename=filename,
            title=d.get("title", ""),
            suggested_tags=d.get("suggested_tags", "#Shorts #gündem"),
            ig_cfg=ig_cfg,
            source="IG-Only-TR",
        )
        save_ig_only_tr_log("success", log_title)

    except Exception as e:
        save_ig_only_tr_log("error", str(e))
        await send_telegram_alert("TR Instagram-Only", str(e))
    finally:
        _ig_only_tr_job_lock = False


def _rebuild_ig_only_tr_scheduler():
    for job in scheduler.get_jobs():
        if job.id.startswith("ig_only_tr_"):
            job.remove()
    cfg = load_ig_only_tr_config()
    if not cfg.get("enabled"):
        return
    for t in cfg.get("times", []):
        try:
            hour, minute = t.strip().split(":")
            scheduler.add_job(
                auto_ig_only_tr_job,
                CronTrigger(hour=int(hour), minute=int(minute), timezone="Europe/Istanbul"),
                id=f"ig_only_tr_{t.replace(':', '')}",
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
    times: str = Form(""),
    voice: str = Form("F1"),
):
    times_list = [t.strip() for t in times.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "times": times_list, "voice": voice}
    IG_ONLY_TR_SCHED_CONFIG.write_text(json.dumps(cfg))
    _rebuild_ig_only_tr_scheduler()
    return {"ok": True}


@app.post("/api/ig-only-tr/run-now")
async def run_ig_only_tr_now():
    asyncio.create_task(auto_ig_only_tr_job())
    return {"ok": True}


# ── Startup / Shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    # Servis restart olduysa "running" kalan log'u temizle
    if IG_ONLY_TR_SCHED_LOG.exists():
        try:
            log = json.loads(IG_ONLY_TR_SCHED_LOG.read_text())
            if log.get("status") == "running":
                IG_ONLY_TR_SCHED_LOG.write_text(json.dumps(
                    {"status": "error", "message": "Servis yeniden başlatıldı, job kesildi", "ts": time.time()},
                    ensure_ascii=False,
                ))
        except Exception:
            pass
    scheduler.start()
    _rebuild_scheduler()
    _rebuild_lv_scheduler()
    _rebuild_lv_en_scheduler()
    _rebuild_en_shorts_scheduler()
    _rebuild_tnlv_scheduler()
    _rebuild_ig_only_tr_scheduler()


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
    times: str = Form("07:00,10:00,13:00,17:00,21:00"),
    lang: str = Form("tr"),
    voice: str = Form("F1"),
):
    time_list = [t.strip() for t in times.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "times": time_list, "lang": lang, "voice": voice}
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
    times: str = Form("08:00,14:00,20:00"),
    voice: str = Form("M1"),
    ig_enabled: str = Form("false"),
):
    time_list = [t.strip() for t in times.split(",") if t.strip()]
    cfg = {"enabled": enabled == "true", "times": time_list, "voice": voice, "ig_enabled": ig_enabled == "true"}
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
    global _shorts_job_lock

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

    # Job lock'ları serbest bırak
    _shorts_job_lock = False

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
         "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
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
    caption = f"{title}\n\nSiz ne düşünüyorsunuz? 👇\n\n{full_tags}" if title else full_tags

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
]


@app.get("/api/backup/download")
async def backup_download():
    """Tüm config dosyalarını ZIP olarak indir."""
    import zipfile, io, datetime
    buf = io.BytesIO()
    today = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in _BACKUP_FILES:
            if p.exists():
                zf.write(str(p), p.name)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=supertonic_backup_{today}.zip"},
    )


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
            if name in allowed:
                Path(name).write_bytes(zf.read(name))
                restored.append(name)
            else:
                skipped.append(name)
    return {"ok": True, "restored": restored, "skipped": skipped}


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
