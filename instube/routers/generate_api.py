"""Video üretimi ve önizleme uçları."""
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse, StreamingResponse

from config import load_settings
import engine
from engine import EngineError

router = APIRouter()


@router.post("/api/generate")
async def generate(
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    topic: str = Form(""),
    region: str = Form("TR"),
    speed: float = Form(1.0),
):
    api_key = load_settings().get("deepseek_key", "")
    if not api_key:
        return JSONResponse(status_code=400, content={"ok": False,
            "error": "DeepSeek API anahtarı ayarlanmamış. Ayarlar sayfasından ekle."})
    try:
        d = await engine.generate_short(api_key, topic, lang, voice, region, speed)
    except EngineError as e:
        return JSONResponse(status_code=502, content={"ok": False, "error": str(e)})

    filename = (d.get("video") or "").split("/").pop()
    return {
        "ok": True,
        "filename": filename,
        "title": d.get("title", ""),
        "tags": d.get("suggested_tags", ""),
        "description": d.get("suggested_description", ""),
        "script": d.get("script", ""),
        "scene_count": d.get("scene_count"),
        "warning": d.get("visual_warning", ""),
        "video_url": f"/api/video/{filename}" if filename else "",
    }


@router.get("/api/video/{filename}")
async def proxy_video(filename: str):
    return StreamingResponse(engine.stream_video(filename), media_type="video/mp4")
