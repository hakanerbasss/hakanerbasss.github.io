"""
Namaz vakti FCM bildirim gönderici.
Aladhan API'den vakitleri çeker, APScheduler ile her gün 00:05'te
o güne ait tüm vakitleri planlar.

Kullanım (app.py'e ekle):
    from namaz_bildirim import start_namaz_scheduler
    start_namaz_scheduler(scheduler)   # mevcut APScheduler instance'ına ekle
"""

import logging
import time
import requests
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, messaging

log = logging.getLogger(__name__)

# ── Firebase Admin ────────────────────────────────────────────────────────────

_fb_initialized = False

def _ensure_firebase():
    global _fb_initialized
    if not _fb_initialized:
        try:
            firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate("firebase_service_account.json")
            firebase_admin.initialize_app(cred)
        _fb_initialized = True

# ── Vakitler ──────────────────────────────────────────────────────────────────

CITIES = [
    "Adana", "Ankara", "Antalya", "Bursa", "Diyarbakir", "Erzurum",
    "Eskisehir", "Gaziantep", "Hatay", "Istanbul", "Izmir", "Kahramanmaras",
    "Kayseri", "Kocaeli", "Konya", "Malatya", "Mersin", "Samsun",
    "Trabzon", "Van"
]

VAKIT_LABELS = {
    "Fajr":    "İmsak",
    "Sunrise": "Güneş",
    "Dhuhr":   "Öğle",
    "Asr":     "İkindi",
    "Maghrib": "Akşam",
    "Isha":    "Yatsı",
}

def _fetch_times(city: str) -> dict:
    """Aladhan'dan bugünün vakitlerini çek. {label: "HH:MM"} döndür."""
    url = "https://api.aladhan.com/v1/timingsByCity"
    for attempt in range(3):
        resp = requests.get(url, params={
            "city": city, "country": "Turkey", "method": 13
        }, timeout=10)
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)
            log.warning("Rate limit %s, %ds bekleniyor...", city, wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        timings = resp.json()["data"]["timings"]
        return {label: timings[key][:5] for key, label in VAKIT_LABELS.items()}
    raise Exception(f"{city} için vakit alınamadı (rate limit)")

# ── FCM gönder ────────────────────────────────────────────────────────────────

def _send_fcm(city: str, vakit: str):
    """Tek bir şehir + vakit için FCM topic mesajı gönder."""
    _ensure_firebase()
    topic = f"namaz_{city.lower()}"
    message = messaging.Message(
        notification=messaging.Notification(
            title=vakit,
            body=f"{vakit} vakti girdi.",
        ),
        topic=topic,
    )
    try:
        messaging.send(message)
        log.info("FCM gönderildi → topic=%s vakit=%s", topic, vakit)
    except Exception as e:
        log.error("FCM hata topic=%s: %s", topic, e)

# ── Günlük planlama ───────────────────────────────────────────────────────────

def _schedule_today(scheduler):
    """Her şehir için bugünün vakitlerini APScheduler'a ekle."""
    today = date.today().isoformat()
    log.info("Namaz vakitleri planlanıyor: %s", today)

    for city in CITIES:
        try:
            times = _fetch_times(city)
        except Exception as e:
            log.error("Vakit çekme hatası %s: %s", city, e)
            continue

        for vakit, time_str in times.items():
            h, m = map(int, time_str.split(":"))
            job_id = f"namaz_{city}_{vakit}_{today}"
            scheduler.add_job(
                _send_fcm,
                trigger="cron",
                hour=h,
                minute=m,
                id=job_id,
                args=[city, vakit],
                replace_existing=True,
                misfire_grace_time=120,
            )
            log.debug("  %s %s → %s", city, vakit, time_str)
        time.sleep(2)  # şehirler arası bekleme — rate limit önleme

    log.info("Tüm vakitler planlandı.")

# ── Public API ────────────────────────────────────────────────────────────────

def start_namaz_scheduler(scheduler):
    """
    app.py'deki APScheduler'a namaz vakti joblarını ekle.
    Her gün 00:05'te _schedule_today çalışır.
    İlk çalıştırmada hemen bugünü de planlar.
    """
    scheduler.add_job(
        _schedule_today,
        trigger="cron",
        hour=0,
        minute=5,
        id="namaz_gunluk_planlama",
        args=[scheduler],
        replace_existing=True,
    )

    # Uygulama açılışında hemen bugünü planla
    _schedule_today(scheduler)
    log.info("Namaz bildirim sistemi başlatıldı.")
