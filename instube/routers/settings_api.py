"""Ayarlar (API anahtarları + Instagram) ve genel durum."""
from fastapi import APIRouter, Form

from config import load_settings, save_settings, mask
import youtube

router = APIRouter()


@router.get("/api/settings")
async def get_settings():
    s = load_settings()
    return {
        "deepseek_set": bool(s.get("deepseek_key")), "deepseek_masked": mask(s.get("deepseek_key", "")),
        "pexels_set": bool(s.get("pexels_key")), "pexels_masked": mask(s.get("pexels_key", "")),
        "openai_set": bool(s.get("openai_key")), "openai_masked": mask(s.get("openai_key", "")),
        "ig_user_id": s.get("ig_user_id", ""),
        "ig_token_set": bool(s.get("ig_access_token")), "ig_token_masked": mask(s.get("ig_access_token", "")),
    }


@router.post("/api/settings")
async def post_settings(
    deepseek_key: str = Form(""),
    pexels_key: str = Form(""),
    openai_key: str = Form(""),
    ig_user_id: str = Form(""),
    ig_access_token: str = Form(""),
):
    s = load_settings()
    # Sadece dolu gelen alanları güncelle — boş bırakılan mevcut değeri korur
    for key, val in [("deepseek_key", deepseek_key), ("pexels_key", pexels_key),
                     ("openai_key", openai_key), ("ig_user_id", ig_user_id),
                     ("ig_access_token", ig_access_token)]:
        if val.strip():
            s[key] = val.strip()
    save_settings(s)
    return {"ok": True}


@router.get("/api/status")
async def status():
    s = load_settings()
    yt = youtube.yt_status()
    return {
        "deepseek_set": bool(s.get("deepseek_key")),
        "pexels_set": bool(s.get("pexels_key")),
        "instagram_set": bool(s.get("ig_user_id") and s.get("ig_access_token")),
        "youtube_configured": yt["configured"],
        "youtube_tr": yt["authorized_tr"],
        "youtube_en": yt["authorized_en"],
    }
