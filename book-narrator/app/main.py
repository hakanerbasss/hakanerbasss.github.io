"""Book Narrator — FastAPI uygulaması.

Başlangıç:
  uvicorn app.main:app --host 0.0.0.0 --port 8003

Lifespan:
  - DB başlatılır (tablo oluşturulur, yarım joblar pending'e alınır)
  - Worker asyncio task olarak başlatılır
  - Uygulama kapanırken worker temiz şekilde durdurulur
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import db, worker
from app.routers import jobs

_worker_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    await db.init()
    _worker_task = asyncio.create_task(worker.run(), name="book-narrator-worker")
    yield
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Book Narrator", version="1.0.0", lifespan=lifespan)
app.include_router(jobs.router)

_static = Path(__file__).parent.parent / "static"
if _static.exists():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    index = _static / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Book Narrator</h1>")


@app.get("/health")
async def health():
    return {"status": "ok"}
