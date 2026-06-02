# Kripto Bot — Claude için Teknik Referans

Bu dosya, AI oturumlarının sistemi yanlış anlamaması için kritik bilgileri içerir.
Her yeni oturumda önce bu dosyayı oku.

---

## 1. Dizin Yapısı (KRİTİK)

```
/root/
├── hakanerbasss.github.io/        ← Git clone (deploy kaynağı)
│   ├── kripto-bot/                ← Kaynak .py dosyaları burada
│   └── .github/workflows/
│       └── deploy.yml
│
└── kripto-bot/                    ← Sunucu ana klasörü
    ├── venv/                      ← Python sanal ortam
    │   └── bin/python
    └── kripto-bot/                ← ★ SERVİS BURADAN ÇALIŞIR ★
        ├── app.py
        ├── bot.py
        ├── config.json
        ├── trades.json
        ├── positions.json
        ├── templates/
        └── static/
```

**Servis unit dosyası:**
```
WorkingDirectory=/root/kripto-bot/kripto-bot
ExecStart=/root/kripto-bot/venv/bin/python app.py
```

> **UYARI:** Deploy `~/kripto-bot/kripto-bot/`'a kopyalar, `~/kripto-bot/`'a DEĞİL.
> Bu ikisi farklı klasördür. Geçmişte bu karışıklık haftalarca fark edilmeden sürdü.

---

## 2. Deploy Akışı

```
git push → main branch + kripto-bot/** değişikliği
    → GitHub Actions tetiklenir
    → SSH: cd ~/hakanerbasss.github.io && git reset --hard origin/main
    → cp kripto-bot/*.py ~/kripto-bot/kripto-bot/
    → find ~/kripto-bot/kripto-bot -name __pycache__ -exec rm -rf {} +
    → systemctl restart kripto-bot
```

**Tetiklenme koşulu:** `main` branch'e push VE `kripto-bot/**` altında dosya değişikliği.
Sadece `deploy.yml` değişirse deploy TETİKLENMEZ. Bir `kripto-bot/` dosyası da değişmeli.

---

## 3. Yeni Ajan / Dosya Eklerken Yapılması Gerekenler

Yeni bir `.py` dosyası eklendiğinde **iki yerde** güncelleme şart:

### 3a. `deploy.yml` — cp satırı ekle
```yaml
cp kripto-bot/yeni_ajan.py $DEST/ 2>/dev/null || true
```

### 3b. `app.py` — import + başlatma
```python
from yeni_ajan import start_yeni_ajan, stop_yeni_ajan
# ve start_all() / stop_all() içine ekle
```

Sadece birini yapmak yeterli değil — ikisi de gerekli.

---

## 4. Mevcut Dosyalar ve Deploy Durumu

| Dosya | Deploy'da mı? | Açıklama |
|---|---|---|
| `app.py` | ✅ | Flask web sunucusu + ajan başlatıcı |
| `bot.py` | ✅ | Çekirdek: alım/satım, config, Telegram |
| `signal_engine.py` | ✅ | UT Bot sinyal motoru |
| `autonomous_agent.py` | ✅ | RSI/MACD/BB teknik analiz ajanı |
| `breakout_agent.py` | ✅ | Hacim spike + kırılım ajanı |
| `edge_agent.py` | ✅ | Funding/OI/CVD piyasa mekaniği ajanı |
| `indicator_agent.py` | ✅ | UT Bot crossover ajanı |
| `wyckoff_agent.py` | ✅ | Wyckoff akümülasyon ajanı |
| `accumulation_agent.py` | ✅ | BB squeeze birikim ajanı |
| `manager_agent.py` | ✅ | CEO portföy yönetim ajanı |
| `telegram_bot.py` | ✅ | Telegram komut işleyici |
| `seans_strategy.py` | ✅ | Seans stratejisi (pasif) |
| `smart_strategy.py` | ✅ | Smart stratejisi (pasif) |
| `trends_backtest.py` | ✅ | Backtest modülü |
| `templates/` | ✅ | Flask HTML şablonları |
| `static/` | ✅ | CSS/JS dosyaları |

---

## 5. Servis Komutları

```bash
systemctl restart kripto-bot    # yeniden başlat
systemctl status kripto-bot     # durum kontrol
systemctl cat kripto-bot        # unit dosyasını gör
journalctl -u kripto-bot -f     # canlı log izle
journalctl -u kripto-bot -n 100 # son 100 satır log
```

---

## 6. Önemli Eşikler ve Konfigürasyon

### bot.py
- `MIN_REENTRY_FLOOR = 0.5` saat — config'de 0 olsa bile minimum re-entry bekleme
- `send_telegram()` — kuyruk sistemi, tek thread, 2 mesaj/sn max

### breakout_agent.py
- `MIN_VOL_24H = 500_000` — $500K min 24s hacim (düşük likidite slippage önlemi)
- `MIN_PRICE_CHG_2H = 5.0` — minimum %5 hareket
- `MAX_CHG_24H = 20.0` — 24s %20+ pompanmış coinlere girme
- `MIN_SCORE = 5.5` — minimum skor eşiği
- `MIN_REENTRY_HOURS = 1.0` — re-entry hard floor (config bağımsız)
- `FG_MIN = 35` — Fear & Greed bu değerin altında tarama yok

### autonomous_agent.py
- `MIN_SCORE = 6.0` — standart skor eşiği
- `MIN_SCORE_SIDEWAY = 6.5` — SIDEWAYS rejimde daha katı
- `DAILY_LOSS_LIMIT = 8.0` — günlük -%8 limiti
- `FG_MIN = 30` — Fear & Greed filtresi

---

## 7. Sık Yapılan Hatalar

| Hata | Açıklama | Çözüm |
|---|---|---|
| Yanlış klasör | Deploy `~/kripto-bot/`'a yazdı, servis `~/kripto-bot/kripto-bot/`'tan okudu | Her zaman `DEST=~/kripto-bot/kripto-bot` kullan |
| Deploy tetiklenmedi | Sadece `deploy.yml` değişti, `kripto-bot/**` değişmedi | Aynı commit'e bir `kripto-bot/` dosyası ekle |
| Eski değerler | `__pycache__` bytecode'u Python'un yeni `.py`'yi okumasını engelledi | Deploy sonunda `__pycache__` sil |
| Eksik ajan | Yeni ajan eklendi ama deploy.yml'ye cp satırı eklenmedi | Bölüm 3'e bak |
| Telegram timeout | Tüm ajanlar aynı anda mesaj gönderdi, rate-limit aşıldı | `bot.py`'deki queue sistemi çözüyor |

---

## 8. Testnet Bilgileri

- `config.json` içinde `"testnet": true` ise Binance testnet kullanılır
- Testnet URL: `https://testnet.binance.vision`
- Testnet bakiyeler gerçek para değildir
- Başlangıç bakiye ~$10,000 USDT (testnet)
