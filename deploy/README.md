# Sıfırdan Sunucu Kurulumu

Bu klasör, **boş bir Ubuntu sunucusunu** tek komutla çalışır hâle getirir.
Eski sunucuya hiçbir bağımlılığı yoktur — her şey GitHub'dan ve paket
depolarından kurulur. **Token/API key gerekmez**; panel açılır, anahtarlar
sonradan arayüzden girilir.

## Tek komut

Yeni sunucuda, root olarak:

```bash
curl -fsSL https://raw.githubusercontent.com/hakanerbasss/hakanerbasss.github.io/main/deploy/bootstrap.sh -o bootstrap.sh
bash bootstrap.sh
```

Bitince panele `http://SUNUCU_IP/` adresinden girilir — **varsayılan şifre:
`instube2026`** (ilk açılışta otomatik oluşur, hemen değiştir).

Alan adları farklıysa:
```bash
MAIN_DOMAIN=ornek.com NEWS_DOMAIN=haber.ornek.com PANEL_DOMAIN=panel.ornek.com bash bootstrap.sh
```

DNS zaten yeni sunucuya bakıyorsa HTTPS de alınsın:
```bash
SSL=1 bash bootstrap.sh
```

Script **tekrar çalıştırılabilir** — yarım kalan kurulumu tamamlamak veya
bozulan bir şeyi onarmak için yeniden çalıştırmak güvenlidir.

## Çalışan sunucuda çalıştırma koruması

Script, `/etc/systemd/system/tts.service` zaten varsa **durur**. Bu koruma
önemli, çünkü bu sunucuda tts/InsTube dışında başka siteler de var
(bathonea, WhatsApp API) ve çalışan bir sunucuda devam etmek şunları bozabilir:

- **nginx'i komple düşürebilir.** Buradaki yapılandırma `default_server`
  kullanıyor; sunucuda zaten `default_server` tanımlayan bir site varsa
  `nginx -t` düşer ve nginx bir daha kalkmaz — o sunucudaki **bütün siteler**
  gider. Ayrıca certbot'un ürettiği HTTPS blokları bu HTTP bloklarıyla
  çakışabilir.
- **systemd ayarlarını siler.** Sunucudaki birim dosyasında bu depoda
  kayıtlı olmayan ek ayarlar olabilir.
- **Çalışan venv'i oynatır.** Bu depoda tam olarak böyle bir kaza geçmişi
  var: httpx sürümü düşünce firebase-admin kırılmıştı.

Sadece kod güncellemek için bu yeter:
```bash
cd /root/hakanerbasss.github.io && git pull && systemctl restart tts instube
```

Gerçekten sıfırdan kurmak gerekiyorsa önce yedek al, sonra `FORCE=1 bash bootstrap.sh`.

## Ne kuruyor

| Adım | İçerik |
|---|---|
| Sistem paketleri | git, python3-venv, **ffmpeg**, nginx, **fontlar** (DejaVu/Liberation/FreeFont — açılış kapağı bunlarla çiziliyor) |
| Swap | Swap yoksa 2G ekler (4GB RAM'de ffmpeg/torch OOM koruması — `exit 137`) |
| Depo | `/root/hakanerbasss.github.io` olarak klonlar |
| systemd | `tts.service` (port 8001) + `instube.service` (port 8002) |
| Python | Her iki proje için **ayrı venv**, bağımlılıklarıyla birlikte |
| Playwright | Chromium indirir (Bilgi Merkezi sekmesi bunsuz çalışmaz) |
| Supertonic TTS | Modelleri şimdiden indirir (`TTS(auto_download=True)`) |
| nginx | Domainleri 8001/8002'ye yönlendirir, IP ile de erişilebilir |
| HTTPS | `SSL=1` ise Let's Encrypt sertifikası alır |

## Kurulumdan sonra elle yapılacaklar

Kod tarafı hazır, bunlar dışarıdan yapılan işler:

1. **DNS** — `wizaicorp.com`, `hakanerbas.wizaicorp.com`, `panel.wizaicorp.com`
   A kayıtlarını yeni IP'ye çevir, sonra `SSL=1 bash bootstrap.sh`.
2. **Anahtarlar** — panelden: DeepSeek + Pexels (zorunlu), OpenAI (opsiyonel),
   Instagram Business ID + uzun ömürlü token, YouTube Client ID/Secret.
   **Panel şifresini değiştir.**
3. **YouTube OAuth** — Google Cloud Console'daki izinli yönlendirme URI'leri
   yeni domaine göre olmalı:
   `https://panel.wizaicorp.com/auth/youtube/callback` (TR) ve
   `.../auth/youtube/en/callback` (EN). Yoksa kanal yetkilendirme
   `redirect_uri_mismatch` ile reddedilir.
4. **GitHub Actions** — `atik-toplama`, `bathonea`, `whatsapp-api`,
   `kripto-bot` iş akışları SSH ile sunucuya bağlanıyor. Depo ayarlarındaki
   `SSH_HOST` / `ATIK_SSH_HOST` secret'larını yeni IP yap.

## Kapsam dışı

Bu script **supertonic-web + InsTube** ikilisini kurar. Aynı depodaki diğer
projelerin kendi kurulum scriptleri var ve ayrı çalıştırılır:

- `atik-toplama/setup-server.sh`
- `whatsapp-api-server/setup-vps.sh` (Node.js + pm2 ister)
- `bathonea` ve `namaz-vakitleri` artık **kendi depolarında** (bkz. CLAUDE.md)

## Kurulumdaki üç tuzak (boş venv'de test edilip çözüldü)

Bunlar `bootstrap.sh` içinde zaten halledildi; buradaki not, ileride biri
"neden böyle yazılmış?" diye sorduğunda tekrar keşfedilmesin diye.

1. **`setuptools<81` zorunlu.** `openai-whisper`'ın `setup.py`'si
   `pkg_resources` import ediyor, setuptools 81 ise onu tamamen kaldırdı.
   Güncel setuptools'la kurulum `ModuleNotFoundError: No module named
   'pkg_resources'` veriyor — üstelik hata çözümleme aşamasında olduğu için
   **tek bir paket yüzünden hiçbir şey kurulmuyor**.
2. **`--no-build-isolation` şart.** pip, derleme için izole bir ortam kurup
   oraya kendi (güncel) setuptools'unu koyuyor; bu yüzden `PIP_CONSTRAINT`
   ile sabitlemek işe yaramıyor. whisper'ı venv'in kendi setuptools'uyla
   derletmenin tek yolu bu bayrak.
3. **torch'un CUDA sürümü ~3,4 GB ölü yük.** PyPI'daki varsayılan linux
   wheel'i GPU'lu geliyor ve yanında `nvidia-*` + `triton` sürüklüyor
   (ölçüldü: 4,9 GB venv, bunun 3,4 GB'ı GPU). CPU sunucusunda hiç
   kullanılmıyor, o yüzden önce CPU-only depo deneniyor.

`import whisper`, `app.py`'nin en üstünde (modül seviyesinde) — yani
kurulamazsa panel hiç açılmaz, "sonra hallederiz" denebilecek bir paket değil.
Bu yüzden bootstrap, servisleri başlatmadan önce kritik modülleri tek tek
import edip eksik varsa **durur**.

## Neden `supertonic-web/setup-venv.sh` çağrılmıyor?

O script **mevcut** sunucu için yazıldı: paketleri `--no-deps` ile kuruyor,
çünkü orada torch/whisper zaten sistem Python'unda kuruluydu ve amaç onları
tekrar indirmemekti (~2 GB tasarruf). **Boş** bir sunucuda o varsayım çöker —
`--no-deps`, alt bağımlılıkları (starlette, pydantic, click, h11...) hiç
kurmaz ve uygulama import anında patlar. `bootstrap.sh` bu yüzden kurulumu
kendisi, bağımlılıklarıyla birlikte yapar.

İkisi bir arada yaşamaya devam ediyor: `setup-venv.sh` mevcut sunucuda
onarım/yeni paket için, `bootstrap.sh` sıfırdan kurulum için.

## Günlük deploy

Kurulumdan sonra normal akış değişmiyor:

```bash
cd /root/hakanerbasss.github.io && git pull && systemctl restart tts instube
```

## Sorun giderme

```bash
systemctl status tts instube          # servis ayakta mı
journalctl -u tts -n 100 --no-pager   # son 100 satır log
nginx -t                              # nginx yapılandırma testi
curl -I http://127.0.0.1:8001/login   # panel gerçekten cevap veriyor mu
curl -I http://127.0.0.1:8002/        # InsTube cevap veriyor mu
```

Servis sürekli yeniden başlıyorsa neredeyse her zaman bir Python import
hatasıdır — `journalctl -u tts -n 50` ilk satırlarda gerçek sebebi gösterir.
