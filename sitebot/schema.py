"""
SiteBot ortak veri şeması.

Tüm şablonlar AYNI bu şemayı okur. Müşteri şablon değiştirdiğinde
içeriği aynen yeni tasarıma taşınır — bu sistemin en önemli kuralı.
Yeni bir alan eklerken üç şablonun da onu kullanabildiğinden emin ol.
"""

from __future__ import annotations

import uuid
from typing import Any

SCHEMA_VERSION = 1

# Şablon listesi — site_templates/<key>/ klasörüyle birebir aynı olmalı.
TEMPLATES = {
    "hizmet": {
        "name": "Hizmet Firması",
        "desc": "Nakliye, hurdacı, tamirci, temizlik — hizmet odaklı, güçlü çağrı butonlu",
        "accent": "#ff6b35",
    },
    "katalog": {
        "name": "Ürün Kataloğu",
        "desc": "Fiyatlı ürün vitrini, kategori filtreli, sepetsiz sipariş",
        "accent": "#2563eb",
    },
    "kurumsal": {
        "name": "Kurumsal / Portfolyo",
        "desc": "Ajans, danışmanlık, mimarlık — sade, geniş görselli, prestijli",
        "accent": "#0f766e",
    },
}

# Hazır renk paletleri — müşteri kod yazmadan tüm siteyi değiştirsin diye.
# 'dark' bayrağı panelin Aydınlık/Karanlık seçicisini besliyor; her iki kipte
# de yeterli seçenek kalsın diye yeni palet eklerken dengeyi koru.
PRESETS = {
    # --- aydınlık ---
    "kar": {"ad": "Kar", "bg": "#ffffff", "fg": "#12151c",
            "primary": "#111827", "accent": "#e11d48", "dark": False},
    "toprak": {"ad": "Toprak", "bg": "#faf7f2", "fg": "#2b2118",
               "primary": "#8b5e34", "accent": "#c2410c", "dark": False},
    "okyanus": {"ad": "Okyanus", "bg": "#f3f8fb", "fg": "#0c2231",
                "primary": "#0369a1", "accent": "#06b6d4", "dark": False},
    "mermer": {"ad": "Mermer", "bg": "#f7f7f4", "fg": "#14181a",
               "primary": "#14532d", "accent": "#b45309", "dark": False},
    "pastel": {"ad": "Pastel", "bg": "#faf7ff", "fg": "#241b33",
               "primary": "#7c3aed", "accent": "#ec4899", "dark": False},
    # --- karanlık ---
    "gece": {"ad": "Gece", "bg": "#0b1020", "fg": "#e8ecf5",
             "primary": "#5b8cff", "accent": "#ff6b35", "dark": True},
    "orman": {"ad": "Orman", "bg": "#0d1512", "fg": "#e6f2ec",
              "primary": "#34d399", "accent": "#fbbf24", "dark": True},
    "gun_batimi": {"ad": "Gün Batımı", "bg": "#1a1020", "fg": "#f6ecff",
                   "primary": "#a855f7", "accent": "#f59e0b", "dark": True},
    "komur": {"ad": "Kömür", "bg": "#08090b", "fg": "#f4f4f5",
              "primary": "#fafafa", "accent": "#f59e0b", "dark": True},
    "neon": {"ad": "Neon", "bg": "#0a0a1f", "fg": "#e6e9ff",
             "primary": "#22d3ee", "accent": "#ff00ff", "dark": True},
}

FONTS = {
    "modern": "'Inter', 'Segoe UI', system-ui, sans-serif",
    "klasik": "'Georgia', 'Times New Roman', serif",
    "teknik": "'Space Grotesk', 'Segoe UI', sans-serif",
    "yumusak": "'Nunito', 'Segoe UI', sans-serif",
}

# Bölümlerin varsayılan sırası. Müşteri panelden sürükleyip sıralayabilir.
DEFAULT_SECTION_ORDER = [
    "banner",
    "services",
    "about",
    "products",
    "gallery",
    "contact",
]


def new_id() -> str:
    """Ürün/hizmet satırları için kısa benzersiz kimlik."""
    return uuid.uuid4().hex[:8]


def blank_site(name: str, title: str, template: str = "hizmet") -> dict[str, Any]:
    """Yeni açılan bir sitenin başlangıç içeriği.

    Boş bir iskelet değil — müşteri paneli ilk açtığında karşısında
    çalışan, dolu, düzenlenmeye hazır bir site görsün diye örnek
    içerikle geliyor.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "site": {
            "name": name,
            "title": title,
            "slogan": "Kısa ve çarpıcı sloganınız buraya",
            "description": f"{title} — güvenilir hizmet, uygun fiyat.",
            "logo": "",
            "favicon": "",
            "lang": "tr",
        },
        "theme": {
            "template": template,
            "preset": "gece",
            "font": "modern",
            "radius": 16,
            "primary": "",   # boşsa preset'ten gelir
            "accent": "",
        },
        "banner": {
            "headline": title,
            "subline": "Bir cümleyle ne yaptığınızı anlatın.",
            "image": "",
            "cta_text": "Hemen Ara",
            "cta_link": "tel:",
            "cta2_text": "WhatsApp",
            "cta2_link": "",
            "overlay": 55,
        },
        "about": {
            "title": "Hakkımızda",
            "text": "Firmanızı birkaç cümleyle tanıtın. Kaç yıldır bu işi "
                    "yaptığınız, farkınızın ne olduğu müşteriye güven verir.",
            "image": "",
            "stats": [
                {"value": "10+", "label": "Yıllık Tecrübe"},
                {"value": "500+", "label": "Mutlu Müşteri"},
                {"value": "7/24", "label": "Destek"},
            ],
        },
        "services": [
            {"id": new_id(), "icon": "⚡", "title": "Hizmet Bir",
             "text": "Bu hizmeti kısaca anlatın.", "image": ""},
            {"id": new_id(), "icon": "🛡️", "title": "Hizmet İki",
             "text": "Bu hizmeti kısaca anlatın.", "image": ""},
            {"id": new_id(), "icon": "🚚", "title": "Hizmet Üç",
             "text": "Bu hizmeti kısaca anlatın.", "image": ""},
        ],
        "products": [],
        "gallery": [],
        "contact": {
            "phone": "",
            "whatsapp": "",
            "email": "",
            "address": "",
            "map_query": "",       # Google Maps'te aratılacak adres/koordinat
            "hours": [
                {"day": "Pazartesi - Cuma", "time": "09:00 - 18:00"},
                {"day": "Cumartesi", "time": "09:00 - 14:00"},
                {"day": "Pazar", "time": "Kapalı"},
            ],
            "form_endpoint": "",   # Formspree — sunucusuz iletişim formu
        },
        "social": {
            "instagram": "", "facebook": "", "x": "",
            "youtube": "", "tiktok": "", "linkedin": "",
        },
        "sections": {
            "order": list(DEFAULT_SECTION_ORDER),
            "enabled": {k: True for k in DEFAULT_SECTION_ORDER},
        },
        "seo": {"keywords": "", "og_image": ""},
    }


def _clean_str(v: Any, limit: int = 4000) -> str:
    return str(v if v is not None else "").strip()[:limit]


def normalize(data: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Panelden gelen ham veriyi şemaya oturt.

    Panel tarafı JavaScript, bize eksik/fazla alan gönderebilir; burada
    her zaman tam ve güvenli bir sözlük üretiyoruz. Bilinmeyen anahtarlar
    düşer, listeler kimliklendirilir, sayısal alanlar sınırlanır.
    """
    base = base or blank_site("site", "Site")
    out = blank_site(base["site"]["name"], base["site"]["title"],
                     base["theme"]["template"])
    d = data or {}

    for key in ("name", "title", "slogan", "description", "logo", "favicon"):
        out["site"][key] = _clean_str(d.get("site", {}).get(key, out["site"][key]), 300)
    out["site"]["description"] = _clean_str(d.get("site", {}).get("description", ""), 500)

    th = d.get("theme", {})
    out["theme"]["template"] = th.get("template") if th.get("template") in TEMPLATES else out["theme"]["template"]
    out["theme"]["preset"] = th.get("preset") if th.get("preset") in PRESETS else "gece"
    out["theme"]["font"] = th.get("font") if th.get("font") in FONTS else "modern"
    try:
        out["theme"]["radius"] = max(0, min(40, int(th.get("radius", 16))))
    except (TypeError, ValueError):
        out["theme"]["radius"] = 16
    out["theme"]["primary"] = _clean_str(th.get("primary", ""), 20)
    out["theme"]["accent"] = _clean_str(th.get("accent", ""), 20)

    bn = d.get("banner", {})
    for key in ("headline", "subline", "image", "cta_text", "cta_link",
                "cta2_text", "cta2_link"):
        out["banner"][key] = _clean_str(bn.get(key, out["banner"][key]), 300)
    try:
        out["banner"]["overlay"] = max(0, min(90, int(bn.get("overlay", 55))))
    except (TypeError, ValueError):
        out["banner"]["overlay"] = 55

    ab = d.get("about", {})
    out["about"]["title"] = _clean_str(ab.get("title", "Hakkımızda"), 120)
    out["about"]["text"] = _clean_str(ab.get("text", ""), 4000)
    out["about"]["image"] = _clean_str(ab.get("image", ""), 300)
    out["about"]["stats"] = [
        {"value": _clean_str(s.get("value"), 20), "label": _clean_str(s.get("label"), 60)}
        for s in (ab.get("stats") or [])[:6] if isinstance(s, dict)
    ]

    out["services"] = [
        {
            "id": _clean_str(s.get("id")) or new_id(),
            "icon": _clean_str(s.get("icon"), 8),
            "title": _clean_str(s.get("title"), 120),
            "text": _clean_str(s.get("text"), 1000),
            "image": _clean_str(s.get("image"), 300),
        }
        for s in (d.get("services") or [])[:24] if isinstance(s, dict)
    ]

    out["products"] = [
        {
            "id": _clean_str(p.get("id")) or new_id(),
            "name": _clean_str(p.get("name"), 160),
            "desc": _clean_str(p.get("desc"), 1200),
            "price": _clean_str(p.get("price"), 40),
            "currency": _clean_str(p.get("currency"), 8) or "₺",
            "category": _clean_str(p.get("category"), 60),
            "badge": _clean_str(p.get("badge"), 30),
            "link": _clean_str(p.get("link"), 400),
            "images": [_clean_str(i, 300) for i in (p.get("images") or [])[:8] if i],
        }
        for p in (d.get("products") or [])[:300] if isinstance(p, dict)
    ]

    out["gallery"] = [
        {"image": _clean_str(g.get("image"), 300), "caption": _clean_str(g.get("caption"), 160)}
        for g in (d.get("gallery") or [])[:120] if isinstance(g, dict) and g.get("image")
    ]

    ct = d.get("contact", {})
    for key in ("phone", "whatsapp", "email", "address", "map_query", "form_endpoint"):
        out["contact"][key] = _clean_str(ct.get(key, ""), 400)
    out["contact"]["hours"] = [
        {"day": _clean_str(h.get("day"), 60), "time": _clean_str(h.get("time"), 60)}
        for h in (ct.get("hours") or [])[:10] if isinstance(h, dict)
    ]

    sc = d.get("social", {})
    for key in out["social"]:
        out["social"][key] = _clean_str(sc.get(key, ""), 300)

    sec = d.get("sections", {})
    order = [s for s in (sec.get("order") or []) if s in DEFAULT_SECTION_ORDER]
    for s in DEFAULT_SECTION_ORDER:          # panelde olmayan bölüm kaybolmasın
        if s not in order:
            order.append(s)
    out["sections"]["order"] = order
    enabled = sec.get("enabled") or {}
    out["sections"]["enabled"] = {
        s: bool(enabled.get(s, True)) for s in DEFAULT_SECTION_ORDER
    }

    seo = d.get("seo", {})
    out["seo"]["keywords"] = _clean_str(seo.get("keywords", ""), 400)
    out["seo"]["og_image"] = _clean_str(seo.get("og_image", ""), 300)

    return out
