"""
Görsel işleme.

Müşteri telefonundan 6 MB'lık bir fotoğraf yükleyebilir; onu olduğu gibi
repoya koymak hem GitHub Pages'in 1 GB repo sınırını hem de ziyaretçinin
mobil verisini yakar. Burada her görsel yeniden boyutlandırılıp WebP'ye
çevriliyor — tipik olarak 6 MB → 120 KB.

Dosyalar önce sunucuda saklanıyor, repoya ancak "Yayınla" anında
gönderiliyor. Böylece müşteri 20 fotoğraf yükleyip tek commit atıyor.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

import db
from config import UPLOAD_DIR

MAX_UPLOAD_BYTES = 12 * 1024 * 1024      # ham dosya sınırı
MAX_SITE_BYTES = 220 * 1024 * 1024       # site başına işlenmiş görsel toplamı
MAX_EDGE = 1800                          # en uzun kenar
LOGO_EDGE = 420
QUALITY = 82

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif",
           "image/avif", "image/heic", "image/heif", "image/bmp"}


def site_dir(site_id: int) -> Path:
    d = UPLOAD_DIR / str(site_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def process(site_id: int, raw: bytes, content_type: str,
            kind: str = "photo") -> dict[str, object]:
    """Yüklenen görseli WebP'ye çevir, diske yaz, kaydını tut.

    kind='logo' küçük tutulur; kind='photo' tam boy kalır.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Görsel çok büyük (en fazla 12 MB).")
    if content_type and content_type.split(";")[0].strip() not in ALLOWED:
        raise HTTPException(415, "Desteklenmeyen dosya türü. JPG, PNG veya WebP yükleyin.")
    if db.site_asset_bytes(site_id) > MAX_SITE_BYTES:
        raise HTTPException(413, "Görsel alanınız doldu. Kullanmadığınız görselleri silin.")

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)      # telefon fotoğrafları yan yatmasın
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Dosya okunamadı, geçerli bir görsel seçin.")

    if img.mode in ("P", "LA", "RGBA"):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (255, 255, 255, 0))
        img = Image.alpha_composite(flat, img).convert("RGBA")
    else:
        img = img.convert("RGB")

    edge = LOGO_EDGE if kind == "logo" else MAX_EDGE
    if max(img.size) > edge:
        img.thumbnail((edge, edge), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=QUALITY, method=5)
    data = buf.getvalue()

    name = hashlib.sha256(data).hexdigest()[:16] + ".webp"
    path = f"assets/{name}"
    target = site_dir(site_id) / name
    if not target.exists():
        target.write_bytes(data)

    db.add_asset(site_id, path, len(data))
    return {"path": path, "bytes": len(data), "width": img.width, "height": img.height}


def read(site_id: int, path: str) -> bytes | None:
    """Repoya gönderilecek dosyanın içeriğini diskten oku."""
    if not path.startswith("assets/") or "/" in path[7:] or ".." in path:
        return None
    f = site_dir(site_id) / path[7:]
    return f.read_bytes() if f.exists() else None


def used_paths(data: dict) -> set[str]:
    """Site verisinde gerçekten kullanılan görsel yolları."""
    used: set[str] = set()
    for key in ("logo", "favicon"):
        if data.get("site", {}).get(key):
            used.add(data["site"][key])
    if data.get("banner", {}).get("image"):
        used.add(data["banner"]["image"])
    if data.get("about", {}).get("image"):
        used.add(data["about"]["image"])
    if data.get("seo", {}).get("og_image"):
        used.add(data["seo"]["og_image"])
    for sv in data.get("services", []):
        if sv.get("image"):
            used.add(sv["image"])
    for pr in data.get("products", []):
        used.update(i for i in pr.get("images", []) if i)
    for g in data.get("gallery", []):
        if g.get("image"):
            used.add(g["image"])
    return {u for u in used if u.startswith("assets/")}
