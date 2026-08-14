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
import hashlib
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


def _theme_idx_for(script: dict) -> int:
    """Video'ya özel, DETERMİNİSTİK tema seçimi — aynı script tekrar
    üretilirse aynı renk çıkar, ama farklı script/video farklı renk alır.
    ÖNCEDEN açılış kartı hep theme_idx=0'a (lacivert/altın) sabitti — art
    arda üretilen videolar hep aynı renkte açılıyordu (kullanıcı geri
    bildirimi). Python'un yerleşik hash()'i string'lerde süreçten
    sürece rastgele (PYTHONHASHSEED) olduğu için KULLANILMIYOR — md5 gibi
    kararlı bir hash lazım."""
    import custom_visuals as cv
    key = f"{script.get('title','')}|{script.get('badge_text','')}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h, 16) % len(cv.THEMES)


def _synth_one(text: str, out_path: Path, voice: str, lang: str):
    """Tek bir metin için TTS (hook narrasyonu / kapanış CTA cümlesi gibi
    sahne-dışı parçalar için) — önce Edge dener, olmazsa yerel supertonic'e
    düşer. _synth_scenes'teki sahne-bazlı fallback ile aynı mantık, tek
    metin için ayrıca kullanılabilir hale getirildi."""
    edge_voice = voice if voice.startswith("E-") else "E-Ahmet"
    try:
        dur_val = _synth_edge(text, edge_voice, out_path)
        if dur_val <= 0:
            raise RuntimeError("süre 0 döndü")
        return out_path, dur_val
    except Exception:
        from supertonic import TTS
        tts = TTS(auto_download=True)
        style = tts.get_voice_style(voice_name="M1")
        wav, dur = tts.synthesize(
            text=clean_tts_text(text), lang=lang, voice_style=style,
            total_steps=8, speed=1.0,
        )
        dur_val = float(dur[0]) if hasattr(dur, "__getitem__") else float(dur)
        tts.save_audio(wav, str(out_path))
        return out_path, dur_val


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

    theme_idx = _theme_idx_for(script)

    if _cache and _cache.get("clip_files"):
        clip_files = list(_cache["clip_files"])
        audio_files = list(_cache["audio_files"])
    else:
        audio_files, clip_files = [], []

        # Açılış (hook) kartı: başlık ANINDA büyük/çarpıcı belirir + eski
        # sistemdeki kalın renkli banda karşılık gelen 'ribbon' şerit.
        title = script.get("title", scenes[0]["text"][:70] if scenes else "")
        hook_text = script.get("hook_text") or title
        ribbon_text = script.get("ribbon_text") or badge_text

        # SESLİ açılış: ÖNCEDEN hook kartı süresince (1.35-2.2sn) tamamen
        # SESSİZDİ (anullsrc), gerçek anlatım ancak sahne 1'de başlıyordu —
        # kullanıcı geri bildirimi: ilk saniyelerde ölü sessizlik "geçme"
        # riski yaratıyor. Şimdi başlık/hook cümlesi TTS ile seslendirilip
        # görsel süre konuşma süresine göre ayarlanıyor (kapak/thumbnail
        # güvenliği için yine de en az 2.0sn tutuluyor).
        hook_audio = work / "audio_hook.wav"
        hook_speech_dur = 0.0
        try:
            _, hook_speech_dur = _synth_one(hook_text, hook_audio, voice, lang)
        except Exception:
            hook_speech_dur = 0.0
        if hook_speech_dur > 0 and hook_audio.exists():
            hook_dur = max(2.0, hook_speech_dur + 0.3)
        else:
            hook_dur = 2.2
            run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(hook_dur),
                "-c:a", "pcm_s16le", str(hook_audio),
            ], timeout=30)

        hook_clip = work / "clip_hook.mp4"
        hook_ok = cv.render_hook_card(
            title, hook_clip, badge_text=badge_text, emphasis_word=emphasis_word,
            duration=hook_dur, lang=lang, brand=brand, ribbon_text=ribbon_text,
            theme_idx=theme_idx,
        )
        if hook_ok:
            clip_files.append(hook_clip)
            audio_files.append(hook_audio)
            if _cache is not None:
                # YouTube'un/Instagram'ın otomatik kapak seçimine güvenmek
                # yerine hook kartının tam oturmuş halinden (1.0s) sabit bir
                # JPEG kapak çıkarıyoruz. thumbnail_filename ile
                # /api/yt/upload'a verilebilir.
                thumb_path = work / "thumb_cover.jpg"
                try:
                    run([
                        "ffmpeg", "-y", "-ss", "1.0", "-i", str(hook_clip),
                        "-frames:v", "1", "-q:v", "2", str(thumb_path),
                    ], timeout=30)
                    if thumb_path.exists() and thumb_path.stat().st_size > 0:
                        _cache["thumb_path"] = thumb_path
                except Exception:
                    pass

        synth = _synth_scenes(scenes, work, voice, lang)
        for i, (scene, (audio_path, dur_val)) in enumerate(zip(scenes, synth)):
            text = scene["text"]
            audio_files.append(audio_path)
            clip_path = _render_scene(
                text, i, total, dur_val, work, badge_text, emphasis_word, lang, brand,
                theme_idx=(i + theme_idx) % len(cv.THEMES),
            )
            clip_files.append(clip_path)
        if _cache is not None:
            _cache["clip_files"] = list(clip_files)
            _cache["audio_files"] = list(audio_files)
            _cache["work"] = work  # dosyalar silinmesin diye referans tutuluyor

    return _finish(script, clip_files, audio_files, out_path, platform, work, voice=voice, lang=lang, theme_idx=theme_idx)


def _render_scene(text, i, total, dur_val, work, badge_text, emphasis_word, lang, brand, theme_idx=None, name=None):
    clip_path = work / f"{name or f'clip_{i}'}.mp4"
    ok = cv.render_scene_clip(
        text, i, total, dur_val, clip_path,
        badge_text=badge_text, emphasis_word=emphasis_word, lang=lang, brand=brand,
        theme_idx=theme_idx,
    )
    if not ok:
        # Animasyonlu kayıt başarısızsa statik karta düş, sonra loop'la
        img_path = work / f"{name or f'scene_{i}'}.jpg"
        ok2 = cv.render_scene_card(
            text, i, total, img_path,
            badge_text=badge_text, emphasis_word=emphasis_word, lang=lang, brand=brand,
            theme_idx=theme_idx,
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


def _finish(script, content_clip_files, content_audio_files, out_path: Path, platform: str, work: Path,
            voice: str = "E-Ahmet", lang: str = "tr", theme_idx: int = 0):
    """İçerik sahneleri hazır (klip+ses) — SESLİ kapanış çağrısı (CTA) +
    kapanış kartını platforma göre ekleyip finali mux eder. produce() ve
    produce_dual() ikisi de burayı çağırır. platform'a göre farklı (YouTube:
    abone ol, Instagram: takip et) çağrı cümlesi kullanıldığı için bu adım
    PAYLAŞILAN _cache'in DIŞINDA, her platform için ayrı ayrı çalışır."""
    clip_files = list(content_clip_files)
    audio_files = list(content_audio_files)
    scenes = script.get("scenes", [])
    total = len(scenes) + 1
    badge_text = script.get("badge_text", "BİLGİ")
    brand = script.get("brand", cv.BRAND_DEFAULT)

    # SESLİ kapanış çağrısı: ÖNCEDEN kapanışta sadece SESSİZ statik bir
    # "Abone Ol/Takip Et" görseli vardı, teşvik edici bir SÖZ yoktu —
    # kullanıcı geri bildirimi: "bizi takip etmeye devam edin" tarzı bir
    # bitiş cümlesi olmalı. Platforma göre ayrı metin (YT: abone, IG: takip
    # + yorum teşviki), script içinden override edilebilir.
    if platform == "youtube":
        cta_text = script.get("closing_text_youtube") or (
            "Bunun gibi daha fazla pratik bilgi için kanalımıza abone olmayı unutmayın."
        )
        cta_badge = "ABONE OL"
    else:
        cta_text = script.get("closing_text_instagram") or (
            "Bunun gibi daha fazla pratik bilgi için bizi takip etmeyi unutmayın, "
            "siz ne düşünüyorsunuz, yorumlarda buluşalım."
        )
        cta_badge = "TAKİP ET"

    cta_audio = work / f"audio_cta_{platform}.wav"
    cta_dur = 0.0
    try:
        _, cta_dur = _synth_one(cta_text, cta_audio, voice, lang)
    except Exception:
        cta_dur = 0.0
    if cta_dur > 0 and cta_audio.exists():
        cta_clip = _render_scene(
            cta_text, len(scenes), total, cta_dur, work, cta_badge, "", lang, brand,
            theme_idx=(len(scenes) + theme_idx) % len(cv.THEMES), name=f"clip_cta_{platform}",
        )
        clip_files.append(cta_clip)
        audio_files.append(cta_audio)
    # cta_dur == 0 ise (TTS iki yöntemde de başarısız oldu) sessizce atlanır
    # — kapanış kartı yine de eklenir, sadece sesli CTA olmaz.

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
    Takip Et). TTS ve sahne render'ını 2 katına çıkarmaz.

    Dönen 3. değer (thumb_path): hook kartının 1.0s'deki sabit karesinden
    çıkarılmış JPEG kapak — /api/yt/upload'a thumbnail_filename olarak
    verilmek üzere (önce /api/upload-raw-video benzeri bir görsel yükleme
    ucundan panele yüklenmesi gerekir, bkz. SISTEM_BILGI.md). None ise
    hook kartı render edilememiş demektir, YouTube kendi otomatik kapağını
    kullanır (artık ilk kare boş olmadığı için bu da makul bir sonuç verir)."""
    cache: dict = {}
    yt_path = produce(script, out_youtube, platform="youtube", voice=voice, lang=lang, _cache=cache)
    ig_path = produce(script, out_instagram, platform="instagram", voice=voice, lang=lang, _cache=cache)
    cv.close_browser()
    thumb_out = None
    src_thumb = cache.get("thumb_path")
    if src_thumb and Path(src_thumb).exists():
        thumb_out = out_youtube.parent / "thumb_cover.jpg"
        shutil.copy2(str(src_thumb), str(thumb_out))
    shutil.rmtree(cache["work"], ignore_errors=True)
    return yt_path, ig_path, thumb_out


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
