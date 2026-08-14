"""
Cloudflare DNS istemcisi.

Alt alan adı → GitHub Pages yönlendirmesi burada kuruluyor.

Sertifika notu: Cloudflare Universal SSL zaten *.wizaicorp.com'u
kapsadığı için proxied=True ile HTTPS **anında** çalışır. proxied=False
seçilirse GitHub kendi Let's Encrypt sertifikasını üretir (5-15 dk) —
daha "saf" ama müşteriye anında teslim edilemez.
"""

from __future__ import annotations

from typing import Any

import httpx

import config

API = "https://api.cloudflare.com/client/v4"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class CloudflareError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    token = config.load()["cloudflare_token"]
    if not token:
        raise CloudflareError("Cloudflare token tanımlı değil (settings.json → cloudflare_token).")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _zone() -> str:
    zone = config.load()["cloudflare_zone_id"]
    if not zone:
        raise CloudflareError("Cloudflare zone_id tanımlı değil.")
    return zone


async def _req(client: httpx.AsyncClient, method: str, path: str, **kw: Any) -> Any:
    r = await client.request(method, f"{API}{path}", headers=_headers(), **kw)
    try:
        body = r.json()
    except ValueError:
        raise CloudflareError(f"Cloudflare yanıtı okunamadı ({r.status_code}).")
    if not body.get("success"):
        errors = body.get("errors") or [{"message": r.text[:200]}]
        msg = "; ".join(str(e.get("message", e)) for e in errors)
        raise CloudflareError(f"Cloudflare {method} {path}: {msg}")
    return body.get("result")


async def check_token() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        zone = await _req(c, "GET", f"/zones/{_zone()}")
        return {"zone": zone.get("name"), "status": zone.get("status")}


async def find_record(name: str) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        result = await _req(c, "GET", f"/zones/{_zone()}/dns_records",
                            params={"name": name, "per_page": 5})
        return result[0] if result else None


async def upsert_cname(subdomain: str, target: str,
                       proxied: bool | None = None) -> dict[str, Any]:
    """slug.wizaicorp.com → org.github.io CNAME kaydı kur (varsa güncelle)."""
    cfg = config.load()
    name = f"{subdomain}.{cfg['root_domain']}"
    proxied = cfg["cloudflare_proxied"] if proxied is None else proxied
    payload = {"type": "CNAME", "name": name, "content": target,
               "ttl": 1, "proxied": proxied}

    existing = await find_record(name)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        if existing:
            return await _req(c, "PUT",
                              f"/zones/{_zone()}/dns_records/{existing['id']}", json=payload)
        return await _req(c, "POST", f"/zones/{_zone()}/dns_records", json=payload)


async def set_proxied(subdomain: str, proxied: bool) -> dict[str, Any] | None:
    """Turuncu bulutu aç/kapat.

    GitHub'ın kendi sertifikasını üretebilmesi için geçici olarak
    kapatmak gerekebiliyor.
    """
    cfg = config.load()
    name = f"{subdomain}.{cfg['root_domain']}"
    existing = await find_record(name)
    if not existing:
        return None
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        return await _req(
            c, "PATCH", f"/zones/{_zone()}/dns_records/{existing['id']}",
            json={"proxied": proxied},
        )


async def delete_cname(subdomain: str) -> bool:
    cfg = config.load()
    name = f"{subdomain}.{cfg['root_domain']}"
    existing = await find_record(name)
    if not existing:
        return False
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        await _req(c, "DELETE", f"/zones/{_zone()}/dns_records/{existing['id']}")
        return True
