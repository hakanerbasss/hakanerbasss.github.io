"""
Sahne görselleri ve overlay'ler.

Görsel hiyerarşisi: DALL-E (OpenAI varsa) → Wikimedia Commons → Pexels.
Kod supertonic-web'den birebir taşındı; sadece Telegram bağımlılığı çıkarıldı.
"""
import io
import sys
import subprocess
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import get_openai_key, get_pexels_key

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]


def find_font() -> str | None:
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


def _fetch_wikimedia_image(keyword: str, width: int = 1920) -> bytes | None:
    try:
        r = httpx.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search", "gsrsearch": keyword,
                "gsrnamespace": "6", "gsrlimit": "5", "prop": "imageinfo",
                "iiprop": "url|mime", "iiurlwidth": str(width), "format": "json",
            },
            timeout=10,
            headers={"User-Agent": "InsTube/1.0"},
        )
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("mime", "").startswith("image/"):
                continue
            url = info.get("thumburl") or info.get("url", "")
            if url:
                return httpx.get(url, timeout=15).content
    except Exception:
        pass
    return None


def _generate_dalle_image(keyword: str, orientation: str, openai_key: str) -> bytes | None:
    import base64
    try:
        from openai import OpenAI as _OAI
        client = _OAI(api_key=openai_key)
        size = "1024x1536" if orientation == "portrait" else "1536x1024"
        resp = client.images.generate(
            model="gpt-image-1-mini",
            prompt=(f"Professional high-quality documentary-style photo of {keyword}, "
                    "realistic, cinematic lighting, no text, no watermarks, no logos"),
            size=size, n=1,
        )
        b64 = resp.data[0].b64_json
        if b64:
            return base64.b64decode(b64)
        url = getattr(resp.data[0], "url", None)
        if url:
            return httpx.get(url, timeout=30).content
    except Exception:
        pass
    return None


def _save_as_jpeg(data: bytes, img_path: Path) -> bool:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.save(str(img_path), "JPEG", quality=92)
        return True
    except Exception:
        return False


def try_ken_burns_clip(img_path: Path, dur: float, clip_path: Path,
                       text_file=None, font_path: str = None) -> bool:
    """Ken Burns zoom efektiyle klip dene. Başarısızsa False döner (fallback için)."""
    frames = max(1, int(dur * 30))
    zoom_expr = f"'min(1+0.12*on/{frames},1.12)'"
    zoompan = (
        f"scale=1296:2304:force_original_aspect_ratio=increase,"
        f"crop=1296:2304,"
        f"zoompan=z={zoom_expr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s=1080x1920:fps=30"
    )
    if text_file and Path(text_file).exists():
        dt = (
            f"drawtext=textfile={Path(text_file).absolute()}"
            f":fontsize=42:fontcolor=white:bordercolor=black:borderw=2"
            f":x=(w-text_w)/2:y=h-th-420:line_spacing=12"
            f":box=1:boxcolor=black@0.55:boxborderw=18"
        )
        if font_path:
            dt += f":fontfile={font_path}"
        vf = zoompan + "," + dt
    else:
        vf = zoompan
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
            "-t", str(dur), "-vf", vf,
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p", str(clip_path),
        ], capture_output=True, timeout=90)
        return result.returncode == 0 and clip_path.exists() and clip_path.stat().st_size > 0
    except Exception:
        return False


def fetch_scene_visual(keyword: str, orientation: str, pexels_key: str, img_path: Path) -> tuple[bool, str]:
    """(başarı: True,"") | (başarısız: False, "neden")"""
    width = 1080 if orientation == "portrait" else 1920
    size_key = "portrait" if orientation == "portrait" else "large2x"

    openai_key = get_openai_key()
    if openai_key:
        data = _generate_dalle_image(keyword, orientation, openai_key)
        if data and _save_as_jpeg(data, img_path):
            return True, ""

    data = _fetch_wikimedia_image(keyword, width=width)
    if data and _save_as_jpeg(data, img_path):
        return True, ""

    if pexels_key:
        try:
            resp = httpx.get(
                "https://api.pexels.com/v1/search",
                params={"query": keyword, "orientation": orientation, "per_page": 3},
                headers={"Authorization": pexels_key},
                timeout=10,
            )
            if resp.status_code == 401:
                return False, "Pexels 401 key geçersiz"
            if resp.status_code == 429:
                return False, "Pexels 429 kota doldu"
            photos = resp.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"].get(size_key) or photos[0]["src"]["large"]
                data = httpx.get(img_url, timeout=15).content
                if _save_as_jpeg(data, img_path):
                    return True, ""
            else:
                return False, f"Pexels sonuç yok ({resp.status_code})"
        except Exception as e:
            return False, f"Pexels hata: {e}"
    else:
        return False, "Pexels key yok"

    return False, "tüm kaynaklar başarısız"


def overlay_like_subscribe_banner(photo_path: Path) -> None:
    """Son sahneye koyu alt bant + 👍 Beğen  🔔 Abone Ol."""
    W, H = 1080, 1920
    img = Image.open(photo_path).convert("RGBA").resize((W, H), Image.LANCZOS)

    BAND_H = 260
    band = Image.new("RGBA", (W, BAND_H), (10, 10, 10, 210))
    img.paste(band, (0, H - BAND_H), band)
    draw = ImageDraw.Draw(img)

    font_path = find_font()
    try:
        font_big = ImageFont.truetype(font_path, 90) if font_path else ImageFont.load_default()
        font_small = ImageFont.truetype(font_path, 46) if font_path else ImageFont.load_default()
    except Exception:
        font_big = font_small = ImageFont.load_default()

    RED, WHITE, YELLOW = (255, 0, 0), (255, 255, 255), (255, 208, 0)
    lx = W // 4
    draw.text((lx, H - BAND_H + 28), "👍", font=font_big, anchor="mt", fill=WHITE)
    draw.text((lx, H - BAND_H + 128), "Beğen", font=font_small, anchor="mt", fill=YELLOW)
    sep_x = W // 2
    draw.line([(sep_x, H - BAND_H + 20), (sep_x, H - 20)], fill=(80, 80, 80), width=2)
    rx = W * 3 // 4
    draw.text((rx, H - BAND_H + 28), "🔔", font=font_big, anchor="mt", fill=WHITE)
    draw.text((rx, H - BAND_H + 128), "Abone Ol", font=font_small, anchor="mt", fill=RED)

    img.convert("RGB").save(str(photo_path), "JPEG", quality=92)


def overlay_first_scene_banner(photo_path: Path, title: str, lang: str = "tr") -> None:
    """İlk sahneye haber overlay: büyük sarı başlık + eğik SON DAKİKA badge."""
    W, H = 1080, 1920
    img = Image.open(photo_path).convert("RGB").resize((W, H), Image.LANCZOS)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)

    fp = find_font()

    def lf(sz):
        if fp:
            try:
                return ImageFont.truetype(fp, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    def tw(text, font):
        try:
            return draw.textlength(text, font=font)
        except AttributeError:
            return font.getlength(text)

    def shadow_text(cx, y, text, font, fill):
        w = int(tw(text, font)); x = cx - w // 2
        for dx, dy in [(5, 5), (4, 4), (3, 3)]:
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
        draw.text((x, y), text, font=font, fill=fill)

    def fit_font(text, start_sz, max_w):
        sz = start_sz
        while sz > 40:
            f = lf(sz)
            if tw(text, f) <= max_w:
                return f, sz
            sz -= 10
        return lf(sz), sz

    YELLOW, RED, BLACK, WHITE = (255, 208, 0), (213, 0, 0), (17, 17, 17), (255, 255, 255)
    CX = W // 2
    cat_text = "GÜNDEM" if lang == "tr" else "BREAKING"
    badge_text = "SON DAKİKA" if lang == "tr" else "BREAKING NEWS"

    words = title.upper().split()
    if len(words) <= 2:
        part_a, part_b, part_c = " ".join(words), "", ""
    elif len(words) <= 4:
        m = len(words) // 2
        part_a, part_b, part_c = " ".join(words[:m]), " ".join(words[m:]), ""
    else:
        part_a, part_b, part_c = " ".join(words[:2]), " ".join(words[2:-2]), " ".join(words[-2:])

    y1, h1 = 150, 120
    draw.rectangle([(0, y1), (W, y1 + h1)], fill=YELLOW)
    draw.rectangle([(0, y1), (W, y1 + 7)], fill=BLACK)
    draw.rectangle([(0, y1 + h1 - 7), (W, y1 + h1)], fill=BLACK)
    cf = lf(52); af = lf(62)
    draw.text((60, y1 + (h1 - 52) // 2), "»»", font=af, fill=BLACK)
    cw = tw(cat_text, cf)
    draw.text((CX - cw // 2, y1 + (h1 - 52) // 2), cat_text, font=cf, fill=BLACK)
    draw.text((W - 60 - int(tw("««", af)), y1 + (h1 - 52) // 2), "««", font=af, fill=BLACK)

    if part_a:
        a_font, _ = fit_font(part_a, 190, W - 120)
        shadow_text(CX, 330, part_a, a_font, YELLOW)

    if part_b:
        b_font, b_sz = fit_font(part_b, 88, W - 100)
        b_w = int(tw(part_b, b_font))
        bx1, bx2 = CX - b_w // 2 - 50, CX + b_w // 2 + 50
        by, bh, sk = 580, b_sz + 40, 20
        poly = [(bx1 + sk, by), (bx2 + sk, by), (bx2 - sk, by + bh), (bx1 - sk, by + bh)]
        acc = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(acc).polygon(poly, fill=(10, 10, 10, 185))
        img = Image.alpha_composite(img.convert("RGBA"), acc).convert("RGB")
        draw = ImageDraw.Draw(img)
        shadow_text(CX, by + 18, part_b, b_font, YELLOW)

    if part_c:
        c_font, _ = fit_font(part_c, 190, W - 120)
        y_c = 750 if part_b else 600
        shadow_text(CX, y_c, part_c, c_font, YELLOW)

    bdf = lf(80); bt = badge_text; btw = int(tw(bt, bdf))
    bw2 = btw + 130; bx_b = CX - bw2 // 2; byy, bhh, sk2 = 1300, 140, 28
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([(CX - 360, byy + 60), (CX + 360, byy + 240)], fill=(255, 30, 40, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)
    rp = [(bx_b + sk2, byy), (bx_b + bw2 + sk2, byy), (bx_b + bw2 - sk2, byy + bhh), (bx_b - sk2, byy + bhh)]
    rib = Image.new("RGBA", (W, H), (0, 0, 0, 0)); rd = ImageDraw.Draw(rib)
    rd.polygon(rp, fill=(213, 0, 0, 255))
    rd.polygon([(bx_b + sk2, byy), (bx_b + bw2 + sk2, byy),
                (bx_b + bw2 + sk2 - 6, byy + 10), (bx_b + sk2 - 6, byy + 10)], fill=(255, 40, 60, 255))
    img = Image.alpha_composite(img.convert("RGBA"), rib).convert("RGB")
    draw = ImageDraw.Draw(img)
    shadow_text(CX, byy + (bhh - 80) // 2, bt, bdf, WHITE)

    img.save(str(photo_path), "JPEG", quality=92)
