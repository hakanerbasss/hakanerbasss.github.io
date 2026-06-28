"""Arka plan worker — SQLite'tan pending job alır, chunk chunk işler.

Pipeline (API key'lere göre opsiyonel adımlar):
  1. Metin çıkar
  2. İçerik başlangıcını bul (DeepSeek)
  3. Chunk'lara böl
  4. Çeviri (DeepSeek, source != target ise)
  5. TTS + Pexels görsel (her chunk)
  6. MP3 birleştir
  7. SRT altyazı üret
  8. MP4 video (Pexels varsa)
  9. YouTube metadata (DeepSeek varsa)
"""

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import settings
from app.services import chunker, extractor
from app.services import tts as tts_svc
from app.services import subtitle, deepseek, pexels, video_builder

_POLL_SEC = 3


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
    await _process(pending[0]["id"])


async def _process(job_id: str):
    await db.update(job_id, _now(), status="processing")

    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(exist_ok=True)
    wav_dir = job_dir / "chunks"
    wav_dir.mkdir(exist_ok=True)
    img_dir = job_dir / "images"
    img_dir.mkdir(exist_ok=True)

    try:
        job = await db.get_job(job_id)
        voice       = job.get("voice")       or settings.tts_voice
        source_lang = job.get("source_lang") or "auto"
        target_lang = job.get("target_lang") or "tr"

        deepseek_key = await db.get_setting("deepseek_key") or ""
        pexels_key   = await db.get_setting("pexels_key")   or ""

        need_translation = (
            bool(deepseek_key)
            and source_lang not in ("auto", "none", target_lang)
        )
        use_images = bool(pexels_key)
        use_meta   = bool(deepseek_key)

        # TTS dili: çeviri varsa hedef dil, yoksa kaynak dil (biliniyorsa)
        if need_translation:
            tts_lang = target_lang
        elif source_lang not in ("auto", "none"):
            tts_lang = source_lang   # orijinal dilde seslendir
        else:
            tts_lang = target_lang   # bilinmiyorsa hedef dil

        # ── 1. Metin çıkar ──────────────────────────────────────────────────
        await db.update(job_id, _now(), progress=2)
        text = extractor.extract(job["input_path"])

        # ── 2. Gereksiz baş kısımları atla ─────────────────────────────────
        if deepseek_key and len(text) > 800:
            try:
                start_idx = await deepseek.find_content_start(text, deepseek_key)
                if start_idx > 200:
                    text = text[start_idx:]
            except Exception:
                pass

        # ── 3. Chunk'lara böl ───────────────────────────────────────────────
        chunks = chunker.split(text)
        total  = len(chunks)
        await db.update(job_id, _now(), total=total, progress=3)

        # ── 4. Çeviri ───────────────────────────────────────────────────────
        if need_translation:
            translated_chunks, keywords_list = await deepseek.translate_chunks(
                chunks, source_lang, target_lang, deepseek_key
            )
        else:
            translated_chunks = chunks
            keywords_list     = ["nature landscape"] * total

        # ── 5. TTS + Pexels görsel (chunk chunk) ────────────────────────────
        wav_files:   list[str]        = []
        durations:   list[float]      = []
        image_files: list[str | None] = []
        done_count = 0

        for i, (chunk_text, kw) in enumerate(zip(translated_chunks, keywords_list)):
            wav_path = str(wav_dir / f"{i:05d}.wav")

            if Path(wav_path).exists():
                dur = len(chunk_text) / 15.0
            else:
                dur = await tts_svc.synthesize(
                    chunk_text, wav_path, voice=voice, lang=tts_lang
                )

            wav_files.append(wav_path)
            durations.append(dur)

            if use_images:
                img = await pexels.fetch_image(kw, str(img_dir), pexels_key, i)
                image_files.append(img)
            else:
                image_files.append(None)

            done_count += 1
            progress = 15 + int(done_count / total * 68)
            await db.update(job_id, _now(), done=done_count, progress=progress)

            current = await db.get_job(job_id)
            if current and current["status"] == "paused":
                return

        # ── 6. MP3 birleştir ────────────────────────────────────────────────
        await db.update(job_id, _now(), progress=84)
        out_mp3 = str(settings.outputs_dir / f"{job_id}.mp3")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, tts_svc.concat_wav_to_mp3, wav_files, out_mp3)
        await db.update(job_id, _now(), output_path=out_mp3, progress=86)

        # ── 7. SRT altyazı ─────────────────────────────────────────────────
        srt_content = subtitle.generate_srt(translated_chunks, durations)
        srt_path    = str(settings.outputs_dir / f"{job_id}.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        await db.update(job_id, _now(), output_srt_path=srt_path, progress=88)

        # ── 8. MP4 video ───────────────────────────────────────────────────
        if use_images:
            out_mp4 = str(settings.outputs_dir / f"{job_id}.mp4")
            await video_builder.build_video(
                image_files, wav_files, durations, srt_path, out_mp4
            )
            await db.update(job_id, _now(), output_video_path=out_mp4, progress=96)

        # ── 9. YouTube metadata ─────────────────────────────────────────────
        if use_meta:
            sample = " ".join(translated_chunks[:8])
            meta   = await deepseek.generate_metadata(
                job["title"], sample, target_lang, deepseek_key
            )
            await db.update(
                job_id, _now(),
                youtube_metadata=json.dumps(meta, ensure_ascii=False),
                progress=99,
            )

        # ── 10. Tamamlandı ─────────────────────────────────────────────────
        await db.update(job_id, _now(), status="completed", progress=100, done=total)

        try:
            shutil.rmtree(str(wav_dir))
        except OSError:
            pass

    except Exception as exc:
        import traceback
        traceback.print_exc()
        await db.update(job_id, _now(), status="failed", error=str(exc)[:500])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
