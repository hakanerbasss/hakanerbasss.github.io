import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'atik.sqlite3')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    telegram_chat_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS neighborhoods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    osm_id INTEGER,
    center_lat REAL,
    center_lon REAL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS streets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood_id INTEGER NOT NULL REFERENCES neighborhoods(id),
    osm_way_id INTEGER,
    name TEXT NOT NULL,
    geometry TEXT NOT NULL,
    visited INTEGER NOT NULL DEFAULT 0,
    visited_by TEXT,
    visited_at INTEGER,
    UNIQUE(neighborhood_id, osm_way_id)
);

CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood_id INTEGER NOT NULL REFERENCES neighborhoods(id),
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    type TEXT NOT NULL,
    note TEXT,
    created_by TEXT,
    created_at INTEGER NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolved_by TEXT,
    resolved_at INTEGER,
    notified INTEGER NOT NULL DEFAULT 0
);
"""

POINT_TYPES = {
    'kaba_atik_dolu':   '🗑️ Kaba atık / konteyner dolu',
    'konteyner_yok':    '🚫 Konteyner yok',
    'temizlik_gerekli': '🧹 Süpürme / yıkama gerekli',
    'toplu_calisma':    '👥 Toplu çalışma yapılacak',
    'diger':            '📝 Diğer not',
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now():
    return int(time.time())
