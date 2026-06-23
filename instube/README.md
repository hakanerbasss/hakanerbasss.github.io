# InsTube — Sade Yayın Paneli

Eski `supertonic-web` projesindeki birbirine girmiş scheduler'lar ve yutulan
hatalardan bağımsız, **temiz ve sade** bir yayın paneli. Her iş **ayrı sayfada**
ve kod **ayrı modüllerde** — hata olunca erken ve net görünsün.

## Sayfalar (her iş ayrı)

- **`/`** — ana sayfa / yönlendirme + durum rozetleri
- **`/settings.html`** — anahtarlar (DeepSeek, Instagram, motor adresi)
- **`/instagram.html`** — videoyu üret, test et, **sadece Instagram** Reels yayınla
- **`/youtube.html`** — videoyu üret, test et, **YouTube**'a yükle; "Instagram'a da
  gönder" toggle'ı açıksa aynı videoyu Instagram'a da atar (kapalıysa sadece YouTube)

Her üretim sayfasında **▶ Üret (Test)** videoyu yayınlamadan üretir; hata olursa
motorun **gerçek hata detayını** ekranda gösterir.

## Kod yapısı (ayrı dosyalar)

```
app.py                    ince ana modül — router'ları bağlar, statik sayfaları sunar
config.py                 settings.json oku/yaz
engine.py                 motor (:8001) ile konuşma (üretim, YT yükleme, indirme)
instagram.py              Instagram Reels gönderimi (Graph API)
routers/settings_api.py   /api/settings, /api/status
routers/generate_api.py   /api/generate, /api/video/{filename}
routers/publish_api.py    /api/publish/instagram, /api/publish/youtube
static/                   index / settings / instagram / youtube sayfaları + style.css + common.js
```

## Mimari

Ağır ve zaten **kanıtlanmış** işler (DeepSeek içerik + Supertonic TTS + ffmpeg
video + YouTube OAuth) hâlâ çalışan **motora** (supertonic-web, varsayılan
`http://localhost:8001`) HTTP ile delege edilir. InsTube yalnızca arayüzü, net
hata gösterimini, test modunu ve **Instagram Reels gönderimini** kendisi yapar.
Böylece çalışan kod hiç bozulmadan üstüne temiz bir katman eklenir.

v1'de **otomatik zamanlayıcı yok** — her şey manuel.

## Çalıştırma

```bash
cd instube
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8002
```

Tarayıcı → `http://SUNUCU:8002` → **⚙️ Ayarlar**'dan DeepSeek anahtarı + Instagram
Business User ID & uzun ömürlü Access Token gir. (YouTube OAuth ve Pexels motorda
zaten kayıtlı.)

`settings.json` ve `downloads/` git'e dahil değildir.
