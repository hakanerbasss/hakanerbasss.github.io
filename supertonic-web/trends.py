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
                title = title.rsplit(" - ", 1)[0].strip()
            if title:
                titles.append(title)
            if len(titles) >= max_items:
                break
        return titles
    except Exception:
        return []


def fetch_youtube_trending(youtube_client, region_code="TR", max_results=25):
    """YouTube trending videolarından frekans bazlı popüler hashtag'leri çeker."""
    try:
        resp = youtube_client.videos().list(
            part="snippet",
            chart="mostPopular",
            regionCode=region_code,
            maxResults=max_results,
        ).execute()

        titles = []
        tag_count = {}

        for item in resp.get("items", []):
            snippet = item["snippet"]
            titles.append(snippet["title"])
            for tag in snippet.get("tags", []):
                tag = tag.strip()
                # Çok kısa veya çok uzun tag'leri atla
                if not tag or len(tag) < 2 or len(tag) > 40:
                    continue
                key = tag.lower()
                tag_count[key] = tag_count.get(key, 0) + 1

        # Frekansa göre sırala — birden fazla videoda geçen tag'ler en popüler
        sorted_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)

        # Hashtag formatına çevir: boşlukları kaldır, # ekle
        top_hashtags = []
        for tag, _ in sorted_tags[:25]:
            ht = "#" + tag.replace(" ", "").replace("-", "")
            if ht not in top_hashtags:
                top_hashtags.append(ht)

        return titles, top_hashtags[:20]
    except Exception:
        return [], []


def get_trends(youtube_client=None, region_code="TR", lang="tr"):
    cached = _load_cache()
    if cached:
        return cached

    # Google News haberleri
    news_topics = fetch_google_news(lang=lang, region=region_code)

    # YouTube trending (varsa)
    yt_topics, yt_hashtags = [], []
    if youtube_client:
        yt_topics, yt_hashtags = fetch_youtube_trending(youtube_client, region_code)

    topics = news_topics + yt_topics

    if not topics:
        topics = ["gündem haberleri", "teknoloji gelişmeleri", "ekonomi"]

    # YouTube trending hashtag'leri + genel hashtag'ler
    base = ["#Shorts", "#keşfet", "#viral", "#trending", "#gündem"]
    # YouTube trending tag'leri öne al — daha değerli
    trend_hashtags = list(dict.fromkeys(yt_hashtags + base))[:20]

    result = {
        "topics": topics[:30],
        "hashtags": trend_hashtags,          # prompt'a giden liste
        "yt_trending_tags": yt_hashtags,     # sadece YouTube kaynaklılar
        "region": region_code,
        "lang": lang,
    }
    _save_cache(result)
    return result
