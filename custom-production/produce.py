#!/usr/bin/env python3
"""
produce.py — Tamamen bağımsız short üretim pipeline'ı (Claude tarafı).

Akış: script (JSON) -> her sahne için supertonic TTS + custom_visuals kartı
-> ffmpeg ile sahne klipleri -> concat + ses mux -> final.mp4

Sunucuya HİÇBİR bağımlılığı yok (DeepSeek yok, Pexels yok, app.py'ye dokunmuyor).
Bitmiş video, ayrı bir adımda /api/upload-raw-video ile sunucuya yüklenir ve
mevcut /api/shorts/send-instagram + /api/yt/upload ile yayınlanır.

Kullanım:
  python3 produce.py script.json out/final.mp4 --platform youtube
"""
import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import custom_visuals as cv

ASSETS = Path(__file__).parent / "assets"
ENDCARD_TR = ASSETS / "endcard_tr.jpg"
ENDCARD_YT = ASSETS / "endcard_youtube.jpg"


def clean_tts_text(text: str) -> str:
    import re
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'%\s*(\d+)', r'yüzde \1', text)
    text = re.sub(r'(\d+)°', r'\1 derece', text)
    return re.sub(r'\s+', ' ', text).strip()


def run(cmd, timeout=120):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg hata: {r.stderr.decode(errors='replace')[-2000:]}")


def produce(script: dict, out_path: Path, platform: str = "youtube", voice: str = "M1", lang: str = "tr"):
    work = Path("/tmp/produce_" + uuid.uuid4().hex)
    work.mkdir(parents=True)

    scenes = script["scenes"]
    badge_text = script.get("badge_text", "BİLGİ")
    emphasis_word = script.get("emphasis_word", "")
    brand = script.get("brand", cv.BRAND_DEFAULT)

    from supertonic import TTS
    tts = TTS(auto_download=True)
    style = tts.get_voice_style(voice_name=voice)

    audio_files, clip_files = [], []
    total = len(scenes) + 1  # +1 = kapanış kartı

    for i, scene in enumerate(scenes):
        text = scene["text"]
        wav, dur = tts.synthesize(
            text=clean_tts_text(text), lang=lang, voice_style=style,
            total_steps=8, speed=1.0,
        )
        dur_val = float(dur[0]) if hasattr(dur, "__getitem__") else float(dur)
        audio_path = work / f"audio_{i}.wav"
        tts.save_audio(wav, str(audio_path))
        audio_files.append(audio_path)

        clip_path = work / f"clip_{i}.mp4"
        ok = cv.render_scene_clip(
            text, i, total, dur_val, clip_path,
            badge_text=badge_text, emphasis_word=emphasis_word, lang=lang, brand=brand,
        )
        if not ok:
            # Animasyonlu kayıt başarısızsa statik karta düş, sonra loop'la
            img_path = work / f"scene_{i}.jpg"
            ok2 = cv.render_scene_card(
                text, i, total, img_path,
                badge_text=badge_text, emphasis_word=emphasis_word, lang=lang, brand=brand,
            )
            if not ok2:
                from PIL import Image
                Image.new("RGB", (1080, 1920), (15, 18, 28)).save(str(img_path), "JPEG", quality=90)
            run([
                "ffmpeg", "-y", "-loop", "1", "-i", str(img_path), "-t", str(dur_val),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_path),
            ], timeout=90)
        clip_files.append(clip_path)

    # Kapanış: sabit marka endcard'ı (platforma göre) + 2sn sessiz ses
    endcard_src = ENDCARD_YT if platform == "youtube" else ENDCARD_TR
    endcard_dur = 2.0
    endcard_img = work / "endcard.jpg"
    shutil.copy2(str(endcard_src), str(endcard_img))
    endcard_clip = work / "clip_end.mp4"
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(endcard_img), "-t", str(endcard_dur),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(endcard_clip),
    ], timeout=90)
    clip_files.append(endcard_clip)
    endcard_audio = work / "audio_end.wav"
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(endcard_dur),
        "-c:a", "pcm_s16le", str(endcard_audio),
    ], timeout=30)
    audio_files.append(endcard_audio)

    # Ses birleştir
    audio_list = work / "audio_list.txt"
    audio_list.write_text("".join(f"file '{a.absolute()}'\n" for a in audio_files))
    combined_audio = work / "combined.wav"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list),
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", str(combined_audio),
    ], timeout=120)

    # Video birleştir
    clip_list = work / "clip_list.txt"
    clip_list.write_text("".join(f"file '{c.absolute()}'\n" for c in clip_files))
    slideshow = work / "slideshow.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clip_list),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-r", "30", "-vsync", "cfr", "-pix_fmt", "yuv420p", str(slideshow),
    ], timeout=300)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(slideshow), "-i", str(combined_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", "30", "-vsync", "cfr",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        "-movflags", "+faststart", "-shortest", str(out_path),
    ], timeout=300)

    cv.close_browser()
    shutil.rmtree(work, ignore_errors=True)
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("script_json")
    ap.add_argument("out_mp4")
    ap.add_argument("--platform", default="youtube", choices=["youtube", "instagram"])
    ap.add_argument("--voice", default="M1")
    ap.add_argument("--lang", default="tr")
    args = ap.parse_args()

    script = json.loads(Path(args.script_json).read_text())
    out = produce(script, Path(args.out_mp4), platform=args.platform, voice=args.voice, lang=args.lang)
    print(f"OK -> {out}")
