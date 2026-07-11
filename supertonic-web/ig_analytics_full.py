"""
Instagram Graph API — tam analytics çekici.
Mevcut /api/instagram/analytics endpoint'inin çok üstünde:
- Tüm postlar (sayfalandırılmış, limit yok)
- Post başına: views, reach, likes, comments, shares, saved, impressions, total_interactions
- Hashtag listesi (caption'dan parse)
- Hesap günlük istatistikleri (son 30 gün)
- Kitle demografisi: cinsiyet+yaş, şehir, ülke
- Takipçi online saat dağılımı (en iyi paylaşım saatleri)
- Günlük takipçi değişimi
"""

import re
import json
import time
import httpx
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone

GRAPH = "https://graph.facebook.com/v21.0"
CACHE_FILE = Path("ig_analytics_cache.json")
CACHE_TTL = 3600  # 1 saat — aynı veriye tekrar istek atmaz


def _parse_hashtags(caption: str) -> list[str]:
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


def _insight_value(data: list, name: str) -> int:
    for item in data:
        if item.get("name") == name:
            v = item.get("value") or (item.get("values") or [{}])[0].get("value", 0)
            return v if isinstance(v, (int, float)) else 0
    return 0


async def _fetch_all_media(uid: str, token: str, client: httpx.AsyncClient) -> list:
    """Tüm medyayı sayfalandırarak çeker."""
    posts = []
    fields = (
        "id,caption,media_type,timestamp,like_count,comments_count,"
        "permalink,thumbnail_url,media_url,views"
    )
    url = f"{GRAPH}/{uid}/media"
    params = {"fields": fields, "limit": 100, "access_token": token}

    while True:
        try:
            r = await client.get(url, params=params, timeout=20)
        except Exception:
            break
        if r.status_code != 200:
            break
        body = r.json()
        posts.extend(body.get("data", []))
        nxt = body.get("paging", {}).get("next")
        if not nxt:
            break
        url = nxt
        params = {}

    return posts


async def _fetch_media_insights(media_id: str, media_type: str, token: str, client: httpx.AsyncClient) -> dict:
    """Post başına tüm metrikler."""
    # likes ve comments insights metriği değil, media object field'ı — bunlar 400 hatası çıkarır
    if media_type in ("VIDEO", "REEL"):
        metrics = "views,reach,shares,saved,total_interactions,impressions"
    else:
        metrics = "impressions,reach,saved,total_interactions"

    try:
        r = await client.get(
            f"{GRAPH}/{media_id}/insights",
            params={"metric": metrics, "period": "lifetime", "access_token": token},
            timeout=15,
        )
        if r.status_code == 200:
            items = r.json().get("data", [])
            result = {}
            for item in items:
                if "total_value" in item:
                    val = item["total_value"].get("value", 0)
                elif "value" in item:
                    val = item["value"] or 0
                elif "values" in item:
                    val = item["values"][0].get("value", 0) if item.get("values") else 0
                else:
                    val = 0
                result[item["name"]] = val if isinstance(val, (int, float)) else 0
            return result
    except Exception:
        pass
    return {}


async def _fetch_account_daily(uid: str, token: str, client: httpx.AsyncClient) -> dict:
    """Son 30 günlük hesap metrikleri (gün gün)."""
    since = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    until = int(datetime.now(timezone.utc).timestamp())
    metrics = ["reach", "impressions", "follower_count", "profile_views", "website_clicks"]
    result = {}

    for metric in metrics:
        try:
            r = await client.get(
                f"{GRAPH}/{uid}/insights",
                params={
                    "metric": metric,
                    "period": "day",
                    "since": since,
                    "until": until,
                    "access_token": token,
                },
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    result[metric] = data[0].get("values", [])
        except Exception:
            pass

    return result


async def _fetch_demographics(uid: str, token: str, client: httpx.AsyncClient) -> dict:
    """Cinsiyet+yaş, şehir, ülke dağılımı."""
    result = {}
    metrics = ["audience_gender_age", "audience_city", "audience_country"]

    for metric in metrics:
        try:
            r = await client.get(
                f"{GRAPH}/{uid}/insights",
                params={"metric": metric, "period": "lifetime", "access_token": token},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    val = (data[0].get("values") or [{}])[0].get("value", {})
                    result[metric] = val
            elif r.status_code != 400:
                result[f"{metric}_error"] = r.text[:100]
        except Exception as e:
            result[f"{metric}_error"] = str(e)

    return result


async def _fetch_online_followers(uid: str, token: str, client: httpx.AsyncClient) -> dict:
    """Takipçilerin gün+saat bazında aktiflik haritası (en iyi paylaşım saatleri)."""
    try:
        r = await client.get(
            f"{GRAPH}/{uid}/insights",
            params={"metric": "online_followers", "period": "lifetime", "access_token": token},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return (data[0].get("values") or [{}])[0].get("value", {})
    except Exception:
        pass
    return {}


async def _fetch_follower_daily(uid: str, token: str, client: httpx.AsyncClient) -> list:
    """Son 30 gün günlük takipçi değişimi."""
    since = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
    until = int(datetime.now(timezone.utc).timestamp())
    try:
        r = await client.get(
            f"{GRAPH}/{uid}/insights",
            params={
                "metric": "follower_count",
                "period": "day",
                "since": since,
                "until": until,
                "access_token": token,
            },
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return data[0].get("values", [])
    except Exception:
        pass
    return []


async def fetch_full_analytics(uid: str, token: str, force: bool = False) -> dict:
    """
    Tüm Instagram verilerini çeker. Cache TTL dolmadıysa dosyadan döner.
    force=True ile cache'i yoksay.
    """
    if not force and CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text())
            if time.time() - cached.get("fetched_at", 0) < CACHE_TTL:
                return cached
        except Exception:
            pass

    result: dict = {"fetched_at": time.time(), "uid": uid}

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Profil
        try:
            rp = await client.get(
                f"{GRAPH}/{uid}",
                params={
                    "fields": "username,followers_count,media_count,biography",
                    "access_token": token,
                },
                timeout=15,
            )
            result["profile"] = rp.json() if rp.status_code == 200 else {}
        except Exception:
            result["profile"] = {}

        # 2. Tüm postlar
        posts = await _fetch_all_media(uid, token, client)
        result["total_posts"] = len(posts)

        # 3. Her post için insights + hashtag parse (eşzamanlı, 10'ar batch)
        enriched = []
        for i in range(0, len(posts), 10):
            batch = posts[i:i + 10]
            tasks = [
                _fetch_media_insights(p["id"], p.get("media_type", "VIDEO"), token, client)
                for p in batch
            ]
            insights_list = await asyncio.gather(*tasks, return_exceptions=True)

            for p, ins in zip(batch, insights_list):
                if isinstance(ins, Exception):
                    ins = {}
                caption = p.get("caption", "") or ""
                enriched.append({
                    "id": p["id"],
                    "type": p.get("media_type"),
                    "caption": caption[:200],
                    "hashtags": _parse_hashtags(caption),
                    "timestamp": p.get("timestamp"),
                    "permalink": p.get("permalink"),
                    "thumbnail": p.get("thumbnail_url") or p.get("media_url"),
                    "likes": ins.get("likes", p.get("like_count", 0)),
                    "comments": ins.get("comments", p.get("comments_count", 0)),
                    "views": ins.get("views") or p.get("views") or 0,
                    "reach": ins.get("reach", 0),
                    "impressions": ins.get("impressions", 0),
                    "shares": ins.get("shares", 0),
                    "saved": ins.get("saved", 0),
                    "total_interactions": ins.get("total_interactions", 0),
                })

        result["posts"] = enriched

        # 4. Hesap günlük istatistikleri
        result["account_daily"] = await _fetch_account_daily(uid, token, client)

        # 5. Demografik veriler
        result["demographics"] = await _fetch_demographics(uid, token, client)

        # 6. Online follower saatleri
        result["online_followers_by_hour"] = await _fetch_online_followers(uid, token, client)

        # 7. Günlük takipçi değişimi
        result["follower_daily"] = await _fetch_follower_daily(uid, token, client)

    # 8. Özet istatistikler
    if enriched:
        views_list = [p["views"] for p in enriched]
        shares_list = [p["shares"] for p in enriched]
        result["summary"] = {
            "total_views": sum(views_list),
            "avg_views": round(sum(views_list) / len(views_list)),
            "max_views": max(views_list),
            "total_shares": sum(shares_list),
            "total_saved": sum(p["saved"] for p in enriched),
            "total_likes": sum(p["likes"] for p in enriched),
            "total_comments": sum(p["comments"] for p in enriched),
            "top_posts": sorted(enriched, key=lambda x: x["views"], reverse=True)[:5],
        }
    else:
        result["summary"] = {}

    CACHE_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
