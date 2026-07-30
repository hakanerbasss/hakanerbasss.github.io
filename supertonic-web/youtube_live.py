"""YouTube Live Streaming API yardımcıları — canlı yayın oluşturma/yönetme.

Video/ses aktarımı burada YOK — Data API v3 sadece yayının "kabuğunu" (broadcast +
stream nesnesi + RTMP giriş adresi) oluşturur. Gerçek video/ses akışı ffmpeg ile
RTMP üzerinden ayrıca yapılır (bkz. app.py: _live_stream_supervisor).
"""
import datetime
from googleapiclient.discovery import build


def create_broadcast(creds, title: str, description: str = "") -> dict:
    """Yeni bir canlı yayın + stream oluşturur, ikisini birbirine bağlar.
    enableAutoStart=True olduğu için ffmpeg RTMP'ye veri göndermeye başlayınca
    YouTube yayını otomatik "live" durumuna geçirir — ayrı bir transition
    çağrısına gerek yok. enableAutoStop=False, ffmpeg akışında kısa bir
    kesinti olduğunda (örn. kuyruktaki dosyalar arası geçiş) yayının
    kendiliğinden sonlanmamasını sağlar."""
    yt = build("youtube", "v3", credentials=creds)

    scheduled_start = (
        datetime.datetime.utcnow() + datetime.timedelta(seconds=30)
    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": (title or "Canlı Yayın")[:100],
                "description": (description or "")[:5000],
                "scheduledStartTime": scheduled_start,
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
        "scheduled_start": scheduled_start,
    }


def update_broadcast_title(creds, broadcast_id: str, title: str, scheduled_start: str) -> None:
    """Yayın devam ederken başlığı günceller. scheduledStartTime update çağrısında
    da zorunlu — create_broadcast'ten dönen değer olduğu gibi iletilmeli."""
    yt = build("youtube", "v3", credentials=creds)
    yt.liveBroadcasts().update(
        part="snippet",
        body={
            "id": broadcast_id,
            "snippet": {
                "title": title[:100],
                "scheduledStartTime": scheduled_start,
            },
        },
    ).execute()


def get_broadcast_if_reusable(creds, broadcast_id: str, stream_id: str) -> dict | None:
    """Mevcut broadcast hâlâ ready/live/testStarting durumundaysa RTMP bilgisini döner,
    aksi hâlde None — supervisor yeni broadcast oluşturmak yerine bu sonucu kullanır."""
    try:
        yt = build("youtube", "v3", credentials=creds)
        br = yt.liveBroadcasts().list(id=broadcast_id, part="id,status,snippet").execute()
        items = br.get("items", [])
        if not items:
            return None
        status = items[0]["status"]["lifeCycleStatus"]
        if status not in ("ready", "testStarting", "live"):
            return None
        st = yt.liveStreams().list(id=stream_id, part="id,cdn").execute()
        st_items = st.get("items", [])
        if not st_items:
            return None
        ingestion = st_items[0]["cdn"]["ingestionInfo"]
        return {
            "broadcast_id": broadcast_id,
            "stream_id": stream_id,
            "ingestion_address": ingestion["ingestionAddress"],
            "stream_name": ingestion["streamName"],
            "watch_url": f"https://www.youtube.com/watch?v={broadcast_id}",
            "scheduled_start": items[0]["snippet"].get("scheduledStartTime", ""),
        }
    except Exception:
        return None


def end_broadcast(creds, broadcast_id: str) -> dict:
    """Yayını 'complete' durumuna geçirip sonlandırır."""
    yt = build("youtube", "v3", credentials=creds)
    return yt.liveBroadcasts().transition(
        broadcastStatus="complete", id=broadcast_id, part="id,status"
    ).execute()
