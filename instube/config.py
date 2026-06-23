"""Ayar/anahtar saklama — tek sorumluluk: settings.json oku/yaz."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

DEFAULT_ENGINE = "http://localhost:8001"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def engine_url() -> str:
    return (load_settings().get("engine_url") or DEFAULT_ENGINE).rstrip("/")


def mask(val: str) -> str:
    if not val:
        return ""
    return val[:4] + "…" + val[-4:] if len(val) > 10 else "••••"
