"""Video üretimi ve önizleme — üretim yerel generator ile yapılır."""
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool

from config import get_deepseek_key, OUTPUT_DIR, THUMB_DIR
import generator

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
    try:
        # Ağır iş thread havuzunda — event loop kilitlenmez, site responsive kalır
        d = await run_in_threadpool(generator.generate_short, api_key, topic, lang, voice, region, speed)
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    return {
        "ok": True,
        "filename": d["filename"],
        "title": d["title"],
        "tags": d["tags"],
        "description": d["description"],
        "script": d["script"],
        "scene_count": d["scene_count"],
        "thumbnail": d.get("thumbnail"),
        "warning": d.get("warning", ""),
        "video_url": f"/api/video/{d['filename']}",
    }


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
