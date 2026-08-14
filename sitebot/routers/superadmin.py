"""
Süper yönetici API'si — yalnızca sen.

Site açma, abonelik süresi verme, paneli kilitleme, şifre sıfırlama,
siteyi tamamen silme ve sistem ayarları burada.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

import auth
import cloudflare_api as cf
import config
import db
import github_api as gh
import provisioner
import schema

router = APIRouter(prefix="/api/super", tags=["super"])


@router.post("/setup")
def first_setup(username: str = Body(..., embed=True),
                password: str = Body(..., embed=True)) -> dict[str, Any]:
    """İlk kurulum: süper yönetici şifresini bir kez belirle.

    Şifre zaten belirlenmişse bu uç kapanır — dışarıdan sıfırlanamaz.
    """
    cfg = config.load(refresh=True)
    if cfg.get("superadmin_password_hash"):
        raise HTTPException(409, "Kurulum zaten tamamlanmış.")
    config.save({
        "superadmin_user": username.strip() or "hakan",
        "superadmin_password_hash": auth.hash_password(password),
    })
    return {"ok": True, "token": auth.superadmin_login(username.strip() or "hakan", password)}


@router.get("/status")
def setup_status() -> dict[str, Any]:
    cfg = config.load(refresh=True)
    return {
        "kurulum_tamam": bool(cfg.get("superadmin_password_hash")),
        "anahtarlar_tamam": config.is_configured(),
        "org": cfg["github_org"],
        "domain": cfg["root_domain"],
        "panel": cfg["panel_domain"],
    }


@router.post("/login")
def login(username: str = Body(..., embed=True),
          password: str = Body(..., embed=True)) -> dict[str, str]:
    return {"token": auth.superadmin_login(username, password)}


# ----------------------------------------------------------------- ayarlar

SAFE_SETTING_KEYS = {
    "github_token", "github_org", "cloudflare_token", "cloudflare_zone_id",
    "root_domain", "cloudflare_proxied", "panel_domain",
    "telegram_token", "telegram_chat_id",
}
SECRET_KEYS = {"github_token", "cloudflare_token", "telegram_token"}


@router.get("/settings")
def get_settings(_: dict = Depends(auth.require_super)) -> dict[str, Any]:
    """Anahtarlar maskeli döner — panel ekranında tam değer hiç görünmez."""
    cfg = config.load(refresh=True)
    out: dict[str, Any] = {}
    for key in SAFE_SETTING_KEYS:
        val = cfg.get(key, "")
        if key in SECRET_KEYS and val:
            out[key] = f"••••••••{str(val)[-4:]}"
            out[f"{key}_var"] = True
        else:
            out[key] = val
            if key in SECRET_KEYS:
                out[f"{key}_var"] = False
    return out


@router.post("/settings")
def set_settings(payload: dict = Body(...),
                 _: dict = Depends(auth.require_super)) -> dict[str, bool]:
    update: dict[str, Any] = {}
    for key, val in payload.items():
        if key not in SAFE_SETTING_KEYS:
            continue
        if key in SECRET_KEYS and (not val or str(val).startswith("••••")):
            continue                      # maskeli değer geri gönderildi, dokunma
        update[key] = val
    if update:
        config.save(update)
    return {"ok": True}


@router.post("/check")
async def check_keys(_: dict = Depends(auth.require_super)) -> dict[str, Any]:
    """Kaydedilen anahtarlar gerçekten çalışıyor mu? Site açmadan önce dene."""
    out: dict[str, Any] = {}
    try:
        out["github"] = {"ok": True, **await gh.check_token()}
    except Exception as exc:                          # noqa: BLE001
        out["github"] = {"ok": False, "hata": str(exc)}
    try:
        out["cloudflare"] = {"ok": True, **await cf.check_token()}
    except Exception as exc:                          # noqa: BLE001
        out["cloudflare"] = {"ok": False, "hata": str(exc)}
    return out


# ------------------------------------------------------------------ siteler

@router.get("/sites")
def sites(_: dict = Depends(auth.require_super)) -> list[dict[str, Any]]:
    out = []
    for s in db.list_sites():
        s.pop("draft_json", None)
        s.pop("live_json", None)
        s["provision_log"] = json.loads(s["provision_log"] or "[]")[-3:]
        out.append(s)
    return out


@router.get("/sites/{site_id}")
def site_detail(site_id: int, _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    site["provision_log"] = json.loads(site["provision_log"] or "[]")
    site["content"] = db.draft_of(site)
    site["unpublished"] = db.has_unpublished(site)
    site.pop("draft_json", None)
    site.pop("live_json", None)
    site["events"] = db.recent_events(site_id, 30)
    return site


@router.post("/sites")
async def create_site(
    title: str = Body(...),
    slug: str = Body(""),
    template: str = Body("hizmet"),
    email: str = Body(...),
    phone: str = Body(""),
    password: str = Body(""),
    _: dict = Depends(auth.require_super),
) -> dict[str, Any]:
    """Yeni müşteri sitesi aç. Kurulum arka planda sürer, panel takip eder."""
    if not config.is_configured():
        raise HTTPException(400, "Önce GitHub ve Cloudflare anahtarlarını ayarlayın.")
    if template not in schema.TEMPLATES:
        raise HTTPException(400, "Geçersiz şablon.")
    if "@" not in email:
        raise HTTPException(400, "Geçerli bir e-posta girin.")

    cfg = config.load()
    slug = auth.validate_slug(auth.slugify(slug or title))
    domain = f"{slug}.{cfg['root_domain']}"
    repo = slug

    content = schema.blank_site(title, title, template)
    content["contact"]["phone"] = phone
    content["contact"]["whatsapp"] = phone
    content["contact"]["email"] = email
    content["banner"]["headline"] = title

    site_id = db.create_site(slug, title, domain, repo, template, content)
    plain = password or auth.random_password()
    db.create_user(site_id, email, auth.hash_password(plain), title)

    provisioner.start_provision(site_id)

    return {
        "id": site_id,
        "slug": slug,
        "domain": domain,
        "admin_url": f"https://{domain}/admin/",
        "email": email,
        "password": plain,          # tek gösterim — veritabanında yalnızca özeti var
        "durum": "kuruluyor",
    }


@router.post("/sites/{site_id}/retry")
async def retry(site_id: int, _: dict = Depends(auth.require_super)) -> dict[str, bool]:
    if not db.get_site(site_id):
        raise HTTPException(404, "Site bulunamadı.")
    db.update_site(site_id, provision_log="[]")
    provisioner.start_provision(site_id)
    return {"ok": True}


@router.post("/sites/{site_id}/publish")
async def republish(site_id: int, _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    if not db.get_site(site_id):
        raise HTTPException(404, "Site bulunamadı.")
    try:
        return await provisioner.publish(site_id, "Yönetici tarafından yeniden yayınlandı")
    except Exception as exc:                          # noqa: BLE001
        raise HTTPException(502, str(exc)) from exc


@router.get("/sites/{site_id}/health")
async def health(site_id: int, _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    return await provisioner.health(site_id)


@router.post("/sites/{site_id}/lock")
def lock(site_id: int, locked: bool = Body(..., embed=True),
         _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    """Aboneliği biten müşterinin panelini kilitle. Sitesi yayında kalır."""
    if not db.get_site(site_id):
        raise HTTPException(404, "Site bulunamadı.")
    db.update_site(site_id, locked=1 if locked else 0)
    if locked:
        db.drop_sessions_of_site(site_id)
    db.log(site_id, "abonelik", "panel kilitlendi" if locked else "panel açıldı")
    return {"ok": True, "locked": locked}


@router.post("/sites/{site_id}/expiry")
def set_expiry(site_id: int, expires_at: int = Body(..., embed=True),
               _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    if not db.get_site(site_id):
        raise HTTPException(404, "Site bulunamadı.")
    db.update_site(site_id, expires_at=int(expires_at))
    return {"ok": True, "expires_at": expires_at}


@router.post("/sites/{site_id}/reset-password")
def reset_password(site_id: int, _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    with db.conn() as c:
        row = c.execute("SELECT * FROM users WHERE site_id=? ORDER BY id LIMIT 1",
                        (site_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Bu sitenin kullanıcısı yok.")
    plain = auth.random_password()
    db.set_password(row["id"], auth.hash_password(plain))
    db.drop_sessions_of_site(site_id)
    db.log(site_id, "sifre", "yönetici şifreyi sıfırladı")
    return {"ok": True, "email": row["email"], "password": plain}


@router.delete("/sites/{site_id}")
async def remove(site_id: int, delete_repo: bool = True,
                 _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    """Siteyi tamamen kaldır — DNS kaydı, GitHub deposu ve kayıtlar."""
    site = db.get_site(site_id)
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    result = await provisioner.teardown(site_id, delete_repo=delete_repo)
    return {"ok": True, "silinen": site["domain"], **result}


@router.get("/events")
def events(limit: int = 60, _: dict = Depends(auth.require_super)) -> list[dict[str, Any]]:
    return db.recent_events(None, min(limit, 200))


@router.post("/slug-check")
def slug_check(value: str = Body(..., embed=True),
               _: dict = Depends(auth.require_super)) -> dict[str, Any]:
    """Panelde yazarken canlı adres kontrolü."""
    slug = auth.slugify(value)
    cfg = config.load()
    try:
        auth.validate_slug(slug)
        return {"slug": slug, "uygun": True, "domain": f"{slug}.{cfg['root_domain']}"}
    except HTTPException as exc:
        return {"slug": slug, "uygun": False, "sebep": exc.detail,
                "domain": f"{slug}.{cfg['root_domain']}"}
