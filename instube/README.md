# InsTube — Sade Yayın Paneli

Eski `supertonic-web` projesindeki birbirine girmiş scheduler'lar ve yutulan
hatalardan bağımsız, **temiz ve sade** bir yayın kontrol paneli.

## Ne yapar?

- **2 sekme:**
  - **📸 Instagram** — videoyu sadece Instagram Reels olarak yayınlar.
  - **▶️ YouTube + Instagram** — YouTube'a yükler; "Instagram'a da gönder"
    toggle'ı açıksa aynı videoyu Instagram'a da atar (kapatınca sadece YouTube).
- **▶ Üret (Test)** — videoyu üretir ama yayınlamaz. Hata olursa **net biçimde
  ekranda gösterir** (eski sistemin en büyük derdi hataların görünmemesiydi).
- v1'de **otomatik zamanlayıcı yok** — her şey manuel. Önce sağlam çalışsın.

## Mimari

Ağır ve zaten kanıtlanmış işler hâlâ çalışan **motora** (supertonic-web,
varsayılan `http://localhost:8001`) HTTP ile delege edilir:

- Video üretimi → `POST /api/generate-shorts`
- YouTube yükleme → `POST /api/yt/upload`

InsTube yalnızca arayüzü, hata gösterimini, test modunu ve **Instagram Reels
gönderimini** (resmî Graph API) kendisi yapar. Böylece çalışan kod hiç
bozulmadan, üzerine temiz bir katman eklenir.

## Çalıştırma

```bash
cd instube
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8002
```

Tarayıcıdan `http://SUNUCU:8002` → **⚙️ Ayarlar**'dan:

- **DeepSeek API anahtarı** (içerik üretimi için)
- **Instagram Business User ID** + **uzun ömürlü Access Token**
- **Motor adresi** (boşsa `http://localhost:8001`)

> Not: YouTube OAuth ve Pexels anahtarı motorda (supertonic-web) zaten kayıtlı
> olduğu için burada tekrar istenmez.

`settings.json` ve `downloads/` git'e dahil değildir (`.gitignore`).
