"""
Pillow ile ürün görseli düzenleyici.

Bir ürün fotoğrafını alır, üzerine:
- Gradient arka plan
- Ürün adı
- Fiyat etiketi
- Satış sayısı / puan
- Watermark / logo
ekler ve 1080x1080 Instagram formatında kaydeder.
"""

import io
import os
import requests
import textwrap
import logging
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Renk teması
THEME = {
    "bg_gradient_top": (15, 15, 25),
    "bg_gradient_bottom": (30, 10, 60),
    "accent": (255, 60, 120),       # pembe/kırmızı vurgu
    "price_bg": (255, 200, 0),      # sarı fiyat etiketi
    "price_text": (20, 20, 20),
    "title_text": (255, 255, 255),
    "subtitle_text": (200, 200, 220),
    "watermark": (255, 255, 255, 100),
}

W, H = 1080, 1080


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Sistem fontunu yükler, bulamazsa varsayılanı kullanır."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        os.path.join(TEMPLATE_DIR, "fonts", "bold.ttf" if bold else "regular.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_gradient_background(draw: ImageDraw.ImageDraw):
    """Dikey gradient arka plan çizer."""
    top = THEME["bg_gradient_top"]
    bot = THEME["bg_gradient_bottom"]
    for y in range(H):
        t = y / H
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _download_image(url: str) -> Image.Image | None:
    """URL'den görsel indirir."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Görsel indirilemedi ({url}): {e}")
        return None


def _paste_product_image(canvas: Image.Image, product_img: Image.Image):
    """Ürün görselini canvas'ın ortasına yerleştirir."""
    # Ürünü beyaz arka planla kare yap
    size = 640
    product_img = product_img.convert("RGBA")

    # Oranı koru ve yeniden boyutlandır
    product_img.thumbnail((size, size), Image.LANCZOS)
    pw, ph = product_img.size

    # Hafif gölge efekti
    shadow = Image.new("RGBA", (pw + 20, ph + 20), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rectangle([10, 10, pw + 10, ph + 10], fill=(0, 0, 0, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(15))

    x = (W - pw) // 2
    y = 160

    canvas.paste(shadow, (x - 10, y - 10), shadow)
    canvas.paste(product_img, (x, y), product_img)


def _draw_price_badge(draw: ImageDraw.ImageDraw, price: str):
    """Sağ üst köşeye fiyat etiketi çizer."""
    font = _load_font(52, bold=True)
    bbox = draw.textbbox((0, 0), price, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 18
    x1, y1 = W - tw - pad * 2 - 30, 30
    x2, y2 = W - 30, th + pad * 2 + 30

    # Etiket arka planı (yuvarlak köşe simülasyonu)
    draw.rectangle([x1, y1, x2, y2], fill=THEME["price_bg"])
    draw.text((x1 + pad, y1 + pad), price, font=font, fill=THEME["price_text"])


def _draw_title(draw: ImageDraw.ImageDraw, title: str):
    """Alt kısma ürün adını çizer."""
    font = _load_font(48, bold=True)
    wrapped = textwrap.fill(title, width=24)
    draw.text((60, 830), wrapped, font=font, fill=THEME["title_text"])


def _draw_stats(draw: ImageDraw.ImageDraw, rating: float | None, sold: str | None):
    """Puan ve satış bilgisini çizer."""
    font = _load_font(36)
    parts = []
    if rating:
        parts.append(f"★ {rating}")
    if sold:
        parts.append(f"🔥 {sold} sold")
    if parts:
        draw.text((60, 980), "  ".join(parts), font=font, fill=THEME["subtitle_text"])


def _draw_watermark(canvas: Image.Image, text: str = "@hakanerbasss"):
    """Sol üst köşeye şeffaf watermark ekler."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _load_font(32)
    draw.text((30, 30), text, font=font, fill=THEME["watermark"])
    canvas.alpha_composite(overlay)


def _draw_accent_bar(draw: ImageDraw.ImageDraw):
    """Alt kısma renkli bir şerit çizer."""
    draw.rectangle([0, H - 8, W, H], fill=THEME["accent"])


def create_product_post(
    title: str,
    price: str,
    image_url: str,
    rating: float | None = None,
    sold_count: str | None = None,
    watermark: str = "@hakanerbasss",
    output_path: str | None = None,
) -> str:
    """
    Ürün bilgilerinden 1080x1080 Instagram postu üretir.
    Kaydedilen dosya yolunu döndürür.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        safe_name = "".join(c if c.isalnum() else "_" for c in title[:30])
        output_path = os.path.join(OUTPUT_DIR, f"{safe_name}.jpg")

    canvas = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(canvas)

    _draw_gradient_background(draw)

    product_img = _download_image(image_url)
    if product_img:
        _paste_product_image(canvas, product_img)
    else:
        # Görsel yoksa placeholder kutu çiz
        draw.rectangle([200, 200, 880, 780], fill=(40, 40, 60), outline=(80, 80, 100), width=3)
        draw.text((400, 460), "No Image", font=_load_font(48), fill=(120, 120, 140))

    _draw_price_badge(draw, price)
    _draw_title(draw, title)
    _draw_stats(draw, rating, sold_count)
    _draw_watermark(canvas, watermark)
    _draw_accent_bar(draw)

    # JPEG olarak kaydet
    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    logger.info(f"Görsel oluşturuldu: {output_path}")
    return output_path


SW, SH = 1080, 1920  # Story boyutu 9:16


def create_story_post(
    title: str,
    price: str,
    image_url: str,
    affiliate_link: str,
    rating: float | None = None,
    output_path: str | None = None,
) -> str:
    """
    1080x1920 Story görseli üretir.
    Ürün görseli ortada, üstte başlık, altta büyük CTA butonu + link metni.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if output_path is None:
        safe_name = "".join(c if c.isalnum() else "_" for c in title[:30])
        output_path = os.path.join(OUTPUT_DIR, f"{safe_name}_story.jpg")

    canvas = Image.new("RGBA", (SW, SH))
    draw = ImageDraw.Draw(canvas)

    # Gradient arka plan (story yüksekliğinde)
    top, bot = THEME["bg_gradient_top"], THEME["bg_gradient_bottom"]
    for y in range(SH):
        t = y / SH
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (SW, y)], fill=(r, g, b))

    # Watermark üst
    wm_font = _load_font(38)
    draw.text((40, 80), "@hakanerbasss", font=wm_font, fill=THEME["watermark"])

    # Başlık
    title_font = _load_font(58, bold=True)
    wrapped = textwrap.fill(title, width=20)
    draw.text((60, 180), wrapped, font=title_font, fill=THEME["title_text"])

    # Fiyat etiketi
    price_font = _load_font(64, bold=True)
    pbbox = draw.textbbox((0, 0), price, font=price_font)
    pw, ph = pbbox[2] - pbbox[0], pbbox[3] - pbbox[1]
    pad = 20
    draw.rectangle([SW - pw - pad * 2 - 30, 160, SW - 30, 160 + ph + pad * 2], fill=THEME["price_bg"])
    draw.text((SW - pw - pad - 30, 160 + pad), price, font=price_font, fill=THEME["price_text"])

    # Ürün görseli ortaya
    product_img = _download_image(image_url)
    if product_img:
        product_img = product_img.convert("RGBA")
        product_img.thumbnail((860, 860), Image.LANCZOS)
        pw2, ph2 = product_img.size
        px = (SW - pw2) // 2
        py = (SH - ph2) // 2 - 60
        canvas.paste(product_img, (px, py), product_img)
    else:
        draw.rectangle([110, 500, 970, 1360], fill=(40, 40, 60))
        draw.text((400, 900), "No Image", font=_load_font(48), fill=(120, 120, 140))

    # Puan
    if rating:
        star_font = _load_font(42)
        draw.text((60, SH - 380), f"★ {rating}", font=star_font, fill=(255, 200, 0))

    # Alt pembe şerit
    draw.rectangle([0, SH - 260, SW, SH], fill=THEME["accent"])

    # CTA butonu metni
    cta_font = _load_font(62, bold=True)
    draw.text((SW // 2 - 200, SH - 220), "SATIN AL →", font=cta_font, fill=(255, 255, 255))

    # Link metni (kopyalanabilsin diye)
    short_link = affiliate_link[:55] + "…" if len(affiliate_link) > 55 else affiliate_link
    link_font = _load_font(28)
    draw.text((40, SH - 60), short_link, font=link_font, fill=(255, 255, 255, 180))

    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    logger.info(f"Story görseli oluşturuldu: {output_path}")
    return output_path
