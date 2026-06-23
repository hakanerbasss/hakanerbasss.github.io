"""
Arka plan üretim işleri.

Üretim 10-15 dk sürdüğü için HTTP isteğini bekletmek olmaz (telefon ekranı
kapanınca bağlantı kopup iş iptal oluyordu). Burada üretim ayrı bir thread'de
çalışır; istek anında job_id ile döner. İş, bağlantıdan bağımsız sürer ve
durumu diske yazılır — kullanıcı geri geldiğinde sonucu hazır bulur.
"""
import json
import threading
import time
import uuid
from pathlib import Path

from config import BASE_DIR
import generator

JOBS_FILE = BASE_DIR / "jobs.json"
_jobs: dict = {}
_lock = threading.Lock()
_current: str | None = None


def _persist():
    try:
        JOBS_FILE.write_text(json.dumps(_jobs, ensure_ascii=False))
    except Exception:
        pass


def _load():
    global _jobs
    if JOBS_FILE.exists():
        try:
            _jobs = json.loads(JOBS_FILE.read_text())
        except Exception:
            _jobs = {}
    # Yeniden başlatmadan önce 'running' kalmış işler kesilmiş demektir
    for j in _jobs.values():
        if j.get("status") == "running":
            j["status"] = "error"
            j["error"] = "Sunucu yeniden başladı, iş kesildi"


_load()


def _run(job_id: str, params: dict):
    global _current
    try:
        result = generator.generate_short(**params)
        with _lock:
            _jobs[job_id].update(status="done", result=result, finished=time.time())
    except Exception as e:
        with _lock:
            _jobs[job_id].update(status="error", error=str(e), finished=time.time())
    finally:
        with _lock:
            if _current == job_id:
                _current = None
            _persist()


def start_generation(params: dict):
    """(job_id, started) döner. Zaten çalışan iş varsa onun id'sini döndürür."""
    global _current
    with _lock:
        if _current and _jobs.get(_current, {}).get("status") == "running":
            return _current, False
        job_id = uuid.uuid4().hex[:8]
        _jobs[job_id] = {
            "id": job_id, "status": "running",
            "created": time.time(), "lang": params.get("lang"),
            "topic": params.get("topic", ""),
        }
        _current = job_id
        _persist()
    threading.Thread(target=_run, args=(job_id, params), daemon=True).start()
    return job_id, True


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def latest_job() -> dict | None:
    if not _jobs:
        return None
    return max(_jobs.values(), key=lambda j: j.get("created", 0))
