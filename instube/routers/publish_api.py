"""Yayınlama uçları — Instagram ve YouTube ayrı ayrı raporlanır."""
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from config import load_settings
import engine
from engine import EngineError
from instagram import post_reel_to_instagram

router = APIRouter()


async def _publish_instagram(filename: str, title: str, tags: str) -> dict:
    s = load_settings()
    ig_user_id = s.get("ig_user_id", "")
    ig_token = s.get("ig_access_token", "")
    if not ig_user_id or not ig_token:
        return {"ok": False, "error": "Instagram kimliği/token ayarlanmamış (Ayarlar)."}
    try:
        local = await engine.download_video(filename)
    except EngineError as e:
        return {"ok": False, "error": str(e)}
    caption = f"{title}\n\n{tags}".strip()
    media_id, err = await post_reel_to_instagram(local, caption, ig_user_id, ig_token)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "media_id": media_id}


@router.post("/api/publish/instagram")
async def publish_instagram(
    filename: str = Form(...),
    title: str = Form(""),
    tags: str = Form(""),
):
    if not filename:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Önce video üret."})
    res = await _publish_instagram(filename, title, tags)
    return {"ok": res["ok"], "results": {"instagram": res}}


@router.post("/api/publish/youtube")
async def publish_youtube(
    filename: str = Form(...),
    title: str = Form(""),
    tags: str = Form(""),
    description: str = Form(""),
    privacy: str = Form("public"),
    channel: str = Form("tr"),
    also_instagram: str = Form("false"),
):
    if not filename:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Önce video üret."})
    results: dict = {}

    try:
        yt = await engine.yt_upload(filename, title, description, tags, privacy, channel)
        results["youtube"] = {"ok": True, **yt}
    except EngineError as e:
        results["youtube"] = {"ok": False, "error": str(e)}

    if also_instagram == "true":
        results["instagram"] = await _publish_instagram(filename, title, tags)

    overall_ok = any(v.get("ok") for v in results.values())
    return {"ok": overall_ok, "results": results}
