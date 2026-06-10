"""
Instagram profili ve gönderileri çeker.
Instagram'ın web API'sini kullanır — login/key gerektirmez.
"""

import re
import time
import requests
from dataclasses import dataclass, field


IG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; SM-G998B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "x-ig-app-id": "936619743392459",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
}

DDG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; SM-G998B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9",
}

SKIP_PATHS = {
    "p", "reel", "reels", "explore", "accounts", "stories", "tv",
    "direct", "ar", "challenge", "about", "help", "press",
}


@dataclass
class IGProfile:
    handle: str = ""
    full_name: str = ""
    bio: str = ""
    followers: str = ""
    profile_pic: str = ""
    posts: list = field(default_factory=list)


def find_instagram_handle(name: str, address: str) -> str:
    """DuckDuckGo'da işletmenin Instagram hesabını arar."""
    city = address.split(",")[0].strip() if address else ""
    query = f"{name} {city} instagram"
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "tr-tr"},
            headers=DDG_HEADERS,
            timeout=12,
        )
        matches = re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})', r.text)
        for m in matches:
            if m not in SKIP_PATHS and not m.startswith("."):
                print(f"[Instagram] Bulunan: @{m}")
                return m
    except Exception as e:
        print(f"[Instagram] DDG hata: {e}")
    return ""


def fetch_profile(handle: str, max_posts: int = 12) -> IGProfile:
    """
    Instagram profil bilgisi ve son gönderilerini çeker.
    Login gerektirmez. Instagram web API kullanır.
    """
    if not handle:
        return IGProfile()
    handle = handle.strip().lstrip("@").split("?")[0].rstrip("/")

    # Yöntem 1: Instagram web_profile_info API
    profile = _fetch_web_profile_api(handle, max_posts)
    if profile and (profile.posts or profile.bio):
        return profile

    # Yöntem 2: Instagram sayfasından meta tag parse
    profile = _fetch_meta_tags(handle)
    if profile and profile.full_name:
        return profile

    print(f"[Instagram] @{handle} çekilemedi (gizli hesap veya bağlantı sorunu)")
    return IGProfile(handle=handle)


def _fetch_web_profile_api(handle: str, max_posts: int) -> IGProfile | None:
    """Instagram'ın web profile API'sini kullanır."""
    try:
        url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={handle}"
        r = requests.get(url, headers=IG_HEADERS, timeout=15)

        if r.status_code == 404:
            print(f"[Instagram] @{handle} bulunamadı (404)")
            return None
        if r.status_code in (401, 403):
            print(f"[Instagram] @{handle} erişim engellendi ({r.status_code}), fallback deneniyor...")
            return None

        data = r.json()
        user = data.get("data", {}).get("user") or data.get("user", {})
        if not user:
            return None

        profile = IGProfile(handle=handle)
        profile.full_name  = user.get("full_name", "")
        profile.bio        = user.get("biography", "")
        profile.profile_pic = user.get("profile_pic_url_hd", user.get("profile_pic_url", ""))

        count = user.get("edge_followed_by", {}).get("count", 0)
        profile.followers = _fmt(count)

        edges = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
        for edge in edges[:max_posts]:
            node = edge.get("node", {})
            caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
            caption = caption_edges[0]["node"]["text"] if caption_edges else ""
            shortcode = node.get("shortcode", "")

            # Resim URL — birden fazla sürüm varsa en büyüğü al
            resources = node.get("display_resources", [])
            img_url = resources[-1]["src"] if resources else node.get("display_url", "")

            if img_url:
                profile.posts.append({
                    "url":       img_url,
                    "thumbnail": img_url,
                    "caption":   caption[:200],
                    "likes":     node.get("edge_liked_by", {}).get("count", 0),
                    "shortcode": shortcode,
                    "ig_link":   f"https://www.instagram.com/p/{shortcode}/" if shortcode else "",
                    "is_video":  node.get("is_video", False),
                })

        return profile

    except Exception as e:
        print(f"[Instagram] web_profile_api hata: {e}")
        return None


def _fetch_meta_tags(handle: str) -> IGProfile | None:
    """Instagram sayfasından meta etiketlerini parse eder (fallback)."""
    try:
        r = requests.get(
            f"https://www.instagram.com/{handle}/",
            headers={**IG_HEADERS, "Accept": "text/html,application/xhtml+xml"},
            timeout=15,
        )
        html = r.text

        profile = IGProfile(handle=handle)

        # og:title → "Full Name (@handle)"
        m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if m:
            profile.full_name = m.group(1).split("(")[0].strip()

        # og:description → "N Followers, N Following, N Posts - ..."
        m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if m:
            desc = m.group(1)
            profile.bio = desc
            follower_m = re.search(r'([\d,.]+[KM]?)\s*Followers', desc, re.I)
            if follower_m:
                profile.followers = follower_m.group(1)

        # og:image → profil fotoğrafı
        m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if m:
            profile.profile_pic = m.group(1)

        # Gömülü JSON'dan görseller
        json_matches = re.findall(r'"display_url":"([^"]+)"', html)
        for url in json_matches[:12]:
            url = url.replace("\\u0026", "&")
            profile.posts.append({
                "url": url, "thumbnail": url,
                "caption": "", "likes": 0,
                "shortcode": "", "ig_link": "", "is_video": False,
            })

        return profile if profile.full_name or profile.posts else None

    except Exception as e:
        print(f"[Instagram] meta_tags hata: {e}")
        return None


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
