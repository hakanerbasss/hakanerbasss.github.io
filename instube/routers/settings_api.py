"""Ayarlar ve durum uçları."""
from fastapi import APIRouter, Form

from config import load_settings, save_settings, mask, DEFAULT_ENGINE
import engine

router = APIRouter()


@router.get("/api/settings")
async def get_settings():
    s = load_settings()
    return {
        "deepseek_set": bool(s.get("deepseek_key")),
        "deepseek_masked": mask(s.get("deepseek_key", "")),
        "ig_user_id": s.get("ig_user_id", ""),
        "ig_token_set": bool(s.get("ig_access_token")),
        "ig_token_masked": mask(s.get("ig_access_token", "")),
        "engine_url": s.get("engine_url") or DEFAULT_ENGINE,
    }


@router.post("/api/settings")
async def post_settings(
    deepseek_key: str = Form(""),
    ig_user_id: str = Form(""),
    ig_access_token: str = Form(""),
    engine_url: str = Form(""),
):
    s = load_settings()
    # Sadece dolu gelen alanları güncelle — boş bırakılan mevcut değeri korur
    if deepseek_key.strip():
        s["deepseek_key"] = deepseek_key.strip()
    if ig_user_id.strip():
        s["ig_user_id"] = ig_user_id.strip()
    if ig_access_token.strip():
        s["ig_access_token"] = ig_access_token.strip()
    if engine_url.strip():
        s["engine_url"] = engine_url.strip()
    save_settings(s)
    return {"ok": True}


@router.get("/api/status")
async def status():
    s = load_settings()
    st = await engine.status()
    st.update({
        "deepseek_set": bool(s.get("deepseek_key")),
        "instagram_set": bool(s.get("ig_user_id") and s.get("ig_access_token")),
    })
    return st
