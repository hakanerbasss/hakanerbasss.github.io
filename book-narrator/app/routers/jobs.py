"""Job API endpoint'leri."""

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from app import db
from app.config import settings
from app.services.extractor import SUPPORTED, detect_format

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    title: str = Form(""),
):
    """Kitap dosyasını yükler, job oluşturur."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            400,
            f"Desteklenmeyen format: '{suffix}'. Kabul edilen: {', '.join(sorted(SUPPORTED))}"
        )

    job_id = uuid.uuid4().hex[:12]
    job_dir = settings.uploads_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    save_path = str(job_dir / f"book{suffix}")

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    book_title = title.strip() or Path(file.filename or "Kitap").stem
    now = datetime.now(timezone.utc).isoformat()
    await db.create_job(job_id, book_title, save_path, suffix, now)

    return {"job_id": job_id, "title": book_title}


@router.get("")
async def list_jobs():
    """Tüm job'ları listeler."""
    jobs = await db.list_jobs()
    return {"jobs": jobs}


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    return job


@router.get("/{job_id}/download")
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
        c if c.isalnum() or c in " -_()" else "_"
        for c in job["title"]
    )[:60] + ".mp3"

    return FileResponse(path, media_type="audio/mpeg", filename=safe_name)


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")

    # Dosyaları temizle
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
