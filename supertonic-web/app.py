import os
import uuid
import asyncio
import subprocess
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import traceback
import aiofiles

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
):
    import json
    import cairosvg
    from openai import OpenAI

    if not topic.strip():
        raise HTTPException(400, "Konu boş olamaz")
    if not api_key.strip():
        raise HTTPException(400, "API key eksik")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    lang_name = LANG_MAP.get(lang, "Turkish")
    prompt = f"""Create a YouTube Shorts video about: {topic}
Narration language: {lang_name}

Return ONLY valid JSON, no markdown, no explanation:
{{
  "scenes": [
    {{
      "text": "narration for this scene (1-2 short sentences)",
      "svg": "<svg width='1080' height='1920' xmlns='http://www.w3.org/2000/svg'>...</svg>"
    }}
  ]
}}

Rules:
- 5 to 7 scenes
- SVG: 1080x1920 portrait, dark background, large readable text, simple shapes and gradients
- No external images, fonts, or URLs in SVG — only basic SVG elements
- Consistent color theme across all scenes
- Total narration under 55 seconds"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    content = response.choices[0].message.content.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    data = json.loads(content.strip())
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

        png_path = scene_dir / f"scene_{i}.png"
        cairosvg.svg2png(
            bytestring=scene["svg"].encode(),
            write_to=str(png_path),
            output_width=1080,
            output_height=1920,
        )
        png_files.append(png_path)

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

    # Slideshow oluştur
    concat_file = scene_dir / "video_list.txt"
    with open(concat_file, "w") as f:
        for png, dur in zip(png_files, durations):
            f.write(f"file '{png.absolute()}'\n")
            f.write(f"duration {dur:.3f}\n")
        f.write(f"file '{png_files[-1].absolute()}'\n")

    slideshow = scene_dir / "slideshow.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(slideshow)
    ], check=True, capture_output=True)

    # Ses ekle
    output_file = OUTPUT_DIR / f"{uid}_shorts.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(slideshow), "-i", str(combined_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_file)
    ], check=True, capture_output=True)

    full_script = " ".join(s["text"] for s in scenes)

    return {
        "video": f"/api/video/{output_file.name}",
        "script": full_script,
        "scene_count": len(scenes),
    }


CONFIG_FILE = Path("yt_config.json")
TOKEN_FILE = Path("yt_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_yt_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


@app.post("/api/yt/config")
async def save_yt_config(client_id: str = Form(...), client_secret: str = Form(...)):
    CONFIG_FILE.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))
    return {"ok": True}


@app.get("/api/yt/config")
async def get_yt_config():
    cfg = load_yt_config()
    return {"configured": bool(cfg), "authorized": TOKEN_FILE.exists()}


VERIFIER_FILE = Path("yt_verifier.txt")


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


@app.post("/api/yt/upload")
async def upload_youtube(
    filename: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy: str = Form("private"),
):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not TOKEN_FILE.exists():
        raise HTTPException(401, "YouTube hesabı bağlı değil")

    video_path = OUTPUT_DIR / filename
    if not video_path.exists():
        raise HTTPException(404, "Video bulunamadı")

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    youtube = build("youtube", "v3", credentials=creds)

    tag_list = [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tag_list,
            "categoryId": "22",
        },
        "status": {"privacyStatus": privacy},
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = req.next_chunk()

    return {"youtube_id": response["id"], "url": f"https://youtu.be/{response['id']}"}


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


app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
