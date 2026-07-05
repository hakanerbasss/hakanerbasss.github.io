import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'atik.db')

# ── Rol sabitleri ───────────────────────────────────────────────────────────
ROLES = {
    'santiye_amiri':    'Şantiye Amiri',
    'cavus':            'Çavuş',
    'onbasi':           'Onbaşı',
    'supurgeci':        'Yaya Süpürgeci',
    'aracli_supurge':   'Araçlı Süpürgeci',
    'kaba_atik':        'Kaba Atık Aracı',
    'cop_araci':        'Çöp Aracı',
    'ring_araci':       'Ring Aracı',
    'konteyner_yikama': 'Konteyner Yıkama',
}

SUPERVISOR_ROLES = {'santiye_amiri', 'cavus', 'onbasi'}
FIELD_ROLES = {'supurgeci', 'aracli_supurge', 'kaba_atik', 'cop_araci', 'ring_araci', 'konteyner_yikama'}

# Hangi rol günlük sıfırlanır
DAILY_RESET_ROLES = {'supurgeci', 'cop_araci', 'ring_araci', 'aracli_supurge'}

# ── Bildirim türleri ────────────────────────────────────────────────────────
NOTIFICATION_TYPES = {
    'dolu_konteyner':   ('🗑️', 'Dolu Konteyner', 'cop_araci'),
    'kaba_atik':        ('🪑', 'Kaba Atık', 'kaba_atik'),
    'yikanmasi_lazim':  ('🚿', 'Konteyner Yıkanması Lazım', 'konteyner_yikama'),
    'suprulmesi_lazim': ('🧹', 'Süpürülmesi Lazım', 'supurgeci'),
    'park_bahce':       ('🌳', 'Park & Bahçe Sorunu', None),
    'fen_isleri':       ('🔧', 'Fen İşleri', None),
    'diger':            ('📝', 'Diğer', None),
}

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- İlçe
CREATE TABLE IF NOT EXISTS districts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  INTEGER NOT NULL
);

-- Mahalle
CREATE TABLE IF NOT EXISTS neighborhoods (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id INTEGER NOT NULL REFERENCES districts(id),
    name        TEXT    NOT NULL,
    osm_id      INTEGER,
    center_lat  REAL,
    center_lon  REAL,
    created_at  INTEGER NOT NULL,
    UNIQUE(district_id, name)
);

-- Sokak / Cadde
CREATE TABLE IF NOT EXISTS streets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood_id  INTEGER NOT NULL REFERENCES neighborhoods(id),
    osm_way_id       INTEGER,
    name             TEXT NOT NULL,
    geometry         TEXT NOT NULL,   -- JSON [[lat,lon],...]
    created_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_streets_neighborhood ON streets(neighborhood_id);

-- Kullanıcı
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT    NOT NULL UNIQUE,
    password_hash     TEXT    NOT NULL,
    display_name      TEXT    NOT NULL,
    role              TEXT    NOT NULL,
    district_id       INTEGER REFERENCES districts(id),
    telegram_chat_id  TEXT,
    default_shift_id  INTEGER REFERENCES shifts(id),
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        INTEGER NOT NULL
);

-- Kullanıcı ↔ Mahalle ataması  (bir kullanıcı birden fazla mahalleye atanabilir)
CREATE TABLE IF NOT EXISTS user_neighborhoods (
    user_id          INTEGER NOT NULL REFERENCES users(id),
    neighborhood_id  INTEGER NOT NULL REFERENCES neighborhoods(id),
    is_primary       INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, neighborhood_id)
);

-- Vardiya tanımları
CREATE TABLE IF NOT EXISTS shifts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id  INTEGER NOT NULL REFERENCES districts(id),
    name         TEXT    NOT NULL,          -- 'sabah' | 'aksam' | 'gece'
    display_name TEXT    NOT NULL,
    start_hour   INTEGER NOT NULL,          -- 6
    end_hour     INTEGER NOT NULL,          -- 15
    UNIQUE(district_id, name)
);

-- Güzergah Ataması  (çavuş belirli gün+vardiya+ekip için sokak atar)
-- work_date NULL = kalıcı atama (silinene kadar geçerli)
CREATE TABLE IF NOT EXISTS route_assignments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood_id  INTEGER NOT NULL REFERENCES neighborhoods(id),
    team_type        TEXT    NOT NULL,      -- 'supurgeci' | 'kaba_atik' | ...
    shift_id         INTEGER REFERENCES shifts(id),
    work_date        TEXT,                  -- YYYY-MM-DD veya NULL (kalıcı)
    assigned_user_id INTEGER REFERENCES users(id),  -- NULL → tüm ekip
    assigned_by      INTEGER NOT NULL REFERENCES users(id),
    created_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ra_date ON route_assignments(work_date, neighborhood_id, team_type);

-- Atamanın sokakları
CREATE TABLE IF NOT EXISTS assignment_streets (
    assignment_id  INTEGER NOT NULL REFERENCES route_assignments(id) ON DELETE CASCADE,
    street_id      INTEGER NOT NULL REFERENCES streets(id),
    PRIMARY KEY (assignment_id, street_id)
);

-- Sokak tamamlama kaydı  (tarih bazlı — asla silinmez, geçmiş tutulur)
CREATE TABLE IF NOT EXISTS street_completions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    street_id      INTEGER NOT NULL REFERENCES streets(id),
    assignment_id  INTEGER REFERENCES route_assignments(id),
    user_id        INTEGER NOT NULL REFERENCES users(id),
    neighborhood_id INTEGER NOT NULL REFERENCES neighborhoods(id),
    work_date      TEXT    NOT NULL,   -- YYYY-MM-DD
    completed_at   INTEGER NOT NULL,
    photo_sent     INTEGER NOT NULL DEFAULT 0,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_sc_date ON street_completions(work_date, neighborhood_id);

-- Bildirim yorumları
CREATE TABLE IF NOT EXISTS notification_comments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_id  INTEGER NOT NULL REFERENCES notifications(id),
    user_id          INTEGER NOT NULL REFERENCES users(id),
    text             TEXT    NOT NULL,
    created_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nc_notif ON notification_comments(notification_id);

-- Ortak bildirim havuzu
CREATE TABLE IF NOT EXISTS notifications (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood_id  INTEGER NOT NULL REFERENCES neighborhoods(id),
    street_id        INTEGER REFERENCES streets(id),   -- NULL = GPS konumlu
    lat              REAL    NOT NULL,
    lon              REAL    NOT NULL,
    type             TEXT    NOT NULL,
    note             TEXT,
    created_by       INTEGER NOT NULL REFERENCES users(id),
    created_at       INTEGER NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'open',  -- open|accepted|resolved|cancelled
    target_team      TEXT,
    accepted_by      INTEGER REFERENCES users(id),
    accepted_at      INTEGER,
    resolved_by      INTEGER REFERENCES users(id),
    resolved_at      INTEGER,
    photo_sent       INTEGER NOT NULL DEFAULT 0,
    cancelled_by     INTEGER REFERENCES users(id),
    cancelled_at     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_notif_status ON notifications(neighborhood_id, status);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _migrate_db():
    """Mevcut DB şemasını gerekli değişikliklerle günceller."""
    conn = get_db()
    try:
        # users tablosuna yeni kolonlar ekle
        existing = {row[1] for row in conn.execute('PRAGMA table_info(users)').fetchall()}
        if 'default_shift_id' not in existing:
            conn.execute('ALTER TABLE users ADD COLUMN default_shift_id INTEGER REFERENCES shifts(id)')
        if 'is_active' not in existing:
            conn.execute('ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
        conn.commit()

        # notification_comments tablosu
        conn.execute("""CREATE TABLE IF NOT EXISTS notification_comments (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id  INTEGER NOT NULL REFERENCES notifications(id),
            user_id          INTEGER NOT NULL REFERENCES users(id),
            text             TEXT    NOT NULL,
            created_at       INTEGER NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nc_notif ON notification_comments(notification_id)")
        conn.commit()

        # notifications tablosuna street_id kolonu ekle
        notif_cols = {row[1] for row in conn.execute('PRAGMA table_info(notifications)').fetchall()}
        if 'street_id' not in notif_cols:
            conn.execute('ALTER TABLE notifications ADD COLUMN street_id INTEGER REFERENCES streets(id)')
        conn.commit()

        # route_assignments.work_date NOT NULL kısıtını kaldır (kalıcı atama için NULL gerekli)
        ra_info = conn.execute('PRAGMA table_info(route_assignments)').fetchall()
        work_date_notnull = next((row[3] for row in ra_info if row[1] == 'work_date'), 0)
        if work_date_notnull:
            conn.executescript("""
                PRAGMA foreign_keys=OFF;
                DROP TABLE IF EXISTS route_assignments_new;
                CREATE TABLE route_assignments_new (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    neighborhood_id  INTEGER NOT NULL REFERENCES neighborhoods(id),
                    team_type        TEXT    NOT NULL,
                    shift_id         INTEGER REFERENCES shifts(id),
                    work_date        TEXT,
                    assigned_user_id INTEGER REFERENCES users(id),
                    assigned_by      INTEGER NOT NULL REFERENCES users(id),
                    created_at       INTEGER NOT NULL
                );
                INSERT INTO route_assignments_new SELECT * FROM route_assignments;
                DROP TABLE route_assignments;
                ALTER TABLE route_assignments_new RENAME TO route_assignments;
                CREATE INDEX IF NOT EXISTS idx_ra_date ON route_assignments(work_date, neighborhood_id, team_type);
                PRAGMA foreign_keys=ON;
            """)
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    _migrate_db()


def now() -> int:
    return int(time.time())


def today() -> str:
    import datetime
    return datetime.date.today().isoformat()
