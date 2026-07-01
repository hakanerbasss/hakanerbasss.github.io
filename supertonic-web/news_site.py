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
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "news_site.db"
templates = Jinja2Templates(directory=str(BASE_DIR / "news_templates"))


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


templates.env.filters["timesince"] = _timesince

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


def get_articles(page: int = 1):
    offset = (page - 1) * PER_PAGE
    with _conn() as c:
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


router = APIRouter()


@router.get("/haberler", response_class=HTMLResponse)
async def haberler_list(request: Request, sayfa: int = 1):
    sayfa = max(1, sayfa)
    rows, total = get_articles(page=sayfa)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return templates.TemplateResponse("liste.html", {
        "request": request, "articles": rows, "page": sayfa, "total_pages": total_pages,
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
    return templates.TemplateResponse("detay.html", {
        "request": request, "a": row, "comments": comments, "likes": likes, "liked": liked,
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
