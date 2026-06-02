"""
Instagram'a fotoğraf gönderen modül.

İki mod:
1. instagrapi  — kişisel/creator/business hesapla çalışır (gayri resmi)
2. Graph API   — sadece Business/Creator hesapla çalışır (resmi Meta API)

Önce instagrapi dener, credential yoksa Graph API'ye düşer.
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class InstagrapiPoster:
    """instagrapi kütüphanesiyle Instagram'a post atar."""

    def __init__(self, username: str, password: str, session_file: str = "session.json"):
        self.username = username
        self.password = password
        self.session_file = session_file
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client
        try:
            from instagrapi import Client

            cl = Client()
            cl.delay_range = [2, 5]  # İnsan gibi davran

            if os.path.exists(self.session_file):
                cl.load_settings(self.session_file)
                cl.login(self.username, self.password)
                logger.info("Session dosyasından giriş yapıldı")
            else:
                cl.login(self.username, self.password)
                cl.dump_settings(self.session_file)
                logger.info("Yeni giriş yapıldı, session kaydedildi")

            self._client = cl
            return cl
        except ImportError:
            raise RuntimeError("instagrapi kurulu değil: pip install instagrapi")

    def post_photo(self, image_path: str, caption: str) -> str:
        """Fotoğraf gönderir. Post URL'sini döndürür."""
        cl = self._get_client()
        media = cl.photo_upload(
            path=image_path,
            caption=caption,
        )
        url = f"https://www.instagram.com/p/{media.code}/"
        logger.info(f"Post başarılı: {url}")
        return url


class GraphAPIPoster:
    """
    Meta Graph API ile Instagram Business/Creator hesabına post atar.
    Gereksinimler:
    - Instagram Business/Creator hesabı
    - Meta Developer App (Basic Display API veya Marketing API)
    - Access Token (uzun ömürlü)
    """

    def __init__(self, access_token: str, ig_user_id: str):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.base_url = "https://graph.instagram.com/v21.0"

    def post_photo(self, image_url: str, caption: str) -> str:
        """
        image_url: Halka açık bir URL olmalı (S3, Cloudinary, vb.)
        Döndürür: Post ID
        """
        import requests

        # Adım 1: Media container oluştur
        container_resp = requests.post(
            f"{self.base_url}/{self.ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json()["id"]
        logger.info(f"Media container oluşturuldu: {container_id}")

        time.sleep(3)

        # Adım 2: Container'ı yayınla
        publish_resp = requests.post(
            f"{self.base_url}/{self.ig_user_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
            timeout=30,
        )
        publish_resp.raise_for_status()
        post_id = publish_resp.json()["id"]
        logger.info(f"Post yayınlandı: {post_id}")
        return post_id


def get_poster(config):
    """Config'e göre uygun poster'ı döndürür."""
    from config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD

    username = config.get("username") or INSTAGRAM_USERNAME
    password = config.get("password") or INSTAGRAM_PASSWORD

    if username and password:
        return InstagrapiPoster(username, password)

    access_token = config.get("access_token") or os.getenv("IG_ACCESS_TOKEN")
    ig_user_id = config.get("ig_user_id") or os.getenv("IG_USER_ID")
    if access_token and ig_user_id:
        return GraphAPIPoster(access_token, ig_user_id)

    raise ValueError(
        "Instagram kimlik bilgisi bulunamadı.\n"
        "INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD veya "
        "IG_ACCESS_TOKEN + IG_USER_ID env değişkenlerini ayarlayın."
    )
