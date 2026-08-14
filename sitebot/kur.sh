#!/usr/bin/env bash
#
# SiteBot tek komutluk kurulum.
#
#   bash /root/hakanerbasss.github.io/sitebot/kur.sh
#
# Yaptiklari: kendi .venv'ini kurar, systemd servisini acar (port 8003),
# nginx'i ayarlar ve kur.wizaicorp.com icin SSL sertifikasi alir.
#
# Sunucudaki diger servislere (supertonic 8001, instube 8002, whatsapp 8000,
# bathonea 5001, atik-toplama 5057, kripto-bot 5000) hic dokunmaz.
#
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
DOMAIN="${SITEBOT_DOMAIN:-kur.wizaicorp.com}"
PORT=8003

say(){ printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
ok(){  printf "\033[1;32m    ✓ %s\033[0m\n" "$*"; }
die(){ printf "\n\033[1;31m HATA: %s\033[0m\n\n" "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "Bu betigi root olarak calistir."

# --- 1. Port bos mu? -------------------------------------------------------
say "Port $PORT kontrol ediliyor"
if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
    ss -tlnp | grep ":$PORT "
    die "Port $PORT kullanimda. Yukaridaki servisi durdur ya da sitebot.service ve
       nginx-sitebot.conf icindeki portu degistir."
fi
ok "Port $PORT bos"

# --- 2. Python ortami ------------------------------------------------------
say "Python sanal ortami kuruluyor (sistem Python'una dokunulmuyor)"
command -v python3 >/dev/null || die "python3 bulunamadi."
python3 -m venv "$DIR/.venv" 2>/dev/null || true
[ -x "$DIR/.venv/bin/pip" ] || die "venv kurulamadi. 'apt install python3-venv' deneyin."
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"
ok "Paketler kuruldu"

# --- 3. Kendi testini calistir --------------------------------------------
say "Sistem testi calistiriliyor"
if "$DIR/.venv/bin/python" "$DIR/test_smoke.py" >/tmp/sitebot-test.log 2>&1; then
    ok "Test gecti (site acma, giris, gorsel, yayin, kiracı izolasyonu)"
else
    tail -20 /tmp/sitebot-test.log
    die "Test basarisiz. Yukaridaki ciktiyi paylas."
fi

# --- 4. systemd servisi ----------------------------------------------------
say "Servis kuruluyor"
sed "s|/root/hakanerbasss.github.io/sitebot|$DIR|g" "$DIR/sitebot.service" \
    > /etc/systemd/system/sitebot.service
systemctl daemon-reload
systemctl enable --now sitebot >/dev/null 2>&1
sleep 3
systemctl is-active --quiet sitebot || {
    journalctl -u sitebot -n 25 --no-pager
    die "Servis baslamadi. Yukaridaki kaydi paylas."
}
curl -fsS "http://127.0.0.1:$PORT/saglik" >/dev/null || die "Servis yanit vermiyor."
ok "sitebot servisi calisiyor (port $PORT)"

# --- 5. nginx --------------------------------------------------------------
say "nginx ayarlaniyor ($DOMAIN)"
command -v nginx >/dev/null || die "nginx kurulu degil: apt install nginx"

# Sertifika henuz yokken nginx acilabilsin diye once sadece port 80.
cat > /etc/nginx/sites-available/sitebot <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    client_max_body_size 16m;
    location / {
        proxy_pass         http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/sitebot /etc/nginx/sites-enabled/sitebot
nginx -t >/dev/null 2>&1 || { nginx -t; die "nginx ayari hatali."; }
systemctl reload nginx
ok "nginx hazir"

# --- 6. SSL ----------------------------------------------------------------
say "SSL sertifikasi aliniyor"
SERVER_IP="$(curl -fsS --max-time 10 https://api.ipify.org 2>/dev/null || echo '')"
DNS_IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo '')"

if [ -z "$DNS_IP" ]; then
    cat <<MSG

  ⚠  $DOMAIN henuz hicbir yere bakmiyor.

     Cloudflare'da su kaydi ekle, sonra bu betigi tekrar calistir:
        Tur    : A
        Isim   : kur
        Icerik : ${SERVER_IP:-<sunucu-ip>}
        Proxy  : KAPALI (gri bulut)  ← certbot icin sart

     Kayit yayilmasi 1-2 dakika surer.

MSG
    ok "Servis calisiyor; DNS kaydini ekleyince tekrar calistir"
    exit 0
fi

if ! command -v certbot >/dev/null; then
    apt-get install -y certbot python3-certbot-nginx >/dev/null 2>&1 \
        || die "certbot kurulamadi: apt install certbot python3-certbot-nginx"
fi

if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
       --register-unsafely-without-email --redirect >/tmp/sitebot-certbot.log 2>&1; then
    ok "Sertifika alindi"
else
    tail -12 /tmp/sitebot-certbot.log
    printf "\n  ⚠  Sertifika alinamadi. En sik sebep: Cloudflare'da turuncu bulut acik.\n"
    printf "     Gri buluta cevirip tekrar calistir. Site su an http:// ile calisiyor.\n\n"
fi

cat <<DONE

  ────────────────────────────────────────────────
   Kurulum bitti.

   Simdi tarayicida ac:  https://$DOMAIN/

   1) Yonetici sifreni belirle
   2) Ayarlar sekmesine gec, GitHub ve Cloudflare
      anahtarlarini yapistir, "Anahtarlari test et"e bas
   3) Yeni site sekmesinden ilk siteni ac

   Servis komutlari:
     systemctl status sitebot
     systemctl restart sitebot
     journalctl -u sitebot -f
  ────────────────────────────────────────────────

DONE
