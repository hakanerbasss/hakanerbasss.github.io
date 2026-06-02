"""
Instagram Otomatik Gönderi Sistemi — Ana Orkestratör

Çalışma akışı:
1. Viral ürünleri çek (AliExpress / Reddit)
2. Her ürün için 1080x1080 görsel üret (Pillow)
3. AI ile caption oluştur (DeepSeek API veya şablon)
4. Instagram'a gönder (instagrapi)
5. Belirli aralıklarla tekrarla
"""

import logging
import os
import sys
import time
from datetime import datetime

from config import (
    DEEPSEEK_API_KEY,
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    MAX_POSTS_PER_DAY,
    POST_INTERVAL_HOURS,
    PRODUCT_NICHE,
)
from product_finder import get_viral_products
from image_editor import create_product_post
from caption_gen import get_caption
from instagram_poster import InstagrapiPoster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("instagram_bot.log"),
    ],
)
logger = logging.getLogger(__name__)

POSTED_LOG = "posted_products.txt"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def load_posted_ids() -> set[str]:
    if not os.path.exists(POSTED_LOG):
        return set()
    with open(POSTED_LOG) as f:
        return {line.strip() for line in f if line.strip()}


def save_posted_id(product_id: str):
    with open(POSTED_LOG, "a") as f:
        f.write(product_id + "\n")


def run_once():
    """Bir tur çalıştır: ürün bul, görsel oluştur, paylaş."""
    posted = load_posted_ids()
    logger.info(f"Daha önce paylaşılan ürün sayısı: {len(posted)}")

    products = get_viral_products(count=MAX_POSTS_PER_DAY + 5)
    new_products = [p for p in products if p.product_url not in posted]

    if not new_products:
        logger.warning("Paylaşılacak yeni ürün bulunamadı.")
        return

    poster = None
    if not DRY_RUN:
        poster = InstagrapiPoster(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

    posts_done = 0
    for product in new_products:
        if posts_done >= MAX_POSTS_PER_DAY:
            logger.info(f"Günlük limit ({MAX_POSTS_PER_DAY}) doldu.")
            break

        logger.info(f"İşleniyor: {product.title}")

        # 1. Görsel üret
        try:
            image_path = create_product_post(
                title=product.title,
                price=product.price,
                image_url=product.image_url,
                rating=product.rating,
                sold_count=product.sold_count,
                watermark=f"@{INSTAGRAM_USERNAME}" if INSTAGRAM_USERNAME else "@your_account",
            )
        except Exception as e:
            logger.error(f"Görsel oluşturma hatası: {e}")
            continue

        # 2. Caption üret
        caption = get_caption(
            title=product.title,
            price=product.price,
            sold_count=product.sold_count,
            niche=PRODUCT_NICHE,
            api_key=DEEPSEEK_API_KEY or None,
        )
        logger.info(f"Caption:\n{caption[:100]}...")

        # 3. Paylaş
        if DRY_RUN:
            logger.info(f"[DRY RUN] Post atılmadı: {image_path}")
        else:
            try:
                post_url = poster.post_photo(image_path, caption)
                logger.info(f"Paylaşıldı: {post_url}")
            except Exception as e:
                logger.error(f"Paylaşma hatası: {e}")
                continue

        save_posted_id(product.product_url)
        posts_done += 1

        # Instagram rate limit'e takılmamak için bekleme
        if posts_done < MAX_POSTS_PER_DAY:
            wait = 60 * 10  # 10 dakika
            logger.info(f"Sonraki post için {wait // 60} dakika bekleniyor...")
            time.sleep(wait)

    logger.info(f"Bu turda {posts_done} post paylaşıldı.")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Tek seferlik çalış ve çık (GitHub Actions için)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Instagram Otomatik Gönderi Sistemi başlatıldı")
    logger.info(f"Hesap: {INSTAGRAM_USERNAME or '(ayarlanmadı)'}")
    logger.info(f"Niş: {PRODUCT_NICHE}")
    logger.info(f"Mod: {'tek seferlik' if args.once else f'{POST_INTERVAL_HOURS} saatte bir'}")
    logger.info(f"DRY_RUN: {DRY_RUN}")
    logger.info("=" * 60)

    if not INSTAGRAM_USERNAME and not DRY_RUN:
        logger.error(
            "INSTAGRAM_USERNAME ayarlanmamış!\n"
            "  export INSTAGRAM_USERNAME='kullanici_adi'\n"
            "  export INSTAGRAM_PASSWORD='sifre'\n"
            "Ya da DRY_RUN=true ile test edin."
        )
        sys.exit(1)

    if args.once:
        run_once()
        return

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            logger.info("Kullanıcı tarafından durduruldu.")
            break
        except Exception as e:
            logger.exception(f"Beklenmeyen hata: {e}")

        next_run = datetime.now().strftime("%H:%M")
        logger.info(f"Sonraki çalışma {POST_INTERVAL_HOURS} saat sonra... (şu an {next_run})")
        time.sleep(POST_INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
