"""
Ücretsiz kaynaklardan viral ürün bulan modül.

Kaynaklar:
1. AliExpress bestseller scraping
2. Reddit (r/BuyItForLife, r/shutupandtakemymoney)
3. Statik viral ürün listesi (fallback)
"""

import requests
import random
import logging
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class Product:
    title: str
    price: str
    image_url: str
    product_url: str
    source: str
    category: str = "general"
    rating: Optional[float] = None
    sold_count: Optional[str] = None


def fetch_aliexpress_trending(category: str = "gadgets") -> list[Product]:
    """AliExpress 'New Arrivals' ve bestseller sayfasını scrape eder."""
    products = []
    urls = [
        "https://www.aliexpress.com/category/3/consumer-electronics.html?SortType=total_tranpro_desc",
        "https://www.aliexpress.com/category/6/phones-telecommunications.html?SortType=total_tranpro_desc",
    ]
    try:
        url = random.choice(urls)
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.select(".list--gallery--C2f2tvm .item--gallery--1Ncs9jq")[:10]:
            title_el = item.select_one(".title--titleWrapper--2UJgoP")
            price_el = item.select_one(".price--currentPriceText--V8_y_b")
            img_el = item.select_one("img")
            link_el = item.select_one("a")

            if not all([title_el, price_el, img_el, link_el]):
                continue

            img_src = img_el.get("src") or img_el.get("data-src", "")
            if img_src.startswith("//"):
                img_src = "https:" + img_src

            products.append(Product(
                title=title_el.get_text(strip=True)[:80],
                price=price_el.get_text(strip=True),
                image_url=img_src,
                product_url="https:" + link_el["href"] if link_el["href"].startswith("//") else link_el["href"],
                source="aliexpress",
                category=category,
            ))
    except Exception as e:
        logger.warning(f"AliExpress scraping hatası: {e}")

    return products


def fetch_reddit_viral_products() -> list[Product]:
    """Reddit'ten viral ürün linkleri çeker (JSON API ile)."""
    products = []
    subreddits = ["BuyItForLife", "shutupandtakemymoney", "malelifestyle"]
    try:
        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
            resp = requests.get(url, headers={"User-Agent": "instagram-bot/1.0"}, timeout=10)
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                p = post["data"]
                # Sadece resim olan gönderiler
                if not p.get("url", "").endswith((".jpg", ".jpeg", ".png")):
                    continue
                if p.get("score", 0) < 100:
                    continue
                products.append(Product(
                    title=p["title"][:80],
                    price="$??",
                    image_url=p["url"],
                    product_url=f"https://reddit.com{p['permalink']}",
                    source=f"reddit/r/{sub}",
                    category="community_pick",
                    rating=None,
                    sold_count=f"{p['score']} upvotes",
                ))
    except Exception as e:
        logger.warning(f"Reddit API hatası: {e}")
    return products


def get_fallback_products() -> list[Product]:
    """Scraping başarısız olursa kullanılan statik ürün listesi."""
    return [
        Product(
            title="Mini Portable Projector - 1080P HD",
            price="$49.99",
            image_url="https://ae01.alicdn.com/kf/S123.jpg",
            product_url="https://www.aliexpress.com",
            source="fallback",
            category="gadgets",
            rating=4.8,
            sold_count="10,000+",
        ),
        Product(
            title="LED Strip Lights 10M RGB Smart",
            price="$12.99",
            image_url="https://ae01.alicdn.com/kf/S456.jpg",
            product_url="https://www.aliexpress.com",
            source="fallback",
            category="home",
            rating=4.7,
            sold_count="50,000+",
        ),
        Product(
            title="Magnetic Phone Holder Car Mount",
            price="$8.99",
            image_url="https://ae01.alicdn.com/kf/S789.jpg",
            product_url="https://www.aliexpress.com",
            source="fallback",
            category="car",
            rating=4.9,
            sold_count="25,000+",
        ),
    ]


def get_viral_products(count: int = 5) -> list[Product]:
    """
    Tüm kaynaklardan viral ürün toplar, karıştırır ve döndürür.
    Hepsi başarısız olursa fallback kullanır.
    """
    all_products: list[Product] = []

    aliexpress = fetch_aliexpress_trending()
    all_products.extend(aliexpress)
    logger.info(f"AliExpress: {len(aliexpress)} ürün")

    reddit = fetch_reddit_viral_products()
    all_products.extend(reddit)
    logger.info(f"Reddit: {len(reddit)} ürün")

    if not all_products:
        logger.warning("Hiç ürün bulunamadı, fallback kullanılıyor")
        all_products = get_fallback_products()

    random.shuffle(all_products)
    return all_products[:count]
