"""
Video üretimi — DeepSeek içerik + Supertonic TTS + görseller + ffmpeg.

supertonic-web'deki /api/generate-shorts mantığının bağımsız, kendi kendine
yeten hâli. Senkron çalışır; router thread havuzunda çağırır ki sunucu üretim
sırasında kilitlenmesin. ffmpeg adımları gerçek hatayı gösteren run_ffmpeg ile.
"""
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from openai import OpenAI

from config import (BASE_DIR, OUTPUT_DIR, UPLOAD_DIR, THUMB_DIR, LANG_MAP,
                    get_pexels_key)
from ffmpeg_util import run_ffmpeg
from trends import get_trends
from visuals import (fetch_scene_visual, find_font, try_ken_burns_clip,
                     overlay_first_scene_banner, overlay_like_subscribe_banner)

ENDCARD = BASE_DIR / "static" / "endcard_tr.jpg"

_tts_model = None


def get_tts():
    global _tts_model
    if _tts_model is None:
        from supertonic import TTS
        _tts_model = TTS(auto_download=True)
    return _tts_model


def _parse_llm_json(text: str) -> dict:
    t = text.strip()
    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0]
    t = t.strip()
    start, end = t.find("{"), t.rfind("}") + 1
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
    return re.sub(r'\s+', ' ', text).strip()


def _build_prompt(topic, lang, trend_topics, trend_tags, yt_tags) -> str:
    lang_name = LANG_MAP.get(lang, "Turkish")
    if topic.strip():
        topic_instruction = (
            f"Topic: {topic}\n"
            f"Use these TODAY'S real trending news to make the content timely and relevant:\n{trend_topics}"
        )
    elif lang == "en":
        topic_instruction = (
            f"Choose ONE of these TODAY'S trending news topics for a US/English-speaking audience:\n{trend_topics}\n"
            f"PRIORITY ORDER: 1) Trump or US President news  2) US politics  "
            f"3) Major US foreign policy  4) Breaking global news impacting the US  5) Any other trending topic.\n"
            f"Always pick the HIGHEST priority category available."
        )
    else:
        topic_instruction = f"Choose ONE of these TODAY'S trending news and make a Short about it:\n{trend_topics}"
    yt_tag_instruction = f"\nYouTube trending hashtags RIGHT NOW (include relevant ones): {yt_tags}" if yt_tags else ""
    return f"""Create a YouTube Shorts video.
Narration language: {lang_name}
{topic_instruction}
Suggested hashtags: {trend_tags}{yt_tag_instruction}

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
- In scene text: NEVER use abbreviations. Always write the full name so TTS reads correctly.
- FIRST scene text MUST use a CURIOSITY-GAP hook — never state the answer directly. Create suspense.
- LAST scene text MUST end with this call to action (translated naturally to {lang_name}): "Beğenmek ve abone olmak için 2 saniye ver!"
- keyword: English, 2-3 words, visual and specific
- Total narration under 55 seconds
- hashtags: 8-12 tags specific to THIS video (mix of {lang_name} and English), always include "Shorts", no # symbol, NO spaces within a tag
"""


def generate_short(api_key: str, topic: str = "", lang: str = "tr",
                   voice: str = "M1", region: str = "TR", speed: float = 1.0) -> dict:
    """Trend haberden Short üretir. Üretilen dosya bilgisini döndürür."""
    pexels_key = get_pexels_key()
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    trend_data = get_trends(region_code=region.upper(), lang=lang)
    trend_topics = ", ".join(trend_data["topics"][:12])
    yt_tags = ", ".join(trend_data.get("yt_trending_tags", [])[:10])
    trend_tags = ", ".join(trend_data["hashtags"][:10])

    prompt = _build_prompt(topic, lang, trend_topics, trend_tags, yt_tags)

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
                raise RuntimeError("DeepSeek geçerli JSON döndürmedi (3 deneme)")

    scenes = data["scenes"]
    uid = uuid.uuid4().hex
    scene_dir = UPLOAD_DIR / uid
    scene_dir.mkdir()

    tts = get_tts()
    style = tts.get_voice_style(voice_name=voice)

    audio_files, png_files, durations = [], [], []
    visual_warnings: set = set()

    for i, scene in enumerate(scenes):
        wav, dur = tts.synthesize(
            text=_clean_tts_text(scene["text"], lang), lang=lang,
            voice_style=style, total_steps=8, speed=speed,
        )
        dur_val = float(dur[0]) if hasattr(dur, '__getitem__') else float(dur)
        audio_path = scene_dir / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)
        durations.append(dur_val)

        is_last_scene = (i == len(scenes) - 1)
        png_path = scene_dir / f"scene_{i}.jpg"
        photo_saved = False

        if is_last_scene and ENDCARD.exists():
            shutil.copy2(str(ENDCARD), str(png_path))
            photo_saved = True
        elif not is_last_scene:
            keyword = scene.get("keyword", topic)
            photo_saved, visual_err = fetch_scene_visual(keyword, "portrait", pexels_key, png_path)
            if not photo_saved and visual_err:
                visual_warnings.add(visual_err)

        if not photo_saved:
            try:
                from PIL import Image as PILImage
                PILImage.new("RGB", (1080, 1920), color=(20, 20, 30)).save(str(png_path), "JPEG", quality=92)
            except Exception:
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:size=1080x1920:rate=1",
                    "-frames:v", "1", str(png_path)
                ], capture_output=True, timeout=90)

        png_files.append(png_path)

    title = data.get("title", topic or scenes[0]["text"][:60])

    if png_files:
        try:
            overlay_first_scene_banner(png_files[0], title, lang=lang)
        except Exception:
            pass

    endcard_used = ENDCARD.exists()
    if png_files and not endcard_used:
        try:
            overlay_like_subscribe_banner(png_files[-1])
        except Exception:
            pass

    font_path = find_font()
    clip_files = []
    for i, (png, dur, scene) in enumerate(zip(png_files, durations, scenes)):
        clip_path = scene_dir / f"clip_{i}.mp4"
        is_last = (i == len(scenes) - 1)

        if is_last and endcard_used:
            run_ffmpeg([
                "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(dur),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
            ], timeout=90, step=f"endcard sahnesi")
            clip_files.append(clip_path)
            continue

        # Metni satırlara böl
        words = scene["text"].split()
        lines, line = [], []
        for w in words:
            if len(" ".join(line + [w])) > 38:
                lines.append(" ".join(line)); line = [w]
            else:
                line.append(w)
        if line:
            lines.append(" ".join(line))
        text_file = scene_dir / f"text_{i}.txt"
        text_file.write_text("\n".join(lines), encoding="utf-8")

        drawtext = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"drawtext=textfile={text_file.absolute()}"
            f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
            f":box=1:boxcolor=black@0.55:boxborderw=18"
        )
        if font_path:
            drawtext += f":fontfile={font_path}"

        if not try_ken_burns_clip(png, float(dur), clip_path, text_file, font_path):
            result = subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(dur),
                "-vf", drawtext, "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
            ], capture_output=True, timeout=90)
            if result.returncode != 0:
                run_ffmpeg([
                    "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(dur),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                    "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path)
                ], timeout=90, step=f"sahne {i}")
        clip_files.append(clip_path)

    # Ses birleştir — pcm re-encode (concat -c copy uyumsuzluk hatasını önler)
    audio_list_file = scene_dir / "audio_list.txt"
    combined_audio = scene_dir / "combined.wav"
    audio_list_file.write_text("".join(f"file '{af.absolute()}'\n" for af in audio_files))
    run_ffmpeg(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list_file),
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", str(combined_audio)],
        timeout=120, step="ses birleştirme"
    )

    # Klipleri birleştir → slideshow
    clip_list_file = scene_dir / "clip_list.txt"
    clip_list_file.write_text("".join(f"file '{cp.absolute()}'\n" for cp in clip_files))
    slideshow = scene_dir / "slideshow.mp4"
    run_ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list_file.absolute()),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-r", "30", "-vsync", "cfr", "-pix_fmt", "yuv420p", str(slideshow.absolute())
    ], timeout=600, step="slideshow")

    # Ses + video birleştir
    output_file = OUTPUT_DIR / f"{uid}_shorts.mp4"
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(slideshow.absolute()), "-i", str(combined_audio.absolute()),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart", "-shortest", str(output_file.absolute())
    ], timeout=600, retries=1, step="ses+video mux")

    full_script = " ".join(s["text"] for s in scenes)
    raw_tags = data.get("hashtags", [])
    if raw_tags:
        video_tags = ", ".join(f"#{t.lstrip('#').replace(' ', '')}" for t in raw_tags[:12] if t.strip())
    else:
        title_tags = [f"#{w.lower()}" for w in title.split()[:3] if len(w) > 3]
        video_tags = ", ".join(["#Shorts"] + title_tags + trend_data["hashtags"][1:6])

    # Thumbnail — ilk sahneyi kopyala
    thumb_path = None
    try:
        thumb_out = THUMB_DIR / f"{uid}_thumb.jpg"
        shutil.copy2(str(png_files[0]), str(thumb_out))
        thumb_path = thumb_out.name
    except Exception:
        pass

    return {
        "filename": output_file.name,
        "title": title,
        "tags": video_tags,
        "description": f"{full_script[:200]}...\n\n{video_tags.replace(', ', ' ')}",
        "script": full_script,
        "scene_count": len(scenes),
        "thumbnail": thumb_path,
        "warning": " | ".join(sorted(visual_warnings)) if visual_warnings else "",
    }
