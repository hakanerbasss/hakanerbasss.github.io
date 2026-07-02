"""Anonim yorum/beğeni destekli genel haber arşivi sitesi.

Bot her Instagram gönderisini doğruladığında add_article() ile buraya bir
kayıt düşer. Video sunucuda tutulmaz — Instagram embed (blockquote) ile
gösterilir, sadece küçük thumbnail görseli yerelde saklanır.
"""
import sqlite3
import time
import hashlib
from pathlib import Path

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "news_site.db"
templates = Jinja2Templates(directory=str(BASE_DIR / "news_templates"))

# Haber sitesi bu alt alan adından herkese açık servis edilir (bkz. auth_middleware, index())
NEWS_SUBDOMAIN = "hakanerbas.wizaicorp.com"
SITE_URL = f"https://{NEWS_SUBDOMAIN}"


def _timesince(ts: int) -> str:
    diff = time.time() - ts
    if diff < 60:
        return "az önce"
    if diff < 3600:
        return f"{int(diff // 60)} dakika önce"
    if diff < 86400:
        return f"{int(diff // 3600)} saat önce"
    days = int(diff // 86400)
    if days < 30:
        return f"{days} gün önce"
    return time.strftime("%d.%m.%Y", time.localtime(ts))


def _isoformat(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))


templates.env.filters["timesince"] = _timesince
templates.env.filters["isoformat"] = _isoformat
templates.env.globals["SITE_URL"] = SITE_URL

PER_PAGE = 12
COMMENT_COOLDOWN = 30  # saniye, IP başına

_CATS = [
    (["ekonomi", "borsa", "döviz", "faiz", "enflasyon", "dolar", "euro", "piyasa",
      "merkez ban", "bütçe", "zam", "maaş", "emekli"], "EKONOMİ", "#1e82dc"),
    (["deprem", "sel", "yangın", "afet", "fırtına", "kasırga", "tsunami", "volkan",
      "heyelan", "sıcaklık", "sıcak hava"], "AFET", "#e66900"),
    (["futbol", "basketbol", "spor", "şampiyona", "lig", "maç", "gol", "transfer",
      "milli takım", "formula"], "SPOR", "#00aa37"),
    (["dünya", "nato", "avrupa", "ukrayna", "rusya", "gazze", "suriye", "savaş",
      "uluslararası", "filistin", "i̇srail", "israil"], "DÜNYA", "#8c32d7"),
    (["teknoloji", "yapay zeka", "nasa", "uzay", "bilim", "robot", "chatgpt",
      "iphone", "android"], "TEKNOLOJİ", "#00afc3"),
]
_DEFAULT_CAT, _DEFAULT_COLOR = "GÜNDEM", "#d50000"
ALL_CATEGORIES = [(_DEFAULT_CAT, _DEFAULT_COLOR)] + [(label, color) for _, label, color in _CATS]

CONTACT_EMAIL = "hakanerbasss@gmail.com"
CONTACT_WHATSAPP = "905530930325"

templates.env.globals["CATEGORIES"] = ALL_CATEGORIES
templates.env.globals["CURRENT_YEAR"] = time.strftime("%Y")


def guess_category(title: str) -> tuple[str, str]:
    tl = (title or "").lower()
    for kws, label, color in _CATS:
        if any(k in tl for k in kws):
            return label, color
    return _DEFAULT_CAT, _DEFAULT_COLOR


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT,
            category_color TEXT,
            thumbnail TEXT,
            ig_permalink TEXT,
            created_at REAL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            author TEXT,
            text TEXT NOT NULL,
            created_at REAL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS likes (
            article_id INTEGER NOT NULL,
            ip_hash TEXT NOT NULL,
            PRIMARY KEY (article_id, ip_hash)
        )""")


init_db()

_last_comment_ts: dict[str, float] = {}


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _can_comment(ip: str) -> bool:
    now = time.time()
    if now - _last_comment_ts.get(ip, 0) < COMMENT_COOLDOWN:
        return False
    _last_comment_ts[ip] = now
    return True


def add_article(title: str, description: str, thumbnail: str, ig_permalink: str) -> int:
    label, color = guess_category(title)
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO articles (title, description, category, category_color, thumbnail, ig_permalink, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title.strip()[:200], (description or "").strip()[:600], label, color,
             thumbnail or "", ig_permalink or "", time.time()),
        )
        return cur.lastrowid


def get_articles(page: int = 1, category: str | None = None):
    offset = (page - 1) * PER_PAGE
    with _conn() as c:
        if category:
            rows = c.execute(
                "SELECT * FROM articles WHERE category=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (category, PER_PAGE, offset),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) FROM articles WHERE category=?", (category,)).fetchone()[0]
        else:
            rows = c.execute(
                "SELECT * FROM articles ORDER BY id DESC LIMIT ? OFFSET ?", (PER_PAGE, offset)
            ).fetchall()
            total = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    return rows, total


def get_article(article_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        if not row:
            return None, [], 0
        comments = c.execute(
            "SELECT * FROM comments WHERE article_id=? ORDER BY id DESC", (article_id,)
        ).fetchall()
        likes = c.execute(
            "SELECT COUNT(*) FROM likes WHERE article_id=?", (article_id,)
        ).fetchone()[0]
    return row, comments, likes


def get_adjacent_ids(article_id: int):
    """Liste sırasına göre (en yeni önce) bir önceki/sonraki haber id'si — swipe navigasyonu için."""
    with _conn() as c:
        newer = c.execute(
            "SELECT id FROM articles WHERE id > ? ORDER BY id ASC LIMIT 1", (article_id,)
        ).fetchone()
        older = c.execute(
            "SELECT id FROM articles WHERE id < ? ORDER BY id DESC LIMIT 1", (article_id,)
        ).fetchone()
    return (newer["id"] if newer else None, older["id"] if older else None)


def get_all_ids_and_dates():
    with _conn() as c:
        return c.execute("SELECT id, created_at FROM articles ORDER BY id DESC").fetchall()


router = APIRouter()


_AI_CRAWLERS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot",  # OpenAI
    "ClaudeBot", "Claude-Web", "anthropic-ai",  # Anthropic
    "PerplexityBot", "Perplexity-User",         # Perplexity
    "Google-Extended",                          # Google Gemini / AI Overviews eğitim verisi
    "Bingbot",                                  # Bing / Copilot
    "Applebot-Extended",                        # Apple Intelligence
]


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    lines = ["User-agent: *", "Allow: /haberler", "Allow: /haber/", "Allow: /hakkinda", "Allow: /iletisim", ""]
    for ua in _AI_CRAWLERS:
        lines += [f"User-agent: {ua}", "Allow: /", ""]
    lines.append(f"Sitemap: {SITE_URL}/sitemap.xml")
    return "\n".join(lines) + "\n"


@router.get("/sitemap.xml")
async def sitemap_xml():
    rows = get_all_ids_and_dates()
    urls = [
        f"<url><loc>{SITE_URL}/haberler</loc><changefreq>hourly</changefreq></url>",
        f"<url><loc>{SITE_URL}/hakkinda</loc><changefreq>monthly</changefreq></url>",
        f"<url><loc>{SITE_URL}/iletisim</loc><changefreq>monthly</changefreq></url>",
    ]
    for r in rows:
        urls.append(
            f"<url><loc>{SITE_URL}/haber/{r['id']}</loc>"
            f"<lastmod>{_isoformat(int(r['created_at']))}</lastmod></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(urls) + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@router.get("/haberler", response_class=HTMLResponse)
async def haberler_list(request: Request, sayfa: int = 1, kategori: str | None = None):
    sayfa = max(1, sayfa)
    rows, total = get_articles(page=sayfa, category=kategori)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse("liste.html", {
        "request": request, "articles": rows, "page": sayfa, "total_pages": total_pages,
        "active_category": kategori,
    })


@router.get("/hakkinda", response_class=HTMLResponse)
async def hakkinda(request: Request):
    return templates.TemplateResponse("hakkinda.html", {"request": request})


@router.get("/iletisim", response_class=HTMLResponse)
async def iletisim(request: Request):
    return templates.TemplateResponse("iletisim.html", {
        "request": request, "contact_email": CONTACT_EMAIL, "contact_whatsapp": CONTACT_WHATSAPP,
    })


@router.get("/haber/{article_id}", response_class=HTMLResponse)
async def haber_detay(request: Request, article_id: int):
    row, comments, likes = get_article(article_id)
    if not row:
        raise HTTPException(404, "Haber bulunamadı")
    with _conn() as c:
        ip = request.client.host if request.client else ""
        liked = c.execute(
            "SELECT 1 FROM likes WHERE article_id=? AND ip_hash=?", (article_id, _ip_hash(ip))
        ).fetchone() is not None
    newer_id, older_id = get_adjacent_ids(article_id)
    return templates.TemplateResponse("detay.html", {
        "request": request, "a": row, "comments": comments, "likes": likes, "liked": liked,
        "newer_id": newer_id, "older_id": older_id,
    })


@router.post("/haber/{article_id}/yorum")
async def yorum_ekle(
    request: Request, article_id: int,
    isim: str = Form(""), metin: str = Form(...), website: str = Form(""),
):
    row, _, _ = get_article(article_id)
    if not row:
        raise HTTPException(404, "Haber bulunamadı")
    if website:  # honeypot dolu → bot
        return RedirectResponse(f"/haber/{article_id}#yorumlar", status_code=303)
    ip = request.client.host if request.client else "unknown"
    text = metin.strip()[:500]
    if text and _can_comment(ip):
        name = (isim.strip() or "Anonim")[:40]
        with _conn() as c:
            c.execute(
                "INSERT INTO comments (article_id, author, text, created_at) VALUES (?, ?, ?, ?)",
                (article_id, name, text, time.time()),
            )
    return RedirectResponse(f"/haber/{article_id}#yorumlar", status_code=303)


@router.post("/haber/{article_id}/begen")
async def begen(request: Request, article_id: int):
    row, _, _ = get_article(article_id)
    if not row:
        raise HTTPException(404, "Haber bulunamadı")
    ip = request.client.host if request.client else "unknown"
    ih = _ip_hash(ip)
    with _conn() as c:
        exists = c.execute(
            "SELECT 1 FROM likes WHERE article_id=? AND ip_hash=?", (article_id, ih)
        ).fetchone()
        if exists:
            c.execute("DELETE FROM likes WHERE article_id=? AND ip_hash=?", (article_id, ih))
            liked = False
        else:
            c.execute("INSERT INTO likes (article_id, ip_hash) VALUES (?, ?)", (article_id, ih))
            liked = True
        count = c.execute("SELECT COUNT(*) FROM likes WHERE article_id=?", (article_id,)).fetchone()[0]
    return {"liked": liked, "count": count}
