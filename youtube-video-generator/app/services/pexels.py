"""Pexels API üzerinden fotoğraf arar ve indirir."""

from pathlib import Path
from typing import List

import httpx

from app.config import settings

_BASE = "https://api.pexels.com/v1"
_FALLBACK_QUERIES = ["abstract background", "nature landscape", "dark atmosphere"]


async def search_and_download(
    keywords: List[str],
    output_path: str,
    orientation: str = "portrait",  # portrait | landscape
) -> bool:
    """Pexels'tan fotoğraf indirir. Başarı durumuna göre bool döner."""
    if not settings.pexels_api_key:
        raise RuntimeError("PEXELS_API_KEY ayarlanmamış.")

    headers = {"Authorization": settings.pexels_api_key}

    queries_to_try = [
        " ".join(keywords[:3]),   # En iyi 3 keyword birleşik
        keywords[0] if keywords else "nature",  # Sadece ilk keyword
        *_FALLBACK_QUERIES,
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        for query in queries_to_try:
            photos = await _search(client, headers, query, orientation)
            if photos:
                return await _download(client, photos[0], output_path)

    return False


async def _search(
    client: httpx.AsyncClient,
    headers: dict,
    query: str,
    orientation: str,
) -> list:
    try:
        resp = await client.get(
            f"{_BASE}/search",
            headers=headers,
            params={
                "query": query,
                "per_page": 15,
                "orientation": orientation,
                "size": "large",
            },
        )
        resp.raise_for_status()
        return resp.json().get("photos", [])
    except Exception as exc:
        print(f"[Pexels] '{query}' araması başarısız: {exc}")
        return []


async def _download(client: httpx.AsyncClient, photo: dict, output_path: str) -> bool:
    src = photo.get("src", {})
    url = src.get("large2x") or src.get("large") or src.get("original")
    if not url:
        return False
    try:
        resp = await client.get(url, timeout=60)
        resp.raise_for_status()
        Path(output_path).write_bytes(resp.content)
        return True
    except Exception as exc:
        print(f"[Pexels] Fotoğraf indirilemedi: {exc}")
        return False
