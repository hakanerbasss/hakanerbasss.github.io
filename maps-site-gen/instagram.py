"""
İşletme için Instagram hesabı bulur ve gerçek içerik çeker.
"""

import re
import time
import requests
from dataclasses import dataclass, field


HEADERS = {
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


def find_instagram_handle(name: str, address: str) -> str:
    """
    İşletmenin Instagram hesabını DuckDuckGo'da arar.
    Bulamazsa "" döner.
    """
    city = address.split(",")[0].strip() if address else ""
    query = f"{name} {city} instagram"

    # DuckDuckGo HTML (bot-dostu, key gerektirmez)
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query, "kl": "tr-tr"},
            headers=HEADERS,
            timeout=12,
        )
        matches = re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})', r.text)
        for m in matches:
            if m not in SKIP_PATHS and not m.startswith("."):
                print(f"[Instagram] '{name}' için bulunan: @{m}")
                return m
    except Exception as e:
        print(f"[Instagram] DuckDuckGo arama hatası: {e}")

    return ""


@dataclass
class IGProfile:
    handle: str = ""
    full_name: str = ""
    bio: str = ""
    followers: str = ""
    profile_pic: str = ""
    posts: list = field(default_factory=list)
    # posts: [{url, thumbnail, caption, ig_link, likes}]


def fetch_profile(handle: str, max_posts: int = 12) -> IGProfile:
    """Instagram profilini çeker (instaloader ile)."""
    if not handle:
        return IGProfile()
    handle = handle.strip().lstrip("@")

    try:
        import instaloader
        L = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            quiet=True,
            request_timeout=15,
        )
        profile = instaloader.Profile.from_username(L.context, handle)

        posts = []
        for post in profile.get_posts():
            if len(posts) >= max_posts:
                break
            try:
                posts.append({
                    "url":       post.url,
                    "thumbnail": post.url,
                    "caption":   (post.caption or "")[:200],
                    "likes":     post.likes,
                    "shortcode": post.shortcode,
                    "ig_link":   f"https://www.instagram.com/p/{post.shortcode}/",
                    "is_video":  post.is_video,
                })
            except Exception:
                continue

        return IGProfile(
            handle=handle,
            full_name=profile.full_name or "",
            bio=profile.biography or "",
            followers=_fmt(profile.followers),
            profile_pic=profile.profile_pic_url or "",
            posts=posts,
        )

    except Exception as e:
        print(f"[Instagram] @{handle} çekilemedi: {e}")
        return IGProfile(handle=handle)


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
