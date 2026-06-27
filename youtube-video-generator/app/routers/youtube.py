"""YouTube OAuth ve yükleme endpoint'leri."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.config import settings
from app.models import JobStatus, YouTubeUploadRequest
from app.routers.video import jobs
from app.services import youtube_uploader

router = APIRouter(prefix="/api/youtube", tags=["youtube"])

# Oturum başına credentials (production'da DB/session kullanın)
_credentials: dict = {}


@router.get("/auth-url")
async def auth_url():
    """YouTube OAuth2 başlatma URL'ini döner."""
    try:
        url = youtube_uploader.get_auth_url()
        return {"auth_url": url}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))


@router.get("/callback")
async def callback(code: str):
    """OAuth2 callback — token alınır, kullanıcı ana sayfaya yönlendirilir."""
    try:
        creds = youtube_uploader.exchange_code(code)
        _credentials["default"] = creds
        return RedirectResponse("/?yt=connected")
    except Exception as exc:
        raise HTTPException(400, f"OAuth hatası: {exc}")


@router.get("/status")
async def yt_status():
    return {"connected": "default" in _credentials}


@router.post("/upload")
async def upload(req: YouTubeUploadRequest):
    if "default" not in _credentials:
        raise HTTPException(401, "YouTube bağlantısı yok. Önce /api/youtube/auth-url ile bağlanın.")

    job = jobs.get(req.job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, f"Video henüz hazır değil: {job.status}")

    try:
        url = await youtube_uploader.upload_video(
            video_path=job.output_path,
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy=req.privacy,
            category_id=req.category_id,
            credentials=_credentials["default"],
        )
        return {"youtube_url": url}
    except Exception as exc:
        raise HTTPException(500, f"Yükleme hatası: {exc}")
