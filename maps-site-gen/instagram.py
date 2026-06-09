"""
Instagram'dan işletme içeriği çeker (instaloader ile).
Giriş gerektirmeyen public profiller için çalışır.
"""

import os
import json
import re
from dataclasses import dataclass, field


@dataclass
class InstagramProfile:
    handle: str = ""
    full_name: str = ""
    bio: str = ""
    followers: str = ""
    profile_pic_url: str = ""
    posts: list = field(default_factory=list)   # [{url, caption, likes}]
    highlights: list = field(default_factory=list)


def fetch_profile(handle: str, max_posts: int = 9) -> InstagramProfile:
    """Instagram profilini çeker. Başarısız olursa boş döner."""
    if not handle:
        return InstagramProfile()

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
        )
        profile = instaloader.Profile.from_username(L.context, handle)

        posts = []
        for post in profile.get_posts():
            if len(posts) >= max_posts:
                break
            try:
                posts.append({
                    "url": post.url,         # Resim/video URL
                    "caption": (post.caption or "")[:200],
                    "likes": post.likes,
                    "shortcode": post.shortcode,
                    "ig_link": f"https://www.instagram.com/p/{post.shortcode}/",
                    "is_video": post.is_video,
                    "thumbnail": post.url if not post.is_video else "",
                })
            except Exception:
                continue

        return InstagramProfile(
            handle=handle,
            full_name=profile.full_name or "",
            bio=profile.biography or "",
            followers=_fmt_number(profile.followers),
            profile_pic_url=profile.profile_pic_url or "",
            posts=posts,
        )

    except Exception as e:
        print(f"[Instagram] @{handle} çekilemedi: {e}")
        return InstagramProfile(handle=handle)


def _fmt_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
