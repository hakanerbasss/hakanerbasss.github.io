"""
SiteBot — web sitesi kuran ve yöneten panel.

Sunucuda tek yaptığı iş: site kurmak, içerik saklamak ve yayınlarken
GitHub'a commit atmak. Üretilen sitelerin hiçbiri bu sunucuda barınmaz —
hepsi GitHub Pages'te durur, sunucu kapansa bile ayakta kalırlar.

Çalıştırma:  uvicorn app:app --host 127.0.0.1 --port 8003
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)

import config
import db
from routers import admin, superadmin

BASE_DIR = Path(__file__).resolve().parent
PANEL_DIR = BASE_DIR / "panel"

app = FastAPI(title="SiteBot", version="1.0", docs_url=None, redoc_url=None)

# Müşterinin admin paneli kendi alan adından çalışıyor (hurdaci.wizaicorp.com/admin)
# ve buraya çapraz kaynaklı istek atıyor. Yalnızca kendi kök alan adımız ve
# alt alan adları kabul edilir.
_root = config.load()["root_domain"].replace(".", r"\.")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=rf"^https://([a-z0-9-]+\.)?{_root}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

app.include_router(admin.router)
app.include_router(superadmin.router)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/saglik")
def saglik() -> dict[str, object]:
    cfg = config.load()
    return {
        "servis": "sitebot",
        "port": cfg["panel_port"],
        "kurulum_tamam": bool(cfg.get("superadmin_password_hash")),
        "anahtarlar_tamam": config.is_configured(),
        "site_sayisi": len(db.list_sites()),
    }


# ------------------------------------------------------------------ arayüz

@app.get("/")
def index() -> FileResponse:
    cfg = config.load(refresh=True)
    if not cfg.get("superadmin_password_hash"):
        return FileResponse(PANEL_DIR / "setup.html")
    return FileResponse(PANEL_DIR / "super.html")


@app.get("/kurulum")
def kurulum() -> FileResponse:
    return FileResponse(PANEL_DIR / "setup.html")


@app.get("/admin")
def admin_redirect() -> RedirectResponse:
    """Yanlışlıkla panel adresinden /admin açanlar için yönlendirme."""
    return RedirectResponse("/", status_code=307)


@app.get("/panel/{slug}")
def musteri_paneli(slug: str) -> HTMLResponse:
    """Müşteri panelinin yedek adresi.

    Normalde panel müşterinin kendi sitesinden açılıyor
    (hurdaci.wizaicorp.com/admin/). O sayfa bir sebeple erişilemezse —
    depo bozulmuş, Pages derlemesi takılmış, alan adı taşınıyor —
    buradan aynı panele girilebilir. Aynı köken olduğu için CORS'a da
    ihtiyaç duymaz.
    """
    site = db.get_site_by_slug(slug)
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    html = (PANEL_DIR / "site_admin.html").read_text("utf-8")
    html = html.replace("__API_BASE__", "").replace("__SITE_SLUG__", site["slug"])
    return HTMLResponse(html, headers={"X-Robots-Tag": "noindex"})


@app.get("/onizleme/{slug}")
def onizleme(slug: str) -> JSONResponse:
    """Site adresini bilmeyen müşteriye kolaylık: adresini söyle."""
    site = db.get_site_by_slug(slug)
    if not site:
        return JSONResponse({"hata": "Site bulunamadı."}, status_code=404)
    return JSONResponse({
        "site": f"https://{site['custom_domain'] or site['domain']}/",
        "panel": f"https://{site['custom_domain'] or site['domain']}/admin/",
        "durum": site["status"],
    })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.load()["panel_port"])
