"""Pexels API — görsel arama ve önbellekli indirme."""

from pathlib import Path
import httpx

_BASE = "https://api.pexels.com/v1"


async def fetch_image(query: str, cache_dir: str, api_key: str, idx: int = 0) -> str | None:
    """Query için Pexels'tan görsel indirir, dosya yolunu döner. Zaten varsa cache'den döner."""
    cache_path = Path(cache_dir) / f"img_{idx:05d}.jpg"
    if cache_path.exists() and cache_path.stat().st_size > 1000:
        return str(cache_path)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_BASE}/search",
                headers={"Authorization": api_key},
                params={"query": query, "per_page": 5, "orientation": "landscape"},
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            if not photos:
                return None

            photo = photos[idx % len(photos)]
            img_url = photo["src"].get("large2x") or photo["src"]["large"]

            img_r = await client.get(img_url, timeout=60.0)
            img_r.raise_for_status()
            cache_path.write_bytes(img_r.content)
            return str(cache_path)
    except Exception:
        return None
