"""
supertonic-web'den kimlik/anahtar içe aktarma.

Sadece komşu projenin DİSKTEKİ config dosyalarını okur — o servisin (:8001)
ayakta olmasına bağlı DEĞİL. YouTube token'ı da kopyalandığı için yeniden
yetkilendirme gerekmez.
"""
import json
import shutil
from pathlib import Path

from config import (BASE_DIR, load_settings, save_settings,
                    YT_CONFIG_FILE, YT_TOKEN_FILE, YT_TOKEN_FILE_EN)

# /root/hakanerbasss.github.io/supertonic-web
DEFAULT_SRC = BASE_DIR.parent / "supertonic-web"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def import_from_supertonic(src_dir: Path | None = None) -> dict:
    src = Path(src_dir) if src_dir else DEFAULT_SRC
    report: dict = {"source": str(src), "imported": [], "skipped": []}

    if not src.exists():
        report["error"] = f"Kaynak klasör bulunamadı: {src}"
        return report

    s = load_settings()

    # API anahtarları + Instagram → settings.json
    ig = _read_json(src / "ig_config.json")
    if ig.get("ig_user_id") and ig.get("access_token"):
        s["ig_user_id"] = ig["ig_user_id"]
        s["ig_access_token"] = ig["access_token"]
        report["imported"].append("Instagram (ID + token)")
    else:
        report["skipped"].append("Instagram")

    for label, fname, dest_key in [
        ("DeepSeek", "deepseek_config.json", "deepseek_key"),
        ("Pexels", "pexels_config.json", "pexels_key"),
        ("OpenAI", "openai_config.json", "openai_key"),
    ]:
        key = _read_json(src / fname).get("api_key", "")
        if key:
            s[dest_key] = key
            report["imported"].append(label)
        else:
            report["skipped"].append(label)

    save_settings(s)

    # YouTube config + token dosyaları → birebir kopyala
    for label, fname, dest in [
        ("YouTube ayarı", "yt_config.json", YT_CONFIG_FILE),
        ("YouTube TR token", "yt_token.json", YT_TOKEN_FILE),
        ("YouTube EN token", "yt_token_en.json", YT_TOKEN_FILE_EN),
    ]:
        srcf = src / fname
        if srcf.exists():
            shutil.copy2(str(srcf), str(dest))
            report["imported"].append(label)
        else:
            report["skipped"].append(label)

    return report
