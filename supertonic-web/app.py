import os
import uuid
import asyncio
import subprocess
import json
import time
import re
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "trace": traceback.format_exc()},
    )

OUTPUT_DIR = Path("outputs")
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

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
    # Markdown kod bloğunu soy
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0]
    t = t.strip()
    # En dıştaki { ... } arasını al
    start = t.find("{")
    end   = t.rfind("}") + 1
    if start >= 0 and end > start:
        t = t[start:end]
    # Trailing comma temizle: ,] ve ,}
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t)


def get_tts():
    global tts_model
    if tts_model is None:
        tts_model = TTS(auto_download=True)
    return tts_model


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

    wav, duration = tts.synthesize(
        text=text,
        lang=lang,
        voice_style=style,
        total_steps=8,
        speed=speed,
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
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1",
         "-f", "wav", str(audio_extracted)],
        check=True, capture_output=True
    )

    # transkript
    whisper_m = get_whisper()
    result = whisper_m.transcribe(str(audio_extracted))
    transcript = result["text"]

    # çeviri istenmişse
    if translate_to and translate_to != lang:
        transcript = GoogleTranslator(source="auto", target=translate_to).translate(transcript)
        lang = translate_to

    # TTS
    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)
    wav, _ = tts.synthesize(
        text=transcript,
        lang=lang,
        voice_style=style,
        total_steps=8,
        speed=speed,
    )
    tts.save_audio(wav, str(tts_audio))

    # sesi videoyla birleştir
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-i", str(tts_audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-shortest", str(output_video)],
        check=True, capture_output=True
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
):
    import json
    import httpx
    from openai import OpenAI

    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    pexels_key = get_pexels_key()

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Trend verileri al
    trend_data = get_trends(region_code="TR", lang=lang)
    trend_topics = ", ".join(trend_data["topics"][:12])
    yt_tags = ", ".join(trend_data.get("yt_trending_tags", [])[:10])
    trend_tags = ", ".join(trend_data["hashtags"][:10])

    lang_name = LANG_MAP.get(lang, "Turkish")
    exclude_instruction = ""
    if exclude_topics.strip():
        exclude_instruction = f"\nIMPORTANT - Do NOT cover these topics (already posted today):\n{exclude_topics}\nPick a DIFFERENT topic from the trending list.\n"
    topic_instruction = (
        f"Topic: {topic}\n"
        f"Use these TODAY'S real trending news to make the content timely and relevant:\n{trend_topics}"
        if topic.strip() else
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
- FIRST scene text MUST start with a hook: a shocking statement OR a question that creates curiosity (e.g. "Biliyor muydunuz?", "Şok gelişme!", "Peki ya şimdi?"). This is critical for retention.
- LAST scene text MUST end with a call to action: "Abone olmayı ve beğenmeyi unutma!" (in {lang_name})
- keyword: English, 2-3 words, visual and specific (e.g. "mountain sunset", "busy city street")
- Total narration under 55 seconds
- hashtags: 8-12 tags specific to THIS video's topic (mix of {lang_name} and English), always include "Shorts", no # symbol, NO spaces within a tag (e.g. "sondakika" not "son dakika", "breaking news" → "breakingnews")"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    data = _parse_llm_json(response.choices[0].message.content)
    scenes = data["scenes"]

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    audio_files = []
    png_files = []
    durations = []

    for i, scene in enumerate(scenes):
        wav, dur = tts.synthesize(
            text=scene["text"],
            lang=lang,
            voice_style=style,
            total_steps=8,
            speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        # Görsel hiyerarşisi: DALL-E → Wikimedia Commons → Pexels
        png_path = scene_dir / f"scene_{i}.jpg"
        keyword = scene.get("keyword", topic)
        photo_saved = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)

        # Fallback: PIL ile garantili siyah arka plan
        if not photo_saved:
            try:
                from PIL import Image as PILImage
                img = PILImage.new("RGB", (1080, 1920), color=(20, 20, 30))
                img.save(str(png_path), "JPEG", quality=92)
            except Exception:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", "color=black:size=1080x1920:rate=1",
                    "-frames:v", "1", str(png_path)
                ], capture_output=True)

        png_files.append(png_path)

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
            f":x=(w-text_w)/2:y=h-th-140:line_spacing=12"
            f":box=1:boxcolor=black@0.55:boxborderw=18"
        )
        if font_path:
            drawtext += f":fontfile={font_path}"

        try:
            result = subprocess.run([
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(png),
                "-t", str(dur),
                "-vf", drawtext,
                "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
            ], capture_output=True)
            if result.returncode != 0:
                # drawtext hata verdiyse metinsiz olarak dene
                subprocess.run([
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(png),
                    "-t", str(dur),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                    "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
                ], check=True, capture_output=True)
        except Exception as fe:
            raise RuntimeError(f"ffmpeg scene {i} failed: {fe}")
        clip_files.append(clip_path)

    # Ses dosyalarını birleştir
    audio_list_file = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list_file, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list_file), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True
    )

    # Video kliplerini birleştir
    clip_list_file = scene_dir / "clip_list.txt"
    with open(clip_list_file, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")

    slideshow = scene_dir / "slideshow.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list_file),
        "-c", "copy", str(slideshow)
    ], check=True, capture_output=True)

    # Ses ekle
    output_file = OUTPUT_DIR / f"{uid}_shorts.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(slideshow), "-i", str(combined_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)
    ], check=True, capture_output=True)

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

    # Thumbnail (ilk sahnenin fotoğrafından)
    thumb_path = None
    try:
        thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
        create_thumbnail(png_files[0].read_bytes(), generated_title, thumb_out, size=(1080, 1920), lang=lang)
        thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

    return {
        "video": f"/api/video/{output_file.name}",
        "thumbnail": thumb_path,
        "script": full_script,
        "title": generated_title,
        "scene_count": len(scenes),
        "suggested_tags": video_tags,
        "suggested_description": f"{full_script[:200]}...\n\n{video_tags.replace(', ', ' ')}",
    }


from trends import get_trends

THUMB_DIR = Path("thumbnails")
THUMB_DIR.mkdir(exist_ok=True)


def create_thumbnail(photo_bytes: bytes, title: str, out_path: Path, size=(1280, 720), lang="tr"):
    """
    Haber kanalı stili thumbnail: PIL ile arka planı karartır,
    FFmpeg drawtext ile sarı başlık + kırmızı SON DAKİKA bandı ekler.
    """
    from PIL import Image
    import io, textwrap, uuid as _uuid, tempfile

    W, H = size
    is_portrait = H > W

    # 1. PIL: yeniden boyutlandır + karart
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    img = img.resize(size, Image.LANCZOS)

    overlay = Image.new("RGBA", size, (0, 0, 0, 145))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay).convert("RGB")

    uid = _uuid.uuid4().hex[:8]
    tmp_dir = Path(tempfile.gettempdir())
    tmp_bg = tmp_dir / f"thumb_bg_{uid}.jpg"
    img.save(str(tmp_bg), "JPEG", quality=92)

    # 2. FFmpeg: metin overlay
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    font_path = next((f for f in font_candidates if Path(f).exists()), None)

    title_fs  = 78 if is_portrait else 68
    badge_fs  = 46 if is_portrait else 38
    band_h    = 100 if is_portrait else 82
    line_h    = title_fs + 18
    max_chars = 18 if is_portrait else 26

    lines = textwrap.wrap(title, width=max_chars)[:(4 if is_portrait else 3)]
    badge_text = "SON DAKIKA" if lang == "tr" else "BREAKING NEWS"

    # Satırları ayrı dosyalara yaz (Türkçe karakter desteği)
    line_files = []
    for i, line in enumerate(lines):
        lf = tmp_dir / f"thumb_line_{uid}_{i}.txt"
        lf.write_text(line, encoding="utf-8")
        line_files.append(lf)

    vf_parts = []

    # Kırmızı alt bant
    vf_parts.append(
        f"drawbox=x=0:y=ih-{band_h}:w=iw:h={band_h}:color=0xD20A0A@1:t=fill"
    )

    # Badge metni (ASCII — Türkçe karakter yok)
    badge_cmd = (
        f"drawtext=text='{badge_text}'"
        f":fontsize={badge_fs}:fontcolor=white"
        f":x=(w-tw)/2:y=h-{band_h//2}-th/2"
    )
    if font_path:
        badge_cmd += f":fontfile='{font_path}'"
    vf_parts.append(badge_cmd)

    # Başlık satırları (alttan yukarı)
    for i, lf in enumerate(line_files):
        y_expr = f"ih-{band_h}-{(len(line_files) - i) * line_h}-10"
        line_cmd = (
            f"drawtext=textfile='{lf}'"
            f":fontsize={title_fs}:fontcolor=#FFE000"
            f":x=(w-tw)/2:y={y_expr}"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.9"
        )
        if font_path:
            line_cmd += f":fontfile='{font_path}'"
        vf_parts.append(line_cmd)

    vf = ",".join(vf_parts)

    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(tmp_bg),
        "-vf", vf,
        "-frames:v", "1", "-q:v", "2",
        str(out_path),
    ], capture_output=True)

    # Temizlik
    tmp_bg.unlink(missing_ok=True)
    for lf in line_files:
        lf.unlink(missing_ok=True)

    # FFmpeg başarısızsa düz resmi kaydet
    if not out_path.exists():
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
- FIRST scene text MUST start with a hook: a shocking statement or question (e.g. "Biliyor muydunuz?", "Şok gelişme!"). Critical for viewer retention.
- LAST scene text MUST end with: "Abone olmayı ve beğenmeyi unutma!" (in {lang_name})
- Each scene: 2-3 sentences packed with facts, context and detail — NOT simple or vague
- Cover the topic thoroughly: introduction, key facts, interesting details, historical context, conclusion
- hashtags: 8-12 relevant tags mixing {lang_name} and English terms, no # symbol, NO spaces within a tag (e.g. "yapayZeka" or "yapayZeka", never "yapay zeka")
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
        wav, dur = tts.synthesize(
            text=scene["text"], lang=lang, voice_style=style,
            total_steps=8, speed=speed,
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
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "color=black:size=1920x1080:rate=1",
                "-frames:v", "1", str(img_path)
            ], capture_output=True)

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

        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-t", str(dur_val),
            "-vf", drawtext,
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
        ], check=True, capture_output=True)
        clip_files.append(clip_path)

    # Sesleri birleştir
    audio_list = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True
    )

    # Klipleri birleştir
    clip_list = scene_dir / "clip_list.txt"
    merged = scene_dir / "merged.mp4"
    with open(clip_list, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(merged)],
        check=True, capture_output=True
    )

    # Ses ekle
    output_file = OUTPUT_DIR / f"{uid}_long.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)
    ], check=True, capture_output=True)

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
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), lv_title, thumb_out, size=(1280, 720), lang=lang)
            thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

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
- VERY FIRST scene of the entire video MUST start with a hook (shocking statement or question). Critical for retention.
- VERY LAST scene MUST end with: "Abone olmayı ve beğenmeyi unutma!" (in {lang_name})
- Each segment: exactly 2 scenes, informative and engaging
- hashtags: 10-15 tags mixing {lang_name} and English, always include news-related tags, no # symbol, NO spaces within a tag (e.g. "sondakika" not "son dakika")
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
        wav, dur = tts.synthesize(
            text=scene["text"], lang=lang, voice_style=style,
            total_steps=8, speed=speed,
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
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "color=black:size=1920x1080:rate=1",
                "-frames:v", "1", str(img_path)
            ], capture_output=True)

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

        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-t", str(dur_val),
            "-vf", drawtext,
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
        ], check=True, capture_output=True)
        clip_files.append(clip_path)

    audio_list = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    with open(audio_list, "w") as f:
        for af in audio_files:
            f.write(f"file '{af.absolute()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True
    )

    clip_list = scene_dir / "clip_list.txt"
    merged = scene_dir / "merged.mp4"
    with open(clip_list, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp.absolute()}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(merged)],
        check=True, capture_output=True
    )

    output_file = OUTPUT_DIR / f"{uid}_tnlv.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)
    ], check=True, capture_output=True)

    full_script = " ".join(s["text"] for s in scenes)
    total_dur = round(sum(durations), 1)
    tnlv_title = data.get("title", f"Günün Trend Haberleri - {today}")

    raw_tags = data.get("hashtags", [])
    suggested_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:15] if t)
    if not suggested_tags:
        suggested_tags = "#gündem, #haberler, #trendler, #güncel, #viral"

    thumb_path = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), tnlv_title, thumb_out, size=(1280, 720), lang=lang)
            thumb_path = f"/api/thumbnail/{thumb_out.name}"
    except Exception:
        pass

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

            # 2. Video bytes'ı yükle
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
            if r2.status_code not in (200, 201):
                return None, f"upload failed: {r2.status_code} {r2.text[:200]}"

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
            # 1. Resumable session (VIDEO story)
            r1 = await client.post(
                f"{graph}/{ig_user_id}/media",
                params={
                    "media_type": "VIDEO",
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

            # 2. Video bytes yükle
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
            if r2.status_code not in (200, 201):
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


def fetch_scene_visual(keyword: str, orientation: str, pexels_key: str, img_path: Path) -> bool:
    """
    Görsel hiyerarşisi: DALL-E → Wikimedia Commons → Pexels.
    Tüm görseller PIL ile JPEG'e dönüştürülür (SVG/GIF/WebP sorunlarını önler).
    Başarılıysa img_path'e yazar ve True döner.
    """
    width = 1080 if orientation == "portrait" else 1920
    size_key = "portrait" if orientation == "portrait" else "large2x"

    openai_key = get_openai_key()
    if openai_key:
        data = _generate_dalle_image(keyword, orientation, openai_key)
        if data and _save_as_jpeg(data, img_path):
            return True

    data = _fetch_wikimedia_image(keyword, width=width)
    if data and _save_as_jpeg(data, img_path):
        return True

    if pexels_key:
        try:
            resp = httpx.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "orientation": orientation, "per_page": 3},
                headers={"Authorization": pexels_key},
                timeout=10,
            )
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"].get(size_key) or photos[0]["src"]["large"]
                data = httpx.get(img_url, timeout=15).content
                if _save_as_jpeg(data, img_path):
                    return True
        except Exception:
            pass

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
    ig_user_id: str = Form(...),
    access_token: str = Form(...),
    post_reels: str = Form("true"),
    post_story: str = Form("true"),
):
    cfg = {
        "ig_user_id": ig_user_id.strip(),
        "access_token": access_token.strip(),
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
        return {"ok": False, "error": f"{r.status_code}: {r.text[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
async def get_yt_analytics(days: int = 28):
    """YouTube Analytics API'dan kanal istatistiklerini çeker."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import datetime

    if not TOKEN_FILE.exists():
        raise HTTPException(401, "YouTube hesabı bağlı değil")

    creds_data = json.loads(TOKEN_FILE.read_text())
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    if creds.expired and creds.refresh_token:
        import google.auth.transport.requests
        creds.refresh(google.auth.transport.requests.Request())
        TOKEN_FILE.write_text(creds.to_json())

    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days - 1)

    try:
        analytics = build("youtubeAnalytics", "v2", credentials=creds)

        # Günlük istatistikler
        daily = analytics.reports().query(
            ids="channel==MINE",
            startDate=str(start_date),
            endDate=str(end_date),
            metrics="views,estimatedMinutesWatched,subscribersGained",
            dimensions="day",
            sort="day",
        ).execute()

        # Video bazlı performans (top 10)
        top_videos = analytics.reports().query(
            ids="channel==MINE",
            startDate=str(start_date),
            endDate=str(end_date),
            metrics="views,estimatedMinutesWatched",
            dimensions="video",
            sort="-views",
            maxResults=10,
        ).execute()

        # Video başlıklarını çek
        yt = build("youtube", "v3", credentials=creds)
        video_ids = []
        for row in top_videos.get("rows", []):
            video_ids.append(row[0])

        video_titles = {}
        if video_ids:
            vresp = yt.videos().list(
                part="snippet",
                id=",".join(video_ids[:10]),
            ).execute()
            for item in vresp.get("items", []):
                video_titles[item["id"]] = item["snippet"]["title"]

        # Toplam özet
        total_views = sum(row[1] for row in daily.get("rows", []))
        total_watch_min = sum(row[2] for row in daily.get("rows", []))
        total_subs = sum(row[3] for row in daily.get("rows", []))

        return {
            "summary": {
                "views": int(total_views),
                "watch_hours": round(total_watch_min / 60, 1),
                "subs_gained": int(total_subs),
                "period_days": days,
            },
            "daily": [
                {"date": row[0], "views": int(row[1]), "watch_min": int(row[2]), "subs": int(row[3])}
                for row in daily.get("rows", [])
            ],
            "top_videos": [
                {
                    "id": row[0],
                    "title": video_titles.get(row[0], row[0]),
                    "views": int(row[1]),
                    "watch_min": int(row[2]),
                }
                for row in top_videos.get("rows", [])
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

    from google.auth.transport.requests import Request as GRequest
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GRequest())
        token_file.write_text(creds.to_json())
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


async def auto_shorts_job():
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
                save_sched_log("error", f"Video üretilemedi: {r.text[:300]}")
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
            save_sched_log("success", d.get("title", ""), result.get("url", ""))

            # 3. Instagram'a gönder — arka planda, job'u bloke etmez
            ig_cfg = get_ig_config()
            if ig_cfg.get("ig_user_id") and ig_cfg.get("access_token"):
                asyncio.create_task(_post_to_instagram_bg(
                    filename=filename,
                    title=d.get("title", ""),
                    suggested_tags=d.get("suggested_tags", "#Shorts #gündem"),
                    ig_cfg=ig_cfg,
                ))

    except Exception as e:
        save_sched_log("error", f"{e}")


async def _post_to_instagram_bg(filename: str, title: str, suggested_tags: str, ig_cfg: dict):
    """Instagram gönderisi arka planda çalışır — scheduler'ı bloke etmez."""
    ig_user_id = ig_cfg["ig_user_id"]
    ig_token = ig_cfg["access_token"]
    caption = f"{title}\n\n{suggested_tags}"
    ig_log = ""

    if ig_cfg.get("post_reels", True):
        video_file = OUTPUT_DIR / filename
        reel_id, reel_err = await post_reel_to_instagram(video_file, caption, ig_user_id, ig_token)
        ig_log = f"Reels hatası: {reel_err}" if reel_err else f"Reels yüklendi: {reel_id}"
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": ig_log}))

    if ig_cfg.get("post_story", True):
        video_file2 = OUTPUT_DIR / filename
        ok, story_err = await post_story_to_instagram(video_file2, ig_user_id, ig_token)
        story_log = "Story yüklendi" if ok else f"Story hatası: {story_err}"
        combined = f"{ig_log} | {story_log}" if ig_log else story_log
        IG_LOG.write_text(json.dumps({"ts": time.time(), "msg": combined}))


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
                save_lv_sched_log("error", f"Video üretilemedi: {r.text[:300]}")
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
                save_lv_en_sched_log("error", f"Video failed: {r.text[:300]}")
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
                save_tnlv_sched_log("error", f"Video üretilemedi: {r.text[:300]}")
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


@app.on_event("startup")
async def startup_event():
    scheduler.start()
    _rebuild_scheduler()
    _rebuild_lv_scheduler()
    _rebuild_lv_en_scheduler()
    _rebuild_tnlv_scheduler()


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


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
