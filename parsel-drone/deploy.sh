#!/bin/bash
set -e

PROJECT_DIR="/root/parsel-drone"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "==> Klasör oluşturuluyor..."
mkdir -p "$BACKEND_DIR" "$FRONTEND_DIR"

echo "==> Dosyalar kopyalanıyor..."
cp backend/*.py backend/requirements.txt "$BACKEND_DIR/"
cp frontend/index.html "$FRONTEND_DIR/"

echo "==> Python venv kuruluyor..."
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --quiet -r requirements.txt

echo "==> Systemd servisi yazılıyor..."
cat > /etc/systemd/system/parsel-drone.service << 'EOF'
[Unit]
Description=Parsel Drone API
After=network.target

[Service]
User=root
WorkingDirectory=/root/parsel-drone/backend
ExecStart=/root/parsel-drone/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 3001
Restart=always
RestartSec=5
Environment=SECRET_KEY=BURAYA_GIZLI_ANAHTAR_YAZ

[Install]
WantedBy=multi-user.target
EOF

echo "==> Servis başlatılıyor..."
systemctl daemon-reload
systemctl enable parsel-drone
systemctl restart parsel-drone

echo "==> Nginx kuruluyor (yoksa)..."
if ! command -v nginx &> /dev/null; then
    apt-get update -qq && apt-get install -y -qq nginx
fi
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

echo "==> Nginx config yazılıyor..."
cat > /etc/nginx/sites-available/parsel-drone << 'EOF'
server {
    listen 80;
    server_name _;  # domain alınca buraya yaz

    # Frontend
    location / {
        root /root/parsel-drone/frontend;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:3001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /health {
        proxy_pass http://127.0.0.1:3001/health;
    }
}
EOF

ln -sf /etc/nginx/sites-available/parsel-drone /etc/nginx/sites-enabled/parsel-drone
nginx -t && systemctl reload nginx

echo ""
echo "✓ Deploy tamamlandı!"
echo "  API:      http://45.143.4.169:3001"
echo "  Frontend: http://45.143.4.169:80"
echo ""
echo "YAPILACAKLAR:"
echo "  1. frontend/index.html içindeki YOUR_CESIUM_ION_TOKEN değerini gir"
echo "  2. parsel-drone.service içindeki SECRET_KEY değerini değiştir"
echo "  3. Domain alınca nginx config güncelle + certbot ile SSL ekle"
