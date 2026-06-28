"""SQLite job store — aiosqlite ile async."""

import aiosqlite
from app.config import settings

DB = str(settings.db_path)


async def init():
    async with aiosqlite.connect(DB) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                progress    INTEGER NOT NULL DEFAULT 0,
                total       INTEGER NOT NULL DEFAULT 0,
                done        INTEGER NOT NULL DEFAULT 0,
                input_path  TEXT,
                output_path TEXT,
                file_format TEXT,
                voice       TEXT NOT NULL DEFAULT 'M1',
                error       TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        await conn.commit()

    # Sütun migrasyonu — eski DB'ye voice ekle (hata olursa zaten var)
    async with aiosqlite.connect(DB) as conn:
        try:
            await conn.execute("ALTER TABLE jobs ADD COLUMN voice TEXT NOT NULL DEFAULT 'M1'")
            await conn.commit()
        except Exception:
            pass

    # Restart sonrası yarım kalan 'processing' işleri pending'e al → devam eder
    # 'paused' işler olduğu yerde kalır — kullanıcı elle devam ettirir
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            "UPDATE jobs SET status='pending', error=NULL WHERE status='processing'"
        )
        await conn.commit()


async def create_job(job_id: str, title: str, input_path: str,
                     file_format: str, voice: str, now: str):
    async with aiosqlite.connect(DB) as conn:
        await conn.execute(
            """INSERT INTO jobs
               (id, title, status, progress, total, done,
                input_path, output_path, file_format, voice, created_at, updated_at)
               VALUES (?, ?, 'pending', 0, 0, 0, ?, NULL, ?, ?, ?, ?)""",
            (job_id, title, input_path, file_format, voice, now, now),
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
