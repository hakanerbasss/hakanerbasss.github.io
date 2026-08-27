# Instagram Otomatik Post Botu

Ana proje: `supertonic-web/` klasörü.

## ⚠️ Oturum çakışmaları — HER OTURUMUN İLK OKUYACAĞI BÖLÜM

Farklı Claude oturumları aynı depoda çalışıyor ve birbirinin işini eziyordu.
Sebebi: her oturum kendi `claude/*` dalına push ediyor, o dal main'e
alınmadan kalıyor; bir sonraki oturum **eski main'den** başlayıp aynı
dosyaları baştan yazıyor.

**Tek kural: main tek doğru kaynaktır. main'e girmeyen iş yok sayılır.**
(Sunucu `git pull` ile sadece main'i çeker — dalda kalan kod hiç yayına girmez.)

Her oturumun sırası:

1. **Başlarken** (kod okumadan önce):
   `git fetch origin main && git reset --hard origin/main`
   Oturum açılışında bu otomatik kontrol ediliyor
   (`.claude/hooks/session-start.sh`) — "bu kopya eski" uyarısı çıkarsa
   **hiçbir dosyaya dokunmadan** önce bu komutu çalıştır.
2. **Ne yapıldığını öğrenmek için:** `instube/DEGISIKLIK-GUNLUGU.md`
   dosyasının en üstteki kaydına bak. Kod okuyup tahmin etme.
3. **İş biterken:** günlüğe en üste kayıt ekle (şablon dosyanın içinde),
   commit et, **main'e al**, kullanılan `claude/*` dalını sil.

Durumu istediğin an elle görmek için: `bash .claude/hooks/session-start.sh`

## Yeni sunucuya taşıma / sıfırdan kurulum

Sunucu kaybedilirse (fatura, çökme, taşıma) her şey **tek komutla** boş bir
Ubuntu'ya kurulur — eski sunucuya hiçbir bağımlılık yok, token/API key
gerekmez (panel açılır, anahtarlar sonradan arayüzden girilir):

```bash
curl -fsSL https://raw.githubusercontent.com/hakanerbasss/hakanerbasss.github.io/main/deploy/bootstrap.sh -o bootstrap.sh
bash bootstrap.sh
```

Ayrıntı, elle yapılacaklar (DNS, OAuth URI'leri, GitHub secret'ları) ve
kurulumdaki bilinen tuzaklar: `deploy/README.md`.

## Özet

- **Sunucu:** Hetzner CX23 — IP: `77.42.45.229` (Helsinki)
- **Servis:** `systemctl status tts` (systemd servisi olarak çalışır)
- **Deploy:** `cd /root/hakanerbasss.github.io && git pull && systemctl restart tts`
- **Python ortamı:** `supertonic-web/.venv` (kendi venv'i). Sistem Python'una **asla** `pip install` yapma — sunucudaki diğer projeleri (firebase-admin vb.) kırar. Yeni paket: `supertonic-web/.venv/bin/pip install <paket>` + `requirements.txt`'e ekle. İlk kurulum/onarım: `bash supertonic-web/setup-venv.sh`
- **Ana dosya:** `supertonic-web/app.py` — FastAPI uygulaması, tüm bot mantığı burada
- **Haber sitesi:** `supertonic-web/news_site.py` — `hakanerbas.wizaicorp.com` subdomaininde yayınlanır
- **Geliştirme branch:** `main` — tüm değişiklikler doğrudan main'e push edilir

## Mimarisi

- **TTS:** Supertonic 1.3.1 (Türkçe, ONNX tabanlı, M1-M5/F1-F5 sesler)
- **AI içerik:** DeepSeek (OpenAI uyumlu API)
- **Haber kaynağı:** Google News RSS + GNews API
- **Video:** FFmpeg ile sahne+ses birleştirme, disclaimer overlay
- **Planlayıcı:** APScheduler CronTrigger — otomatik Instagram paylaşımı
- **Instagram:** Meta Graph API (Reels upload)
- **Telegram:** Bot bildirimleri

## Önemli Kurallar

- Yeni `.py` dosyası eklersen `app.py`'e import ekle
- `supertonic-web/` dışındaki klasörler başka projeler — karıştırma
- Secrets: sunucudaki `supertonic-web/ig_config.json`, `supertonic-web/secrets.json`

## InsTube — ikinci, bağımsız yayın paneli

`instube/` klasörü. supertonic-web'in iç içe geçmiş scheduler'ları ve
"site bazen hiç açılmıyor" sorunlarından kaçınmak için sıfırdan yazılmış,
supertonic-web'e **hiç bağımlı olmayan** ayrı bir video üretim +
Instagram/YouTube yayın paneli. **v1 — scheduler yok, her şey elle/manuel**
(sayfa başına: sadece Instagram, veya YouTube + isteğe bağlı IG çapraz paylaşım).

- **Sunucu:** Aynı sunucu (77.42.45.229), arka planda port `8002`
- **Erişim:** **https://panel.wizaicorp.com/** — nginx bu adresi sunucudaki
  `8002` portuna yönlendiriyor (aynı sunucu, ayrı subdomain, tıpkı
  `bathonea.wizaicorp.com` gibi). YouTube OAuth callback URI'leri de bu
  domaine göre ayarlı: `https://panel.wizaicorp.com/auth/youtube/callback` (TR),
  `https://panel.wizaicorp.com/auth/youtube/en/callback` (EN).
- **Servis:** `systemctl status instube` (systemd servisi)
- **Deploy:** `cd /root/hakanerbasss.github.io && git pull && systemctl restart instube`
- **Python ortamı:** ⚠️ supertonic-web'in aksine **kendi venv'i yok** —
  `instube.service` doğrudan sistem Python'unu çalıştırıyor
  (`ExecStart=/usr/bin/python3 -m uvicorn app:app ...`). supertonic-web'deki
  "sistem Python'una asla pip install yapma" kuralı burada zaten uygulanmıyor
  ama aynı çakışma riski (firebase-admin vb. diğer projelerle) geçerli —
  yeni paket eklerken dikkatli ol.
- **Ana dosya:** `instube/app.py` — router'ları bağlayan ince modül. Gerçek
  mantık ayrı dosyalarda: `generator.py` (DeepSeek + Supertonic TTS + ffmpeg
  pipeline), `visuals.py` (sahne görselleri: DALL-E/Wikimedia/Pexels),
  `youtube.py`, `instagram.py`, `trends.py`
- **Sayfalar:** `/` (durum rozetleri), `/settings.html` (API key'ler +
  Instagram/YouTube bağlantısı), `/instagram.html` (sadece IG Reels üret/test/yayınla),
  `/youtube.html` (YouTube'a yükle, toggle açıksa IG'ye de gönder)
- **Ayarlar/secrets (git'e dahil değil):** `instube/settings.json` (DeepSeek
  ve Pexels key zorunlu, OpenAI opsiyonel, Instagram kimliği), `instube/yt_config.json`
  + `yt_token.json` / `yt_token_en.json` (YouTube OAuth, TR/EN kanal ayrı)
- **Bağımlılık:** `ffmpeg` ve Supertonic TTS sunucuda zaten kurulu olmalı
  (supertonic-web kullandığı için mevcut, ayrıca kurulum gerekmez)

Detaylı kod yapısı ve ilk kurulum adımları: `instube/README.md`.

## SiteBot — müşteriye satılık web sitesi kurma paneli

`sitebot/` klasörü. Bilgileri girince ~60 saniyede müşteriye kendi alan adında,
sertifikalı, kendi yönetim panelli bir site kuran sistem. supertonic-web ve
instube'den **tamamen bağımsız**.

- **Sunucu:** Aynı sunucu (77.42.45.229), port **`8003`**
  (8001 supertonic-web, 8002 instube, 8000 whatsapp, 5057 atık-toplama,
  5001 bathonea, 5000 kripto-bot ile çakışmaz)
- **Erişim:** **https://kur.wizaicorp.com/** — nginx `8003`'e yönlendirir
  (`panel.wizaicorp.com` instube'de olduğu için ayrı subdomain)
- **Servis:** `systemctl status sitebot`
- **Deploy:** `cd /root/hakanerbasss.github.io && git pull && systemctl restart sitebot`
- **Python ortamı:** `sitebot/.venv` (kendi venv'i, supertonic-web gibi).
  Sistem Python'una **asla** `pip install` yapma. İlk kurulum: `bash sitebot/setup-venv.sh`
- **Ana dosya:** `sitebot/app.py` — ince router modülü. Gerçek mantık:
  `provisioner.py` (kurulum/yayın akışı), `renderer.py` (Jinja2 statik HTML),
  `github_api.py`, `cloudflare_api.py`, `schema.py` (ortak veri şeması),
  `images.py` (WebP dönüştürme), `db.py` (SQLite), `auth.py`
- **Üretilen siteler sunucuda DEĞİL** — GitHub org `wizaicorp` altında ayrı
  birer public repo, GitHub Pages'te yayında. Sunucu kapansa siteler ayakta kalır.
- **Şablonlar:** `site_templates/hizmet|katalog|kurumsal` — üçü de aynı veri
  şemasını okur, müşteri şablon değiştirince içeriği kaybolmaz
- **Ayarlar/secrets (git'e dahil değil):** `sitebot/settings.json` (GitHub
  fine-grained token, Cloudflare token + zone ID), `sitebot/sitebot.db`,
  `sitebot/uploads/`. Yedek alırken bu üçünü al.
- **Test:** `cd sitebot && .venv/bin/python test_smoke.py` (GitHub/Cloudflare
  taklit edilir, anahtar gerekmez)
- **Dikkat:** Yeni bir subdomain servisi eklersen `config.py` içindeki
  `RESERVED_SUBDOMAINS` listesine de ekle — yoksa bir müşteriye satılabilir.

Detay: `sitebot/README.md`.

## Diğer Klasörler

- `custom-production/` — supertonic-web'e bağımsız, Cowork oturumlarının (Playwright ile
  özel görsel + Supertonic yerel TTS) ürettiği "Türkiye Bilgi Merkezi" video pipeline'ı.
  Sunucu koduna hiç dokunmuyor, bitmiş videoyu `/api/upload-raw-video` ile sunucuya
  yükleyip mevcut `/api/shorts/send-instagram` + `/api/yt/upload` ile yayınlıyor.
  Detay/devir notu: `custom-production/SISTEM_BILGI.md`.
- `whatsapp-api-server/` — WhatsApp servisi (`wa.wizaicorp.com`)
- `ses-klonu/` — Kendi sesle TTS (XTTS-v2, ücretsiz HuggingFace Space'e deploy edilir) + konuşan fotoğraf (Wav2Lip, `konusan-foto/`)
- Namaz Vakitleri Android uygulaması → **kendi deposuna taşındı**: https://github.com/hakanerbasss/namaz-vakitleri (2026-07-22). Bu depoda değil.
- Baretim Mavi Android uygulaması (`com.bluechip.finance`) → **kendi deposuna taşındı**: https://github.com/hakanerbasss/baretim-mavi-admob (2026-07-22). Bu depoda değil.
- Bathonea Toplu İş Sözleşmesi Asistanı → **kendi deposuna taşındı**: https://github.com/hakanerbasss/bathonea (2026-08-03). `bathonea.wizaicorp.com` — aynı sunucu (77.42.45.229), ayrı systemd servisi (`bathonea`).
