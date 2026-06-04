"""
Instagram'a elle koyman için gereken HER ŞEYİ Telegram'a gönderir:
feed görseli, story görseli, kopyalanabilir caption ve affiliate link.

Telegram'da <code>...</code> blokları mobilde tek dokunuşla kopyalanır.
"""

import html
import urllib.parse
import requests
import logging

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"


def make_amazon_link(product_title: str, associate_tag: str) -> str:
    """Ürün adından Amazon affiliate arama linki üretir."""
    query = urllib.parse.quote_plus(product_title)
    return f"https://www.amazon.com/s?k={query}&tag={associate_tag}"


def _send_photo(token: str, chat_id: str, image_path: str, caption: str) -> bool:
    try:
        with open(image_path, "rb") as photo:
            resp = requests.post(
                API.format(token=token, method="sendPhoto"),
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": photo},
                timeout=30,
            )
        if not resp.ok:
            logger.error(f"Telegram foto hatası {resp.status_code}: {resp.text}")
        return resp.ok
    except Exception as e:
        logger.error(f"Telegram foto gönderme hatası: {e}")
        return False


def _send_text(token: str, chat_id: str, text: str) -> bool:
    try:
        resp = requests.post(
            API.format(token=token, method="sendMessage"),
            data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        if not resp.ok:
            logger.error(f"Telegram mesaj hatası {resp.status_code}: {resp.text}")
        return resp.ok
    except Exception as e:
        logger.error(f"Telegram mesaj gönderme hatası: {e}")
        return False


def send_post(
    bot_token: str,
    chat_id: str,
    feed_image_path: str,
    story_image_path: str,
    caption: str,
    affiliate_link: str,
    title: str = "",
    price: str = "",
    rating=None,
    sold_count: str = "",
    shop_url: str = "https://hakanerbasss.github.io/shop",
) -> bool:
    """
    Instagram'a elle koyman için tam paket gönderir:
      1) Feed görseli (1080x1080)
      2) Story görseli (1080x1920)
      3) Ürün bilgisi (başlık/fiyat/puan)
      4) Caption — tek dokunuşla kopyalanır
      5) Affiliate link — tek dokunuşla kopyalanır
    """
    ok = True

    # 1. Feed görseli
    ok &= _send_photo(
        bot_token, chat_id, feed_image_path,
        "🖼 <b>FEED GÖRSELİ</b> — Instagram gönderisine yükle",
    )

    # 2. Story görseli
    ok &= _send_photo(
        bot_token, chat_id, story_image_path,
        "📱 <b>STORY GÖRSELİ</b> — Hikayene yükle, linki elle ekle 👆",
    )

    # 3. Ürün özeti
    info_lines = ["📦 <b>ÜRÜN BİLGİSİ</b>"]
    if title:
        info_lines.append(f"• {html.escape(title)}")
    if price:
        info_lines.append(f"• 💰 Fiyat: {html.escape(price)}")
    if rating:
        info_lines.append(f"• ⭐ Puan: {rating}")
    if sold_count:
        info_lines.append(f"• 🔥 Satış: {html.escape(sold_count)}")
    _send_text(bot_token, chat_id, "\n".join(info_lines))

    # 4. Caption — kopyalanabilir blok
    _send_text(
        bot_token, chat_id,
        "✍️ <b>AÇIKLAMA (kopyalamak için dokun):</b>\n"
        f"<code>{html.escape(caption)}</code>",
    )

    # 5. Affiliate link — kopyalanabilir blok
    _send_text(
        bot_token, chat_id,
        "🔗 <b>AFFILIATE LİNK (kopyalamak için dokun):</b>\n"
        f"<code>{html.escape(affiliate_link)}</code>\n\n"
        f"🌐 Bio linki: <code>{html.escape(shop_url)}</code>",
    )

    if ok:
        logger.info("Telegram'a tam paket gönderildi.")
    return ok
