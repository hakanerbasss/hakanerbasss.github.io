# Kaba Atık Toplama Rota

Belediye saha ekipleri için: bir mahalledeki sokakları gezerken hangilerinin
tarandığını işaretleyen, konteyner/kaba atık notları ekleyen, bu notları
sesli okuyan ve yetkiliye Telegram üzerinden bildiren mobil web (PWA)
uygulaması.

- Harita: OpenStreetMap + Leaflet (ücretsiz, API key gerekmez)
- Sokak verisi: mahalle adı girilince Nominatim + Overpass API'den otomatik çekilir
- Backend: Flask + SQLite
- Giriş: kişiye özel kullanıcı adı/şifre (`manage.py` ile eklenir)
- Bildirim: Telegram bot token/chat id ile

## Yerel geliştirme

```bash
cd atik-toplama
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config.example.json config.json
# config.json içine gerçek telegram_bot_token / telegram_chat_id / secret_key yaz

python manage.py adduser hakan sifre123 "Hakan Erbaş"

python app.py   # http://localhost:5057
```

## Sunucuya ilk kurulum (tek seferlik, elle yapılır)

Deploy workflow'u (`.github/workflows/atik-toplama-deploy.yml`) sadece
dosyaları kopyalayıp servisi yeniden başlatır; servisin kendisini ve
`config.json`'ı önceden elle kurman gerekir:

```bash
mkdir -p ~/atik-toplama/atik-toplama
cd ~/atik-toplama
python3 -m venv venv
venv/bin/pip install -r ~/hakanerbasss.github.io/atik-toplama/requirements.txt

# config.json'ı sunucuda oluştur (git'e girmez)
cp ~/hakanerbasss.github.io/atik-toplama/config.example.json atik-toplama/config.json
nano atik-toplama/config.json

# kullanıcı ekle
cd atik-toplama
../venv/bin/python manage.py adduser <kullanici> <sifre> "<Görünen Ad>"
```

`systemd` servis dosyası (`/etc/systemd/system/atik-toplama.service`):

```ini
[Unit]
Description=Atik Toplama Rota
After=network.target

[Service]
WorkingDirectory=/root/atik-toplama/atik-toplama
ExecStart=/root/atik-toplama/venv/bin/python app.py
Environment=PORT=5057
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now atik-toplama
```

Bundan sonra `main` branch'e `atik-toplama/**` altında bir değişiklik push
edildiğinde otomatik deploy olur (kripto-bot ile aynı akış).

## Telegram bot kurulumu

1. Telegram'da `@BotFather`'a `/newbot` yaz, adını belirle → token alırsın.
2. Bildirimlerin gideceği kişi/grup ile botu konuşturup (`/start`),
   `https://api.telegram.org/bot<TOKEN>/getUpdates` adresinden `chat.id`'yi öğren.
3. Bu iki değeri `config.json` içine yaz.

## Kullanım akışı

1. Giriş yap → ☰ menüsünden mahalle adı yaz (örn. "Gümüşpala Mahallesi,
   Avcılar, İstanbul") → "Yükle" (ilk seferde sokaklar OSM'den çekilir ve
   kaydedilir, sonraki seferlerde listeden seçilir).
2. Bir sokağa dokunup gezildi olarak işaretle (yeşil = gezildi, kırmızı =
   gezilmedi).
3. "📍 Nokta Ekle" ile haritada bir yere dokunup tür (kaba atık dolu,
   konteyner yok, temizlik gerekli, toplu çalışma, diğer) + not gir, istersen
   "Yetkiliye gönder" ile Telegram'a düşsün.
4. Yakınına gelince not otomatik sesli okunur; sokağa girip henüz
   işaretlenmemişse hatırlatma sesli söylenir.
5. "🧭 Girilmeyen Sokaklar" ile kalan sokakları mesafeye göre sıralı gör.
6. Tarama bitince "✅ Bitti" — özet Telegram'a gider.
