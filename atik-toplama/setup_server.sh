#!/bin/bash
# Atik Toplama — Bir kez çalıştırılan sunucu kurulum betiği
# Kullanım: bash setup_server.sh
# Çalıştırmadan önce: SSH ile sunucuya bağlan, bu betiği ~/atik-toplama/ altına kopyala

set -e

APP_DIR="$HOME/atik-toplama"
VENV="$APP_DIR/venv"
DEST="$APP_DIR/atik-toplama"
SERVICE="atik-toplama"
PORT=5057

echo "=== Atik Toplama Kurulum ==="
echo "Hedef dizin: $DEST"
echo ""

# 1. Dizinleri oluştur
mkdir -p "$DEST"
echo "[1/6] Dizinler oluşturuldu."

# 2. Python venv kur (yoksa)
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    echo "[2/6] Sanal ortam oluşturuldu: $VENV"
else
    echo "[2/6] Sanal ortam zaten mevcut."
fi

# 3. Gereksinimler (requirements.txt varsa)
if [ -f "$DEST/requirements.txt" ]; then
    "$VENV/bin/pip" install -q -r "$DEST/requirements.txt"
    echo "[3/6] Python paketleri yüklendi."
else
    "$VENV/bin/pip" install -q Flask==3.0.3 requests==2.32.3 Werkzeug==3.0.4
    echo "[3/6] Python paketleri yüklendi (requirements.txt bulunamadı, varsayılanlar kullanıldı)."
fi

# 4. config.json oluştur (yoksa)
if [ ! -f "$DEST/config.json" ]; then
    cat > "$DEST/config.json" <<EOF
{
  "secret_key": "$(python3 -c 'import secrets; print(secrets.token_hex(32))')",
  "telegram_bot_token": "BURAYA_BOT_TOKEN_YAZ",
  "telegram_chat_id": "BURAYA_CHAT_ID_YAZ",
  "neighborhood_telegram_chats": {}
}
EOF
    echo "[4/6] config.json oluşturuldu — lütfen Telegram bilgilerini girin:"
    echo "      nano $DEST/config.json"
else
    echo "[4/6] config.json zaten mevcut."
fi

# 5. Veritabanını başlat + ilçe + admin kullanıcı ekle
cd "$DEST"
if [ ! -f "$DEST/saha.db" ]; then
    "$VENV/bin/python" manage.py initdb
    echo "[5/6] Veritabanı başlatıldı."

    # İlçe adını sor
    read -p "İlçe adı (örn. Avcılar): " DISTRICT_NAME
    DISTRICT_NAME="${DISTRICT_NAME:-Avcılar}"
    "$VENV/bin/python" manage.py adddistrict "$DISTRICT_NAME"

    # Admin kullanıcı oluştur
    echo ""
    echo "--- Şantiye Amiri (admin) kullanıcısı oluştur ---"
    read -p "Kullanıcı adı [admin]: " ADMIN_USER
    ADMIN_USER="${ADMIN_USER:-admin}"
    read -s -p "Şifre: " ADMIN_PASS
    echo ""
    read -p "Görünen ad [Şantiye Amiri]: " ADMIN_DISPLAY
    ADMIN_DISPLAY="${ADMIN_DISPLAY:-Şantiye Amiri}"
    "$VENV/bin/python" manage.py adduser "$ADMIN_USER" "$ADMIN_PASS" "$ADMIN_DISPLAY" santiye_amiri 1
    echo "Admin kullanıcısı oluşturuldu."
else
    echo "[5/6] Veritabanı zaten mevcut."
fi

# 6. systemd servis dosyasını oluştur
SERVICE_FILE="/etc/systemd/system/$SERVICE.service"
if [ ! -f "$SERVICE_FILE" ]; then
    if command -v sudo &>/dev/null; then
        sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Atik Toplama Saha Yönetim
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DEST
ExecStart=$VENV/bin/python app.py
Restart=on-failure
RestartSec=5
Environment=PORT=$PORT

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable "$SERVICE"
        sudo systemctl start "$SERVICE"
        echo "[6/6] systemd servisi oluşturuldu ve başlatıldı."
        echo ""
        sudo systemctl status "$SERVICE" --no-pager
    else
        echo "[6/6] sudo bulunamadı — servis dosyasını manuel oluşturun:"
        echo "      $SERVICE_FILE"
    fi
else
    echo "[6/6] systemd servisi zaten mevcut."
fi

echo ""
echo "=== Kurulum Tamamlandı ==="
echo "Uygulama: http://localhost:$PORT"
echo ""
echo "Sonraki adımlar:"
echo "  1. Telegram token ve chat_id bilgilerini girin: nano $DEST/config.json"
echo "  2. Çavuş/personel ekle: cd $DEST && $VENV/bin/python manage.py adduser ..."
echo "  3. GitHub Secrets'a SSH bilgilerini gir (deploy otomatik çalışır):"
echo "     SSH_HOST, SSH_USER, SSH_KEY"
echo "  4. Nginx veya ters proxy ile port $PORT'ü dışarıya aç"
