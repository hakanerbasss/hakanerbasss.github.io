import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'bathonea.db')

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS admin_users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Yüklenen kaynak belgeler (toplu iş sözleşmesi vb.). Her seferinde tek belge "aktif" olur;
-- AI sadece aktif belgeye bakarak cevap verir. Eskiler geçmiş olarak saklanır.
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'processing',  -- processing|ready|error
    error       TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number  INTEGER NOT NULL,
    image_path   TEXT    NOT NULL,
    text         TEXT,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_doc ON pages(document_id, page_number);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,   -- 'user' | 'assistant'
    text        TEXT    NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now() -> int:
    return int(time.time())


def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    conn = get_db()
    conn.execute('INSERT INTO settings (key, value) VALUES (?, ?) '
                 'ON CONFLICT(key) DO UPDATE SET value = excluded.value', (key, value))
    conn.commit()
    conn.close()


def get_active_document():
    conn = get_db()
    doc = conn.execute('SELECT * FROM documents WHERE is_active = 1 ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return dict(doc) if doc else None


def get_document_pages(document_id):
    conn = get_db()
    rows = conn.execute('SELECT * FROM pages WHERE document_id = ? ORDER BY page_number', (document_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
