# WhatsApp API Server — Kurulum Kılavuzu

Yeni bir VPS'e sıfırdan kurulum için adım adım rehber.

---

## Gereksinimler

| Gereksinim | Minimum |
|---|---|
| VPS işletim sistemi | Ubuntu 20.04 / 22.04 |
| RAM | 1 GB |
| Disk | 10 GB |
| Node.js | 18+ (script otomatik kurar) |
| Alan adı (domain) | İsteğe bağlı — IP ile de çalışır |

---

## 1. GitHub Repo Forkla veya Klonla

Bu repoyu kendi GitHub hesabına **fork**la ya da **private repo** olarak kopyala.

> Kendi repona taşırsan `whatsapp-api.yml` içindeki `hakanerbasss/hakanerbasss.github.io` referanslarını güncellemeye gerek yok — workflow sadece `whatsapp-api-server/**` yolunu dinler.

---

## 2. GitHub Secrets Tanımla

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret adı | Değer |
|---|---|
| `SSH_HOST` | VPS IP adresi (örn. `45.143.4.169`) |
| `SSH_USER` | SSH kullanıcısı (genellikle `root`) |
| `SSH_KEY` | VPS'in private SSH anahtarı (aşağıda nasıl alınır) |

### SSH Key nasıl alınır?

VPS'e bağlan, şu komutu çalıştır:

```bash
cat ~/.ssh/id_rsa
```

Eğer yoksa önce oluştur:

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
cat ~/.ssh/id_rsa.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/id_rsa
```

Çıkan `-----BEGIN OPENSSH PRIVATE KEY-----` ile başlayan tüm metni `SSH_KEY` secret'ına yapıştır.

---

## 3. VPS'e İlk Kurulum

VPS'e SSH ile bağlan ve şu komutları çalıştır:

```bash
# Repoyu klonla
git clone https://github.com/KULLANICI_ADI/REPO_ADI.git ~/hakanerbasss.github.io
cd ~/hakanerbasss.github.io

# Kurulum scriptini çalıştır
bash whatsapp-api-server/setup-vps.sh
```

Script otomatik olarak şunları yapar:
- Node.js 20 kurar
- pm2 kurar
- Dosyaları `~/whatsapp-api/` klasörüne kopyalar
- npm paketlerini yükler
- Baileys kütüphanesine gerekli patch'i uygular
- `.env` dosyası oluşturur (JWT_SECRET rastgele üretilir)
- pm2 ile servisi başlatır
- Sunucu yeniden başlayınca otomatik çalışacak şekilde ayarlar

---

## 4. Nginx Reverse Proxy (Domain varsa)

Domain kullanacaksan nginx kurarak yönlendirme yap:

```bash
apt-get install -y nginx
```

`/etc/nginx/sites-available/whatsapp-api` dosyasını oluştur:

```nginx
server {
    listen 80;
    server_name wa.DOMAIN_ADINIZ.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Etkinleştir:

```bash
ln -s /etc/nginx/sites-available/whatsapp-api /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Ardından `.env` dosyasındaki port'u güncelle:

```bash
nano ~/whatsapp-api/.env
# PORT=8000 yap (nginx 80'den 8000'e yönlendirir)
pm2 restart whatsapp-api
```

---

## 5. SSL (HTTPS) — Opsiyonel

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d wa.DOMAIN_ADINIZ.com
```

---

## 6. İlk Admin Hesabı Oluştur

Tarayıcıda şu adrese git:

```
http://SUNUCU_IP veya https://wa.DOMAIN_ADINIZ.com
```

Karşına kurulum sayfası gelir. Kullanıcı adı ve şifre belirle → **Hesap Oluştur**.

---

## 7. Admin Paneli Ayarları

Giriş yaptıktan sonra **Ayarlar** menüsünden şunları doldur:

| Ayar | Açıklama |
|---|---|
| Site URL | Panel adresi (örn. `https://wa.DOMAIN_ADINIZ.com`) |
| İletişim Telefonu | Admin WhatsApp numarası (bildirimler buraya gelir) |
| İletişim E-posta | Yedek iletişim |
| Limit Aşım Mesajı | Müşteriye gösterilecek hata metni |
| Paketler | Fiyat ve kota bilgileri |

---

## 8. Sonraki Güncellemeler (Otomatik Deploy)

Kod güncellendiğinde GitHub Actions otomatik devreye girer:

1. `whatsapp-api-server/**` altında bir değişiklik `main` branch'e push'lanır
2. GitHub Actions VPS'e SSH ile bağlanır
3. Kodu günceller, npm install yapar, pm2 restart eder

**Manuel güncelleme** gerekirse VPS'te:

```bash
cd ~/hakanerbasss.github.io
git fetch origin && git reset --hard origin/main
cp -r whatsapp-api-server/src ~/whatsapp-api/
cp -r whatsapp-api-server/panel ~/whatsapp-api/
pm2 restart whatsapp-api
```

---

## 9. Şifre Sıfırlama

Admin şifresini unutursan VPS'te:

```bash
cd ~/whatsapp-api
node reset-password.js
```

---

## 10. Yararlı Komutlar

```bash
# Logları izle
pm2 logs whatsapp-api

# Servisi yeniden başlat
pm2 restart whatsapp-api

# Servis durumu
pm2 status

# Sunucu yeniden başlayınca otomatik çalış (zaten setup ile kurulur)
pm2 startup && pm2 save

# Veritabanı konumu
ls -lh ~/whatsapp-api/data/database.bin
```

---

## Sorun Giderme

**Port zaten kullanılıyor hatası:**
```bash
ss -tlnp | grep :8000
# Hangi proses olduğunu bul, kapat veya farklı port kullan
```

**pm2 çalışmıyor:**
```bash
pm2 logs whatsapp-api --lines 50
```

**WhatsApp bağlantısı kopuyor:**
- Müşteri panelinden tekrar QR okut veya telefon numarası ile eşleştir
- Baileys patch uygulandığından emin ol:
```bash
grep "passive" ~/whatsapp-api/node_modules/baileys/lib/Utils/validate-connection.js
# "passive: false" görünmeli
```

**Git pull diverged hatası:**
```bash
cd ~/hakanerbasss.github.io
git fetch origin && git reset --hard origin/main
```

---

## Dosya Yapısı

```
~/whatsapp-api/
├── src/
│   ├── index.js       # Ana sunucu
│   ├── database.js    # SQLite veritabanı
│   └── whatsapp.js    # Baileys WhatsApp bağlantısı
├── panel/
│   ├── index.html     # Admin paneli
│   ├── musteri.html   # Müşteri paneli
│   ├── toplu.html     # Toplu mesaj
│   └── kayit.html     # Kurulum sayfası
├── data/
│   └── database.bin   # Veritabanı (yedekle!)
├── logs/
│   └── server.log
├── .env               # Gizli ayarlar (JWT_SECRET, PORT)
├── package.json
└── reset-password.js
```

> **Önemli:** `data/database.bin` ve `.env` dosyalarını düzenli yedekle. Bunlar silinirse tüm müşteri verileri ve oturumlar kaybolur.
