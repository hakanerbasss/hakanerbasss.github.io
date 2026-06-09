"""
Google Maps scraper — web sitesi olmayan işletmeleri bulur, detaylı bilgi toplar.
"""

import asyncio
import random
import re
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from playwright.async_api import async_playwright, Page
import config


@dataclass
class BusinessInfo:
    # Temel
    name: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    has_website: bool = False
    slug: str = ""
    google_maps_url: str = ""

    # Puanlama
    rating: float = 0.0
    review_count: int = 0
    reviews_snippet: list = field(default_factory=list)  # İlk 3-5 yorum

    # Saatler
    hours: dict = field(default_factory=dict)
    is_open_now: bool = False

    # Medya
    photos: list = field(default_factory=list)       # Google Maps fotoğrafları (URL)
    cover_photo: str = ""

    # Sosyal medya
    instagram_handle: str = ""
    facebook_url: str = ""
    instagram_posts: list = field(default_factory=list)  # Son 9 post URL
    instagram_bio: str = ""
    instagram_followers: str = ""

    # Hizmet/ürün bilgisi
    services: list = field(default_factory=list)     # Menü/hizmet listesi (varsa)
    about: str = ""                                   # Google'daki açıklama

    # İletişim için
    place_id: str = ""

    def to_dict(self):
        return asdict(self)


async def _delay(a=1.5, b=3.0):
    await asyncio.sleep(random.uniform(a, b))


async def _setup(pw):
    browser = await pw.chromium.launch(
        headless=config.HEADLESS,
        slow_mo=config.SLOW_MO,
        args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1366,768",
        ],
    )
    ctx = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="tr-TR",
        timezone_id="Europe/Istanbul",
        extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9"},
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
    )
    return browser, ctx


async def _accept_cookies(page: Page):
    try:
        for sel in ['button:has-text("Tümünü kabul et")', 'button:has-text("Accept all")',
                    'button:has-text("Kabul et")']:
            btn = page.locator(sel)
            if await btn.count() > 0:
                await btn.first.click()
                await _delay(1, 2)
                return
    except Exception:
        pass


async def search_place_urls(page: Page, query: str, max_n: int) -> list[str]:
    """Google Maps'te arama yapar, işletme URL listesi döner."""
    url = "https://www.google.com/maps/search/" + query.replace(" ", "+")
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await _accept_cookies(page)
    await _delay(2, 3)

    urls, seen, scrolls = [], set(), 0
    while len(urls) < max_n * 2 and scrolls < 20:
        cards = page.locator('a[href*="/maps/place/"]')
        for i in range(await cards.count()):
            try:
                href = await cards.nth(i).get_attribute("href")
                if href and href not in seen and "/maps/place/" in href:
                    seen.add(href)
                    urls.append(href)
            except Exception:
                pass
        feed = page.locator('div[role="feed"]')
        if await feed.count():
            await feed.evaluate("el=>el.scrollBy(0,600)")
        await _delay(1.5, 2.5)
        scrolls += 1
    return urls[:max_n * 2]


async def _get_text(page: Page, *selectors) -> str:
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count():
                return (await el.first.inner_text()).strip()
        except Exception:
            pass
    return ""


async def _get_attr(page: Page, attr: str, *selectors) -> str:
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.count():
                val = await el.first.get_attribute(attr)
                if val:
                    return val.strip()
        except Exception:
            pass
    return ""


async def _extract_hours(page: Page) -> dict:
    hours = {}
    try:
        # Saatleri göster butonuna tıkla
        toggle = page.locator('[data-item-id="oh"] button, button[aria-label*="saatler"], button[aria-label*="hours"]')
        if await toggle.count():
            await toggle.first.click()
            await _delay(0.5, 1)

        rows = page.locator('table.WgFkxc tr, div[jsaction*="openhours"] table tr')
        for i in range(await rows.count()):
            cells = rows.nth(i).locator("td")
            if await cells.count() >= 2:
                day = (await cells.nth(0).inner_text()).strip()
                time = (await cells.nth(1).inner_text()).strip()
                if day:
                    hours[day] = time
    except Exception:
        pass
    return hours


async def _extract_photos(page: Page, place_name: str) -> list[str]:
    """Google Maps'ten fotoğraf URL'leri çeker."""
    photos = []
    try:
        # Fotoğraf galerisi butonuna tıkla
        photo_btn = page.locator(
            'button[aria-label*="fotoğraf"], button[aria-label*="photo"], '
            'div[data-photo-index] button, a[aria-label*="Fotoğraf"]'
        )
        if await photo_btn.count():
            await photo_btn.first.click()
            await _delay(2, 3)

        # Görselleri topla
        imgs = page.locator('img[src*="googleusercontent.com"][src*="=w"]')
        for i in range(min(await imgs.count(), 12)):
            src = await imgs.nth(i).get_attribute("src") or ""
            if "googleusercontent.com" in src and src not in photos:
                # Yüksek çözünürlük
                src = re.sub(r"=w\d+", "=w1200", src)
                src = re.sub(r"-h\d+", "-h900", src)
                photos.append(src)

        # Geri dön
        back = page.locator('button[aria-label*="Geri"], button[aria-label*="Back"]')
        if await back.count():
            await back.first.click()
            await _delay(1, 1.5)
    except Exception:
        pass
    return photos[:9]


async def _extract_reviews(page: Page) -> list[str]:
    snippets = []
    try:
        review_els = page.locator('div.MyEned span.wiI7pd, span[jslog*="review"] .wiI7pd')
        for i in range(min(await review_els.count(), 5)):
            text = (await review_els.nth(i).inner_text()).strip()
            if text and len(text) > 20:
                snippets.append(text)
    except Exception:
        pass
    return snippets


async def _extract_services(page: Page) -> list[str]:
    services = []
    try:
        items = page.locator('div[aria-label*="menü"] li, div.m6QErb li.hfpxzc span')
        for i in range(min(await items.count(), 12)):
            t = (await items.nth(i).inner_text()).strip()
            if t and len(t) < 60 and t not in services:
                services.append(t)
    except Exception:
        pass
    return services


async def _find_instagram(page: Page, name: str, address: str) -> str:
    """İşletmenin Instagram hesabını bulmaya çalışır."""
    # 1. Google Maps sayfasında social link var mı?
    try:
        ig_link = page.locator('a[href*="instagram.com"]')
        if await ig_link.count():
            href = await ig_link.first.get_attribute("href") or ""
            match = re.search(r'instagram\.com/([^/?&\s]+)', href)
            if match:
                return match.group(1)
    except Exception:
        pass

    # 2. Google araması (ayrı sayfa açmadan — web verisi arama)
    try:
        city = address.split(",")[-1].strip() if address else ""
        query = f"{name} {city} instagram"
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        response_text = ""
        async with page.expect_response(lambda r: "google.com/search" in r.url) as _:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        content = await page.content()
        match = re.search(r'instagram\.com/([a-zA-Z0-9_.]{2,30})', content)
        if match:
            handle = match.group(1)
            if handle not in ("p", "reel", "explore", "accounts", "stories"):
                return handle
    except Exception:
        pass

    return ""


async def scrape_detail(page: Page, url: str) -> Optional[BusinessInfo]:
    """Tek bir işletmenin tüm detaylarını çeker."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await _delay(2, 3)

        b = BusinessInfo()
        b.google_maps_url = url

        # İsim
        b.name = await _get_text(page,
            'h1.DUwDvf', 'h1[data-attrid="title"]', 'div.tAiQdd h1')

        # Kategori
        b.category = await _get_text(page, 'button.DkEaL', 'div.DkEaL', 'span.YhemCb')

        # Adres
        b.address = await _get_text(page,
            'button[data-item-id="address"] div.fontBodyMedium',
            'div[data-item-id="address"] div.fontBodyMedium',
            'button[data-tooltip="Adresi kopyala"] div.fontBodyMedium')

        # Telefon
        phone_raw = await _get_text(page,
            'button[data-item-id*="phone"] div.fontBodyMedium',
            'a[data-item-id*="phone"] div.fontBodyMedium')
        b.phone = re.sub(r"[^\d\+\s\-\(\)]", "", phone_raw).strip()

        # Web sitesi var mı?
        ws = await _get_attr(page, "href",
            'a[data-item-id="authority"]',
            'a[aria-label*="web sitesi"]',
            'a[aria-label*="website"]')
        if ws and "google.com" not in ws:
            b.website = ws
            b.has_website = True

        # Rating
        try:
            r = await _get_text(page, 'div.fontDisplayLarge', 'span.ceNzKf')
            b.rating = float(r.replace(",", ".")) if r else 0.0
        except ValueError:
            pass

        # Yorum sayısı
        try:
            aria = await _get_attr(page, "aria-label",
                'button[aria-label*="yorum"]', 'span[aria-label*="yorum"]')
            nums = re.findall(r"[\d\.]+", aria.replace(".", ""))
            if nums:
                b.review_count = int(nums[0])
        except Exception:
            pass

        # Açık mı?
        open_text = await _get_text(page, 'span.dv0ZP', 'span[aria-label*="açık"]')
        b.is_open_now = "açık" in open_text.lower()

        # Açıklama / About
        b.about = await _get_text(page,
            'div.PYvSYb', 'div[data-attrid="description"] span', 'div.WeS02d span')

        # Saatler
        b.hours = await _extract_hours(page)

        # Fotoğraflar
        b.photos = await _extract_photos(page, b.name)
        if b.photos:
            b.cover_photo = b.photos[0]

        # Yorumlar
        b.reviews_snippet = await _extract_reviews(page)

        # Hizmetler
        b.services = await _extract_services(page)

        # Instagram
        if b.name:
            b.instagram_handle = await _find_instagram(page, b.name, b.address)

        # Slug
        b.slug = _make_slug(b.name)

        return b if b.name else None

    except Exception as e:
        print(f"[Scraper] HATA ({url[:60]}): {e}")
        return None


def _make_slug(name: str) -> str:
    tr = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    s = name.translate(tr).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "isletme"


async def find_businesses_without_website(
    query: str,
    location: str = "",
    max_results: int = None,
    progress_cb=None,
) -> list[BusinessInfo]:
    """Ana fonksiyon. progress_cb(current, total, name) ile ilerleme bildirimi."""
    if max_results is None:
        max_results = config.MAX_BUSINESSES

    results = []
    search_query = f"{query} {location}".strip()

    async with async_playwright() as pw:
        browser, ctx = await _setup(pw)
        try:
            page = await ctx.new_page()
            urls = await search_place_urls(page, search_query, max_results)

            total = len(urls)
            print(f"[Scraper] {total} URL bulundu, işleniyor...")

            for i, url in enumerate(urls):
                if len(results) >= max_results:
                    break

                b = await scrape_detail(page, url)
                if progress_cb:
                    progress_cb(i + 1, total, b.name if b else "...")

                if b and b.name and not b.has_website:
                    results.append(b)
                    print(f"[Scraper] ✓ {b.name} — {b.phone}")
                elif b:
                    print(f"[Scraper] ✗ Web sitesi var: {b.name}")

                await _delay(config.REQUEST_DELAY, config.REQUEST_DELAY + 1.5)

        finally:
            await browser.close()

    return results


def save_json(businesses: list[BusinessInfo], path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([b.to_dict() for b in businesses], f, ensure_ascii=False, indent=2)


def load_json(path: str) -> list[BusinessInfo]:
    with open(path, "r", encoding="utf-8") as f:
        return [BusinessInfo(**d) for d in json.load(f)]
