"""
Viral Ürün Post Sistemi

Akış:
1. Viral ürün bul
2. Görsel üret → public/latest.jpg
3. Caption üret → public/latest_caption.txt
4. Telegram önizleme gönder
(Instagram postu workflow'un git push adımından sonra ayrıca atılır)
"""

import logging
import os
import shutil
import sys
import time

from config import (
    AMAZON_ASSOCIATE_TAG,
    DEEPSEEK_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MAX_POSTS_PER_DAY,
    POST_INTERVAL_HOURS,
    PRODUCT_NICHE,
)
from product_finder import get_viral_products
from image_editor import create_product_post
from caption_gen import get_caption
from telegram_sender import send_post, make_amazon_link

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

POSTED_LOG = "posted_products.txt"
PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")
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
    posted = load_posted_ids()
    products = get_viral_products(count=10)
    new_products = [p for p in products if p.product_url not in posted]

    if not new_products:
        logger.warning("Yeni ürün bulunamadı.")
        return

    product = new_products[0]
    logger.info(f"İşleniyor: {product.title}")

    # 1. Görsel üret
    image_path = create_product_post(
        title=product.title,
        price=product.price,
        image_url=product.image_url,
        rating=product.rating,
        sold_count=product.sold_count,
    )

    # 2. Caption + affiliate link üret
    affiliate_link = make_amazon_link(product.title, AMAZON_ASSOCIATE_TAG)
    caption = get_caption(
        title=product.title,
        price=product.price,
        sold_count=product.sold_count,
        niche=PRODUCT_NICHE,
        api_key=DEEPSEEK_API_KEY or None,
    )
    full_caption = f"{caption}\n\n🛒 Amazon: {affiliate_link}"

    # 3. public/ klasörüne kaydet (workflow bu dosyaları commit edecek)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    public_image = os.path.join(PUBLIC_DIR, "latest.jpg")
    public_caption = os.path.join(PUBLIC_DIR, "latest_caption.txt")
    shutil.copy2(image_path, public_image)
    with open(public_caption, "w") as f:
        f.write(full_caption)
    logger.info(f"Görsel: {public_image}")
    logger.info(f"Caption kaydedildi.")

    # 4. Telegram önizleme
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID and not DRY_RUN:
        send_post(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, image_path, caption, affiliate_link)

    save_posted_id(product.product_url)
    logger.info("Tamamlandı. Workflow şimdi git push + Instagram post yapacak.")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logger.info(f"Niş: {PRODUCT_NICHE} | DRY_RUN: {DRY_RUN}")

    if args.once:
        run_once()
        return

    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.exception(f"Hata: {e}")
        time.sleep(POST_INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
