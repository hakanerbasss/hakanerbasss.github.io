#!/bin/bash
# WhatsApp API Server - VPS İlk Kurulum Scripti
# Kullanım: bash setup-vps.sh
# Sadece bir kere çalıştır. Sonraki güncellemeler GitHub Actions ile gelir.

set -e

G='\033[0;32m'; C='\033[0;36m'; R='\033[0;31m'; Y='\033[0;33m'; X='\033[0m'
ok()   { echo -e "${G} OK  ${X} $1"; }
info() { echo -e "${C} ... ${X} $1"; }
err()  { echo -e "${R} HAT ${X} $1"; }

DEST=~/whatsapp-api

echo -e "\n${G}╔══════════════════════════════════════════╗"
echo    "║   WhatsApp API Server  -  VPS Kurulum   ║"
echo -e "╚══════════════════════════════════════════╝${X}\n"

# Node.js 20 kur (yoksa)
if ! command -v node &>/dev/null || [[ $(node -e "process.exit(parseInt(process.version.slice(1)) < 18 ? 1 : 0)" 2>/dev/null; echo $?) -ne 0 ]]; then
  info "Node.js 20 kuruluyor..."
  apt-get update -y -q
  apt-get install -y -q unzip curl
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null 2>&1
  apt-get install -y -q nodejs
  ok "Node.js $(node -v) kuruldu"
else
  ok "Node.js $(node -v) mevcut"
fi

# pm2 kur (yoksa)
if ! command -v pm2 &>/dev/null; then
  info "pm2 kuruluyor..."
  npm install -g pm2 --silent
  ok "pm2 kuruldu"
else
  ok "pm2 $(pm2 -v) mevcut"
fi

# Klasör oluştur
mkdir -p "$DEST/logs" "$DEST/data"
ok "Klasörler oluşturuldu: $DEST"

# Repo'dan dosyaları kopyala
REPO=~/hakanerbasss.github.io
if [ ! -d "$REPO" ]; then
  err "Repo bulunamadı: $REPO"
  err "Önce: git clone git@github.com:hakanerbasss/hakanerbasss.github.io.git ~/hakanerbasss.github.io"
  exit 1
fi

info "Dosyalar kopyalanıyor..."
cp -r "$REPO/whatsapp-api-server/src"   "$DEST/"
cp -r "$REPO/whatsapp-api-server/panel" "$DEST/"
cp    "$REPO/whatsapp-api-server/package.json"      "$DEST/"
cp    "$REPO/whatsapp-api-server/reset-password.js" "$DEST/"
ok "Dosyalar kopyalandı"

# npm install
info "Paketler yükleniyor (1-2 dakika)..."
cd "$DEST"
npm install --no-audit --no-fund --silent
ok "npm paketleri yüklendi"

# Baileys patch
info "Baileys patch uygulanıyor..."
BAILEYS_VALIDATE="$DEST/node_modules/baileys/lib/Utils/validate-connection.js"
BAILEYS_SOCKET="$DEST/node_modules/baileys/lib/Socket/socket.js"
if [ -f "$BAILEYS_VALIDATE" ]; then
  sed -i 's/passive: true,/passive: false,/g' "$BAILEYS_VALIDATE"
  sed -i '/lidDbMigrated: false/d' "$BAILEYS_VALIDATE"
fi
if [ -f "$BAILEYS_SOCKET" ]; then
  sed -i 's/await noise\.finishInit();/noise.finishInit();/g' "$BAILEYS_SOCKET"
fi
ok "Baileys patch tamamlandı"

# .env oluştur (yoksa)
if [ ! -f "$DEST/.env" ]; then
  SECRET=$(cat /proc/sys/kernel/random/uuid | tr -d '-')$(date +%s)
  cat > "$DEST/.env" <<EOF
PORT=80
JWT_SECRET=${SECRET}
EOF
  ok ".env oluşturuldu (PORT=80 — domain için)"
else
  ok ".env zaten var, dokunulmadı"
fi

# Port 80 kontrol
if ss -tlnp 2>/dev/null | grep -q ':80 ' || netstat -tlnp 2>/dev/null | grep -q ':80 '; then
  echo -e "\n${Y} UYR ${X} Port 80 başka bir servis tarafından kullanılıyor!"
  ss -tlnp 2>/dev/null | grep ':80 ' || netstat -tlnp 2>/dev/null | grep ':80 '
  echo -e "${Y} UYR ${X} nginx/apache varsa durdurun: systemctl stop nginx apache2"
  echo -e "${Y} UYR ${X} Devam etmek için Enter'a basın (veya Ctrl+C ile iptal)..."
  read -r
fi

# pm2 ile başlat
info "pm2 servisi başlatılıyor..."
cd "$DEST"
pm2 delete whatsapp-api 2>/dev/null || true
pm2 start src/index.js --name whatsapp-api --log logs/server.log
pm2 save

# systemd auto-start
info "Sunucu yeniden başlayınca otomatik başlasın diye ayarlanıyor..."
pm2 startup systemd -u root --hp /root 2>/dev/null | grep "sudo" | bash 2>/dev/null || true
pm2 save

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

echo -e "\n${G}╔══════════════════════════════════════════╗"
echo    "║  Kurulum tamamlandı!                    ║"
echo -e "║  Panel: http://${SERVER_IP} (port 80)      ║"
echo    "║  pm2 logs whatsapp-api   → loglar       ║"
echo    "║  pm2 restart whatsapp-api → yeniden     ║"
echo -e "╚══════════════════════════════════════════╝${X}"
