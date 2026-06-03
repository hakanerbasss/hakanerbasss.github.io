import os

# Telegram (önizleme)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Instagram Graph API
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("IG_USER_ID", "")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "hakanerbasss/hakanerbasss.github.io")

# DeepSeek API (caption üretimi için — platform.deepseek.com'dan al)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Pexels API (görsel için — pexels.com/api'den al)
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")


AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "hakanerb-20")

# Gönderi ayarları
POST_INTERVAL_HOURS = int(os.getenv("POST_INTERVAL_HOURS", "6"))  # kaç saatte bir gönderi
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "4"))
PRODUCT_NICHE = os.getenv("PRODUCT_NICHE", "viral gadgets")  # ürün kategorisi

# Görsel ayarları
IMAGE_WIDTH = 1080
IMAGE_HEIGHT = 1080
FONT_DIR = os.path.join(os.path.dirname(__file__), "templates", "fonts")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# AliExpress scraping
ALIEXPRESS_CURRENCY = "USD"
ALIEXPRESS_LOCALE = "en_US"

# Hashtag'ler
DEFAULT_HASHTAGS = [
    "#viral", "#trending", "#mustbuy", "#amazingproducts",
    "#gadgets", "#shopping", "#deals", "#productoftheday",
    "#affiliate", "#onlineshopping"
]
