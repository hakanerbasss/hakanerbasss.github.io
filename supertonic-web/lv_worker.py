#!/usr/bin/env python3
"""
Uzun video üretim worker'ı.
uvicorn'dan bağımsız, ayrı OS process olarak çalışır.
Kullanım: python3 lv_worker.py
Job parametrelerini lv_job.json'dan okur, sonucu manual_lv_log.json'a yazar.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ─── Çalışma dizinini script'in yanı sıra tut ────────────────────────────────
WORK_DIR = Path(__file__).parent.resolve()
os.chdir(WORK_DIR)
sys.path.insert(0, str(WORK_DIR))

# ─── Path sabitleri ───────────────────────────────────────────────────────────
OUTPUT_DIR       = WORK_DIR / "outputs"
UPLOAD_DIR       = WORK_DIR / "uploads"
THUMB_DIR        = WORK_DIR / "thumbnails"
MANUAL_LV_LOG    = WORK_DIR / "manual_lv_log.json"
LV_JOB_FILE      = WORK_DIR / "lv_job.json"
PEXELS_CONFIG    = WORK_DIR / "pexels_config.json"
OPENAI_CONFIG    = WORK_DIR / "openai_config.json"
TELEGRAM_CONFIG  = WORK_DIR / "telegram_config.json"

OUTPUT_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
THUMB_DIR.mkdir(exist_ok=True)

LANG_MAP = {
    "tr": "Turkish", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "ru": "Russian", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese (Simplified)", "ar": "Arabic",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish",
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]

# ─── Config okuma ─────────────────────────────────────────────────────────────

def get_pexels_key() -> str:
    if PEXELS_CONFIG.exists():
        try:
            return json.loads(PEXELS_CONFIG.read_text()).get("api_key", "")
        except Exception:
            pass
    return ""


def get_openai_key() -> str:
    if OPENAI_CONFIG.exists():
        try:
            return json.loads(OPENAI_CONFIG.read_text()).get("api_key", "")
        except Exception:
            pass
    return ""


def get_telegram_config() -> dict:
    if TELEGRAM_CONFIG.exists():
        try:
            return json.loads(TELEGRAM_CONFIG.read_text())
        except Exception:
            pass
    return {}


# ─── Log ─────────────────────────────────────────────────────────────────────

def save_lv_log(status: str, result: dict = None, error: str = "", started_at: float = None):
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


# ─── Text helpers ─────────────────────────────────────────────────────────────

def _parse_llm_json(text: str) -> dict:
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
    t = re.sub(r",\s*([}\]])", r"\1", t)
    t = re.sub(r'(?<!\\)\n', ' ', t)
    t = re.sub(r'(?<!\\)\r', '', t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        t2 = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)
        return json.loads(t2)


def _clean_tts_text(text: str, lang: str = "tr") -> str:
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'`[^`]*`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    if lang == "tr":
        text = re.sub(r'(\d)\.(\d{3})\b', r'\1\2', text)
        text = re.sub(r'%\s*(\d+)', r'yüzde \1', text)
        text = re.sub(r'(\d+)°', r'\1 derece', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[#@|_~^\\<>{}[\]]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ─── Görsel / video ───────────────────────────────────────────────────────────

def _fetch_wikimedia_image(keyword: str, width: int = 1920) -> bytes | None:
    try:
        import httpx
        r = httpx.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search",
                "gsrsearch": keyword, "gsrnamespace": "6", "gsrlimit": "5",
                "prop": "imageinfo", "iiprop": "url|mime",
                "iiurlwidth": str(width), "format": "json",
            },
            timeout=10, headers={"User-Agent": "SupertonicBot/1.0"},
        )
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("mime", "").startswith("image/"):
                continue
            url = info.get("thumburl") or info.get("url", "")
            if url:
                return httpx.get(url, timeout=15).content
    except Exception:
        pass
    return None


def _generate_dalle_image(keyword: str, orientation: str, openai_key: str) -> bytes | None:
    import base64
    try:
        import httpx
        from openai import OpenAI as _OAI
        client = _OAI(api_key=openai_key)
        size = "1024x1536" if orientation == "portrait" else "1536x1024"
        resp = client.images.generate(
            model="gpt-image-1-mini",
            prompt=(
                f"Professional high-quality documentary-style photo of {keyword}, "
                "realistic, cinematic lighting, no text, no watermarks, no logos"
            ),
            size=size, n=1,
        )
        b64 = resp.data[0].b64_json
        if b64:
            return base64.b64decode(b64)
        url = getattr(resp.data[0], "url", None)
        if url:
            return httpx.get(url, timeout=30).content
    except Exception:
        pass
    return None


def _save_as_jpeg(data: bytes, img_path: Path) -> bool:
    from PIL import Image
    import io
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.save(str(img_path), "JPEG", quality=92)
        return True
    except Exception:
        return False


def fetch_scene_visual(keyword: str, pexels_key: str, img_path: Path) -> bool:
    import httpx
    openai_key = get_openai_key()
    if openai_key:
        data = _generate_dalle_image(keyword, "landscape", openai_key)
        if data and _save_as_jpeg(data, img_path):
            return True

    data = _fetch_wikimedia_image(keyword, width=1920)
    if data and _save_as_jpeg(data, img_path):
        return True

    if pexels_key:
        try:
            resp = httpx.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "orientation": "landscape", "per_page": 3},
                headers={"Authorization": pexels_key},
                timeout=10,
            )
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"].get("large2x") or photos[0]["src"]["large"]
                data = httpx.get(img_url, timeout=15).content
                if _save_as_jpeg(data, img_path):
                    return True
        except Exception:
            pass
    return False


def fetch_pexels_video(keyword: str, pexels_key: str, raw_path: Path, min_duration: float) -> tuple[bool, str]:
    if not pexels_key:
        return False, "Pexels key yok"
    try:
        import httpx
        resp = httpx.get(
            "https://api.pexels.com/videos/search",
            params={"query": keyword, "orientation": "landscape", "per_page": 5, "size": "medium"},
            headers={"Authorization": pexels_key},
            timeout=15,
        )
        if resp.status_code != 200:
            return False, f"Pexels video HTTP {resp.status_code}"
        videos = resp.json().get("videos", [])
        if not videos:
            return False, "Pexels video sonuç yok"
        suitable = [v for v in videos if v.get("duration", 0) >= max(min_duration - 1, 2)]
        video = (suitable or videos)[0]
        vfiles = video.get("video_files", [])
        # Landscape (w > h) tercih et
        landscape = [f for f in vfiles if f.get("width", 0) > f.get("height", 0)]
        candidates = landscape or vfiles
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


# ─── Banner overlay'leri ──────────────────────────────────────────────────────

def overlay_lv_title_banner(photo_path: Path, title: str) -> None:
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        img = PILImage.open(str(photo_path)).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        fp = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
        font_big = ImageFont.truetype(fp, 56) if fp else ImageFont.load_default()
        font_sm  = ImageFont.truetype(fp, 32) if fp else ImageFont.load_default()
        overlay = PILImage.new("RGBA", (1920, 180), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (1920, 180)], fill=(10, 10, 20, 210))
        img.paste(PILImage.new("RGB", (1920, 180), (10, 10, 20)), (0, 0), mask=overlay.split()[3])
        words = title.split()
        line1, line2 = [], []
        for w in words:
            if draw.textlength(" ".join(line1 + [w]), font=font_big) < 1800:
                line1.append(w)
            else:
                line2.append(w)
        draw.text((40, 20), " ".join(line1), fill=(255, 220, 0), font=font_big, stroke_width=2, stroke_fill=(0, 0, 0))
        if line2:
            draw.text((40, 90), " ".join(line2[:8]), fill=(255, 220, 0), font=font_big, stroke_width=2, stroke_fill=(0, 0, 0))
        img.save(str(photo_path), "JPEG", quality=90)
    except Exception:
        pass


def overlay_lv_subscribe_banner(photo_path: Path) -> None:
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
        img = PILImage.open(str(photo_path)).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        fp = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
        font = ImageFont.truetype(fp, 58) if fp else ImageFont.load_default()
        overlay = PILImage.new("RGBA", (1920, 160), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (1920, 160)], fill=(10, 10, 20, 220))
        img.paste(PILImage.new("RGB", (1920, 160), (10, 10, 20)), (0, 920), mask=overlay.split()[3])
        text = "👍  Beğen         🔔  Abone Ol"
        tw = draw.textlength(text, font=font)
        draw.text(((1920 - tw) // 2, 940), text, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        img.save(str(photo_path), "JPEG", quality=90)
    except Exception:
        pass


def create_thumbnail(photo_bytes: bytes, title: str, out_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    import io
    W, H = 1280, 720
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB").resize((W, H), Image.LANCZOS)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    fp = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)
    def lf(sz):
        if fp:
            try: return ImageFont.truetype(fp, sz)
            except Exception: pass
        return ImageFont.load_default()
    words = title.upper().split()
    lines, line = [], []
    for w in words:
        if draw.textlength(" ".join(line + [w]), font=lf(52)) < W - 60:
            line.append(w)
        else:
            if line: lines.append(" ".join(line))
            line = [w]
    if line: lines.append(" ".join(line))
    y = 60
    for ln in lines[:3]:
        draw.text((30, y), ln, fill=(255, 208, 0), font=lf(52), stroke_width=2, stroke_fill=(0, 0, 0))
        y += 70
    img.save(str(out_path), "JPEG", quality=90)


# ─── Telegram video gönderimi (sync) ─────────────────────────────────────────

def send_telegram_video_sync(video_path: Path, title: str, description: str, tags: str) -> None:
    import html as _html
    import httpx
    cfg = get_telegram_config()
    token   = cfg.get("bot_token", "").strip()
    chat_id = cfg.get("chat_id", "").strip()
    if not token or not chat_id:
        return
    parts = []
    if title:       parts.append(f"<b>{_html.escape(title)}</b>")
    if description: parts.append(_html.escape(description[:800]))
    if tags:        parts.append(_html.escape(tags[:300]))
    caption = "\n\n".join(parts)[:1024]
    try:
        with open(video_path, "rb") as vf:
            httpx.post(
                f"https://api.telegram.org/bot{token}/sendVideo",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", "supports_streaming": "true"},
                files={"video": (video_path.name, vf, "video/mp4")},
                timeout=300,
            )
    except Exception as e:
        print(f"[TELEGRAM] Gönderim hatası: {e}", file=sys.stderr)


# ─── Ana üretim fonksiyonu (sync) ─────────────────────────────────────────────

def generate_long_video(job: dict) -> dict:
    from openai import OpenAI
    from supertonic import TTS

    topic        = job.get("topic", "")
    api_key      = job["api_key"]
    lang         = job.get("lang", "tr")
    voice        = job.get("voice", "M1")
    speed        = float(job.get("speed", 1.0))
    duration_min = int(job.get("duration_min", 5))
    use_video    = job.get("use_video", "false")

    use_video_mode = use_video == "true"
    pexels_key = get_pexels_key()
    lang_name = LANG_MAP.get(lang, "Turkish")

    # If scenes already provided (e.g. from file upload), skip AI generation
    if "scenes" in job:
        scenes = job["scenes"]
        data = {
            "title": job.get("title", topic or "Video"),
            "description": job.get("description", ""),
            "hashtags": job.get("hashtags", []),
            "scenes": scenes,
        }
    else:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
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
- NEVER use phrases that imply real footage or real photos exist. Narration must describe events in storytelling form, never reference visuals.
- FIRST scene text MUST use a CURIOSITY-GAP hook — create suspense, ask a question, or give a partial reveal. The viewer MUST feel compelled to keep watching.
- LAST scene text MUST end with (in {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!"
- Each scene: 2-3 sentences packed with facts, context and detail
- hashtags: 8-12 relevant tags, ALWAYS include "belgesel", "eğitim", "keşfet". No # symbol, NO spaces within a tag.
- keyword: English, specific and visual"""

        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000,
        )
        data = _parse_llm_json(response.choices[0].message.content)
        scenes = data["scenes"]

    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = TTS(auto_download=True)
    style = tts.get_voice_style(voice_name=voice)
    font_path = next((f for f in FONT_CANDIDATES if Path(f).exists()), None)

    audio_files, clip_files, durations = [], [], []

    for i, scene in enumerate(scenes):
        # TTS
        wav, dur = tts.synthesize(
            _clean_tts_text(scene["text"], lang),
            lang=lang, voice_style=style, total_steps=8, speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        img_path = scene_dir / f"scene_{i}.jpg"
        raw_vid = None

        # İlk sahne her zaman görsel (banner için)
        if use_video_mode and pexels_key and i > 0:
            vid_ok, vid_result = fetch_pexels_video(
                scene.get("keyword", topic), pexels_key,
                scene_dir / f"rawvid_{i}.mp4", dur_val,
            )
            if vid_ok:
                raw_vid = Path(vid_result)
            else:
                fetch_scene_visual(scene.get("keyword", topic), pexels_key, img_path)
        else:
            fetch_scene_visual(scene.get("keyword", topic), pexels_key, img_path)

        if not img_path.exists() and not raw_vid:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:size=1920x1080:rate=1",
                 "-frames:v", "1", str(img_path)],
                capture_output=True, timeout=90,
            )

        # Banner overlay
        if img_path.exists():
            if i == 0:
                overlay_lv_title_banner(img_path, data.get("title", topic))
            elif i == len(scenes) - 1:
                overlay_lv_subscribe_banner(img_path)

        # Altyazı dosyası
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

        clip_path = scene_dir / f"clip_{i}.mp4"
        if raw_vid:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(raw_vid), "-t", str(dur_val),
                 "-vf", drawtext, "-r", "30", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, timeout=180,
            )
        else:
            subprocess.run(
                ["ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-t", str(dur_val),
                 "-vf", drawtext, "-r", "30", "-c:v", "libx264",
                 "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", str(clip_path)],
                check=True, capture_output=True, timeout=180,
            )
        clip_files.append(clip_path)

    # Ses birleştir
    audio_list = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    audio_list.write_text("".join(f"file '{af.absolute()}'\n" for af in audio_files))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c", "copy", str(combined_audio)],
        check=True, capture_output=True, timeout=180,
    )

    # Klip birleştir
    clip_list = scene_dir / "clip_list.txt"
    merged = scene_dir / "merged.mp4"
    clip_list.write_text("".join(f"file '{cp.absolute()}'\n" for cp in clip_files))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list), "-c", "copy", str(merged)],
        check=True, capture_output=True, timeout=180,
    )

    # Ses ekle
    output_file = OUTPUT_DIR / f"{uid}_long.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(merged), "-i", str(combined_audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", str(output_file)],
        check=True, capture_output=True, timeout=120,
    )

    lv_title = data.get("title", topic)
    raw_tags = data.get("hashtags", [])
    suggested_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:12] if t)
    if not suggested_tags:
        suggested_tags = f"#{topic.split()[0]}, #belgesel, #eğitim, #keşfet, #teknoloji"

    thumb_path = None
    try:
        first_img = scene_dir / "scene_0.jpg"
        if first_img.exists():
            thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
            create_thumbnail(first_img.read_bytes(), lv_title, thumb_out)
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
        "script": " ".join(s["text"] for s in scenes),
        "duration_sec": round(sum(durations), 1),
        "scene_count": len(scenes),
    }


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    if not LV_JOB_FILE.exists():
        print("[LV WORKER] lv_job.json bulunamadı, çıkılıyor.", file=sys.stderr)
        sys.exit(1)

    try:
        job = json.loads(LV_JOB_FILE.read_text())
    except Exception as e:
        print(f"[LV WORKER] lv_job.json okunamadı: {e}", file=sys.stderr)
        sys.exit(1)

    started_at = job.get("started_at", time.time())
    save_lv_log("running", started_at=started_at)
    print(f"[LV WORKER] Başladı: {job.get('topic', '?')}", file=sys.stderr)

    try:
        result = generate_long_video(job)
        save_lv_log("done", result=result)
        print(f"[LV WORKER] Tamamlandı: {result.get('title', '?')}", file=sys.stderr)

        # Telegram'a gönder
        video_file = OUTPUT_DIR / result["video"].split("/")[-1]
        if video_file.exists():
            send_telegram_video_sync(
                video_file,
                result.get("title", ""),
                result.get("description", ""),
                result.get("suggested_tags", ""),
            )
            print("[LV WORKER] Telegram'a gönderildi.", file=sys.stderr)
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[LV WORKER] HATA:\n{err}", file=sys.stderr)
        save_lv_log("error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
