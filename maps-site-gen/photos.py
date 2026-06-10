"""
Ücretsiz stok fotoğraf çekici.

Öncelik:
1. PEXELS_API_KEY varsa → Pexels (kategori bazlı, yüksek kalite)
2. Yoksa → kategori bazlı sabit Unsplash URL'leri (key gerektirmez)
"""

import requests
import config

PEXELS_URL = "https://api.pexels.com/v1/search"

# Kategori → Unsplash koleksiyonu (stabil, key gerektirmez)
UNSPLASH_CATEGORY_PHOTOS = {
    "restoran": [
        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1200",
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1200",
        "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=1200",
    ],
    "kafe": [
        "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=1200",
        "https://images.unsplash.com/photo-1525610553991-2bede1a236e2?w=1200",
        "https://images.unsplash.com/photo-1521017432531-fbd92d768814?w=1200",
    ],
    "berber": [
        "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=1200",
        "https://images.unsplash.com/photo-1599351431613-18ef1fdd27e1?w=1200",
        "https://images.unsplash.com/photo-1585747860715-2ba37e788b70?w=1200",
    ],
    "kuaför": [
        "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=1200",
        "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=1200",
        "https://images.unsplash.com/photo-1493256338651-d82f7acb2b38?w=1200",
    ],
    "eczane": [
        "https://images.unsplash.com/photo-1585435557343-3b092031a831?w=1200",
        "https://images.unsplash.com/photo-1576671081837-49000212a370?w=1200",
    ],
    "market": [
        "https://images.unsplash.com/photo-1542838132-92c53300491e?w=1200",
        "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=1200",
    ],
    "fırın": [
        "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=1200",
        "https://images.unsplash.com/photo-1517433367423-c7e5b0f35086?w=1200",
        "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=1200",
    ],
    "doktor": [
        "https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?w=1200",
        "https://images.unsplash.com/photo-1579684385127-1ef15d508118?w=1200",
    ],
    "otel": [
        "https://images.unsplash.com/photo-1551882547-ff40c63fe5fa?w=1200",
        "https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1200",
        "https://images.unsplash.com/photo-1582719508461-905c673771fd?w=1200",
    ],
    "güzellik": [
        "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=1200",
        "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=1200",
    ],
    "spor": [
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=1200",
        "https://images.unsplash.com/photo-1540497077202-7c8a3999166f?w=1200",
    ],
    "tamirci": [
        "https://images.unsplash.com/photo-1530046339160-ce3e530c7d2f?w=1200",
        "https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?w=1200",
    ],
    "default": [
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1200",
        "https://images.unsplash.com/photo-1497366811353-6870744d04b2?w=1200",
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1200",
    ],
}


def fetch_photos(category: str, name: str = "", count: int = 6) -> list[str]:
    """
    İşletme kategorisine göre fotoğraf URL'leri döner.
    Pexels key varsa Pexels, yoksa Unsplash statiği.
    """
    api_key = config.PEXELS_API_KEY

    if api_key:
        photos = _from_pexels(api_key, category, name, count)
        if photos:
            return photos

    return _from_unsplash(category, count)


def _from_pexels(api_key: str, category: str, name: str, count: int) -> list[str]:
    query = _build_query(category, name)
    try:
        r = requests.get(
            PEXELS_URL,
            headers={"Authorization": api_key},
            params={"query": query, "per_page": count, "orientation": "landscape"},
            timeout=10,
        )
        data = r.json()
        return [p["src"]["large2x"] for p in data.get("photos", [])]
    except Exception as e:
        print(f"[Photos] Pexels hatası: {e}")
        return []


def _from_unsplash(category: str, count: int) -> list[str]:
    cat_lower = category.lower()
    photos = None

    for key, urls in UNSPLASH_CATEGORY_PHOTOS.items():
        if key in cat_lower:
            photos = urls
            break

    if not photos:
        photos = UNSPLASH_CATEGORY_PHOTOS["default"]

    # count kadar döndür (tekrarla gerekirse)
    result = []
    while len(result) < count:
        result.extend(photos)
    return result[:count]


def _build_query(category: str, name: str) -> str:
    cat_map = {
        "restoran": "restaurant interior food",
        "kafe": "coffee cafe interior",
        "berber": "barber shop haircut",
        "kuaför": "hair salon beauty",
        "eczane": "pharmacy drugstore",
        "market": "grocery store supermarket",
        "fırın": "bakery bread fresh",
        "doktor": "doctor clinic medical",
        "otel": "hotel lobby room",
        "güzellik": "beauty salon spa",
        "spor": "gym fitness",
        "tamirci": "auto repair mechanic",
    }
    cat_lower = category.lower()
    for key, query in cat_map.items():
        if key in cat_lower:
            return query
    return f"{category} business interior"
