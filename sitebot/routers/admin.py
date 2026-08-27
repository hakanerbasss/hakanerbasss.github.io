"""
Müşteri paneli API'si.

Bu router'daki her sorgu oturumdan gelen site_id ile sınırlı — bir müşteri
başka bir müşterinin verisine hiçbir uç noktadan ulaşamaz.

Arayüzün kendisi müşterinin kendi alan adından (ör. hurdaci.wizaicorp.com/admin)
servis edildiği için istekler çapraz kaynaklı geliyor; kimlik Bearer token ile
taşınıyor, çerez kullanılmıyor.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

import auth
import db
import images
import provisioner
import renderer
import schema

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Aynı sitenin iki sekmeden aynı anda yayınlanmasını engelle.
_publish_locks: dict[int, asyncio.Lock] = {}


def _lock(site_id: int) -> asyncio.Lock:
    return _publish_locks.setdefault(site_id, asyncio.Lock())


def _site_of(sess: dict[str, Any]) -> dict[str, Any]:
    site = sess.get("site") or db.get_site(sess["site_id"])
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    return site


@router.post("/login")
def login(slug: str = Body(..., embed=True),
          email: str = Body(..., embed=True),
          password: str = Body(..., embed=True)) -> dict[str, Any]:
    site = db.get_site_by_slug(slug)
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    user = db.find_user(email, site["id"])
    # Kullanıcı yoksa da şifre doğrulamasını çalıştırıyoruz: yanıt süresinden
    # "bu e-posta kayıtlı mı" bilgisi sızmasın.
    stored = user["password_hash"] if user else auth.hash_password("x" * 12)
    if not auth.verify_password(password, stored) or not user:
        raise HTTPException(401, "E-posta veya şifre hatalı.")
    if site["locked"]:
        raise HTTPException(403, "Paneliniz kilitli. Lütfen bizimle iletişime geçin.")

    db.touch_login(user["id"])
    token = auth.issue_token(site["id"], user["id"], "admin")
    return {
        "token": token,
        "site": {"slug": site["slug"], "title": site["title"], "domain": site["domain"]},
        "user": {"email": user["email"], "name": user["display_name"]},
    }


@router.post("/logout")
def logout(sess: dict = Depends(auth.require_admin)) -> dict[str, bool]:
    db.drop_session(sess["token"])
    return {"ok": True}


@router.get("/me")
def me(sess: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    site = _site_of(sess)
    return {
        "site": {
            "slug": site["slug"],
            "title": site["title"],
            "domain": site["custom_domain"] or site["domain"],
            "status": site["status"],
            "published_at": site["published_at"],
            "expires_at": site["expires_at"],
        },
        "content": db.draft_of(site),
        "unpublished": db.has_unpublished(site),
        "templates": schema.TEMPLATES,
        "presets": schema.PRESETS,
        "fonts": list(schema.FONTS),
        "sections": schema.DEFAULT_SECTION_ORDER,
        "min_password": auth.MIN_PASSWORD,
        "storage": {
            "site_id": site["id"],          # önizlemede görsel adresini kurmak için
            "used": db.site_asset_bytes(site["id"]),
            "limit": images.MAX_SITE_BYTES,
        },
    }


@router.put("/content")
def save_content(payload: dict = Body(...),
                 sess: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    """Taslağı kaydet. Siteye dokunmaz — yayına almak ayrı bir adım.

    Bu ayrım GitHub Pages'in saatlik derleme sınırını korumak için var:
    müşteri istediği kadar kaydeder, tek seferde yayınlar.
    """
    site = _site_of(sess)
    clean = schema.normalize(payload, db.draft_of(site))
    db.set_draft(site["id"], clean)
    if clean["site"]["title"] != site["title"]:
        db.update_site(site["id"], title=clean["site"]["title"])
    if clean["theme"]["template"] != site["template"]:
        db.update_site(site["id"], template=clean["theme"]["template"])
    return {"ok": True, "unpublished": True, "content": clean}


@router.post("/upload")
async def upload(file: UploadFile = File(...),
                 kind: str = Form("photo"),
                 sess: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    site = _site_of(sess)
    raw = await file.read()
    return images.process(site["id"], raw, file.content_type or "", kind)


@router.post("/publish")
async def publish(sess: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    site = _site_of(sess)
    if site["status"] == "kuruluyor":
        raise HTTPException(409, "Siteniz hâlâ kuruluyor, birkaç saniye sonra tekrar deneyin.")
    lock = _lock(site["id"])
    if lock.locked():
        raise HTTPException(409, "Yayınlama zaten sürüyor.")
    async with lock:
        try:
            result = await provisioner.publish(site["id"])
        except Exception as exc:                       # noqa: BLE001
            db.log(site["id"], "hata", f"yayin: {exc}")
            raise HTTPException(502, f"Yayınlanamadı: {exc}") from exc
    return {
        "ok": True,
        **result,
        "message": "Yayınlandı. Siteniz 1 dakika içinde güncellenir.",
    }


def _previewable(html: str, site_id: int) -> str:
    """Henüz repoya gitmemiş görselleri önizlemede gösterebilmek için
    /assets/... yollarını sunucudaki geçici uca çevir.

    Görselin geçebileceği her yeri kapsamalı: src özniteliği, CSS url(),
    ve ürün galerisinin data-imgs listesi (boru işaretiyle ayrılmış).
    Biri atlanırsa müşteri önizlemede kırık görsel görür.
    """
    hedef = f"/api/admin/asset/{site_id}/"
    for eski in ('src="/assets/', "url(/assets/", 'data-imgs="/assets/', "|/assets/"):
        yeni = eski.replace("/assets/", hedef)
        html = html.replace(eski, yeni)
    return html


@router.get("/asset/{site_id}/{name}")
def asset(site_id: int, name: str) -> FileResponse:
    """Yayınlanmamış görselin önizlemesi.

    Dosya adı içeriğin sha256 özeti olduğu için tahmin edilemez; buradaki
    içerik zaten yayınlandığında herkese açık olacak bir site görseli.
    """
    if "/" in name or ".." in name or not name.endswith(".webp"):
        raise HTTPException(404, "Bulunamadı.")
    path = images.site_dir(site_id) / name
    if not path.exists():
        raise HTTPException(404, "Bulunamadı.")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=31536000"})


@router.get("/preview", response_class=HTMLResponse)
def preview(sess: dict = Depends(auth.require_admin)) -> HTMLResponse:
    """Yayınlanmamış taslağın birebir görüntüsü."""
    site = _site_of(sess)
    html = renderer.preview_html(db.draft_of(site), site["custom_domain"] or site["domain"])
    return HTMLResponse(_previewable(html, site["id"]), headers={"X-Robots-Tag": "noindex"})


@router.post("/preview", response_class=HTMLResponse)
def preview_live(payload: dict = Body(...),
                 sess: dict = Depends(auth.require_admin)) -> HTMLResponse:
    """Kaydetmeden önizleme — panelde her değişiklikte anında yenilenir."""
    site = _site_of(sess)
    clean = schema.normalize(payload, db.draft_of(site))
    html = renderer.preview_html(clean, site["custom_domain"] or site["domain"])
    return HTMLResponse(_previewable(html, site["id"]), headers={"X-Robots-Tag": "noindex"})


@router.get("/health")
async def site_health(sess: dict = Depends(auth.require_admin)) -> dict[str, Any]:
    return await provisioner.health(_site_of(sess)["id"])


@router.post("/password")
def change_password(current: str = Body(..., embed=True),
                    new: str = Body(..., embed=True),
                    sess: dict = Depends(auth.require_admin)) -> dict[str, bool]:
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE id=? AND site_id=?",
            (sess["user_id"], sess["site_id"]),
        ).fetchone()
    user = dict(row) if row else None
    if not user or not auth.verify_password(current, user["password_hash"]):
        raise HTTPException(401, "Mevcut şifreniz hatalı.")
    db.set_password(user["id"], auth.hash_password(new))
    db.drop_sessions_of_site(sess["site_id"])
    return {"ok": True}
