"""SQLite job store — aiosqlite ile async."""

import aiosqlite
from app.config import settings

DB = str(settings.db_path)

_MIGRATIONS = [
    "ALTER TABLE jobs ADD COLUMN voice TEXT NOT NULL DEFAULT 'M1'",
    "ALTER TABLE jobs ADD COLUMN source_lang TEXT NOT NULL DEFAULT 'auto'",
    "ALTER TABLE jobs ADD COLUMN target_lang TEXT NOT NULL DEFAULT 'tr'",
    "ALTER TABLE jobs ADD COLUMN output_video_path TEXT",
    "ALTER TABLE jobs ADD COLUMN output_srt_path TEXT",
    "ALTER TABLE jobs ADD COLUMN youtube_metadata TEXT",
]


async def init():
    async with aiosqlite.connect(DB) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                TEXT PRIMARY KEY,
                title             TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                progress          INTEGER NOT NULL DEFAULT 0,
                total             INTEGER NOT NULL DEFAULT 0,
                done              INTEGER NOT NULL DEFAULT 0,
                input_path        TEXT,
                output_path       TEXT,
                output_video_path TEXT,
                output_srt_path   TEXT,
                youtube_metadata  TEXT,
                file_format       TEXT,
                voice             TEXT NOT NULL DEFAULT 'M1',
                source_lang       TEXT NOT NULL DEFAULT 'auto',
                target_lang       TEXT NOT NULL DEFAULT 'tr',
                error             TEXT,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await conn.commit()

    # Sütun migrasyonları — eski DB'ye eksik sütunlar eklenir
    async with aiosqlite.connect(DB) as conn:
        for sql in _MIGRATIONS:
            try:
                await conn.execute(sql)
                await conn.commit()
            except Exception:
                pass

    # Restart sonrası yarım kalan 'processing' işleri pending'e al
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            "UPDATE jobs SET status='pending', error=NULL WHERE status='processing'"
        )
        await conn.commit()


async def create_job(job_id: str, title: str, input_path: str,
                     file_format: str, voice: str, now: str,
                     source_lang: str = "auto", target_lang: str = "tr"):
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            """INSERT INTO jobs
               (id, title, status, progress, total, done,
                input_path, output_path, file_format, voice,
                source_lang, target_lang, created_at, updated_at)
               VALUES (?, ?, 'pending', 0, 0, 0, ?, NULL, ?, ?, ?, ?, ?, ?)""",
            (job_id, title, input_path, file_format, voice,
             source_lang, target_lang, now, now),
        )
        await conn.commit()


async def get_job(job_id: str) -> dict | None:
    async with aiosqlite.connect(DB) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_jobs() -> list[dict]:
    async with aiosqlite.connect(DB) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def update(job_id: str, now: str, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [now, job_id]
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            f"UPDATE jobs SET {cols}, updated_at=? WHERE id=?", vals
        )
        await conn.commit()


async def delete_job(job_id: str):
    async with aiosqlite.connect(DB) as conn:
        await conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        await conn.commit()


async def get_setting(key: str) -> str | None:
    async with aiosqlite.connect(DB) as conn:
        async with conn.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await conn.commit()
