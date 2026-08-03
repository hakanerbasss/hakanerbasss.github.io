# Instagram Otomatik Post Botu

Ana proje: `supertonic-web/` klasörü.

## Özet

- **Sunucu:** Hetzner CX23 — IP: `77.42.45.229` (Helsinki)
- **Servis:** `systemctl status tts` (systemd servisi olarak çalışır)
- **Deploy:** `cd /root/hakanerbasss.github.io && git pull && systemctl restart tts`
- **Ana dosya:** `supertonic-web/app.py` — FastAPI uygulaması, tüm bot mantığı burada
- **Haber sitesi:** `supertonic-web/news_site.py` — `hakanerbas.wizaicorp.com` subdomaininde yayınlanır
- **Geliştirme branch:** `claude/arduino-smart-home-uj82ef`

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

## Diğer Klasörler

- `whatsapp-api-server/` — WhatsApp servisi (`wa.wizaicorp.com`)
- Namaz Vakitleri Android uygulaması → **kendi deposuna taşındı**: https://github.com/hakanerbasss/namaz-vakitleri (2026-07-22). Bu depoda değil.
- Baretim Mavi Android uygulaması (`com.bluechip.finance`) → **kendi deposuna taşındı**: https://github.com/hakanerbasss/baretim-mavi-admob (2026-07-22, Google Play'in targetSdk 36 zorunluluğu + Termux'un aapt2'sinin API 36'yı derleyememesi nedeniyle GitHub Actions'a geçildi). Bu depoda değil.
- Bathonea Toplu İş Sözleşmesi Asistanı → **kendi deposuna taşındı**: https://github.com/hakanerbasss/bathonea (2026-08-03). Bu depoda değil. `bathonea.wizaicorp.com` — aynı sunucu (77.42.45.229), ayrı systemd servisi (`bathonea`).
