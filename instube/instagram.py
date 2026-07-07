"""
Instagram Reels gönderimi — resmî Graph API (v21.0), resumable upload.

Bu kod supertonic-web'deki kanıtlanmış akışın birebir taşınmış, bağımsız hâli.
(media_id, error) döner; error boş string ise başarılı.
"""
import asyncio
from pathlib import Path

import httpx

GRAPH = "https://graph.facebook.com/v21.0"


async def post_reel_to_instagram(
    video_path: Path, caption: str, ig_user_id: str, access_token: str
) -> tuple[str | None, str]:
    try:
        video_bytes = video_path.read_bytes()
        video_size = len(video_bytes)

        async with httpx.AsyncClient(timeout=60) as client:
            # 1. Resumable upload session başlat
            r1 = await client.post(
                f"{GRAPH}/{ig_user_id}/media",
                params={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": access_token,
                },
            )
            if r1.status_code != 200:
                return None, f"session create failed: {r1.status_code} {r1.text[:300]}"
            j1 = r1.json()
            media_id = j1.get("id")
            upload_uri = j1.get("uri")
            if not media_id or not upload_uri:
                return None, f"no id/uri: {r1.text[:300]}"

            # Container'ın hazır olması için kısa bekleme
            await asyncio.sleep(3)

            # 2. Video bytes yükle — 3 deneme
            r2 = None
            for attempt in range(3):
                r2 = await client.post(
                    upload_uri,
                    headers={
                        "Authorization": f"OAuth {access_token}",
                        "offset": "0",
                        "file_size": str(video_size),
                        "Content-Type": "video/mp4",
                    },
                    content=video_bytes,
                    timeout=180,
                )
                if r2.status_code in (200, 201):
                    break
                if attempt < 2:
                    await asyncio.sleep(8)
            if r2 is None or r2.status_code not in (200, 201):
                return None, f"upload failed: {r2.status_code if r2 else '??'} {r2.text[:200] if r2 else ''}"

            # 3. İşlenme tamamlanana kadar bekle (maks ~5 dk)
            for _ in range(30):
                await asyncio.sleep(10)
                r3 = await client.get(
                    f"{GRAPH}/{media_id}",
                    params={"fields": "status_code,status", "access_token": access_token},
                    timeout=15,
                )
                if r3.status_code == 200:
                    st = r3.json()
                    code = st.get("status_code", "")
                    if code == "FINISHED":
                        break
                    if code == "ERROR":
                        return None, f"processing error: {st.get('status', '')}"

            # 4. Yayınla
            r4 = await client.post(
                f"{GRAPH}/{ig_user_id}/media_publish",
                params={"creation_id": media_id, "access_token": access_token},
                timeout=30,
            )
            if r4.status_code == 200:
                return r4.json().get("id"), ""
            return None, f"publish failed: {r4.status_code} {r4.text[:200]}"
    except Exception as e:
        return None, str(e)
