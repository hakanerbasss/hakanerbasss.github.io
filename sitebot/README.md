# SiteBot — web sitesi kuran ve yöneten panel

Bilgileri gir, ~60 saniye sonra müşterinin sitesi kendi alan adında,
sertifikalı ve kendi yönetim paneliyle yayında olsun.

```
Sen  →  kur.wizaicorp.com (sunucu :8003)
             │
             ├─ GitHub API      → repo aç, dosyaları bas, Pages'i aç
             ├─ Cloudflare API  → hurdaci.wizaicorp.com CNAME kaydı
             └─ SQLite          → içerik, kullanıcılar, oturumlar
                      ↓
        https://hurdaci.wizaicorp.com/         ← müşterinin sitesi (GitHub Pages)
        https://hurdaci.wizaicorp.com/admin/   ← müşterinin yönetim paneli
```

**Üretilen sitelerin hiçbiri bu sunucuda barınmaz.** Hepsi GitHub Pages'te
durur; sunucu kapansa bile siteler ayakta kalır. Sunucu yalnızca içerik
düzenlenirken ve yayınlanırken devreye girer.

## Kurulum

### 1. Sunucuda

```bash
cd /root/hakanerbasss.github.io/sitebot
bash setup-venv.sh                      # kendi .venv'i — sistem Python'una dokunma
cp sitebot.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now sitebot
systemctl status sitebot
```

### 2. nginx + alan adı

`kur.wizaicorp.com` için Cloudflare'da **A kaydı** aç (77.42.45.229,
DNS-only/gri bulut), sonra:

```bash
cp nginx-sitebot.conf /etc/nginx/sites-available/sitebot
ln -s /etc/nginx/sites-available/sitebot /etc/nginx/sites-enabled/
certbot --nginx -d kur.wizaicorp.com
nginx -t && systemctl reload nginx
```

### 3. İlk açılış

`https://kur.wizaicorp.com/` → kurulum ekranı çıkar, yönetici şifresini
belirle. Sonra **Ayarlar** sekmesinden anahtarları gir ve
**"Anahtarları test et"** ile doğrula:

| Anahtar | Nereden |
|---|---|
| GitHub fine-grained token | GitHub → Settings → Developer settings. Kapsam: org `wizaicorp`. İzinler: **Administration**, **Contents**, **Pages** → Read and write |
| Cloudflare API token | Cloudflare → My Profile → API Tokens → **Edit zone DNS**, zone: wizaicorp.com |
| Cloudflare Zone ID | wizaicorp.com → Overview sayfasının sağ altı |

### 4. Bir kerelik: GitHub'da alan adı doğrulaması

GitHub org → Settings → Pages → **Verified domains** → `wizaicorp.com` ekle,
istediği TXT kaydını Cloudflare'a gir. Bu, başkasının senin alan adını kendi
reposuna bağlamasını engeller.

## Günlük kullanım

1. **Yeni site** sekmesi → firma adı, adres, şablon, müşteri e-postası
2. **Siteyi kur** → ekranda müşteriye vereceğin panel adresi + şifre çıkar
   (şifre bir daha gösterilmez)
3. Müşteri `https://<adres>.wizaicorp.com/admin/` adresinden girip her şeyi
   kendi düzenler

## Şablonlar

Üçü de **aynı veri şemasını** okur — müşteri şablon değiştirdiğinde ürünleri,
fiyatları, görselleri aynen yeni tasarıma taşınır.

| Şablon | Kime |
|---|---|
| `hizmet` | Nakliye, hurdacı, tamirci, temizlik — büyük çağrı butonları, hizmet kartları |
| `katalog` | Fiyatlı ürün vitrini, kategori filtresi, sipariş butonu |
| `kurumsal` | Ajans, danışmanlık, mimarlık — geniş görseller, sade tipografi |

Yeni şablon eklemek: `site_templates/<ad>/index.html.j2` oluştur, `schema.py`
içindeki `TEMPLATES` sözlüğüne ekle. Ortak parçalar (menü, iletişim bölümü,
WhatsApp butonu, sosyal ikonlar) `site_templates/_shared/parts.html.j2`
içinde macro olarak duruyor.

## Kod yapısı

| Dosya | İş |
|---|---|
| `app.py` | FastAPI, CORS, arayüz yönlendirmeleri |
| `schema.py` | Ortak veri şeması, şablon/palet listeleri, doğrulama |
| `renderer.py` | Jinja2 ile bitmiş statik HTML üretimi |
| `provisioner.py` | Kurulum ve yayınlama akışı |
| `github_api.py` | Repo, tek-commit push, Pages, özel alan adı |
| `cloudflare_api.py` | DNS kaydı aç/güncelle/sil |
| `images.py` | WebP'ye çevirme, boyutlandırma, alan sınırı |
| `auth.py` | scrypt şifre, oturum, slug doğrulama |
| `db.py` | SQLite — siteler, kullanıcılar, oturumlar, görseller, günlük |
| `routers/admin.py` | Müşteri paneli API'si (kiracı izolasyonu burada) |
| `routers/superadmin.py` | Senin panelin |
| `panel/site_admin.html` | Müşteri paneli — her siteye kopyalanır |
| `panel/super.html` | Senin yönetim ekranın |

## Bilinmesi gerekenler

- **Kaydet ≠ Yayınla.** Kaydet taslağı sunucuda tutar; Yayınla tek commit
  atar. GitHub Pages repo başına saatte 10 derleme sınırı koyduğu için bu
  ayrım bilerek var — müşteri 30 kere kaydetse bile tek commit gider.
- **Görseller yayınla anında** aynı commit'e biner. O ana kadar sunucuda
  `uploads/<site_id>/` altında bekler.
- **Türkçe karakter alan adında kullanılmaz.** `hurdacı` → `hurdaci`
  otomatik çevrilir; punycode alan adlarında Pages sertifikası sorun
  çıkarıyor.
- **Ayrılmış alt alan adları** `config.py` → `RESERVED_SUBDOMAINS`. Sunucudaki
  mevcut servisler (panel, wa, bathonea, hakanerbas…) burada; yeni servis
  eklersen listeye de ekle.
- **Abonelik bitince** siteyi silme, paneli kilitle: müşterinin sitesi yayında
  kalır, yalnızca düzenleme kapanır.
- **Repolar public.** GitHub Pages ücretsiz planda böyle çalışıyor. Repoya
  hiçbir anahtar yazılmıyor — müşteri paneli de sadece API adresini biliyor,
  tüm yetkilendirme sunucuda.

## Test

```bash
cd sitebot && .venv/bin/python test_smoke.py
```

GitHub ve Cloudflare taklit edilir; gerçek repo açılmaz, anahtar gerekmez.
Site açma, giriş, içerik kaydetme, görsel yükleme, üç şablonun da aynı veriyle
render olması, tek-commit yayın, kiracı izolasyonu ve abonelik kilidi kontrol
edilir.

## Ayarlar ve gizli veriler

`settings.json`, `sitebot.db`, `uploads/` git'e **dahil değil** (`.gitignore`).
Yedek alırken bu üçünü al — sitelerin tüm içeriği burada.
