"""Supertonic TTS sarmalayıcı — singleton model, WAV çıktı, MP3 birleştirme."""

import asyncio
import os
import subprocess
from pathlib import Path

from app.config import settings, VOICES, PREVIEW_TEXT

_model = None


def _get_model():
    global _model
    if _model is None:
        from supertonic import TTS
        _model = TTS(auto_download=True)
    return _model


def synthesize_sync(text: str, output_wav: str,
                    voice: str | None = None, lang: str | None = None) -> float:
    """Sync — thread executor'da çağırılmalı."""
    import functools
    tts = _get_model()
    v = voice or settings.tts_voice
    l = lang or settings.tts_lang
    style = tts.get_voice_style(voice_name=v)
    wav, dur = tts.synthesize(
        text=text,
        lang=l,
        voice_style=style,
        total_steps=settings.tts_steps,
        speed=settings.tts_speed,
    )
    dur_val = float(dur[0]) if hasattr(dur, "__getitem__") else float(dur)
    tts.save_audio(wav, output_wav)
    return dur_val


async def synthesize(text: str, output_wav: str,
                     voice: str | None = None, lang: str | None = None) -> float:
    """Async sarmalayıcı."""
    import functools
    loop = asyncio.get_event_loop()
    fn = functools.partial(synthesize_sync, text, output_wav, voice, lang)
    return await loop.run_in_executor(None, fn)


async def generate_preview(voice: str) -> str:
    """Seçili ses için ~10 saniyelik önizleme MP3 üretir. Dosya yolunu döner."""
    if voice not in VOICES:
        voice = settings.tts_voice

    out_mp3 = str(settings.previews_dir / f"preview_{voice}.mp3")
    tmp_wav = out_mp3 + ".tmp.wav"

    await synthesize(PREVIEW_TEXT, tmp_wav, voice=voice)

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_wav,
         "-c:a", "libmp3lame", "-q:a", "3", "-ar", "44100", out_mp3],
        capture_output=True, timeout=60,
    )
    try:
        os.remove(tmp_wav)
    except OSError:
        pass

    if r.returncode != 0:
        raise RuntimeError(f"Önizleme encode hatası: {r.stderr.decode()[-500:]}")

    return out_mp3


def concat_wav_to_mp3(wav_files: list[str], output_mp3: str) -> None:
    """WAV chunk listesini tek MP3'e birleştirir."""
    list_path = output_mp3 + ".list.txt"
    with open(list_path, "w") as f:
        for wav in wav_files:
            f.write(f"file '{os.path.abspath(wav)}'\n")

    tmp_wav = output_mp3 + ".tmp.wav"
    r1 = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", tmp_wav],
        capture_output=True, timeout=7200,
    )
    if r1.returncode != 0:
        raise RuntimeError(f"FFmpeg concat hatası: {r1.stderr.decode()[-1000:]}")

    r2 = subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_wav,
         "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100", output_mp3],
        capture_output=True, timeout=600,
    )
    if r2.returncode != 0:
        raise RuntimeError(f"FFmpeg MP3 encode hatası: {r2.stderr.decode()[-1000:]}")

    for f in (tmp_wav, list_path):
        try:
            os.remove(f)
        except OSError:
            pass
