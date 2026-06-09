"""
İşletme verilerinden statik HTML siteleri üretir.
"""

import os
import datetime
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
    {"primary": "#1b2a4a", "primary_dark": "#0d1529", "accent": "#ff6b35"},
]


def _env(template_dir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["replace"] = lambda s, old, new: s.replace(old, new)
    return env


def generate_business_site(
    business: BusinessInfo,
    output_dir: str,
    template_dir: str = None,
) -> str:
    if template_dir is None:
        template_dir = os.path.join(os.path.dirname(__file__), "templates", "site")

    env = _env(template_dir)
    tpl = env.get_template("business.html")

    content = content_ai.generate_content(business)
    theme_idx = sum(ord(c) for c in (business.slug or "x")) % len(THEMES)
    theme = THEMES[theme_idx]

    html = tpl.render(
        business=business,
        content=content,
        theme=theme,
        year=datetime.datetime.now().year,
    )

    site_dir = os.path.join(output_dir, business.slug)
    os.makedirs(site_dir, exist_ok=True)
    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Generator] ✓ {business.name} → {site_dir}/index.html")
    return site_dir


def generate_all(
    businesses: list[BusinessInfo],
    output_dir: str = None,
    title: str = "İşletme Rehberi",
    location: str = "",
) -> str:
    if output_dir is None:
        output_dir = config.OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    ok = []
    for b in businesses:
        try:
            generate_business_site(b, output_dir)
            ok.append(b)
        except Exception as e:
            print(f"[Generator] HATA ({b.name}): {e}")

    print(f"[Generator] {len(ok)}/{len(businesses)} site üretildi → {os.path.abspath(output_dir)}")
    return output_dir
