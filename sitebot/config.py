"""Ayar yükleyici. Gerçek anahtarlar settings.json'da, git'e girmez."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "settings.json"
DB_PATH = BASE_DIR / "sitebot.db"
UPLOAD_DIR = BASE_DIR / "uploads"

DEFAULTS: dict[str, Any] = {
    # --- GitHub ---
    "github_token": "",          # fine-grained PAT (Administration/Contents/Pages: RW)
    "github_org": "wizaicorp",   # siteler bu hesapta açılır (org ya da kullanıcı)
    "github_pages_host": "",     # boşsa <org>.github.io olarak hesaplanır

    # --- Cloudflare ---
    "cloudflare_token": "",
    "cloudflare_zone_id": "",
    "root_domain": "wizaicorp.com",
    "cloudflare_proxied": True,  # True: HTTPS anında (CF edge sertifikası)

    # --- Panel ---
    "panel_domain": "kur.wizaicorp.com",
    "panel_port": 8003,
    "session_secret": "",        # ilk açılışta otomatik üretilir
    "superadmin_user": "hakan",
    "superadmin_password_hash": "",   # ilk kurulumda /kurulum ekranından set edilir

    # --- Bildirim (opsiyonel) ---
    "telegram_token": "",
    "telegram_chat_id": "",
}

# Bu alt alan adları müşteriye verilemez — sunucudaki mevcut servisler
# ve ileride lazım olabilecek isimler.
RESERVED_SUBDOMAINS = {
    "www", "panel", "kur", "api", "admin", "mail", "smtp", "imap", "ftp",
    "ns1", "ns2", "cdn", "static", "assets", "img", "blog", "test", "dev",
    "staging", "wa", "bathonea", "hakanerbas", "app", "portal", "shop",
    "demo", "docs", "status", "git", "vpn", "db", "s3", "media",
}

_cache: dict[str, Any] | None = None


def load(refresh: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not refresh:
        return _cache

    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"settings.json bozuk: {exc}") from exc

    # Ortam değişkeni her zaman dosyayı ezer (systemd'den geçici override için).
    for key in DEFAULTS:
        env = os.environ.get(f"SITEBOT_{key.upper()}")
        if env:
            data[key] = env

    if not data.get("session_secret"):
        data["session_secret"] = secrets.token_urlsafe(48)
        save(data)

    if not data.get("github_pages_host"):
        data["github_pages_host"] = f"{data['github_org']}.github.io"

    _cache = data
    return data


def save(data: dict[str, Any]) -> None:
    global _cache
    merged = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            merged.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
        except json.JSONDecodeError:
            pass
    merged.update(data)
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), "utf-8"
    )
    SETTINGS_PATH.chmod(0o600)
    _cache = None


def is_configured() -> bool:
    """Site açabilmek için gereken minimum anahtarlar var mı?"""
    c = load()
    return bool(c["github_token"] and c["cloudflare_token"] and c["cloudflare_zone_id"])
