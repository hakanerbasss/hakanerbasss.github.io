"""TTS servisi: önce supertonic HTTP API dener, başarısız olursa edge-tts kullanır."""

import asyncio
from pathlib import Path

import httpx

from app.config import settings


async def synthesize(text: str, output_path: str) -> float:
    """Metni sese çevirir, MP3 olarak kaydeder. Ses süresini (saniye) döner."""
    if settings.tts_backend == "supertonic":
        try:
            return await _supertonic(text, output_path)
        except Exception as exc:
            print(f"[TTS] supertonic başarısız ({exc}), edge-tts'e geçiliyor.")

    return await _edge_tts(text, output_path)


async def _supertonic(text: str, output_path: str) -> float:
    """Supertonic TTS HTTP API — OpenAI-uyumlu endpoint dener, sonra basit endpoint."""
    async with httpx.AsyncClient(timeout=60) as client:
        # Önce OpenAI-uyumlu /v1/audio/speech endpoint'i dene
        try:
            resp = await client.post(
                f"{settings.tts_url}/v1/audio/speech",
                json={
                    "input": text,
                    "voice": settings.tts_speaker,
                    "response_format": "mp3",
                },
            )
            resp.raise_for_status()
        except Exception:
            # Basit /synthesize endpoint'i dene
            resp = await client.post(
                f"{settings.tts_url}/synthesize",
                json={"text": text, "speaker": settings.tts_speaker},
            )
            resp.raise_for_status()

    Path(output_path).write_bytes(resp.content)
    return await _audio_duration(output_path)


async def _edge_tts(text: str, output_path: str) -> float:
    """Microsoft Edge TTS — ücretsiz, Türkçe destekli (tr-TR-EmelNeural)."""
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts yüklü değil: pip install edge-tts")

    communicate = edge_tts.Communicate(text, voice="tr-TR-EmelNeural")
    await communicate.save(output_path)
    return await _audio_duration(output_path)


async def _audio_duration(path: str) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 5.0  # fallback
