"""YouTube Data API v3 ile OAuth2 akışı ve video yükleme."""

from typing import List

from app.config import settings

_CLIENT_CONFIG = {
    "web": {
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _flow():
    from google_auth_oauthlib.flow import Flow

    config = {
        **_CLIENT_CONFIG,
        "web": {
            **_CLIENT_CONFIG["web"],
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "redirect_uris": [settings.youtube_redirect_uri],
        },
    }
    return Flow.from_client_config(
        config, scopes=SCOPES, redirect_uri=settings.youtube_redirect_uri
    )


def get_auth_url() -> str:
    if not settings.youtube_client_id:
        raise RuntimeError("YOUTUBE_CLIENT_ID ayarlanmamış.")
    auth_url, _ = _flow().authorization_url(
        prompt="consent", access_type="offline"
    )
    return auth_url


def exchange_code(code: str) -> dict:
    flow = _flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }


async def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: List[str],
    privacy: str,
    category_id: str,
    credentials: dict,
) -> str:
    """Videoyu YouTube'a yükler, video URL'ini döner."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=credentials["token"],
        refresh_token=credentials["refresh_token"],
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category_id,
            "defaultLanguage": "tr",
        },
        "status": {"privacyStatus": privacy},
    }

    insert_req = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        _, response = insert_req.next_chunk()

    video_id = response["id"]
    return f"https://www.youtube.com/watch?v={video_id}"
