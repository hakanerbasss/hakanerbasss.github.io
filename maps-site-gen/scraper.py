"""
Requests tabanlı scraper — tarayıcı/Playwright gerektirmez.
Termux dahil her yerde çalışır.

Mod 1 (GOOGLE_PLACES_API_KEY varsa): Google Places API — tam veri
Mod 2 (key yoksa): Overpass API (OpenStreetMap) — ücretsiz, key gerektirmez
"""

import os
import re
import json
import time
import random
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional
import config


@dataclass
class BusinessInfo:
    name: str = ""
    category: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    has_website: bool = False
    slug: str = ""
    google_maps_url: str = ""
    rating: float = 0.0
    review_count: int = 0
    reviews_snippet: list = field(default_factory=list)
    hours: dict = field(default_factory=dict)
    is_open_now: bool = False
    photos: list = field(default_factory=list)
    cover_photo: str = ""
    instagram_handle: str = ""
    facebook_url: str = ""
    instagram_posts: list = field(default_factory=list)
    instagram_bio: str = ""
    instagram_followers: str = ""
    services: list = field(default_factory=list)
    about: str = ""
    place_id: str = ""

    def to_dict(self):
        return asdict(self)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; SM-G998B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PLACES_SEARCH = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAIL = "https://maps.googleapis.com/maps/api/place/details/json"
PLACES_PHOTO  = "https://maps.googleapis.com/maps/api/place/photo"
OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


# ─── GOOGLE PLACES API ────────────────────────────────────────────

def _places_search(query: str, location: str, api_key: str, page_token: str = None) -> dict:
    params = {
        "query": f"{query} {location}".strip(),
        "key": api_key,
        "language": "tr",
        "region": "tr",
    }
    if page_token:
        params["pagetoken"] = page_token
    r = requests.get(PLACES_SEARCH, params=params, headers=HEADERS, timeout=15)
    return r.json()


def _places_detail(place_id: str, api_key: str) -> dict:
    fields = (
        "name,formatted_address,formatted_phone_number,website,"
        "rating,user_ratings_total,opening_hours,types,"
        "photos,reviews,url,place_id"
    )
    r = requests.get(
        PLACES_DETAIL,
        params={"place_id": place_id, "key": api_key, "language": "tr", "fields": fields},
        headers=HEADERS,
        timeout=15,
    )
    return r.json().get("result", {})


def _photo_url(photo_ref: str, api_key: str, max_width: int = 1200) -> str:
    return (
        f"{PLACES_PHOTO}?maxwidth={max_width}"
        f"&photo_reference={photo_ref}&key={api_key}"
    )


def _parse_hours(opening_hours: dict) -> dict:
    days_tr = {
        "Monday": "Pazartesi", "Tuesday": "Salı", "Wednesday": "Çarşamba",
        "Thursday": "Perşembe", "Friday": "Cuma",
        "Saturday": "Cumartesi", "Sunday": "Pazar",
    }
    hours = {}
    for period_text in opening_hours.get("weekday_text", []):
        # "Monday: 09:00 – 22:00" formatı
        parts = period_text.split(": ", 1)
        if len(parts) == 2:
            day_en, time_str = parts
            day_tr = days_tr.get(day_en.strip(), day_en.strip())
            hours[day_tr] = time_str.strip()
    return hours


def scrape_with_places_api(
    query: str,
    location: str,
    max_results: int,
    api_key: str,
    progress_cb=None,
) -> list[BusinessInfo]:
    results = []
    page_token = None
    all_place_ids = []

    # Arama yap (sayfalama ile)
    for _ in range(3):  # max 3 sayfa = 60 sonuç
        data = _places_search(query, location, api_key, page_token)
        for p in data.get("results", []):
            all_place_ids.append(p["place_id"])
        page_token = data.get("next_page_token")
        if not page_token or len(all_place_ids) >= max_results * 2:
            break
        time.sleep(2)  # next_page_token geçerli olana kadar bekle

    print(f"[Scraper] {len(all_place_ids)} işletme bulundu, web sitesi kontrolü...")

    for i, pid in enumerate(all_place_ids):
        if len(results) >= max_results:
            break

        detail = _places_detail(pid, api_key)
        if not detail:
            continue

        b = BusinessInfo()
        b.name = detail.get("name", "")
        b.place_id = pid
        b.address = detail.get("formatted_address", "")
        b.phone = detail.get("formatted_phone_number", "")
        b.website = detail.get("website", "")
        b.has_website = bool(b.website)
        b.rating = float(detail.get("rating", 0))
        b.review_count = detail.get("user_ratings_total", 0)
        b.google_maps_url = detail.get("url", "")

        types = detail.get("types", [])
        b.category = _type_to_tr(types[0] if types else "")

        oh = detail.get("opening_hours", {})
        b.hours = _parse_hours(oh)
        b.is_open_now = oh.get("open_now", False)

        # Reviews
        for rev in detail.get("reviews", [])[:4]:
            text = rev.get("text", "")
            if text and len(text) > 20:
                b.reviews_snippet.append(text[:200])

        # Fotoğraflar
        for photo in detail.get("photos", [])[:9]:
            ref = photo.get("photo_reference", "")
            if ref:
                b.photos.append(_photo_url(ref, api_key))
        if b.photos:
            b.cover_photo = b.photos[0]

        b.slug = _make_slug(b.name)

        if progress_cb:
            progress_cb(i + 1, len(all_place_ids), b.name)

        if not b.has_website and b.name:
            results.append(b)
            print(f"[Scraper] ✓ {b.name} — {b.phone}")
        else:
            print(f"[Scraper] ✗ Web sitesi var: {b.name}")

        time.sleep(0.3)  # API rate limit

    return results


# ─── OVERPASS API (ücretsiz, key gerektirmez) ─────────────────────

OSM_TYPE_MAP = {
    "restaurant": "Restoran", "cafe": "Kafe", "bar": "Bar",
    "fast_food": "Hızlı Yemek", "bakery": "Fırın", "pharmacy": "Eczane",
    "hospital": "Hastane", "clinic": "Klinik", "dentist": "Diş Hekimi",
    "doctor": "Doktor", "hairdresser": "Kuaför", "barber": "Berber",
    "beauty_salon": "Güzellik Salonu", "supermarket": "Süpermarket",
    "convenience": "Market", "butcher": "Kasap", "bakehouse": "Fırın",
    "florist": "Çiçekçi", "clothes": "Giyim", "shoes": "Ayakkabı",
    "hardware": "Hırdavat", "electronics": "Elektronik",
    "car_repair": "Oto Tamiri", "fuel": "Akaryakıt",
    "hotel": "Otel", "hostel": "Hostel", "guest_house": "Pansiyon",
    "gym": "Spor Salonu", "laundry": "Çamaşırhane",
    "optician": "Optik", "jewelry": "Kuyumcu",
    "books": "Kitapçı", "stationery": "Kırtasiye",
    "dry_cleaning": "Kuru Temizleyici", "tailor": "Terzi",
}

QUERY_TO_OSM = {
    "restoran": [("amenity", "restaurant")],
    "kafe": [("amenity", "cafe")],
    "berber": [("shop", "barber")],
    "kuaför": [("shop", "hairdresser")],
    "eczane": [("amenity", "pharmacy")],
    "market": [("shop", "convenience"), ("shop", "supermarket")],
    "fırın": [("shop", "bakery")],
    "doktor": [("amenity", "doctors"), ("amenity", "clinic")],
    "otel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "güzellik": [("shop", "beauty")],
    "spor": [("leisure", "fitness_centre")],
    "tamirci": [("shop", "car_repair")],
}


def _geocode_location(location: str) -> Optional[tuple[float, float]]:
    """Konum adını lat/lon'a çevirir."""
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": location, "format": "json", "limit": 1, "countrycodes": "tr"},
            headers={"User-Agent": "maps-site-gen/1.0"},
            timeout=10,
        )
        results = r.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"[Geocode] Hata: {e}")
    return None


def _overpass_query(tag_key: str, tag_val: str, lat: float, lon: float, radius: int = 3000) -> list[dict]:
    """Overpass API ile OSM veritabanında işletme arar."""
    query = f"""
[out:json][timeout:25];
(
  node["{tag_key}"="{tag_val}"][!"website"](around:{radius},{lat},{lon});
  way["{tag_key}"="{tag_val}"][!"website"](around:{radius},{lat},{lon});
);
out body center;
"""
    try:
        r = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
        return r.json().get("elements", [])
    except Exception as e:
        print(f"[Overpass] Hata: {e}")
        return []


def _osm_element_to_business(el: dict) -> Optional[BusinessInfo]:
    tags = el.get("tags", {})
    name = tags.get("name", "")
    if not name:
        return None

    b = BusinessInfo()
    b.name = name
    b.phone = tags.get("phone", tags.get("contact:phone", ""))
    b.website = tags.get("website", tags.get("contact:website", ""))
    b.has_website = bool(b.website)
    b.email = tags.get("email", tags.get("contact:email", ""))
    b.instagram_handle = _extract_ig(tags.get("contact:instagram", ""))
    b.facebook_url = tags.get("contact:facebook", "")

    # Adres
    addr_parts = [
        tags.get("addr:street", ""),
        tags.get("addr:housenumber", ""),
        tags.get("addr:district", ""),
        tags.get("addr:city", ""),
    ]
    b.address = ", ".join(p for p in addr_parts if p)

    # Kategori
    for key in ("amenity", "shop", "tourism", "leisure"):
        val = tags.get(key, "")
        if val:
            b.category = OSM_TYPE_MAP.get(val, val.replace("_", " ").title())
            break

    # Saatler
    oh = tags.get("opening_hours", "")
    if oh:
        b.hours = _parse_osm_hours(oh)

    b.slug = _make_slug(b.name)

    # Google Maps linki
    lat = el.get("lat") or el.get("center", {}).get("lat", "")
    lon = el.get("lon") or el.get("center", {}).get("lon", "")
    if lat and lon:
        b.google_maps_url = f"https://www.google.com/maps?q={lat},{lon}"

    return b


def _extract_ig(val: str) -> str:
    if not val:
        return ""
    match = re.search(r'instagram\.com/([^/?&\s]+)', val)
    if match:
        return match.group(1)
    if val.startswith("@"):
        return val[1:]
    return val


def _parse_osm_hours(oh_str: str) -> dict:
    """OSM opening_hours formatını dict'e çevirir."""
    days_map = {
        "Mo": "Pazartesi", "Tu": "Salı", "We": "Çarşamba",
        "Th": "Perşembe", "Fr": "Cuma", "Sa": "Cumartesi", "Su": "Pazar",
        "PH": "Resmi Tatil",
    }
    result = {}
    for rule in oh_str.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        # "Mo-Fr 09:00-18:00" veya "Sa,Su 10:00-16:00"
        parts = rule.split(" ", 1)
        if len(parts) == 2:
            days_raw, times = parts
            # Gün aralığı
            day_labels = []
            for d in re.split(r"[,\-]", days_raw):
                d = d.strip()
                day_labels.append(days_map.get(d, d))
            if "-" in days_raw and len(day_labels) == 2:
                result[f"{day_labels[0]}-{day_labels[1]}"] = times.strip()
            else:
                for dl in day_labels:
                    result[dl] = times.strip()
    return result


def scrape_with_overpass(
    query: str,
    location: str,
    max_results: int,
    progress_cb=None,
) -> list[BusinessInfo]:
    """Overpass API ile OSM'den web sitesiz işletme bulur."""

    # Konum → lat/lon
    coords = _geocode_location(location) if location else None
    if not coords:
        # Varsayılan: İstanbul merkezi
        coords = (41.0082, 28.9784)
        print(f"[Scraper] Konum bulunamadı, İstanbul merkezi kullanılıyor.")
    lat, lon = coords
    print(f"[Scraper] Koordinat: {lat:.4f}, {lon:.4f}")

    # Query'ye göre OSM tag'lerini bul
    query_lower = query.lower()
    osm_tags = None
    for key, tags in QUERY_TO_OSM.items():
        if key in query_lower:
            osm_tags = tags
            break
    if not osm_tags:
        # Genel arama: hem amenity hem shop dene
        osm_tags = [("amenity", query_lower), ("shop", query_lower)]

    elements = []
    for tag_key, tag_val in osm_tags:
        found = _overpass_query(tag_key, tag_val, lat, lon)
        elements.extend(found)
        if len(elements) >= max_results * 2:
            break

    print(f"[Scraper] Overpass: {len(elements)} sonuç (web sitesiz filtresi uygulandı)")

    results = []
    for i, el in enumerate(elements):
        if len(results) >= max_results:
            break
        b = _osm_element_to_business(el)
        if b and b.name and not b.has_website:
            # Fotoğraf yoksa stok fotoğraf ekle
            if not b.photos:
                try:
                    from photos import fetch_photos
                    b.photos = fetch_photos(b.category, b.name, 6)
                    b.cover_photo = b.photos[0] if b.photos else ""
                except Exception:
                    pass
            results.append(b)
            if progress_cb:
                progress_cb(i + 1, len(elements), b.name)
            print(f"[Scraper] ✓ {b.name} — {b.phone or 'telefon yok'}")

    return results


# ─── ANA FONKSİYON ────────────────────────────────────────────────

def find_businesses_without_website(
    query: str,
    location: str = "",
    max_results: int = None,
    progress_cb=None,
) -> list[BusinessInfo]:
    """
    Otomatik mod seçimi:
    - GOOGLE_PLACES_API_KEY varsa → Google Places API (tam veri)
    - Yoksa → Overpass/OSM API (ücretsiz, key gerektirmez)
    """
    if max_results is None:
        max_results = config.MAX_BUSINESSES

    api_key = config.GOOGLE_PLACES_API_KEY

    if api_key:
        print(f"[Scraper] Mod: Google Places API")
        return scrape_with_places_api(query, location, max_results, api_key, progress_cb)
    else:
        print(f"[Scraper] Mod: Overpass/OpenStreetMap (key yok)")
        return scrape_with_overpass(query, location, max_results, progress_cb)


# ─── YARDIMCI ─────────────────────────────────────────────────────

GOOGLE_TYPE_MAP = {
    "restaurant": "Restoran", "food": "Yemek", "cafe": "Kafe",
    "bar": "Bar", "bakery": "Fırın", "pharmacy": "Eczane",
    "hospital": "Hastane", "doctor": "Doktor", "dentist": "Diş Hekimi",
    "hair_care": "Kuaför", "beauty_salon": "Güzellik", "spa": "Spa",
    "grocery_or_supermarket": "Market", "store": "Mağaza",
    "car_repair": "Oto Tamir", "clothing_store": "Giyim",
    "electronics_store": "Elektronik", "shoe_store": "Ayakkabı",
    "jewelry_store": "Kuyumcu", "book_store": "Kitapçı",
    "gym": "Spor Salonu", "laundry": "Çamaşırhane",
    "lodging": "Konaklama", "hotel": "Otel",
}


def _type_to_tr(type_str: str) -> str:
    return GOOGLE_TYPE_MAP.get(type_str, type_str.replace("_", " ").title())


def _make_slug(name: str) -> str:
    tr = str.maketrans("ğüşıöçĞÜŞİÖÇ", "gusiocGUSIOC")
    s = name.translate(tr).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "isletme"


def save_json(businesses: list[BusinessInfo], path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([b.to_dict() for b in businesses], f, ensure_ascii=False, indent=2)


def load_json(path: str) -> list[BusinessInfo]:
    with open(path, "r", encoding="utf-8") as f:
        return [BusinessInfo(**d) for d in json.load(f)]
