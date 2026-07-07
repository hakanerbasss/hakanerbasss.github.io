# InsTube — Sade, Bağımsız Yayın Paneli

Eski `supertonic-web` projesindeki birbirine girmiş scheduler'lar, yutulan
hatalar ve "site bazen hiç açılmıyor" derdinden kurtulmak için **sıfırdan,
tamamen bağımsız** yazılmış yayın paneli. Hiçbir dış servise bağımlı değildir —
video üretimi, TTS, görseller, ffmpeg ve YouTube yüklemesi **hepsi içindedir**.

## Neden daha sağlam?

- **Tek işe odaklı, scheduler yok (v1).** Eskiden tek süreçte 5-6 zamanlanmış iş
  vardı; biri patlayınca tüm site düşüyordu. Burada her şey manuel ve izole.
- **Ağır üretim thread havuzunda çalışır** → bir video üretimi patlasa bile
  arayüz ve diğer işlemler ayakta kalır.
- **Hatalar yutulmaz.** ffmpeg gerçek hata çıktısını gösterir; üretim/yayın
  hataları ilgili sayfada net görünür.
- _Not:_ Üretim sırasındaki ffmpeg hatasının kökü sunucu RAM/CPU yetersizliği
  (OOM) ise, bunu hiçbir yazılım çözemez — ama InsTube sana **tam sebebi
  gösterir** (örn. `exit 137` = bellek yetersiz → swap/RAM gerekir).

## Sayfalar (her iş ayrı)

- **`/`** — giriş + durum rozetleri
- **`/settings.html`** — API anahtarları (DeepSeek, Pexels, OpenAI), Instagram,
  YouTube OAuth
- **`/instagram.html`** — üret, test et, **sadece Instagram** Reels
- **`/youtube.html`** — üret, test et, **YouTube**'a yükle; toggle açıksa
  Instagram'a da gönder

**▶ Üret (Test)** videoyu yayınlamadan üretir; hata olursa ekranda gösterir.

## Kod yapısı (ayrı dosyalar)

```
app.py            ince ana modül — router'ları bağlar, sayfaları sunar
config.py         ayar/anahtar/yol sabitleri
generator.py      DeepSeek içerik + Supertonic TTS + görsel + ffmpeg pipeline
visuals.py        sahne görselleri (DALL-E/Wikimedia/Pexels) + overlay'ler
youtube.py        YouTube OAuth + yükleme
instagram.py      Instagram Reels gönderimi (Graph API)
trends.py         Google News / YouTube trend verisi
ffmpeg_util.py    gerçek hatayı gösteren ffmpeg sarmalayıcı
routers/          settings / generate / publish / youtube uçları
static/           index / settings / instagram / youtube sayfaları
```

## Çalıştırma

```bash
cd instube
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8002
```

`http://SUNUCU:8002` → **⚙️ Ayarlar**:

1. **DeepSeek** ve **Pexels** anahtarlarını gir (zorunlu). OpenAI opsiyonel.
2. **Instagram** Business User ID + uzun ömürlü Access Token gir.
3. **YouTube**: Client ID/Secret gir, sonra TR/EN kanalını yetkilendir.
   - Google Cloud konsolunda yetkili yönlendirme URI olarak şunu eklemen gerekir:
     `http://SUNUCU:8002/auth/youtube/callback` (EN için `/auth/youtube/en/callback`).

> `ffmpeg` ve Supertonic TTS sunucuda kurulu olmalı (supertonic-web zaten
> kullandığı için mevcut). `settings.json`, token'lar ve üretim klasörleri
> git'e dahil değildir.
