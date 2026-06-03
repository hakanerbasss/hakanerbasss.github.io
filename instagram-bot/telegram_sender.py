"""
Telegram'a görsel + caption gönderir.
"""

import requests
import logging

logger = logging.getLogger(__name__)


def send_post(bot_token: str, chat_id: str, image_path: str, caption: str) -> bool:
    """Görseli ve caption'ı Telegram'a gönderir."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        with open(image_path, "rb") as photo:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": photo},
                timeout=30,
            )
        resp.raise_for_status()
        logger.info("Telegram'a gönderildi.")
        return True
    except Exception as e:
        logger.error(f"Telegram gönderme hatası: {e}")
        return False
