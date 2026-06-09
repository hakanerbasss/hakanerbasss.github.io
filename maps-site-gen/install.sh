#!/bin/bash
# maps-site-gen kurulum — Linux/Termux için

set -e

IS_TERMUX=false
[[ -d /data/data/com.termux ]] && IS_TERMUX=true

echo "=============================="
echo " maps-site-gen Kurulum"
echo " Ortam: $( $IS_TERMUX && echo 'Termux (Android)' || echo 'Linux')"
echo "=============================="

if $IS_TERMUX; then
  echo "[Termux] Paketler güncelleniyor..."
  pkg update -y
  pkg install -y python chromium
  # Termux'ta Playwright sistem Chromium'unu kullanır
  export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="$(which chromium-browser 2>/dev/null || which chromium 2>/dev/null)"
  echo "export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=\"$PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH\"" >> ~/.bashrc
else
  if ! command -v python3 &>/dev/null; then
    echo "[!] Python 3 bulunamadı."
    exit 1
  fi
fi

echo "[1/3] Python bağımlılıkları yükleniyor..."
pip install -r requirements.txt

if $IS_TERMUX; then
  echo "[2/3] Termux: Playwright sistem Chromium kullanacak, tarayıcı indirme atlanıyor."
  python -c "from playwright.sync_api import sync_playwright; print('[OK] Playwright hazır')" 2>/dev/null || true
else
  echo "[2/3] Playwright Chromium indiriliyor..."
  playwright install chromium
fi

# .env oluştur
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[3/3] .env dosyası oluşturuldu. Düzenleyebilirsiniz:"
  echo "  nano .env"
fi

echo ""
echo "=============================="
echo " Kurulum Tamamlandı!"
echo "=============================="
echo ""
echo " Web uygulamasını başlatmak için:"
echo "   python app.py"
echo ""
echo " Sonra tarayıcıda aç:"
echo "   http://localhost:5000"
echo ""
if $IS_TERMUX; then
  echo " Termux'tan telefon tarayıcısında aç:"
  echo "   http://127.0.0.1:5000"
fi
