"""Video üretimi (arka plan işi) ve önizleme."""
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, FileResponse

from config import get_deepseek_key, OUTPUT_DIR, THUMB_DIR
import jobs

router = APIRouter()


@router.post("/api/generate")
async def generate(
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    topic: str = Form(""),
    region: str = Form("TR"),
    speed: float = Form(1.0),
):
    api_key = get_deepseek_key()
    if not api_key:
        return JSONResponse(status_code=400, content={"ok": False,
            "error": "DeepSeek API anahtarı ayarlanmamış. Ayarlar sayfasından ekle."})
    # Arka planda başlat; iş bağlantıdan bağımsız sürer (telefon kapansa da devam eder)
    job_id, started = jobs.start_generation({
        "api_key": api_key, "topic": topic, "lang": lang,
        "voice": voice, "region": region, "speed": speed,
    })
    return {"ok": True, "job_id": job_id, "started": started}


@router.get("/api/job")
async def job_latest():
    j = jobs.latest_job()
    return j or {"status": "none"}


@router.get("/api/job/{job_id}")
async def job_status(job_id: str):
    j = jobs.get_job(job_id)
    return j or {"status": "none"}


@router.get("/api/video/{filename}")
async def get_video(filename: str):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Video bulunamadı"})
    return FileResponse(str(path), media_type="video/mp4")


@router.get("/api/thumbnail/{filename}")
async def get_thumbnail(filename: str):
    path = THUMB_DIR / filename
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Thumbnail bulunamadı"})
    return FileResponse(str(path), media_type="image/jpeg")
