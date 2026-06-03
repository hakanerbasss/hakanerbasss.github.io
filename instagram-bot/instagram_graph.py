"""
Instagram Graph API ile otomatik post atar.
Görsel GitHub raw URL üzerinden erişilebilir hale getirilir.
"""

import time
import requests
import logging

logger = logging.getLogger(__name__)

BASE = "https://graph.facebook.com/v21.0"


def post_story_to_instagram(ig_user_id: str, access_token: str, image_url: str, link_url: str) -> bool:
    """Story atar — link sticker ile doğrudan tıklanabilir link ekler."""
    try:
        data = {
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": access_token,
        }
        if link_url:
            data["link_sticker_url"] = link_url

        r = requests.post(f"{BASE}/{ig_user_id}/media", data=data, timeout=30)
        r.raise_for_status()
        container_id = r.json().get("id")
        if not container_id:
            logger.error(f"Story container ID alınamadı: {r.text}")
            return False
        logger.info(f"Story container oluşturuldu: {container_id}")

        time.sleep(5)

        r2 = requests.post(
            f"{BASE}/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": access_token},
            timeout=30,
        )
        r2.raise_for_status()
        story_id = r2.json().get("id")
        logger.info(f"Story yayınlandı: {story_id}")
        return True

    except Exception as e:
        logger.error(f"Story post hatası: {e}")
        if hasattr(e, "response") and e.response is not None:
            logger.error(f"Detay: {e.response.text}")
        return False


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
