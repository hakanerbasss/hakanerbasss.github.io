import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.environ.get("SLOW_MO", "80"))
MAX_BUSINESSES = int(os.environ.get("MAX_BUSINESSES", "30"))
REQUEST_DELAY = float(os.environ.get("REQUEST_DELAY", "2.5"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
FLASK_SECRET = os.environ.get("FLASK_SECRET", "maps-site-gen-secret-2024")
FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
