# Kripto Bot — Sistem Kılavuzu

## Genel Mimari

```
GitHub (hakanerbasss/hakanerbasss.github.io)
    └── kripto-bot/ (kaynak kod)
            │
            │  [main branch'e push → GitHub Actions tetiklenir]
            ▼
        Sunucu (/root/kripto-bot/)
            │
            │  [systemctl restart kripto-bot]
            ▼
        Flask App (port 5000) + 3 Ajan Thread
```

Sunucuda iki ayrı git repo vardır:
- `/root/hakanerbasss.github.io/` → GitHub'ın kopyası (deploy için)
- `/root/kripto-bot/.git` → yerel yedek (deploy etmez, kullanma)

---

## Auto-Deploy Nasıl Çalışır?

### Tetikleyici
`main` branch'e `kripto-bot/**` altında bir dosya push edildiğinde GitHub Actions devreye girer.

### Akış
1. GitHub Actions → SSH ile sunucuya bağlanır
2. `/root/hakanerbasss.github.io/` içinde `git reset --hard origin/main` çalışır
3. Python dosyaları `/root/kripto-bot/` klasörüne kopyalanır
4. `systemctl restart kripto-bot` ile bot yeniden başlar

### Workflow Dosyası
`.github/workflows/deploy.yml` — tetikleyici ve kopyalanan dosyalar burada tanımlıdır.

---

## Kod Değişikliği Yapma Adımları

### 1. Dosyayı Düzenle
Kripto bot dosyaları `kripto-bot/` klasöründedir:
```
kripto-bot/
├── app.py              ← Flask API + web arayüzü
├── bot.py              ← Temel fonksiyonlar (load_config, send_telegram, vb.)
├── signal_engine.py    ← UT Bot indikatörü (calc_ut_bot)
├── autonomous_agent.py ← Otonom ajan (kendi coin seçer)
├── edge_agent.py       ← Edge ajan (UT Bot sinyali)
├── indicator_agent.py  ← İndikatör ajanı (3 indikatör test eder)
├── smart_strategy.py   ← Smart strateji (4 faktör skoru)
├── seans_strategy.py   ← Seans stratejisi (TR saatine göre)
├── telegram_bot.py     ← Telegram komut botu
└── templates/
    └── index.html      ← Web dashboard
```

### 2. Commit Et
```bash
git add kripto-bot/<değiştirilen_dosya>
git commit -m "Ne yaptığını açıkla"
```

### 3. Push Et → Deploy Otomatik Olur
```bash
git push origin main
```
Push'tan sonra ~30-60 saniye içinde sunucu güncellenir ve bot yeniden başlar.

---

## Sunucu Üzerinde Manuel İşlemler

### Bot Durumunu Kontrol Et
```bash
systemctl status kripto-bot
```

### Log'ları İzle (canlı)
```bash
journalctl -u kripto-bot -f
```

### Bot'u Yeniden Başlat
```bash
systemctl restart kripto-bot
```

### Bot'u Durdur / Başlat
```bash
systemctl stop kripto-bot
systemctl start kripto-bot
```

---

## Kritik Uyarılar

### YAPMA: `/root/kripto-bot/` İçinde git reset --hard
```bash
# BU KOMUTU ÇALIŞTIRMA — tüm yerel dosyaları siler!
git reset --hard origin/main   # ← TEHLİKELİ
```
`/root/kripto-bot/.git` ayrı bir repodur. Orada reset yapılırsa JSON dosyaları korunur ama `.py` dosyaları silinir.

### YAPMA: Manuel Dosya Silme
`/root/kripto-bot/` içindeki JSON dosyaları (positions.json, trades.json vb.) bot'un verisidir. Silme.

### JSON Veri Dosyaları (Git'e Eklenmez)
Bunlar sunucuda yaşar, GitHub'da olmaz:
```
/root/kripto-bot/
├── config.json          ← API anahtarları, coin listesi, ayarlar
├── positions.json       ← Açık pozisyonlar
├── trades.json          ← İşlem geçmişi
├── agent_state.json     ← Otonom ajan durumu
├── edge_state.json      ← Edge ajan durumu
├── indicator_state.json ← İndikatör ajan durumu
├── signal_state.json    ← Sinyal motoru durumu
├── edge_performance.json← Edge performans kaydı
└── tg_offset.json       ← Telegram mesaj offset'i
```

---

## Ajanlar

| Ajan | Dosya | Ne Yapar |
|------|-------|----------|
| **Edge** | `edge_agent.py` | UT Bot sinyaliyle `config.json`'daki coinleri izler |
| **Otonom** | `autonomous_agent.py` | Top-50 USDT çiftini tarayıp kendi coin seçer |
| **İndikatör** | `indicator_agent.py` | 3 indikatörü test eder (UT Bot / Smart / Seans) |

### İndikatör Ajanı Nasıl Çalışır?
Otonom ajan gibi top-50 coin tarar. Her coin için 3 indikatör sırayla denenir:
1. **UT Bot** (`calc_ut_bot` → `signal_engine.py`) — ATR tabanlı trailing stop crossover
2. **Smart** (`check_smart_signal` → `smart_strategy.py`) — RSI + SMA20 + Hacim + Bollinger
3. **Seans** (`check_seans_signal` → `seans_strategy.py`) — TR saati 09-12 / 20-23

İşlemler `source` alanıyla etiketlenir: `INDICATOR-UTBOT`, `INDICATOR-SMART`, `INDICATOR-SEANS`

---

## Telegram Komutları

| Komut | Açıklama |
|-------|----------|
| `/durum` | Açık pozisyonlar, K/Z, başarı oranı |
| `/pozisyonlar` | Detaylı pozisyon listesi |
| `/baslat` | Botu başlat |
| `/durdur` | Botu duraklat |
| `/restart` | Botu yeniden başlat |
| `/yardim` | Komut listesi |

---

## Yeni Bir Dosya Eklenince

Workflow'a da eklenmesi gerekir. `.github/workflows/deploy.yml` dosyasına:
```yaml
cp kripto-bot/yeni_dosya.py ~/kripto-bot/ 2>/dev/null || true
```
satırını ekle, yoksa sunucuya kopyalanmaz.

---

## Sorun Giderme

### Bot Başlamıyor
```bash
journalctl -u kripto-bot -n 50 --no-pager
```
Genellikle sebep: eksik modül (import hatası) veya syntax hatası.

### Deploy Olmadı
- GitHub → Actions sekmesinde workflow'un başarılı olup olmadığını kontrol et
- `kripto-bot/**` dışında bir dosya değiştirildiyse deploy tetiklenmez

### Telegram Mesajı Gelmiyor
- `config.json`'da `telegram_token` ve `telegram_chat_id` doğru mu?
- `bot.py` içindeki `send_telegram()` fonksiyonu mesaj gönderir; log'larda hata var mı bak

### Pytz Hatası
Sunucuda pytz kurulu değil. `seans_strategy.py` artık stdlib `datetime.timezone` kullanıyor — pytz ekleme.
