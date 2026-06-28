"""Job API endpoint'leri."""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app import db
from app.config import settings, VOICES
from app.services.extractor import SUPPORTED
from app.services import tts as tts_svc

router = APIRouter(prefix="/api", tags=["jobs"])


# ── Sesler ───────────────────────────────────────────────────────────────────

@router.get("/voices")
async def list_voices():
    return {"voices": [{"id": k, "label": v} for k, v in VOICES.items()]}


@router.post("/preview")
async def preview_voice(voice: str = Form("M1")):
    """Seçili ses için ~10 saniyelik önizleme MP3 üretir."""
    if voice not in VOICES:
        raise HTTPException(400, f"Geçersiz ses: {voice}. Seçenekler: {list(VOICES)}")
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
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            400, f"Desteklenmeyen format: '{suffix}'. Kabul edilen: {', '.join(sorted(SUPPORTED))}"
        )
    if voice not in VOICES:
        voice = settings.tts_voice

    job_id = uuid.uuid4().hex[:12]
    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    save_path = str(job_dir / f"book{suffix}")

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    book_title = title.strip() or Path(file.filename or "Kitap").stem
    now = datetime.now(timezone.utc).isoformat()
    await db.create_job(job_id, book_title, save_path, suffix, voice, now)

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
async def download(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    if job["status"] != "completed":
        raise HTTPException(400, f"MP3 henüz hazır değil. Durum: {job['status']}")
    path = job["output_path"]
    if not path or not Path(path).exists():
        raise HTTPException(500, "MP3 dosyası bulunamadı.")

    safe_name = "".join(
        c if c.isalnum() or c in " -_()" else "_" for c in job["title"]
    )[:60] + ".mp3"
    return FileResponse(path, media_type="audio/mpeg", filename=safe_name)


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
        raise HTTPException(400, f"Zaten çalışıyor veya tamamlandı: {job['status']}")
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
    out = job.get("output_path")
    if out and Path(out).exists():
        try:
            Path(out).unlink()
        except OSError:
            pass
    await db.delete_job(job_id)
    return {"deleted": job_id}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
