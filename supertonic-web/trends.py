import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

CACHE_FILE = Path("trends_cache.json")
CACHE_TTL = 3600  # 1 saat


def _load_cache():
    if CACHE_FILE.exists():
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("ts", 0) < CACHE_TTL:
            return data
    return None


def _save_cache(data: dict):
    data["ts"] = time.time()
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False))


def fetch_google_news(lang="tr", region="TR", max_items=20):
    """Google News RSS'den güncel haber başlıklarını çeker."""
    url = f"https://news.google.com/rss?hl={lang}&gl={region}&ceid={region}:{lang}"
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.text)
        titles = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            if title and " - " in title:
                # "Haber başlığı - Kaynak Adı" formatından sadece başlığı al
                title = title.rsplit(" - ", 1)[0].strip()
            if title:
                titles.append(title)
            if len(titles) >= max_items:
                break
        return titles
    except Exception:
        return []


def fetch_youtube_trending(youtube_client, region_code="TR", max_results=10):
    try:
        resp = youtube_client.videos().list(
            part="snippet",
            chart="mostPopular",
            regionCode=region_code,
            maxResults=max_results,
        ).execute()
        titles = [item["snippet"]["title"] for item in resp.get("items", [])]
        tags = []
        for item in resp.get("items", []):
            tags.extend(item["snippet"].get("tags", [])[:2])
        return titles, list(set(tags))[:15]
    except Exception:
        return [], []


def get_trends(youtube_client=None, region_code="TR", lang="tr"):
    cached = _load_cache()
    if cached:
        return cached

    # Google News haberleri
    news_topics = fetch_google_news(lang=lang, region=region_code)

    # YouTube trending (varsa)
    yt_topics, yt_tags = [], []
    if youtube_client:
        yt_topics, yt_tags = fetch_youtube_trending(youtube_client, region_code)

    topics = news_topics + yt_topics

    # Fallback
    if not topics:
        topics = ["gündem haberleri", "teknoloji gelişmeleri", "ekonomi"]

    trend_hashtags = list(set(
        ["#Shorts", "#keşfet", "#viral", "#trending", "#gündem"]
        + [f"#{t.split()[0].lower()}" for t in yt_tags[:5] if t]
    ))[:15]

    result = {
        "topics": topics[:20],
        "hashtags": trend_hashtags,
        "region": region_code,
        "lang": lang,
    }
    _save_cache(result)
    return result
