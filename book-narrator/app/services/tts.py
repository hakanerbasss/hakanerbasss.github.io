"""Supertonic TTS sarmalayıcı.

instube/generator.py'deki aynı pattern: singleton model, WAV çıktı.
Model ilk çağrıda yüklenir (auto_download=True).
"""

import asyncio
from pathlib import Path
from app.config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        from supertonic import TTS
        _model = TTS(auto_download=True)
    return _model


def synthesize_sync(text: str, output_wav: str) -> float:
    """Metni WAV dosyasına yazar, süreyi (saniye) döner. Sync — thread'de çağırılmalı."""
    tts = _get_model()
    style = tts.get_voice_style(voice_name=settings.tts_voice)
    wav, dur = tts.synthesize(
        text=text,
        lang=settings.tts_lang,
        voice_style=style,
        total_steps=settings.tts_steps,
        speed=settings.tts_speed,
    )
    dur_val = float(dur[0]) if hasattr(dur, "__getitem__") else float(dur)
    tts.save_audio(wav, output_wav)
    return dur_val


async def synthesize(text: str, output_wav: str) -> float:
    """Async sarmalayıcı — event loop'u bloklamaz."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, synthesize_sync, text, output_wav)


def concat_wav_to_mp3(wav_files: list[str], output_mp3: str) -> None:
    """WAV chunk listesini tek MP3'e birleştirir. FFmpeg gerektirir."""
    import subprocess
    import tempfile
    import os

    list_path = output_mp3 + ".list.txt"
    with open(list_path, "w") as f:
        for wav in wav_files:
            f.write(f"file '{os.path.abspath(wav)}'\n")

    # Önce WAV concat, sonra MP3 encode — iki adım daha güvenilir
    tmp_wav = output_mp3 + ".tmp.wav"
    r1 = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "1", tmp_wav],
        capture_output=True, timeout=3600
    )
    if r1.returncode != 0:
        raise RuntimeError(f"FFmpeg concat hatası: {r1.stderr.decode()[-1000:]}")

    r2 = subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_wav,
         "-c:a", "libmp3lame", "-q:a", "2", "-ar", "44100", output_mp3],
        capture_output=True, timeout=600
    )
    if r2.returncode != 0:
        raise RuntimeError(f"FFmpeg MP3 encode hatası: {r2.stderr.decode()[-1000:]}")

    # Temizlik
    try:
        os.remove(tmp_wav)
        os.remove(list_path)
    except OSError:
        pass
