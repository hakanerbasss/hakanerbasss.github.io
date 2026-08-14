"""
Kimlik doğrulama ve kiracı izolasyonu.

Şifreler stdlib scrypt ile saklanıyor — ek bağımlılık yok, bcrypt kadar
güvenli. Oturumlar veritabanında; müşterinin admin paneli kendi alan
adından (hurdaci.wizaicorp.com/admin) çalıştığı için çerez değil
Bearer token kullanıyoruz.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Any

from fastapi import Header, HTTPException

import config
import db

SESSION_TTL = 60 * 60 * 24 * 14      # 14 gün
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1

_TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


# ------------------------------------------------------------------- şifreler

def hash_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(400, "Şifre en az 8 karakter olmalı.")
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt,
                         n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, key_hex = stored.split("$")
        if algo != "scrypt":
            return False
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                             n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(key.hex(), key_hex)
    except (ValueError, TypeError):
        return False


def random_password(length: int = 12) -> str:
    """Yeni müşteriye verilecek okunabilir geçici şifre (karışan harf yok)."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------- slug

def slugify(text: str) -> str:
    """'Hurdacı Ali' → 'hurdaci-ali'.

    Alan adı olacağı için Türkçe karakterler ASCII'ye indirgeniyor:
    punycode'a düşen alan adlarında GitHub Pages sertifikası sorun
    çıkarabiliyor.
    """
    text = (text or "").translate(_TR_MAP)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = re.sub(r"-{2,}", "-", text)
    return text[:40].strip("-")


def validate_slug(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])?", slug or ""):
        raise HTTPException(
            400, "Adres yalnızca küçük harf, rakam ve tire içerebilir (2-40 karakter)."
        )
    if slug in config.RESERVED_SUBDOMAINS:
        raise HTTPException(400, f"'{slug}' adresi sistem tarafından ayrılmış, başka bir ad seçin.")
    if db.get_site_by_slug(slug):
        raise HTTPException(409, f"'{slug}' adresi zaten kullanımda.")
    return slug


# ------------------------------------------------------------------ oturumlar

def issue_token(site_id: int, user_id: int, kind: str = "admin") -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(token, site_id, user_id, kind, SESSION_TTL)
    return token


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Oturum bulunamadı, tekrar giriş yapın.")
    return authorization.split(" ", 1)[1].strip()


def current_session(authorization: str | None = Header(None)) -> dict[str, Any]:
    sess = db.get_session(_token_from_header(authorization))
    if not sess:
        raise HTTPException(401, "Oturum süresi doldu, tekrar giriş yapın.")
    return sess


def require_admin(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Müşteri paneli için: oturumu doğrula, sitesini getir, kilidi kontrol et.

    Dönen sözlükteki site_id dışına çıkan sorgu yazılmamalı — kiracı
    izolasyonunun tamamı buna dayanıyor.
    """
    sess = current_session(authorization)
    if sess["kind"] == "super":
        return sess
    site = db.get_site(sess["site_id"])
    if not site:
        raise HTTPException(404, "Site bulunamadı.")
    if site["locked"]:
        raise HTTPException(
            403, "Paneliniz kilitli. Aboneliğinizi yenilemek için bizimle iletişime geçin."
        )
    sess["site"] = site
    return sess


def require_super(authorization: str | None = Header(None)) -> dict[str, Any]:
    sess = current_session(authorization)
    if sess["kind"] != "super":
        raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekiyor.")
    return sess


def superadmin_login(username: str, password: str) -> str:
    cfg = config.load(refresh=True)
    stored = cfg.get("superadmin_password_hash") or ""
    if not stored:
        raise HTTPException(400, "Süper yönetici şifresi henüz belirlenmemiş. /kurulum adresini açın.")
    if username.strip() != cfg.get("superadmin_user") or not verify_password(password, stored):
        raise HTTPException(401, "Kullanıcı adı veya şifre hatalı.")
    return issue_token(site_id=0, user_id=0, kind="super")
