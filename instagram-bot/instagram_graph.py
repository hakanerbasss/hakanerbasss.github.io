"""
Instagram Graph API ile otomatik post atar.
Görsel GitHub raw URL üzerinden erişilebilir hale getirilir.
"""

import time
import requests
import logging

logger = logging.getLogger(__name__)

BASE = "https://graph.instagram.com/v21.0"


def post_to_instagram(ig_user_id: str, access_token: str, image_url: str, caption: str) -> bool:
    """Görseli Instagram'a poster."""
    try:
        # 1. Media container oluştur
        r = requests.post(
            f"{BASE}/{ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": caption[:2200],
                "access_token": access_token,
            },
            timeout=30,
        )
        r.raise_for_status()
        container_id = r.json().get("id")
        if not container_id:
            logger.error(f"Container ID alınamadı: {r.text}")
            return False
        logger.info(f"Container oluşturuldu: {container_id}")

        time.sleep(5)

        # 2. Yayınla
        r2 = requests.post(
            f"{BASE}/{ig_user_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": access_token,
            },
            timeout=30,
        )
        r2.raise_for_status()
        post_id = r2.json().get("id")
        logger.info(f"Instagram'a yayınlandı: {post_id}")
        return True

    except Exception as e:
        logger.error(f"Instagram post hatası: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Detay: {e.response.text}")
        return False
