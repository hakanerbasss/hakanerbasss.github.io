"""
Google Maps scraper - web sitesi olmayan işletmeleri bulur ve bilgilerini toplar.
Playwright kullanır, anti-detection önlemleri içerir.
"""

import asyncio
import random
import time
import re
import json
from dataclasses import dataclass, field, asdict
from typing import Optional
from playwright.async_api import async_playwright, Page, BrowserContext
import config


@dataclass
class BusinessInfo:
    name: str = ""
    category: str = ""
    address: str = ""
    city: str = ""
    district: str = ""
    phone: str = ""
    website: str = ""
    rating: float = 0.0
    review_count: int = 0
    hours: dict = field(default_factory=dict)
    photos: list = field(default_factory=list)
    description: str = ""
    google_maps_url: str = ""
    slug: str = ""
    has_website: bool = False

    def to_dict(self):
        return asdict(self)


async def random_delay(min_s: float = 1.0, max_s: float = 3.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def setup_browser(playwright):
    """Anti-detection önlemleriyle tarayıcı başlatır."""
    browser = await playwright.chromium.launch(
        headless=config.HEADLESS,
        slow_mo=config.SLOW_MO,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--window-size=1366,768",
        ],
    )

    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="tr-TR",
        timezone_id="Europe/Istanbul",
        extra_http_headers={
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )

    # navigator.webdriver'ı gizle
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['tr-TR', 'tr', 'en-US']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    """)

    return browser, context


async def accept_cookies(page: Page):
    """Google cookie uyarısını kabul eder."""
    try:
        btn = page.locator('button:has-text("Tümünü kabul et"), button:has-text("Accept all")')
        if await btn.count() > 0:
            await btn.first.click()
            await random_delay(1, 2)
    except Exception:
        pass


async def search_google_maps(
    page: Page,
    query: str,
    location: str = "",
    max_results: int = 20,
) -> list[str]:
    """
    Google Maps'te arama yapar ve işletme URL listesi döner.
    """
    search_term = f"{query} {location}".strip()
    maps_url = f"https://www.google.com/maps/search/{search_term.replace(' ', '+')}"

    print(f"[Scraper] Aranıyor: {search_term}")
    await page.goto(maps_url, wait_until="networkidle", timeout=30000)
    await accept_cookies(page)
    await random_delay(2, 4)

    urls = []
    last_count = 0
    scroll_attempts = 0

    while len(urls) < max_results and scroll_attempts < 15:
        # İşletme kartlarını bul
        cards = page.locator('a[href*="/maps/place/"]')
        current_count = await cards.count()

        if current_count > last_count:
            last_count = current_count
            for i in range(current_count):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    if href and href not in urls and "/maps/place/" in href:
                        urls.append(href)
                except Exception:
                    continue

        # Listeyi aşağı kaydır
        result_list = page.locator('div[role="feed"]')
        if await result_list.count() > 0:
            await result_list.evaluate("el => el.scrollBy(0, 500)")
        else:
            await page.evaluate("window.scrollBy(0, 500)")

        await random_delay(1.5, 2.5)
        scroll_attempts += 1

        if current_count == last_count and scroll_attempts > 5:
            break

    print(f"[Scraper] {len(urls[:max_results])} işletme URL'si bulundu.")
    return urls[:max_results]


async def extract_hours(page: Page) -> dict:
    """Çalışma saatlerini çeker."""
    hours = {}
    try:
        # Saatler genellikle gizlenmiş bir tabloda
        hour_rows = page.locator('table.WgFkxc tr, div[data-hide-tooltip-on-mouse-down] table tr')
        count = await hour_rows.count()
        for i in range(count):
            row = hour_rows.nth(i)
            cells = row.locator("td")
            if await cells.count() >= 2:
                day = (await cells.nth(0).inner_text()).strip()
                time_text = (await cells.nth(1).inner_text()).strip()
                if day:
                    hours[day] = time_text
    except Exception:
        pass
    return hours


async def extract_photos(page: Page, max_photos: int = 5) -> list[str]:
    """Fotoğraf URL'lerini çeker."""
    photos = []
    try:
        # Fotoğraf butonuna tıkla
        photo_btn = page.locator('button[aria-label*="fotoğraf"], button[aria-label*="photo"]')
        if await photo_btn.count() > 0:
            await photo_btn.first.click()
            await random_delay(2, 3)

        img_elements = page.locator('img[src*="googleusercontent.com"]')
        count = min(await img_elements.count(), max_photos)

        for i in range(count):
            src = await img_elements.nth(i).get_attribute("src")
            if src and "googleusercontent.com" in src:
                # Yüksek çözünürlük için URL'yi düzenle
                src = re.sub(r"=w\d+-h\d+", "=w800-h600", src)
                if src not in photos:
                    photos.append(src)

        # Fotoğraf galerisinden geri dön
        back_btn = page.locator('button[aria-label*="geri"], button[aria-label*="back"]')
        if await back_btn.count() > 0:
            await back_btn.first.click()
            await random_delay(1, 2)
    except Exception:
        pass
    return photos[:max_photos]


async def scrape_business_detail(page: Page, url: str) -> Optional[BusinessInfo]:
    """Tek bir işletmenin detay sayfasını çeker."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await random_delay(2, 3)

        info = BusinessInfo()
        info.google_maps_url = url

        # İşletme adı
        name_el = page.locator('h1.DUwDvf, h1[data-attrid="title"]')
        if await name_el.count() > 0:
            info.name = (await name_el.first.inner_text()).strip()

        # Kategori
        cat_el = page.locator('button[jsaction*="category"], div.DkEaL')
        if await cat_el.count() > 0:
            info.category = (await cat_el.first.inner_text()).strip()

        # Adres
        addr_el = page.locator(
            'button[data-item-id="address"], div[data-item-id="address"] div.fontBodyMedium'
        )
        if await addr_el.count() > 0:
            info.address = (await addr_el.first.inner_text()).strip()

        # Telefon
        phone_el = page.locator(
            'button[data-item-id*="phone"], a[data-item-id*="phone"] div.fontBodyMedium'
        )
        if await phone_el.count() > 0:
            info.phone = (await phone_el.first.inner_text()).strip()
            info.phone = re.sub(r"[^\d\+\s\-\(\)]", "", info.phone).strip()

        # Web sitesi - VAR MI kontrol et
        website_el = page.locator(
            'a[data-item-id="authority"], a[aria-label*="web sitesi"], a[aria-label*="website"]'
        )
        if await website_el.count() > 0:
            href = await website_el.first.get_attribute("href")
            if href and not href.startswith("https://www.google.com"):
                info.website = href
                info.has_website = True

        # Rating
        rating_el = page.locator('div.fontDisplayLarge, span.ceNzKf')
        if await rating_el.count() > 0:
            try:
                rating_text = (await rating_el.first.inner_text()).strip().replace(",", ".")
                info.rating = float(rating_text)
            except ValueError:
                pass

        # Yorum sayısı
        review_el = page.locator('button[aria-label*="yorum"], span[aria-label*="yorum"]')
        if await review_el.count() > 0:
            try:
                review_text = await review_el.first.get_attribute("aria-label") or ""
                numbers = re.findall(r"\d+", review_text.replace(".", "").replace(",", ""))
                if numbers:
                    info.review_count = int(numbers[0])
            except Exception:
                pass

        # Çalışma saatleri
        info.hours = await extract_hours(page)

        # Fotoğraflar
        info.photos = await extract_photos(page)

        # Slug oluştur
        info.slug = _make_slug(info.name)

        return info

    except Exception as e:
        print(f"[Scraper] Hata ({url}): {e}")
        return None


def _make_slug(name: str) -> str:
    """URL-uyumlu slug üretir."""
    tr_map = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    slug = name.translate(tr_map).lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


async def find_businesses_without_website(
    query: str,
    location: str = "",
    max_results: int = None,
) -> list[BusinessInfo]:
    """
    Ana fonksiyon: Arama yapar, web sitesi olmayan işletmeleri döner.
    """
    if max_results is None:
        max_results = config.MAX_BUSINESSES

    results = []

    async with async_playwright() as pw:
        browser, context = await setup_browser(pw)
        try:
            page = await context.new_page()

            # İlk arama - daha fazla URL topla (filtreleme için 2x)
            urls = await search_google_maps(page, query, location, max_results * 2)

            print(f"[Scraper] {len(urls)} işletme işlenecek...")

            for i, url in enumerate(urls):
                if len(results) >= max_results:
                    break

                print(f"[Scraper] [{i+1}/{len(urls)}] Detay çekiliyor...")
                info = await scrape_business_detail(page, url)

                if info and info.name:
                    if not info.has_website:
                        results.append(info)
                        print(f"[Scraper] ✓ Web sitesi YOK: {info.name}")
                    else:
                        print(f"[Scraper] ✗ Web sitesi var, atlanıyor: {info.name}")

                await random_delay(config.REQUEST_DELAY, config.REQUEST_DELAY + 1)

        finally:
            await browser.close()

    print(f"\n[Scraper] Tamamlandı. {len(results)} web sitesiz işletme bulundu.")
    return results


def save_businesses_json(businesses: list[BusinessInfo], filepath: str):
    """İşletme listesini JSON dosyasına kaydeder."""
    data = [b.to_dict() for b in businesses]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[Scraper] Kaydedildi: {filepath}")


def load_businesses_json(filepath: str) -> list[BusinessInfo]:
    """JSON dosyasından işletme listesi yükler."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [BusinessInfo(**d) for d in data]
