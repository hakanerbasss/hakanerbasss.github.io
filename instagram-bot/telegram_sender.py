"""
Telegram'a görsel + caption + affiliate linki gönderir.
"""

import urllib.parse
import requests
import logging

logger = logging.getLogger(__name__)


def make_amazon_link(product_title: str, associate_tag: str) -> str:
    """Ürün adından Amazon affiliate arama linki üretir."""
    query = urllib.parse.quote_plus(product_title)
    return f"https://www.amazon.com/s?k={query}&tag={associate_tag}"


def send_post(
    bot_token: str,
    chat_id: str,
    image_path: str,
    caption: str,
    affiliate_link: str = "",
) -> bool:
    """Görseli, caption'ı ve affiliate linkini Telegram'a gönderir."""

    # Affiliate linki ayrı mesaj olarak gönder (caption'a sığmayabilir)
    photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    link_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    caption = caption[:1024]

    try:
        # 1. Görseli gönder
        with open(image_path, "rb") as photo:
            resp = requests.post(
                photo_url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": photo},
                timeout=30,
            )
        if not resp.ok:
            logger.error(f"Telegram foto hatası {resp.status_code}: {resp.text}")
            return False

        # 2. Affiliate linki ayrı gönder
        if affiliate_link:
            link_text = f"🛒 Amazon'dan satın al (komisyonlu link):\n{affiliate_link}"
            requests.post(
                link_url,
                data={"chat_id": chat_id, "text": link_text},
                timeout=15,
            )

        logger.info("Telegram'a gönderildi.")
        return True
    except Exception as e:
        logger.error(f"Telegram gönderme hatası: {e}")
        return False
