"""Ayarlar API — DeepSeek ve Pexels API key yönetimi."""

from fastapi import APIRouter
from pydantic import BaseModel
from app import db
from app.config import LANGUAGES

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsIn(BaseModel):
    deepseek_key: str = ""
    pexels_key: str = ""


def _mask(s: str) -> str:
    if not s:
        return ""
    if len(s) < 8:
        return "***"
    return s[:4] + "***" + s[-4:]


@router.get("/settings")
async def get_settings():
    ds = await db.get_setting("deepseek_key") or ""
    px = await db.get_setting("pexels_key") or ""
    return {
        "deepseek_key": _mask(ds),
        "deepseek_configured": bool(ds),
        "pexels_key": _mask(px),
        "pexels_configured": bool(px),
        "languages": [{"id": k, "label": v} for k, v in LANGUAGES.items()],
    }


@router.post("/settings")
async def save_settings(body: SettingsIn):
    if body.deepseek_key and "***" not in body.deepseek_key:
        await db.set_setting("deepseek_key", body.deepseek_key.strip())
    if body.pexels_key and "***" not in body.pexels_key:
        await db.set_setting("pexels_key", body.pexels_key.strip())
    return {"saved": True}
