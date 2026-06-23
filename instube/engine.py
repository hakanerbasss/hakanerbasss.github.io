"""
Motor (supertonic-web :8001) ile konuşan katman.

Ağır işler buraya delege edilir; hatalar olduğu gibi yukarı taşınır ki
arayüzde net görünsün. Fonksiyonlar hata durumunda EngineError fırlatır.
"""
from pathlib import Path

import httpx

from config import engine_url, DOWNLOAD_DIR


class EngineError(Exception):
    pass


def _extract_detail(r: httpx.Response) -> str:
    try:
        return str(r.json().get("detail", r.text))
    except Exception:
        return r.text


async def status() -> dict:
    """Motor ve YouTube bağlantı durumunu döndür (hata fırlatmaz)."""
    eng = engine_url()
    out = {"engine": eng, "engine_ok": False, "youtube_tr": False, "youtube_en": False}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{eng}/api/yt/config")
            out["engine_ok"] = r.status_code == 200
            if out["engine_ok"]:
                j = r.json()
                out["youtube_tr"] = bool(j.get("connected") or j.get("configured"))
            r2 = await client.get(f"{eng}/api/yt/en/config")
            if r2.status_code == 200:
                j2 = r2.json()
                out["youtube_en"] = bool(j2.get("connected") or j2.get("configured"))
    except Exception:
        pass
    return out


async def generate_short(api_key: str, topic: str, lang: str, voice: str,
                         region: str, speed: float) -> dict:
    eng = engine_url()
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            r = await client.post(
                f"{eng}/api/generate-shorts",
                data={
                    "topic": topic, "api_key": api_key, "lang": lang,
                    "voice": voice, "speed": str(speed),
                    "exclude_topics": "", "region": region,
                },
            )
    except Exception as e:
        raise EngineError(f"Motora ({eng}) ulaşılamadı: {e}")
    if r.status_code != 200:
        raise EngineError(f"Video üretilemedi (motor {r.status_code}): {_extract_detail(r)[:800]}")
    return r.json()


async def yt_upload(filename: str, title: str, description: str, tags: str,
                    privacy: str, channel: str) -> dict:
    eng = engine_url()
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            r = await client.post(
                f"{eng}/api/yt/upload",
                data={
                    "filename": filename, "title": title, "description": description,
                    "tags": tags, "privacy": privacy, "channel": channel,
                },
            )
    except Exception as e:
        raise EngineError(f"Motora ({eng}) ulaşılamadı: {e}")
    if r.status_code != 200:
        raise EngineError(_extract_detail(r)[:600])
    return r.json()


async def download_video(filename: str) -> Path:
    """Üretilen videoyu yerel diske indir (Instagram yüklemesi için gerekli)."""
    eng = engine_url()
    out = DOWNLOAD_DIR / filename
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.get(f"{eng}/api/video/{filename}")
        if r.status_code != 200:
            raise EngineError(f"Video indirilemedi (motor {r.status_code})")
        out.write_bytes(r.content)
    return out


async def stream_video(filename: str):
    """Önizleme için videoyu motordan akıt."""
    eng = engine_url()
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("GET", f"{eng}/api/video/{filename}") as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk
