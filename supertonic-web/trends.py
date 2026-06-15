import json
import time
from pathlib import Path

CACHE_FILE = Path("trends_cache.json")
CACHE_TTL = 6 * 3600  # 6 saat


def _load_cache():
    if CACHE_FILE.exists():
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("ts", 0) < CACHE_TTL:
            return data
    return None


def _save_cache(data: dict):
    data["ts"] = time.time()
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False))


def fetch_youtube_trending(youtube_client, region_code="TR", max_results=10):
    try:
        resp = youtube_client.videos().list(
            part="snippet",
            chart="mostPopular",
            regionCode=region_code,
            maxResults=max_results,
        ).execute()
        items = resp.get("items", [])
        topics = []
        hashtags = set()
        for item in items:
            snippet = item["snippet"]
            topics.append(snippet["title"])
            tags = snippet.get("tags", [])
            hashtags.update(tags[:3])
        return topics, list(hashtags)[:20]
    except Exception:
        return [], []


def fetch_google_trends(region="turkey", lang="tr"):
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl=f"{lang}-TR", tz=180, timeout=(10, 25))
        df = pt.trending_searches(pn=region)
        return df[0].tolist()[:10]
    except Exception:
        return []


def get_trends(youtube_client=None, region_code="TR", lang="tr"):
    cached = _load_cache()
    if cached:
        return cached

    topics = []
    hashtags = []

    # Google Trends
    google = fetch_google_trends(lang=lang)
    topics.extend(google)

    # YouTube Trending (varsa)
    if youtube_client:
        yt_topics, yt_tags = fetch_youtube_trending(youtube_client, region_code)
        topics.extend(yt_topics)
        hashtags.extend(yt_tags)

    # Fallback
    if not topics:
        topics = ["teknoloji", "yapay zeka", "gündem", "spor", "magazin"]

    # Trend hashtagler
    trend_hashtags = list(set(
        [f"#{t.replace(' ', '').lower()}" for t in topics[:5]]
        + hashtags[:10]
        + ["#Shorts", "#keşfet", "#viral", "#trending"]
    ))[:20]

    result = {
        "topics": topics[:15],
        "hashtags": trend_hashtags,
        "region": region_code,
        "lang": lang,
    }
    _save_cache(result)
    return result
