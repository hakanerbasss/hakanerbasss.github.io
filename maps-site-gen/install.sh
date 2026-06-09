#!/bin/bash
# maps-site-gen kurulum — Termux + Linux

set -e

IS_TERMUX=false
[[ -d /data/data/com.termux ]] && IS_TERMUX=true

echo "=============================="
echo " maps-site-gen Kurulum"
if $IS_TERMUX; then
  echo " Ortam: Termux (Android)"
else
  echo " Ortam: Linux/Sunucu"
fi
echo "=============================="

echo ""
echo "[1/2] Python bağımlılıkları yükleniyor..."
echo "      (flask, requests, jinja2, instaloader...)"
pip install -r requirements.txt

echo ""
echo "[2/2] .env dosyası oluşturuluyor..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  ✓ .env oluşturuldu"
else
  echo "  ✓ .env zaten var"
fi

echo ""
echo "=============================="
echo " ✅ Kurulum Tamamlandı!"
echo "=============================="
echo ""
echo " Başlatmak için:"
echo "   python app.py"
echo ""
echo " Tarayıcıda aç:"
if $IS_TERMUX; then
  echo "   http://127.0.0.1:5000"
else
  echo "   http://localhost:5000"
  echo "   veya http://SUNUCU_IP:5000"
fi
echo ""
echo " NOT: Varsayılan olarak Overpass/OpenStreetMap kullanılır."
echo " Google Places API için .env dosyasına key ekle:"
echo "   nano .env"
