"""
XTTS-v2 ile kendi ses klonu TTS.

Model ilk çağrıda yüklenir (~10-15 sn), sonrasında RAM'de kalır.
Referans ses: supertonic-web/referans_sesim.wav (20-30 sn temiz kayıt)

Kullanım:
    from xtts_clone import seslendir, hazir_mi
    dur = await seslendir("Merhaba dünya", "/tmp/out.wav")
"""

import os
import asyncio
import threading
import wave
from pathlib import Path

os.environ["COQUI_TOS_AGREED"] = "1"

_lock = threading.Lock()
_tts = None

REF_AUDIO_PATH = Path(__file__).parent / "referans_sesim.wav"
_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def _get_model():
    global _tts
    if _tts is None:
        with _lock:
            if _tts is None:
                print("[xtts] Model yükleniyor (~10 sn)...", flush=True)
                from TTS.api import TTS
                _tts = TTS(_MODEL_NAME)
                print("[xtts] Model hazır.", flush=True)
    return _tts


def _chunk_text(metin: str, max_chars: int = 220) -> list[str]:
    """XTTS 400 token sınırı için metni kısa cümlelere böl."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', metin.strip())
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            # Tek cümle max_chars'ı aşıyorsa virgülden böl
            if len(s) > max_chars:
                parts = re.split(r'(?<=,)\s+', s)
                buf = ""
                for p in parts:
                    if len(buf) + len(p) + 1 <= max_chars:
                        buf = (buf + " " + p).strip()
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = p
                if buf:
                    chunks.append(buf)
            else:
                current = s
    if current:
        chunks.append(current)
    return chunks or [metin]


def seslendir_sync(metin: str, out_path: str, language: str = "tr",
                   speed: float = 1.0, ref_audio: str | None = None) -> float:
    import numpy as np
    ref = ref_audio or (str(REF_AUDIO_PATH) if REF_AUDIO_PATH.exists() else None)
    if not ref:
        raise FileNotFoundError(
            "Referans ses bulunamadı. /api/tts/upload-reference ile yükle."
        )
    tts = _get_model()
    chunks = _chunk_text(metin)
    wavs = []
    for chunk in chunks:
        wav = tts.tts(
            text=chunk,
            speaker_wav=ref,
            language=language,
            speed=float(speed),
        )
        wavs.append(np.array(wav, dtype=np.float32))
    combined = np.concatenate(wavs) if len(wavs) > 1 else wavs[0]
    # sample rate XTTS'te sabit 24000
    import scipy.io.wavfile as wavfile
    wavfile.write(str(out_path), 24000, combined)
    dur = len(combined) / 24000
    return float(dur)


async def seslendir(metin: str, out_path: str, language: str = "tr",
                    speed: float = 1.0, ref_audio: str | None = None) -> float:
    return await asyncio.to_thread(
        seslendir_sync, metin, out_path, language, speed, ref_audio
    )


def hazir_mi() -> bool:
    """Referans ses dosyası mevcut mu?"""
    return REF_AUDIO_PATH.exists()


def ref_audio_path() -> Path:
    return REF_AUDIO_PATH
