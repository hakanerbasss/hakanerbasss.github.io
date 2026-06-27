"""Arka plan worker — SQLite'tan pending job alır, işler.

Sunucu restart'ta DB'deki 'processing' joblar 'pending'e alınır (db.init),
worker başlarken onları da yakalar ve devam eder.

Tasarım:
- Tek asyncio.Task olarak app başlangıcında çalışır
- Aynı anda 1 job işler (CPU-bound TTS için yeterli)
- Her chunk bitiminde DB'ye yazar → sayfa yenileme güvenli
- Chunk WAV dosyaları diske yazılır — restart'ta kaldığı yerden devam eder
"""

import asyncio
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import settings
from app.services import chunker, extractor, tts as tts_svc

_POLL_SEC = 3  # pending job yoksa kaç saniyede bir kontrol et


async def run():
    while True:
        try:
            await _tick()
        except Exception as exc:
            print(f"[worker] beklenmeyen hata: {exc}")
        await asyncio.sleep(_POLL_SEC)


async def _tick():
    jobs = await db.list_jobs()
    pending = [j for j in jobs if j["status"] == "pending"]
    if not pending:
        return
    job = pending[0]
    await _process(job["id"])


async def _process(job_id: str):
    now = _now()
    await db.update(job_id, now, status="processing")

    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(exist_ok=True)
    wav_dir = job_dir / "chunks"
    wav_dir.mkdir(exist_ok=True)

    try:
        job = await db.get_job(job_id)

        # ── 1. Metin çıkar ───────────────────────────────────────────────────
        await db.update(job_id, _now(), progress=2)
        text = extractor.extract(job["input_path"])

        # ── 2. Chunk'lara böl ───────────────────────────────────────────────
        chunks = chunker.split(text)
        total = len(chunks)
        await db.update(job_id, _now(), total=total, progress=3)

        # ── 3. Mevcut WAV'ları kontrol et — kaldığı yerden devam ───────────
        wav_files = []
        done_count = 0

        for i, chunk_text in enumerate(chunks):
            wav_path = str(wav_dir / f"{i:05d}.wav")

            if Path(wav_path).exists():
                # Önceki çalışmadan kalan dosya — atla
                wav_files.append(wav_path)
                done_count += 1
                continue

            # Yeni chunk seslendirme
            await tts_svc.synthesize(chunk_text, wav_path)
            wav_files.append(wav_path)
            done_count += 1

            progress = 5 + int(done_count / total * 88)  # 5% → 93%
            await db.update(job_id, _now(), done=done_count, progress=progress)

        # ── 4. WAV → MP3 birleştirme ─────────────────────────────────────
        await db.update(job_id, _now(), progress=94)
        out_path = str(settings.outputs_dir / f"{job_id}.mp3")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, tts_svc.concat_wav_to_mp3, wav_files, out_path
        )

        # ── 5. Tamamlandı ────────────────────────────────────────────────────
        await db.update(
            job_id, _now(),
            status="completed",
            progress=100,
            done=total,
            output_path=out_path,
        )

        # Chunk WAV'larını temizle (MP3 artık hazır, yer kaplıyorlar)
        try:
            shutil.rmtree(str(wav_dir))
        except OSError:
            pass

    except Exception as exc:
        import traceback
        traceback.print_exc()
        await db.update(
            job_id, _now(),
            status="failed",
            error=str(exc)[:500],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
