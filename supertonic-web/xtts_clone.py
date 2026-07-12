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


def seslendir_sync(metin: str, out_path: str, language: str = "tr",
                   speed: float = 1.0, ref_audio: str | None = None) -> float:
    ref = ref_audio or (str(REF_AUDIO_PATH) if REF_AUDIO_PATH.exists() else None)
    if not ref:
        raise FileNotFoundError(
            "Referans ses bulunamadı. /api/tts/upload-reference ile yükle."
        )
    tts = _get_model()
    tts.tts_to_file(
        text=metin,
        speaker_wav=ref,
        language=language,
        file_path=str(out_path),
        speed=float(speed),
        split_sentences=True,
    )
    with wave.open(str(out_path)) as wf:
        dur = wf.getnframes() / wf.getframerate()
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
