"""
SQLite veri katmanı.

Tek dosya, tek bağlantı havuzu yok — SiteBot'ta eşzamanlı yazma trafiği
düşük olduğu için her istekte kısa ömürlü bağlantı açmak yeterli ve
kilitlenme riskini en aza indiriyor.

Kiracı (tenant) izolasyonu buradaki her sorgunun site_id ile
sınırlanmasına dayanıyor — admin router'ı asla site_id'siz sorgu atmamalı.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              TEXT UNIQUE NOT NULL,      -- hurdaci  → hurdaci.wizaicorp.com
    title             TEXT NOT NULL,
    domain            TEXT NOT NULL,             -- tam alan adı
    custom_domain     TEXT DEFAULT '',           -- müşterinin kendi domaini
    repo              TEXT NOT NULL,             -- org/repo
    template          TEXT NOT NULL DEFAULT 'hizmet',
    draft_json        TEXT NOT NULL,             -- panelde düzenlenen hali
    live_json         TEXT NOT NULL DEFAULT '',  -- en son yayınlanan hali
    status            TEXT NOT NULL DEFAULT 'kuruluyor',
    provision_log     TEXT NOT NULL DEFAULT '[]',
    expires_at        INTEGER DEFAULT 0,         -- 0 = süresiz
    locked            INTEGER NOT NULL DEFAULT 0,
    created_at        INTEGER NOT NULL,
    published_at      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id       INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    created_at    INTEGER NOT NULL,
    last_login    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(site_id, email)
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    site_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'admin',   -- admin | super
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id    INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,            -- assets/xxx.webp
    bytes      INTEGER NOT NULL DEFAULT 0,
    pushed     INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    UNIQUE(site_id, path)
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id    INTEGER NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL,
    message    TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_events_site ON events(site_id, id DESC);
"""


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def now() -> int:
    return int(time.time())


# --------------------------------------------------------------------- siteler

def create_site(slug: str, title: str, domain: str, repo: str,
                template: str, draft: dict[str, Any]) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO sites (slug, title, domain, repo, template, draft_json, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (slug, title, domain, repo, template,
             json.dumps(draft, ensure_ascii=False), now()),
        )
        return int(cur.lastrowid)


def get_site(site_id: int) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        return dict(row) if row else None


def get_site_by_slug(slug: str) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute("SELECT * FROM sites WHERE slug=?", (slug,)).fetchone()
        return dict(row) if row else None


def list_sites() -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT s.*, (SELECT email FROM users u WHERE u.site_id=s.id "
            "             ORDER BY u.id LIMIT 1) AS owner_email "
            "FROM sites s ORDER BY s.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def update_site(site_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "title", "template", "draft_json", "live_json", "status", "locked",
        "expires_at", "published_at", "provision_log", "custom_domain", "domain",
    }
    sets, vals = [], []
    for key, val in fields.items():
        if key not in allowed:
            raise ValueError(f"güncellenemeyen alan: {key}")
        sets.append(f"{key}=?")
        vals.append(val)
    vals.append(site_id)
    with conn() as c:
        c.execute(f"UPDATE sites SET {', '.join(sets)} WHERE id=?", vals)


def delete_site(site_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE site_id=?", (site_id,))
        c.execute("DELETE FROM sites WHERE id=?", (site_id,))


def draft_of(site: dict[str, Any]) -> dict[str, Any]:
    return json.loads(site["draft_json"])


def set_draft(site_id: int, data: dict[str, Any]) -> None:
    update_site(site_id, draft_json=json.dumps(data, ensure_ascii=False))


def has_unpublished(site: dict[str, Any]) -> bool:
    return site["draft_json"] != site["live_json"]


# ----------------------------------------------------------------- kullanıcılar

def create_user(site_id: int, email: str, password_hash: str,
                display_name: str = "") -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO users (site_id, email, password_hash, display_name, created_at) "
            "VALUES (?,?,?,?,?)",
            (site_id, email.lower().strip(), password_hash, display_name, now()),
        )
        return int(cur.lastrowid)


def find_user(email: str, site_id: int | None = None) -> dict[str, Any] | None:
    with conn() as c:
        if site_id is None:
            row = c.execute(
                "SELECT * FROM users WHERE email=? ORDER BY id LIMIT 1",
                (email.lower().strip(),),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM users WHERE email=? AND site_id=?",
                (email.lower().strip(), site_id),
            ).fetchone()
        return dict(row) if row else None


def set_password(user_id: int, password_hash: str) -> None:
    with conn() as c:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))


def touch_login(user_id: int) -> None:
    with conn() as c:
        c.execute("UPDATE users SET last_login=? WHERE id=?", (now(), user_id))


# --------------------------------------------------------------------- oturumlar

def create_session(token: str, site_id: int, user_id: int, kind: str, ttl: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        c.execute(
            "INSERT INTO sessions (token, site_id, user_id, kind, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?)",
            (token, site_id, user_id, kind, now(), now() + ttl),
        )


def get_session(token: str) -> dict[str, Any] | None:
    with conn() as c:
        row = c.execute(
            "SELECT * FROM sessions WHERE token=? AND expires_at > ?", (token, now())
        ).fetchone()
        return dict(row) if row else None


def drop_session(token: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (token,))


def drop_sessions_of_site(site_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE site_id=?", (site_id,))


# ---------------------------------------------------------------------- görseller

def add_asset(site_id: int, path: str, size: int) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO assets (site_id, path, bytes, pushed, created_at) "
            "VALUES (?,?,?,0,?)",
            (site_id, path, size, now()),
        )


def pending_assets(site_id: int) -> list[dict[str, Any]]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM assets WHERE site_id=? AND pushed=0", (site_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_assets_pushed(site_id: int, paths: list[str]) -> None:
    if not paths:
        return
    with conn() as c:
        c.executemany(
            "UPDATE assets SET pushed=1 WHERE site_id=? AND path=?",
            [(site_id, p) for p in paths],
        )


def site_asset_bytes(site_id: int) -> int:
    with conn() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(bytes),0) AS t FROM assets WHERE site_id=?", (site_id,)
        ).fetchone()
        return int(row["t"])


# ------------------------------------------------------------------------ günlük

def log(site_id: int, kind: str, message: str = "") -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO events (site_id, kind, message, created_at) VALUES (?,?,?,?)",
            (site_id, kind, message[:2000], now()),
        )


def recent_events(site_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with conn() as c:
        if site_id is None:
            rows = c.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM events WHERE site_id=? ORDER BY id DESC LIMIT ?",
                (site_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
