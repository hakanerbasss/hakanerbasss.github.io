from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.routers import video, youtube

app = FastAPI(
    title="YouTube Story Video Generator",
    version="1.0.0",
    description="Türkçe metinden otomatik YouTube videosu üretir.",
)

app.include_router(video.router)
app.include_router(youtube.router)

_static = Path(__file__).parent.parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    index = _static / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>YouTube Story Video Generator</h1><p>static/index.html bulunamadı.</p>")


@app.get("/health")
async def health():
    return {"status": "ok"}
