import os

# Anthropic API - web sitesi içeriği üretmek için (opsiyonel)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Çıktı klasörü
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")

# Tarayıcı ayarları
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.environ.get("SLOW_MO", "50"))  # ms, anti-detection için

# GitHub Pages deploy ayarları
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # örn: kullanici/repo

# Scraping limitleri
MAX_BUSINESSES = int(os.environ.get("MAX_BUSINESSES", "20"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "2.0"))  # saniye
