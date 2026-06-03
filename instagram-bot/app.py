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
from image_editor import create_product_post, create_story_post
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


def _update_shop_page(affiliate_link: str, product_title: str, price: str, image_url: str):
    """Linktree benzeri ürün listesi sayfasını günceller — yeni ürünü başa ekler."""
    import re
    import json as _json

    shop_path = os.path.join(os.path.dirname(__file__), "..", "shop.html")

    products = []
    if os.path.exists(shop_path):
        with open(shop_path) as f:
            content = f.read()
        m = re.search(r"<!--PRODUCTS:(.*?)-->", content, re.DOTALL)
        if m:
            try:
                products = _json.loads(m.group(1))
            except Exception:
                products = []

    new_item = {"title": product_title, "price": price, "url": affiliate_link, "image": image_url}
    products = [p for p in products if p.get("url") != affiliate_link]
    products.insert(0, new_item)
    products = products[:9]  # Instagram grid 3x3 — son 9 ürün yeterli

    cards_html = ""
    for i, p in enumerate(products):
        badge = '<span class="new">YENİ</span>' if i == 0 else ""
        img_html = (
            f'<img src="{p["image"]}" alt="{p["title"]}">'
            if p.get("image") else '<div class="no-img">📦</div>'
        )
        cards_html += f"""
    <a href="{p['url']}" class="card" target="_blank" rel="nofollow">
      <div class="thumb">{img_html}{badge}</div>
      <div class="info">
        <div class="title">{p['title']}</div>
        <div class="price">{p['price']}</div>
        <div class="btn">Amazon'da Gör →</div>
      </div>
    </a>"""

    products_json = _json.dumps(products, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>@hakanerbasss | Viral Ürünler</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0f0f19;color:#fff;font-family:-apple-system,sans-serif;min-height:100vh}}
    header{{text-align:center;padding:28px 16px 12px}}
    header h1{{font-size:1.5rem;color:#ff3c78;letter-spacing:1px}}
    header p{{color:#999;font-size:.85rem;margin-top:6px}}
    .hint{{background:#1e1e30;border-left:3px solid #ff3c78;margin:0 16px 4px;padding:10px 14px;font-size:.8rem;color:#ccc;border-radius:0 8px 8px 0}}
    .grid{{display:flex;flex-direction:column;gap:10px;padding:12px 16px;max-width:480px;margin:0 auto}}
    .card{{display:flex;background:#1e1e30;border-radius:14px;overflow:hidden;text-decoration:none;color:#fff;border:1px solid #2a2a40}}
    .thumb{{position:relative;width:100px;height:100px;flex-shrink:0;background:#111}}
    .thumb img{{width:100%;height:100%;object-fit:cover}}
    .no-img{{display:flex;align-items:center;justify-content:center;height:100%;font-size:2rem}}
    .new{{position:absolute;top:6px;left:6px;background:#ff3c78;color:#fff;font-size:.6rem;font-weight:700;padding:2px 6px;border-radius:4px}}
    .info{{padding:12px 14px;flex:1;display:flex;flex-direction:column;justify-content:space-between}}
    .title{{font-size:.82rem;font-weight:600;line-height:1.35;color:#eee}}
    .price{{color:#ffc800;font-weight:700;font-size:.95rem;margin-top:4px}}
    .btn{{background:#ff3c78;color:#fff;border-radius:8px;padding:5px 12px;font-size:.75rem;font-weight:600;display:inline-block;margin-top:6px;width:fit-content}}
    footer{{text-align:center;padding:20px;color:#444;font-size:.72rem}}
  </style>
</head>
<body>
<!--PRODUCTS:{products_json}-->
<header>
  <h1>@hakanerbasss</h1>
  <p>Son paylaşılan viral ürünler 🔥</p>
</header>
<p class="hint">📸 Instagram'da hangi ürünü gördüysen aşağıdan bul ve tıkla</p>
<div class="grid">{cards_html}
</div>
<footer>Affiliate linkler içerir. Satın alma yapılırsa komisyon kazanılabilir.</footer>
</body>
</html>"""

    with open(shop_path, "w") as f:
        f.write(html)
    logger.info(f"shop.html güncellendi ({len(products)} ürün) → {affiliate_link}")


def run_once():
    posted = load_posted_ids()
    products = get_viral_products(count=10)
    new_products = [p for p in products if p.product_url not in posted]

    if not new_products:
        logger.warning("Yeni ürün bulunamadı.")
        return

    product = new_products[0]
    logger.info(f"İşleniyor: {product.title}")

    # 1. Görsel üret (feed + story)
    affiliate_link = make_amazon_link(product.title, AMAZON_ASSOCIATE_TAG)
    image_path = create_product_post(
        title=product.title,
        price=product.price,
        image_url=product.image_url,
        rating=product.rating,
        sold_count=product.sold_count,
    )
    story_path = create_story_post(
        title=product.title,
        price=product.price,
        image_url=product.image_url,
        affiliate_link=affiliate_link,
        rating=product.rating,
    )

    # 2. Caption üret
    caption = get_caption(
        title=product.title,
        price=product.price,
        sold_count=product.sold_count,
        niche=PRODUCT_NICHE,
        api_key=DEEPSEEK_API_KEY or None,
    )
    # Link Instagram'da tıklanamaz ama kopyalanabilir; bio linki tüm ürünleri listeler
    full_caption = (
        f"{caption}\n\n"
        f"🔗 {affiliate_link}\n\n"
        f"👆 Bio linki: hakanerbasss.github.io/shop"
    )

    # Bio sayfasını güncelle (hakanerbasss.github.io/shop) — ürünü listeye ekler
    _update_shop_page(affiliate_link, product.title, product.price, product.image_url)

    # 3. public/ klasörüne kaydet (workflow bu dosyaları commit edecek)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    public_image = os.path.join(PUBLIC_DIR, "latest.jpg")
    public_story = os.path.join(PUBLIC_DIR, "latest_story.jpg")
    public_caption = os.path.join(PUBLIC_DIR, "latest_caption.txt")
    public_link = os.path.join(PUBLIC_DIR, "latest_link.txt")
    shutil.copy2(image_path, public_image)
    shutil.copy2(story_path, public_story)
    with open(public_caption, "w") as f:
        f.write(full_caption)
    with open(public_link, "w") as f:
        f.write(affiliate_link)
    logger.info(f"Feed görseli: {public_image}")
    logger.info(f"Story görseli: {public_story}")
    logger.info(f"Caption ve link kaydedildi.")

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
