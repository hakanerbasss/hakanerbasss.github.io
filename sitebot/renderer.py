"""
Statik site üreteci.

Şablonlar tarayıcıda JSON okumuyor — panel "Yayınla" dediğinde bitmiş
HTML burada üretilip repoya basılıyor. Böylece site saf statik kalıyor:
Google tam görüyor, ilk açılış anında oluyor, JavaScript kapalıyken bile
çalışıyor.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

import config
from schema import FONTS, PRESETS, TEMPLATES

TEMPLATE_DIR = Path(__file__).resolve().parent / "site_templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ------------------------------------------------------------------ yardımcılar

def _tel(raw: str) -> str:
    """'0532 111 22 33' → 'tel:+905321112233'."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = "90" + digits[1:]
    elif not digits.startswith("90") and len(digits) == 10:
        digits = "90" + digits
    return f"tel:+{digits}"


def _wa(raw: str, message: str = "") -> str:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("0"):
        digits = "90" + digits[1:]
    elif not digits.startswith("90") and len(digits) == 10:
        digits = "90" + digits
    url = f"https://wa.me/{digits}"
    if message:
        from urllib.parse import quote
        url += f"?text={quote(message)}"
    return url


def _map_src(query: str) -> str:
    if not query:
        return ""
    from urllib.parse import quote
    return f"https://maps.google.com/maps?q={quote(query)}&output=embed&hl=tr"


def _social_url(kind: str, value: str) -> str:
    """Kullanıcı '@firma' da yazsa tam adres de yapıştırsa doğru linke çevir."""
    if not value:
        return ""
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    handle = value.lstrip("@/")
    bases = {
        "instagram": "https://instagram.com/",
        "facebook": "https://facebook.com/",
        "x": "https://x.com/",
        "youtube": "https://youtube.com/@",
        "tiktok": "https://tiktok.com/@",
        "linkedin": "https://linkedin.com/company/",
    }
    return bases.get(kind, "https://") + handle


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = (color or "").lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        return (91, 140, 255)
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (91, 140, 255)


def _mix(color: str, other: str, ratio: float) -> str:
    r1, g1, b1 = _hex_to_rgb(color)
    r2, g2, b2 = _hex_to_rgb(other)
    mix = lambda a, b: int(a + (b - a) * ratio)  # noqa: E731
    return f"#{mix(r1, r2):02x}{mix(g1, g2):02x}{mix(b1, b2):02x}"


def build_theme(data: dict[str, Any]) -> dict[str, Any]:
    """Şablonların kullanacağı hazır CSS değerleri.

    Müşteri panelden bir palet seçiyor; buradan çıkan sözlük tüm
    renk hesaplarını (yumuşak zeminler, kenarlıklar, gölgeler) otomatik
    türetiyor, böylece hiçbir kombinasyon okunmaz bir sonuç vermiyor.
    """
    th = data.get("theme", {})
    preset = PRESETS.get(th.get("preset"), PRESETS["gece"])
    primary = th.get("primary") or preset["primary"]
    accent = th.get("accent") or preset["accent"]
    bg, fg, dark = preset["bg"], preset["fg"], preset["dark"]

    pr, pg, pb = _hex_to_rgb(primary)
    ar, ag, ab = _hex_to_rgb(accent)
    return {
        "bg": bg,
        "fg": fg,
        "primary": primary,
        "accent": accent,
        "dark": dark,
        "primary_rgb": f"{pr},{pg},{pb}",
        "accent_rgb": f"{ar},{ag},{ab}",
        "surface": _mix(bg, fg, 0.05 if dark else 0.035),
        "surface_2": _mix(bg, fg, 0.09 if dark else 0.07),
        "border": _mix(bg, fg, 0.16 if dark else 0.12),
        "muted": _mix(fg, bg, 0.38),
        "on_primary": "#ffffff" if sum(_hex_to_rgb(primary)) < 520 else "#0b1020",
        "on_accent": "#ffffff" if sum(_hex_to_rgb(accent)) < 520 else "#0b1020",
        "font": FONTS.get(th.get("font"), FONTS["modern"]),
        "radius": th.get("radius", 16),
    }


def prepare(data: dict[str, Any], domain: str) -> dict[str, Any]:
    """Ham şema verisini şablonun doğrudan kullanabileceği hale getir."""
    contact = data.get("contact", {})
    site = data.get("site", {})
    banner = dict(data.get("banner", {}))

    tel = _tel(contact.get("phone", ""))
    wa = _wa(contact.get("whatsapp") or contact.get("phone", ""),
             f"Merhaba, {site.get('title', '')} sitenizden yazıyorum.")

    # Banner butonları boşsa telefona/WhatsApp'a bağla — müşteri hiçbir şey
    # ayarlamasa bile site çalışır durumda olsun.
    if not banner.get("cta_link") or banner.get("cta_link") == "tel:":
        banner["cta_link"] = tel or "#iletisim"
    if not banner.get("cta2_link"):
        banner["cta2_link"] = wa or "#iletisim"
    if not wa:
        banner["cta2_text"] = ""

    socials = [
        {"kind": k, "url": _social_url(k, v), "label": k}
        for k, v in (data.get("social") or {}).items() if v
    ]

    categories: list[str] = []
    for p in data.get("products", []):
        if p.get("category") and p["category"] not in categories:
            categories.append(p["category"])

    enabled = data.get("sections", {}).get("enabled", {})
    order = data.get("sections", {}).get("order", [])
    sections = [s for s in order if enabled.get(s, True)]
    if data.get("products"):
        pass
    else:
        sections = [s for s in sections if s != "products"]
    if not data.get("gallery"):
        sections = [s for s in sections if s != "gallery"]
    if not data.get("services"):
        sections = [s for s in sections if s != "services"]

    return {
        "d": data,
        "site": site,
        "banner": banner,
        "about": data.get("about", {}),
        "services": data.get("services", []),
        "products": data.get("products", []),
        "gallery": data.get("gallery", []),
        "contact": contact,
        "categories": categories,
        "sections": sections,
        "socials": socials,
        "tel": tel,
        "whatsapp": wa,
        "map_src": _map_src(contact.get("map_query") or contact.get("address", "")),
        "theme": build_theme(data),
        "domain": domain,
        "year": datetime.now(timezone.utc).year,
        "templates": TEMPLATES,
    }


# ------------------------------------------------------------------------ üretim

def render_html(data: dict[str, Any], domain: str) -> str:
    key = data.get("theme", {}).get("template", "hizmet")
    if key not in TEMPLATES:
        key = "hizmet"
    return _env.get_template(f"{key}/index.html.j2").render(**prepare(data, domain))


def _sitemap(domain: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>https://{domain}/</loc><lastmod>{today}</lastmod>"
        "<changefreq>weekly</changefreq><priority>1.0</priority></url>\n"
        "</urlset>\n"
    )


def _not_found(data: dict[str, Any], domain: str) -> str:
    theme = build_theme(data)
    title = html.escape(data.get("site", {}).get("title", "Site"))
    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sayfa bulunamadı | {title}</title>
<style>
  body{{margin:0;min-height:100vh;display:grid;place-items:center;text-align:center;
       background:{theme['bg']};color:{theme['fg']};font-family:{theme['font']};padding:24px}}
  .c{{max-width:460px}} h1{{font-size:clamp(64px,18vw,140px);margin:0;line-height:1;
       background:linear-gradient(135deg,{theme['primary']},{theme['accent']});
       -webkit-background-clip:text;background-clip:text;color:transparent}}
  p{{color:{theme['muted']};margin:12px 0 28px}}
  a{{display:inline-block;padding:14px 28px;border-radius:{theme['radius']}px;
     background:{theme['primary']};color:{theme['on_primary']};text-decoration:none;font-weight:600}}
</style></head>
<body><div class="c"><h1>404</h1>
<p>Aradığınız sayfa taşınmış veya hiç var olmamış olabilir.</p>
<a href="/">Ana sayfaya dön</a></div></body></html>
"""


def render_site(data: dict[str, Any], domain: str,
                admin_files: dict[str, str] | None = None) -> dict[str, str]:
    """Repoya basılacak tüm dosyaları üret."""
    files: dict[str, str] = {
        "index.html": render_html(data, domain),
        "site.json": json.dumps(data, ensure_ascii=False, indent=2),
        "404.html": _not_found(data, domain),
        "CNAME": domain + "\n",
        "robots.txt": f"User-agent: *\nAllow: /\nDisallow: /admin/\n\nSitemap: https://{domain}/sitemap.xml\n",
        "sitemap.xml": _sitemap(domain),
        ".nojekyll": "",   # Pages'in Jekyll işlemesini atla → build daha hızlı
    }
    if admin_files:
        files.update(admin_files)
    return files


def preview_html(data: dict[str, Any], domain: str) -> str:
    """Panel içi canlı önizleme — yayınlanmamış taslağı gösterir."""
    return render_html(data, domain)


def available_templates() -> dict[str, Any]:
    return TEMPLATES
