#!/bin/bash
# Yeni sunucuya atik-toplama kurulum scripti
# Kullanım: bash setup-server.sh
set -e

REPO_URL="https://github.com/hakanerbasss/hakanerbasss.github.io.git"
APP_DIR="$HOME/atik-toplama/atik-toplama"
VENV_DIR="$HOME/atik-toplama/venv"
REPO_DIR="$HOME/hakanerbasss.github.io"
SERVICE_NAME="atik-toplama"
APP_PORT=5000

echo "==> Sistem paketleri güncelleniyor..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git nginx curl

echo "==> Repo klonlanıyor..."
if [ -d "$REPO_DIR" ]; then
  cd "$REPO_DIR" && git pull origin main
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "==> Uygulama dizini hazırlanıyor..."
mkdir -p "$APP_DIR"
cd "$REPO_DIR"

cp atik-toplama/app.py           "$APP_DIR/"
cp atik-toplama/db.py            "$APP_DIR/"
cp atik-toplama/overpass.py      "$APP_DIR/"
cp atik-toplama/telegram_notify.py "$APP_DIR/"
cp atik-toplama/manage.py        "$APP_DIR/"
cp atik-toplama/requirements.txt "$APP_DIR/"
cp -r atik-toplama/templates     "$APP_DIR/"
cp -r atik-toplama/static        "$APP_DIR/"

echo "==> Python sanal ortamı kuruluyor..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q gunicorn
"$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> systemd servisi oluşturuluyor..."
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Atik Toplama Flask App
After=network.target

[Service]
User=root
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/gunicorn -w 2 -b 127.0.0.1:${APP_PORT} app:app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "==> Nginx yapılandırılıyor..."
cat > /etc/nginx/sites-available/${SERVICE_NAME} <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    location /static/ {
        alias ${APP_DIR}/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "✅ Kurulum tamamlandı!"
echo "   Uygulama: http://77.42.45.229/"
echo ""
echo "⚠️  VERİTABANINI TAŞIMAYI UNUTMA:"
echo "   Eski sunucuda çalıştır:"
echo "   scp root@45.143.4.169:~/atik-toplama/atik-toplama/atik.db root@77.42.45.229:${APP_DIR}/atik.db"
echo "   Sonra: systemctl restart atik-toplama"
