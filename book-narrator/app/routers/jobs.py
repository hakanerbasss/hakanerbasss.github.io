"""Job API endpoint'leri."""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app import db
from app.config import settings, VOICES, LANGUAGES
from app.services.extractor import SUPPORTED
from app.services import tts as tts_svc

router = APIRouter(prefix="/api", tags=["jobs"])


# ── Sesler ───────────────────────────────────────────────────────────────────

@router.get("/voices")
async def list_voices():
    return {"voices": [{"id": k, "label": v} for k, v in VOICES.items()]}


@router.post("/preview")
async def preview_voice(voice: str = Form("M1")):
    if voice not in VOICES:
        raise HTTPException(400, f"Geçersiz ses: {voice}")
    try:
        mp3_path = await tts_svc.generate_preview(voice)
    except Exception as exc:
        raise HTTPException(500, f"Önizleme üretilemedi: {exc}")
    return FileResponse(mp3_path, media_type="audio/mpeg",
                        filename=f"onizleme_{voice}.mp3")


# ── Job CRUD ─────────────────────────────────────────────────────────────────

@router.post("/jobs/upload")
async def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    voice: str = Form("M1"),
    source_lang: str = Form("auto"),
    target_lang: str = Form("tr"),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            400, f"Desteklenmeyen format: '{suffix}'. Kabul edilen: {', '.join(sorted(SUPPORTED))}"
        )
    if voice not in VOICES:
        voice = settings.tts_voice
    if source_lang not in LANGUAGES:
        source_lang = "auto"
    if target_lang not in LANGUAGES or target_lang == "auto":
        target_lang = "tr"

    job_id  = uuid.uuid4().hex[:12]
    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    save_path = str(job_dir / f"book{suffix}")

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    book_title = title.strip() or Path(file.filename or "Kitap").stem
    now = datetime.now(timezone.utc).isoformat()
    await db.create_job(
        job_id, book_title, save_path, suffix, voice, now,
        source_lang=source_lang, target_lang=target_lang,
    )
    return {"job_id": job_id, "title": book_title}


@router.get("/jobs")
async def list_jobs():
    return {"jobs": await db.list_jobs()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    return job


@router.get("/jobs/{job_id}/download")
async def download_mp3(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    if job["status"] != "completed":
        raise HTTPException(400, f"Henüz hazır değil. Durum: {job['status']}")
    path = job.get("output_path")
    if not path or not Path(path).exists():
        raise HTTPException(500, "MP3 dosyası bulunamadı.")
    safe_name = _safe(job["title"]) + ".mp3"
    return FileResponse(path, media_type="audio/mpeg", filename=safe_name)


@router.get("/jobs/{job_id}/video")
async def download_video(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    path = job.get("output_video_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Video henüz hazır değil.")
    safe_name = _safe(job["title"]) + ".mp4"
    return FileResponse(path, media_type="video/mp4", filename=safe_name)


@router.get("/jobs/{job_id}/srt")
async def download_srt(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    path = job.get("output_srt_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Altyazı dosyası henüz hazır değil.")
    safe_name = _safe(job["title"]) + ".srt"
    return FileResponse(path, media_type="text/plain", filename=safe_name)


# ── Duraklatma / Devam ───────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    if job["status"] not in ("pending", "processing"):
        raise HTTPException(400, f"Duraklatılamaz, durum: {job['status']}")
    await db.update(job_id, _now(), status="paused")
    return {"status": "paused"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    if job["status"] != "paused":
        raise HTTPException(400, f"Zaten çalışıyor: {job['status']}")
    await db.update(job_id, _now(), status="pending")
    return {"status": "pending"}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    job_dir = settings.uploads_dir / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    for key in ("output_path", "output_video_path", "output_srt_path"):
        p = job.get(key)
        if p and Path(p).exists():
            try:
                Path(p).unlink()
            except OSError:
                pass
    await db.delete_job(job_id)
    return {"deleted": job_id}


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in " -_()" else "_" for c in s)[:60]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
