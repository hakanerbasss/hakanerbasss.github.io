"""Ayarlar, anahtarlar, sabitler ve dosya yolları — tek kaynak."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Çalışma klasörleri
OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR = BASE_DIR / "uploads"
THUMB_DIR = BASE_DIR / "thumbnails"
DOWNLOAD_DIR = BASE_DIR / "downloads"
for d in (OUTPUT_DIR, UPLOAD_DIR, THUMB_DIR, DOWNLOAD_DIR):
    d.mkdir(exist_ok=True)

# Ayar / kimlik dosyaları
SETTINGS_FILE = BASE_DIR / "settings.json"      # API anahtarları + IG kimliği
YT_CONFIG_FILE = BASE_DIR / "yt_config.json"    # YouTube OAuth client_id/secret
YT_TOKEN_FILE = BASE_DIR / "yt_token.json"      # TR kanalı token
YT_TOKEN_FILE_EN = BASE_DIR / "yt_token_en.json"  # EN kanalı token
YT_VERIFIER = BASE_DIR / "yt_verifier.txt"
YT_VERIFIER_EN = BASE_DIR / "yt_verifier_en.txt"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

LANG_MAP = {
    "tr": "Turkish", "en": "English", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "ru": "Russian", "ar": "Arabic",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish",
}
VOICES = ["M1", "M2", "M3", "F1", "F2", "F3"]


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_deepseek_key() -> str:
    return load_settings().get("deepseek_key", "")


def get_pexels_key() -> str:
    return load_settings().get("pexels_key", "")


def get_openai_key() -> str:
    return load_settings().get("openai_key", "")


def mask(val: str) -> str:
    if not val:
        return ""
    return val[:4] + "…" + val[-4:] if len(val) > 10 else "••••"
