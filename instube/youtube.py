"""YouTube OAuth ve video yükleme — bağımsız, kendi token dosyalarını kullanır."""
import json
import re

from config import (SCOPES, OUTPUT_DIR, THUMB_DIR, YT_CONFIG_FILE,
                    YT_TOKEN_FILE, YT_TOKEN_FILE_EN)


def load_yt_config() -> dict:
    if YT_CONFIG_FILE.exists():
        return json.loads(YT_CONFIG_FILE.read_text())
    return {}


def save_yt_config(client_id: str, client_secret: str) -> None:
    YT_CONFIG_FILE.write_text(json.dumps({"client_id": client_id, "client_secret": client_secret}))


def yt_status() -> dict:
    return {
        "configured": bool(load_yt_config()),
        "authorized_tr": YT_TOKEN_FILE.exists(),
        "authorized_en": YT_TOKEN_FILE_EN.exists(),
    }


def build_flow(cfg: dict, redirect_uri: str):
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(
        {"web": {"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                 "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                 "token_uri": "https://oauth2.googleapis.com/token",
                 "redirect_uris": [redirect_uri]}},
        scopes=SCOPES, redirect_uri=redirect_uri,
    )


def upload_video(filename: str, title: str, description: str = "", tags: str = "",
                 privacy: str = "public", channel: str = "tr",
                 thumbnail: str = "", category_id: str = "25") -> dict:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GRequest
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_file = YT_TOKEN_FILE_EN if channel == "en" else YT_TOKEN_FILE
    if not token_file.exists():
        raise RuntimeError("YouTube hesabı bağlı değil (Ayarlar'dan yetkilendir)")
    video_path = OUTPUT_DIR / filename
    if not video_path.exists():
        raise RuntimeError("Video bulunamadı")

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GRequest())
        token_file.write_text(creds.to_json())
    youtube = build("youtube", "v3", credentials=creds)

    tag_list = [t.lstrip("#").strip() for t in re.split(r"[\s,]+", tags) if t.strip().lstrip("#")]
    if "Shorts" not in tag_list:
        tag_list.insert(0, "Shorts")
    hashtag_str = " ".join(f"#{t}" if not t.startswith("#") else t for t in tag_list)
    full_description = f"{description}\n\n{hashtag_str}".strip() if description else hashtag_str

    body = {
        "snippet": {"title": title[:100], "description": full_description[:5000],
                    "tags": tag_list[:500], "categoryId": category_id},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = req.next_chunk()
    video_id = response["id"]

    if thumbnail:
        thumb_path = THUMB_DIR / thumbnail
        if thumb_path.exists():
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
                ).execute()
            except Exception:
                pass

    return {"youtube_id": video_id, "url": f"https://youtu.be/{video_id}"}
