"""YouTube Live Streaming API yardımcıları — canlı yayın oluşturma/yönetme.

Video/ses aktarımı burada YOK — Data API v3 sadece yayının "kabuğunu" (broadcast +
stream nesnesi + RTMP giriş adresi) oluşturur. Gerçek video/ses akışı ffmpeg ile
RTMP üzerinden ayrıca yapılır (bkz. app.py: _live_stream_supervisor).
"""
from googleapiclient.discovery import build


def create_broadcast(creds, title: str, description: str = "") -> dict:
    """Yeni bir canlı yayın + stream oluşturur, ikisini birbirine bağlar.
    enableAutoStart=True olduğu için ffmpeg RTMP'ye veri göndermeye başlayınca
    YouTube yayını otomatik "live" durumuna geçirir — ayrı bir transition
    çağrısına gerek yok. enableAutoStop=False, ffmpeg akışında kısa bir
    kesinti olduğunda (örn. kuyruktaki dosyalar arası geçiş) yayının
    kendiliğinden sonlanmamasını sağlar."""
    yt = build("youtube", "v3", credentials=creds)

    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": (title or "Canlı Yayın")[:100],
                "description": (description or "")[:5000],
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": False,
                "enableDvr": True,
                "recordFromStart": True,
                "latencyPreference": "normal",
            },
        },
    ).execute()

    stream = yt.liveStreams().insert(
        part="snippet,cdn",
        body={
            "snippet": {"title": f"{(title or 'Canlı Yayın')[:90]} — stream"},
            "cdn": {"frameRate": "30fps", "ingestionType": "rtmp", "resolution": "1080p"},
        },
    ).execute()

    yt.liveBroadcasts().bind(
        id=broadcast["id"], part="id,contentDetails", streamId=stream["id"]
    ).execute()

    ingestion = stream["cdn"]["ingestionInfo"]
    return {
        "broadcast_id": broadcast["id"],
        "stream_id": stream["id"],
        "ingestion_address": ingestion["ingestionAddress"],
        "stream_name": ingestion["streamName"],
        "watch_url": f"https://www.youtube.com/watch?v={broadcast['id']}",
    }


def end_broadcast(creds, broadcast_id: str) -> dict:
    """Yayını 'complete' durumuna geçirip sonlandırır."""
    yt = build("youtube", "v3", credentials=creds)
    return yt.liveBroadcasts().transition(
        broadcastStatus="complete", id=broadcast_id, part="id,status"
    ).execute()
