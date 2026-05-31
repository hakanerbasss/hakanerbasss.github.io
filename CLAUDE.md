# Proje Genel Yapısı

Bu repo içinde birden fazla proje var. Kripto botla ilgili her şey için önce oku:

→ **`kripto-bot/CLAUDE.md`** — Sistem mimarisi, deploy kuralları, sık hatalar

## Özet (Kripto Bot)

- Servis şu klasörden çalışır: `/root/kripto-bot/kripto-bot/`
- Deploy hedefi: `~/kripto-bot/kripto-bot/` (`~/kripto-bot/` DEĞİL)
- Deploy tetiklemek için: `main` branch + `kripto-bot/**` altında değişiklik şart
- Yeni `.py` eklersen: hem `deploy.yml`'e cp satırı hem `app.py`'e import ekle
- Geliştirme branch: `claude/crypto-bot-performance-6ozvU`

## Diğer Projeler

- `baretim-mavi/` — Ayrı bir mobil uygulama projesi
