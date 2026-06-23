"""
InsTube — sade, bağımsız yayın paneli (ince ana modül).

Sorumluluklar modüllere bölünmüştür:
  config.py             — ayar/anahtar saklama
  engine.py             — motor (supertonic-web :8001) ile konuşma
  instagram.py          — Instagram Reels gönderimi (Graph API)
  routers/settings_api  — /api/settings, /api/status
  routers/generate_api  — /api/generate, /api/video/{filename}
  routers/publish_api   — /api/publish/instagram, /api/publish/youtube
  static/*.html         — her iş için AYRI sayfa (ayarlar / instagram / youtube)

Çalıştırma:  uvicorn app:app --host 0.0.0.0 --port 8002
"""
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR
from routers import settings_api, generate_api, publish_api

app = FastAPI(title="InsTube")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Hatanın gerçek sebebini HER ZAMAN görünür kıl.
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": str(exc), "trace": traceback.format_exc()},
    )


app.include_router(settings_api.router)
app.include_router(generate_api.router)
app.include_router(publish_api.router)

# Statik sayfalar — en son mount edilir ki /api/* uçları öncelikli kalsın.
app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
