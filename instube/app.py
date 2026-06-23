"""
InsTube — sade, bağımsız yayın kontrol paneli.

Tasarım felsefesi:
- Ağır ve KANITLANMIŞ işler (DeepSeek içerik üretimi + Supertonic TTS + ffmpeg
  video pipeline + YouTube OAuth yükleme) hâlâ çalışan "motor"a (supertonic-web,
  varsayılan http://localhost:8001) HTTP ile delege edilir. Böylece o karmaşık
  kod yeniden yazılıp YENİ hatalar üretilmez.
- InsTube sadece şunları kendisi yapar: temiz 2-sekmeli arayüz, NET hata
  gösterimi, "Test Üret" (yayınlamadan üret) ve Instagram Reels gönderimi.
- Eski projedeki birbirine girmiş 5-6 scheduler burada YOK. v1 tamamen manuel.

Çalıştırma:  uvicorn app:app --host 0.0.0.0 --port 8002
"""
import json
import traceback
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from instagram import post_reel_to_instagram

app = FastAPI(title="InsTube")

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

DEFAULT_ENGINE = "http://localhost:8001"


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Hatanın gerçek sebebini HER ZAMAN görünür kıl — eski sistemin en büyük derdi
    # hataların yutulmasıydı.
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": str(exc), "trace": traceback.format_exc()},
    )


# ── Ayarlar ──────────────────────────────────────────────────────────────────
def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def engine_url() -> str:
    return (load_settings().get("engine_url") or DEFAULT_ENGINE).rstrip("/")


def _mask(val: str) -> str:
    if not val:
        return ""
    return val[:4] + "…" + val[-4:] if len(val) > 10 else "••••"


@app.get("/api/settings")
async def get_settings():
    s = load_settings()
    return {
        "deepseek_set": bool(s.get("deepseek_key")),
        "deepseek_masked": _mask(s.get("deepseek_key", "")),
        "ig_user_id": s.get("ig_user_id", ""),
        "ig_token_set": bool(s.get("ig_access_token")),
        "ig_token_masked": _mask(s.get("ig_access_token", "")),
        "engine_url": s.get("engine_url") or DEFAULT_ENGINE,
    }


@app.post("/api/settings")
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


# ── Motor durumu ─────────────────────────────────────────────────────────────
@app.get("/api/status")
async def status():
    s = load_settings()
    eng = engine_url()
    engine_ok, yt_tr, yt_en = False, False, False
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{eng}/api/yt/config")
            engine_ok = r.status_code == 200
            if engine_ok:
                j = r.json()
                yt_tr = bool(j.get("connected") or j.get("configured"))
            r2 = await client.get(f"{eng}/api/yt/en/config")
            if r2.status_code == 200:
                yt_en = bool(r2.json().get("connected") or r2.json().get("configured"))
    except Exception:
        pass
    return {
        "engine": eng,
        "engine_ok": engine_ok,
        "deepseek_set": bool(s.get("deepseek_key")),
        "instagram_set": bool(s.get("ig_user_id") and s.get("ig_access_token")),
        "youtube_tr": yt_tr,
        "youtube_en": yt_en,
    }


# ── Üretim (motor /api/generate-shorts'a delege) ─────────────────────────────
@app.post("/api/generate")
async def generate(
    lang: str = Form("tr"),
    voice: str = Form("M1"),
    topic: str = Form(""),
    region: str = Form("TR"),
    speed: float = Form(1.0),
):
    s = load_settings()
    api_key = s.get("deepseek_key", "")
    if not api_key:
        return JSONResponse(status_code=400, content={"ok": False,
            "error": "DeepSeek API anahtarı ayarlanmamış. Ayarlar bölümünden ekle."})

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
        return JSONResponse(status_code=502, content={"ok": False,
            "error": f"Motora ({eng}) ulaşılamadı: {e}"})

    if r.status_code != 200:
        # Motorun gerçek hata detayını olduğu gibi göster
        detail = r.text
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            pass
        return JSONResponse(status_code=502, content={"ok": False,
            "error": f"Video üretilemedi (motor {r.status_code}): {str(detail)[:800]}"})

    d = r.json()
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


# ── Video önizleme (motordan proxy) ──────────────────────────────────────────
@app.get("/api/video/{filename}")
async def proxy_video(filename: str):
    eng = engine_url()

    async def stream():
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", f"{eng}/api/video/{filename}") as resp:
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="video/mp4")


async def _download_video(filename: str) -> Path:
    """Motordan üretilmiş videoyu yerel diske indir (IG yüklemesi için gerekli)."""
    eng = engine_url()
    out = DOWNLOAD_DIR / filename
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.get(f"{eng}/api/video/{filename}")
        if r.status_code != 200:
            raise RuntimeError(f"Video indirilemedi: {r.status_code}")
        out.write_bytes(r.content)
    return out


# ── Yayınlama ────────────────────────────────────────────────────────────────
@app.post("/api/publish")
async def publish(
    filename: str = Form(...),
    title: str = Form(""),
    tags: str = Form(""),
    description: str = Form(""),
    target: str = Form("instagram"),     # "instagram" | "youtube"
    also_instagram: str = Form("false"),  # YouTube sekmesindeki toggle
    privacy: str = Form("public"),
    channel: str = Form("tr"),
):
    if not filename:
        return JSONResponse(status_code=400, content={"ok": False, "error": "Önce video üret."})

    results: dict = {}
    eng = engine_url()
    do_youtube = target == "youtube"
    do_instagram = target == "instagram" or (do_youtube and also_instagram == "true")

    # 1) YouTube
    if do_youtube:
        try:
            async with httpx.AsyncClient(timeout=900) as client:
                r = await client.post(
                    f"{eng}/api/yt/upload",
                    data={
                        "filename": filename, "title": title,
                        "description": description, "tags": tags,
                        "privacy": privacy, "channel": channel,
                    },
                )
            if r.status_code == 200:
                results["youtube"] = {"ok": True, **r.json()}
            else:
                detail = r.text
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    pass
                results["youtube"] = {"ok": False, "error": str(detail)[:600]}
        except Exception as e:
            results["youtube"] = {"ok": False, "error": str(e)}

    # 2) Instagram Reels
    if do_instagram:
        s = load_settings()
        ig_user_id = s.get("ig_user_id", "")
        ig_token = s.get("ig_access_token", "")
        if not ig_user_id or not ig_token:
            results["instagram"] = {"ok": False,
                "error": "Instagram kimliği/token ayarlanmamış (Ayarlar)."}
        else:
            try:
                local = await _download_video(filename)
                caption = f"{title}\n\n{tags}".strip()
                media_id, err = await post_reel_to_instagram(local, caption, ig_user_id, ig_token)
                if err:
                    results["instagram"] = {"ok": False, "error": err}
                else:
                    results["instagram"] = {"ok": True, "media_id": media_id}
            except Exception as e:
                results["instagram"] = {"ok": False, "error": str(e)}

    overall_ok = any(v.get("ok") for v in results.values()) if results else False
    return {"ok": overall_ok, "results": results}


# Statik dosyalar (UI)
app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
