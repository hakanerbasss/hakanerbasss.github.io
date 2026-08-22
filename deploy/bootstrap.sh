#!/bin/bash
# ============================================================================
# SIFIRDAN SUNUCU KURULUMU — supertonic-web (tts) + InsTube
# ============================================================================
# Bu script, boş bir Ubuntu sunucusunu tek komutla çalışır hâle getirir.
# ESKİ SUNUCUYA HİÇBİR BAĞIMLILIĞI YOKTUR — her şeyi GitHub'dan ve paket
# depolarından kurar. Token/API key GEREKMEZ: panel açılır, anahtarlar
# sonradan arayüzden girilir.
#
# Kullanım (yeni sunucuda root olarak):
#   curl -fsSL https://raw.githubusercontent.com/hakanerbasss/hakanerbasss.github.io/main/deploy/bootstrap.sh -o bootstrap.sh
#   bash bootstrap.sh
#
# Alan adlarını değiştirmek istersen:
#   MAIN_DOMAIN=ornek.com PANEL_DOMAIN=panel.ornek.com bash bootstrap.sh
#
# DNS zaten yeni sunucuya bakıyorsa HTTPS sertifikasını da alsın:
#   SSL=1 bash bootstrap.sh
#
# Tekrar tekrar çalıştırılabilir (idempotent) — yarım kalan bir kurulumu
# tamamlamak veya bozulan bir şeyi onarmak için yeniden çalıştırmak güvenlidir.
# ============================================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/hakanerbasss/hakanerbasss.github.io.git}"
REPO_DIR="${REPO_DIR:-/root/hakanerbasss.github.io}"
MAIN_DOMAIN="${MAIN_DOMAIN:-wizaicorp.com}"
NEWS_DOMAIN="${NEWS_DOMAIN:-hakanerbas.wizaicorp.com}"
PANEL_DOMAIN="${PANEL_DOMAIN:-panel.wizaicorp.com}"
SSL="${SSL:-0}"
SSL_EMAIL="${SSL_EMAIL:-wizaicorp@gmail.com}"

say() { echo ""; echo "==> $*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "HATA: root olarak çalıştır (sudo bash bootstrap.sh)." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 1) Sistem paketleri
# ---------------------------------------------------------------------------
say "Sistem paketleri kuruluyor (ffmpeg, nginx, python3-venv, fontlar)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  git curl ca-certificates \
  python3 python3-venv python3-pip \
  ffmpeg nginx libcairo2 \
  fonts-dejavu-core fonts-liberation fonts-freefont-ttf
# libcairo2: cairosvg/cairocffi libcairo.so.2'yi çalışma anında yüklüyor;
# minimal sunucu imajlarında bu kütüphane gelmiyor ve import anında patlıyor.
# Fontlar şart: açılış kapağındaki başlık/rozet bunlarla çiziliyor
# (supertonic-web/app.py → overlay_first_scene_banner, font_candidates).
# Eksikse PIL varsayılan bitmap fonta düşer ve kapak okunmaz hâle gelir.

# ---------------------------------------------------------------------------
# 2) Swap — 4GB'lık sunucuda ffmpeg/torch OOM'a düşüyor
# ---------------------------------------------------------------------------
# instube/README.md'de not edilen "exit 137 = bellek yetersiz" hatasının
# önlemi. Zaten swap varsa dokunulmaz.
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ]; then
  say "Swap alanı yok — 2G swap oluşturuluyor (ffmpeg/torch OOM koruması)..."
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap -q /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  say "Swap zaten var, atlanıyor."
fi

# ---------------------------------------------------------------------------
# 3) Depo
# ---------------------------------------------------------------------------
say "Depo hazırlanıyor: $REPO_DIR"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch origin main
  git -C "$REPO_DIR" reset --hard origin/main
else
  git clone --depth 50 "$REPO_URL" "$REPO_DIR"
fi

# ---------------------------------------------------------------------------
# 4) systemd birimleri (venv kurulumundan ÖNCE)
# ---------------------------------------------------------------------------
# setup-venv.sh sonunda tts.service'i güncelleyip yeniden başlatıyor; birim
# dosyası yoksa "elle oluştur" uyarısı verip çıkıyor. O yüzden önce yazılır.
say "systemd birimleri yazılıyor..."
for svc in tts instube; do
  sed "s#__REPO_DIR__#${REPO_DIR}#g" \
    "$REPO_DIR/deploy/systemd/${svc}.service" > "/etc/systemd/system/${svc}.service"
  echo "    /etc/systemd/system/${svc}.service"
done
systemctl daemon-reload

# ---------------------------------------------------------------------------
# 5) Python venv'leri + bağımlılıklar
# ---------------------------------------------------------------------------
# NOT: Burada bilinçli olarak supertonic-web/setup-venv.sh ÇAĞRILMIYOR.
# O script mevcut sunucu için yazıldı ve paketleri "--no-deps" ile kuruyor —
# çünkü orada torch/whisper zaten SİSTEM Python'unda kuruluydu ve amaç onları
# tekrar indirmemekti. BOŞ bir sunucuda o varsayım çöker: --no-deps, alt
# bağımlılıkları (starlette, pydantic, click, h11...) hiç kurmaz ve uygulama
# import anında patlar. Sıfırdan kurulumda paketler bağımlılıklarıyla kurulur.
ST_VENV="$REPO_DIR/supertonic-web/.venv"
IG_VENV="$REPO_DIR/instube/.venv"

say "supertonic-web bağımlılıkları kuruluyor (uzun sürebilir, ~2 GB indirme)..."
[ -d "$ST_VENV" ] || python3 -m venv "$ST_VENV"
"$ST_VENV/bin/pip" install -q --upgrade pip
# setuptools<81 ZORUNLU: openai-whisper'ın setup.py'si pkg_resources import
# ediyor, setuptools 81 ise pkg_resources'ı tamamen kaldırdı. Güncel setuptools
# ile kurulum "ModuleNotFoundError: No module named 'pkg_resources'" ile
# patlıyor — üstelik toplu kurulumun TAMAMI çözümleme aşamasında düşüyor,
# yani tek bir paket yüzünden hiçbir şey kurulmuyor. (22.08.2026'da boş bir
# venv'de birebir doğrulandı.)
"$ST_VENV/bin/pip" install -q "setuptools<81" wheel

# torch: whisper'ın bağımlılığı. PyPI'daki varsayılan linux wheel'i CUDA'lı
# geliyor ve yanında ~3,4 GB GPU paketi (nvidia-*, triton) sürüklüyor —
# CPU sunucusunda tamamen ölü yük. CPU-only depo denenir, erişilemezse
# standart sürüme düşülür (kurulum yine çalışır, sadece yer kaplar).
if ! "$ST_VENV/bin/pip" install -q torch --index-url https://download.pytorch.org/whl/cpu; then
  echo "    UYARI: CPU-only torch alınamadı, standart sürüm kuruluyor (~3,4 GB fazla yer)."
  "$ST_VENV/bin/pip" install -q torch
fi

# --no-build-isolation: whisper'ı venv'in KENDİ setuptools<81'iyle derlet.
# İzole derleme ortamı kendi (güncel) setuptools'unu kurduğu için PIP_CONSTRAINT
# ile sabitlemek işe yaramıyor — bu da doğrulandı.
"$ST_VENV/bin/pip" install -q --no-build-isolation openai-whisper==20240930

# Kalanı normal kurulur; whisper/torch zaten karşılandığı için tekrar derlenmez.
"$ST_VENV/bin/pip" install -q -r "$REPO_DIR/supertonic-web/requirements.txt"

say "InsTube bağımlılıkları kuruluyor..."
[ -d "$IG_VENV" ] || python3 -m venv "$IG_VENV"
"$IG_VENV/bin/pip" install -q --upgrade pip setuptools wheel
"$IG_VENV/bin/pip" install -q -r "$REPO_DIR/instube/requirements.txt"

# Kritik modüller gerçekten import edilebiliyor mu? Servisi başlatıp systemd'yi
# sonsuz restart döngüsüne sokmadan ÖNCE anlaşılsın.
say "Kurulum doğrulanıyor..."
# Listedekilerin hepsi app.py'de MODÜL SEVİYESİNDE import ediliyor — biri
# eksikse servis hiç ayağa kalkmaz, systemd sonsuz restart döngüsüne girer.
# whisper ve cairosvg özellikle önemli: ikisi de kurulumda patlamaya en yatkın
# olanlar (whisper kaynaktan derleniyor, cairosvg sistem kütüphanesi istiyor).
"$ST_VENV/bin/python" - <<'PY'
import sys
eksik = []
for m in ["fastapi", "uvicorn", "httpx", "openai", "edge_tts", "supertonic",
          "whisper", "cairosvg", "PIL", "playwright", "trafilatura", "apscheduler"]:
    try:
        __import__(m)
        print(f"    ok    : {m}")
    except Exception as e:
        eksik.append(m)
        print(f"    EKSİK : {m} -> {type(e).__name__}: {e}")
if eksik:
    print(f"\nHATA: şu modüller olmadan panel çalışmaz: {', '.join(eksik)}", file=sys.stderr)
    sys.exit(1)
PY

"$IG_VENV/bin/python" - <<'PY'
import sys
eksik = []
for m in ["fastapi", "uvicorn", "httpx", "openai", "supertonic", "PIL"]:
    try:
        __import__(m)
    except Exception as e:
        eksik.append(f"{m} ({type(e).__name__})")
if eksik:
    print(f"HATA: InsTube için eksik: {', '.join(eksik)}", file=sys.stderr)
    sys.exit(1)
print("    ok    : InsTube modülleri")
PY

# ---------------------------------------------------------------------------
# 6) Playwright + Chromium (custom-production / "Bilgi Merkezi" sekmesi)
# ---------------------------------------------------------------------------
# pip paketi tarayıcıyı indirmiyor; bu adım atlanırsa panel çökmez ama
# "Şimdi Üret ve Yayınla" butonu hata verir (custom-production/SISTEM_BILGI.md).
say "Playwright Chromium kuruluyor..."
"$ST_VENV/bin/playwright" install chromium --with-deps

# ---------------------------------------------------------------------------
# 7) Supertonic TTS modellerini şimdiden indir
# ---------------------------------------------------------------------------
# TTS(auto_download=True) modelleri ilk kullanımda indiriyor. Burada tetiklemek,
# indirme sorununu ilk video üretimi sırasında değil, kurulumda görmemizi sağlar.
say "Supertonic TTS modelleri indiriliyor..."
"$ST_VENV/bin/python" -c \
  "from supertonic import TTS; TTS(auto_download=True); print('    modeller hazır')" \
  || echo "    UYARI: model indirilemedi — ilk video üretiminde tekrar denenecek."

# ---------------------------------------------------------------------------
# 8) nginx
# ---------------------------------------------------------------------------
say "nginx yapılandırılıyor..."
sed -e "s#__MAIN_DOMAIN__#${MAIN_DOMAIN}#g" \
    -e "s#__NEWS_DOMAIN__#${NEWS_DOMAIN}#g" \
    "$REPO_DIR/deploy/nginx/supertonic-web.conf" > /etc/nginx/sites-available/supertonic-web
sed -e "s#__PANEL_DOMAIN__#${PANEL_DOMAIN}#g" \
    "$REPO_DIR/deploy/nginx/instube.conf" > /etc/nginx/sites-available/instube

ln -sf /etc/nginx/sites-available/supertonic-web /etc/nginx/sites-enabled/supertonic-web
ln -sf /etc/nginx/sites-available/instube        /etc/nginx/sites-enabled/instube
# Varsayılan site kaldırılmazsa default_server çakışması nginx'i başlatmıyor.
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# ---------------------------------------------------------------------------
# 9) Servisleri başlat
# ---------------------------------------------------------------------------
say "Servisler başlatılıyor..."
systemctl enable --now tts instube
sleep 3
systemctl --no-pager --lines=0 status tts     || true
systemctl --no-pager --lines=0 status instube || true

# ---------------------------------------------------------------------------
# 10) HTTPS (opsiyonel — DNS bu sunucuya bakıyorsa)
# ---------------------------------------------------------------------------
if [ "$SSL" = "1" ]; then
  say "Let's Encrypt sertifikaları alınıyor..."
  apt-get install -y -qq certbot python3-certbot-nginx
  # DNS henüz taşınmadıysa bu adım başarısız olur ama kurulumun geri kalanı
  # ayakta kalsın — HTTP üzerinden panel yine çalışır.
  certbot --nginx --non-interactive --agree-tos -m "$SSL_EMAIL" \
    -d "$MAIN_DOMAIN" -d "$NEWS_DOMAIN" -d "$PANEL_DOMAIN" \
    || echo "    UYARI: certbot başarısız (DNS henüz bu sunucuya bakmıyor olabilir). Sonra tekrar dene: certbot --nginx"
else
  say "HTTPS atlandı (SSL=1 ile çalıştırırsan sertifika da alınır)."
fi

IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo 'SUNUCU_IP')"

cat <<SUMMARY

============================================================================
KURULUM TAMAM
============================================================================
Panel (bot)     : http://${IP}/          → giriş şifresi: instube2026
InsTube         : http://${IP}:8002/     (veya https://${PANEL_DOMAIN} — DNS taşınınca)
Haber sitesi    : http://${NEWS_DOMAIN}/ (DNS taşınınca)

SIRADAKİ ADIMLAR — bunlar elle yapılır, kod tarafı hazır:

  1. DNS: ${MAIN_DOMAIN}, ${NEWS_DOMAIN}, ${PANEL_DOMAIN} A kayıtlarını
     ${IP} adresine çevir. Sonra: SSL=1 bash bootstrap.sh

  2. Panele gir (şifre: instube2026), Ayarlar'dan gir:
       - DeepSeek API key, Pexels key (zorunlu), OpenAI (opsiyonel)
       - Instagram: Business User ID + uzun ömürlü Access Token
       - YouTube: Client ID/Secret + kanal yetkilendirme
     ŞİFREYİ DEĞİŞTİR — varsayılan şifre herkesçe bilinir.

  3. YouTube OAuth: Google Cloud Console'da izinli yönlendirme URI'leri
     yeni domaine göre olmalı:
       https://${PANEL_DOMAIN}/auth/youtube/callback
       https://${PANEL_DOMAIN}/auth/youtube/en/callback

  4. GitHub Actions kullanan projeler (atik-toplama, bathonea, whatsapp-api,
     kripto-bot): depo ayarlarındaki SSH_HOST / ATIK_SSH_HOST secret'larını
     ${IP} yap, yoksa otomatik deploy eski sunucuya bağlanmaya çalışır.

Günlük deploy bundan sonra:
  cd ${REPO_DIR} && git pull && systemctl restart tts instube
============================================================================
SUMMARY
