"""
InsTube — sade, TAMAMEN BAĞIMSIZ yayın paneli (ince ana modül).

Hiçbir dış servise (eski supertonic-web :8001) bağımlı DEĞİL — video üretimi,
TTS, görseller, ffmpeg ve YouTube yüklemesi hepsi burada. Eski projedeki
birbirine girmiş 5-6 scheduler yok; v1 tamamen manuel. Ağır üretim thread
havuzunda çalışır, böylece bir üretim patlasa bile site/diğer işler düşmez.

Modüller:
  config.py             — ayar/anahtar/yol sabitleri
  generator.py          — DeepSeek içerik + TTS + görsel + ffmpeg pipeline
  visuals.py            — sahne görselleri + overlay'ler
  youtube.py            — YouTube OAuth + yükleme
  instagram.py          — Instagram Reels gönderimi (Graph API)
  trends.py             — Google News / YouTube trend verisi
  ffmpeg_util.py        — gerçek hatayı gösteren ffmpeg sarmalayıcı
  routers/*             — settings / generate / publish / youtube uçları
  static/*.html         — her iş için AYRI sayfa

Çalıştırma:  uvicorn app:app --host 0.0.0.0 --port 8002
"""
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import BASE_DIR
from routers import settings_api, generate_api, publish_api, youtube_api

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
app.include_router(youtube_api.router)

# Statik sayfalar — en son mount edilir ki /api/* uçları öncelikli kalsın.
app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
