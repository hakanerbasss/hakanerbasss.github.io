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
import os
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

# Sunucudaki gerçek Edge TTS (E-Ahmet/E-Emel) sesini kullanmak için —
# supertonic yerel/offline ama daha düşük kalite; edge çok daha doğal.
PANEL_BASE = os.environ.get("PANEL_BASE", "https://panel.wizaicorp.com")
PANEL_COOKIE = os.environ.get("PANEL_COOKIE", "")  # "session=xxxxx" formatında


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


def _synth_edge(text: str, voice: str, out_path: Path) -> float:
    """/api/tts-only ile gerçek Edge sesi (E-Ahmet/E-Emel). PANEL_COOKIE
    ortam değişkeni gerekli. Başarısız olursa istisna fırlatır -> çağıran
    supertonic'e düşer."""
    import httpx
    if not PANEL_COOKIE:
        raise RuntimeError("PANEL_COOKIE ayarlanmamış")
    r = httpx.post(
        f"{PANEL_BASE}/api/tts-only",
        data={"text": clean_tts_text(text), "voice": voice, "speed": "1.0"},
        headers={"Cookie": PANEL_COOKIE},
        timeout=30,
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return float(r.headers.get("X-Duration-Seconds", "0"))


def _synth_scenes(scenes, work: Path, voice: str, lang: str):
    """Her sahne için (audio_path, duration) listesi döner. Önce Edge TTS
    dener (PANEL_COOKIE varsa), sahne bazında başarısız olursa o sahne için
    supertonic'e düşer (tamamı iptal olmaz)."""
    results = []
    _tts_local = {"tts": None, "style": None}

    def _local(text, i):
        if _tts_local["tts"] is None:
            from supertonic import TTS
            _tts_local["tts"] = TTS(auto_download=True)
            _tts_local["style"] = _tts_local["tts"].get_voice_style(voice_name="M1")
        wav, dur = _tts_local["tts"].synthesize(
            text=clean_tts_text(text), lang=lang, voice_style=_tts_local["style"],
            total_steps=8, speed=1.0,
        )
        dur_val = float(dur[0]) if hasattr(dur, "__getitem__") else float(dur)
        audio_path = work / f"audio_{i}.wav"
        _tts_local["tts"].save_audio(wav, str(audio_path))
        return audio_path, dur_val

    edge_voice = voice if voice.startswith("E-") else "E-Ahmet"
    for i, scene in enumerate(scenes):
        text = scene["text"]
        audio_path = work / f"audio_{i}.wav"
        try:
            dur_val = _synth_edge(text, edge_voice, audio_path)
            if dur_val <= 0:
                raise RuntimeError("süre 0 döndü")
        except Exception:
            audio_path, dur_val = _local(text, i)
        results.append((audio_path, dur_val))
    return results


def produce(script: dict, out_path: Path, platform: str = "youtube", voice: str = "E-Ahmet", lang: str = "tr",
            _cache: dict = None):
    """_cache: {'clip_files':[...], 'audio_files':[...]} veriliriyse sahne
    üretimini (TTS+görsel) atlar, sadece kapanış kartını değiştirip finali
    mux eder — aynı script'ten YouTube+Instagram ikisini üretirken TTS'i
    2 kez çağırmamak için (bkz. produce_dual)."""
    work = Path("/tmp/produce_" + uuid.uuid4().hex)
    work.mkdir(parents=True)

    scenes = script["scenes"]
    badge_text = script.get("badge_text", "BİLGİ")
    emphasis_word = script.get("emphasis_word", "")
    brand = script.get("brand", cv.BRAND_DEFAULT)

    total = len(scenes) + 1  # +1 = kapanış kartı

    if _cache and _cache.get("clip_files"):
        clip_files = list(_cache["clip_files"])
        audio_files = list(_cache["audio_files"])
    else:
        audio_files, clip_files = [], []

        # Açılış (hook) kartı: başlık ANINDA büyük/çarpıcı belirir — video
        # kapağı/thumbnail ilk kareden alındığı için scroll durdurma gücü
        # burada. Karaoke altyazılı sahneler ondan SONRA başlar.
        title = script.get("title", scenes[0]["text"][:70] if scenes else "")
        hook_dur = 1.35
        hook_clip = work / "clip_hook.mp4"
        hook_ok = cv.render_hook_card(
            title, hook_clip, badge_text=badge_text, emphasis_word=emphasis_word,
            duration=hook_dur, lang=lang, brand=brand,
        )
        if hook_ok:
            hook_audio = work / "audio_hook.wav"
            run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(hook_dur),
                "-c:a", "pcm_s16le", str(hook_audio),
            ], timeout=30)
            clip_files.append(hook_clip)
            audio_files.append(hook_audio)

        synth = _synth_scenes(scenes, work, voice, lang)
        for i, (scene, (audio_path, dur_val)) in enumerate(zip(scenes, synth)):
            text = scene["text"]
            audio_files.append(audio_path)
            clip_path = _render_scene(text, i, total, dur_val, work, badge_text, emphasis_word, lang, brand)
            clip_files.append(clip_path)
        if _cache is not None:
            _cache["clip_files"] = list(clip_files)
            _cache["audio_files"] = list(audio_files)
            _cache["work"] = work  # dosyalar silinmesin diye referans tutuluyor

    return _finish(script, clip_files, audio_files, out_path, platform, work)


def _render_scene(text, i, total, dur_val, work, badge_text, emphasis_word, lang, brand):
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
    return clip_path


def _finish(script, content_clip_files, content_audio_files, out_path: Path, platform: str, work: Path):
    """İçerik sahneleri hazır (klip+ses) — kapanış kartını platforma göre
    ekleyip finali mux eder. produce() ve produce_dual() ikisi de burayı
    çağırır."""
    clip_files = list(content_clip_files)
    audio_files = list(content_audio_files)

    endcard_src = ENDCARD_YT if platform == "youtube" else ENDCARD_TR
    endcard_dur = 2.0
    endcard_img = work / f"endcard_{platform}.jpg"
    shutil.copy2(str(endcard_src), str(endcard_img))
    endcard_clip = work / f"clip_end_{platform}.mp4"
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(endcard_img), "-t", str(endcard_dur),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(endcard_clip),
    ], timeout=90)
    clip_files.append(endcard_clip)
    endcard_audio = work / f"audio_end_{platform}.wav"
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(endcard_dur),
        "-c:a", "pcm_s16le", str(endcard_audio),
    ], timeout=30)
    audio_files.append(endcard_audio)

    # Ses birleştir
    audio_list = work / f"audio_list_{platform}.txt"
    audio_list.write_text("".join(f"file '{a.absolute()}'\n" for a in audio_files))
    combined_audio = work / f"combined_{platform}.wav"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list),
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", str(combined_audio),
    ], timeout=120)

    # Video birleştir
    clip_list = work / f"clip_list_{platform}.txt"
    clip_list.write_text("".join(f"file '{c.absolute()}'\n" for c in clip_files))
    slideshow = work / f"slideshow_{platform}.mp4"
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
    return out_path


def produce_dual(script: dict, out_youtube: Path, out_instagram: Path, voice: str = "E-Ahmet", lang: str = "tr"):
    """Aynı senaryoyu TEK SEFER seslendirip/render edip, sadece kapanış
    kartı farklı iki final video üretir (YouTube: Abone Ol, Instagram:
    Takip Et). TTS ve sahne render'ını 2 katına çıkarmaz."""
    cache: dict = {}
    yt_path = produce(script, out_youtube, platform="youtube", voice=voice, lang=lang, _cache=cache)
    ig_path = produce(script, out_instagram, platform="instagram", voice=voice, lang=lang, _cache=cache)
    cv.close_browser()
    shutil.rmtree(cache["work"], ignore_errors=True)
    return yt_path, ig_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("script_json")
    ap.add_argument("out_mp4")
    ap.add_argument("--platform", default="youtube", choices=["youtube", "instagram"])
    ap.add_argument("--voice", default="E-Ahmet")
    ap.add_argument("--lang", default="tr")
    args = ap.parse_args()

    script = json.loads(Path(args.script_json).read_text())
    out = produce(script, Path(args.out_mp4), platform=args.platform, voice=args.voice, lang=args.lang)
    print(f"OK -> {out}")
