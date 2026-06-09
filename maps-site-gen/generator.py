"""
İşletme verilerinden statik HTML sitesi üretir.
Her işletme için ayrı klasör, bir de ana liste sayfası oluşturur.
"""

import os
import shutil
import datetime
import random
from jinja2 import Environment, FileSystemLoader, select_autoescape
from scraper import BusinessInfo
import content_ai
import config


THEMES = [
    {"primary": "#1e3a5f", "primary_dark": "#0f1e33", "accent": "#e67e22"},
    {"primary": "#1a472a", "primary_dark": "#0d2614", "accent": "#f39c12"},
    {"primary": "#4a1942", "primary_dark": "#2d0f28", "accent": "#e74c3c"},
    {"primary": "#154360", "primary_dark": "#0a2236", "accent": "#1abc9c"},
    {"primary": "#512e5f", "primary_dark": "#2e1a38", "accent": "#e91e63"},
]


def _get_env(template_dir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["urlencode"] = lambda s: s.replace(" ", "+").replace(",", "%2C")
    return env


def generate_business_site(
    business: BusinessInfo,
    output_dir: str,
    template_dir: str = None,
) -> str:
    """
    Tek bir işletme için HTML klasörü oluşturur.
    Döner: oluşturulan klasör yolu.
    """
    if template_dir is None:
        template_dir = os.path.join(os.path.dirname(__file__), "templates")

    env = _get_env(template_dir)
    tpl = env.get_template("business.html")

    # İçerik üret
    print(f"[Generator] İçerik üretiliyor: {business.name}")
    content = content_ai.generate_content(business)

    # Tema seç (slug hash'e göre sabit)
    theme_idx = sum(ord(c) for c in business.slug) % len(THEMES)
    theme = THEMES[theme_idx]

    html = tpl.render(
        business=business,
        content=content,
        theme=theme,
        year=datetime.datetime.now().year,
    )

    # Klasör oluştur ve kaydet
    site_dir = os.path.join(output_dir, business.slug)
    os.makedirs(site_dir, exist_ok=True)
    index_path = os.path.join(site_dir, "index.html")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Generator] ✓ Site oluşturuldu: {index_path}")
    return site_dir


def generate_listing_page(
    businesses: list[BusinessInfo],
    output_dir: str,
    template_dir: str = None,
    title: str = "İşletme Rehberi",
    location: str = "",
):
    """Ana liste sayfasını (index.html) oluşturur."""
    if template_dir is None:
        template_dir = os.path.join(os.path.dirname(__file__), "templates")

    env = _get_env(template_dir)
    tpl = env.get_template("index.html")

    html = tpl.render(
        businesses=businesses,
        title=title,
        location=location,
        generated_at=datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
    )

    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Generator] ✓ Liste sayfası: {index_path}")


def generate_all(
    businesses: list[BusinessInfo],
    output_dir: str = None,
    title: str = "İşletme Rehberi",
    location: str = "",
):
    """Tüm işletmeler için site üretir + ana liste sayfası."""
    if output_dir is None:
        output_dir = config.OUTPUT_DIR

    os.makedirs(output_dir, exist_ok=True)
    template_dir = os.path.join(os.path.dirname(__file__), "templates")

    success = []
    for b in businesses:
        try:
            generate_business_site(b, output_dir, template_dir)
            success.append(b)
        except Exception as e:
            print(f"[Generator] HATA ({b.name}): {e}")

    generate_listing_page(success, output_dir, template_dir, title, location)

    print(f"\n[Generator] Tamamlandı. {len(success)}/{len(businesses)} site oluşturuldu.")
    print(f"[Generator] Çıktı klasörü: {os.path.abspath(output_dir)}")
    return output_dir
