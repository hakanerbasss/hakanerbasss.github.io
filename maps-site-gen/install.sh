#!/bin/bash
# maps-site-gen kurulum scripti
set -e

echo "=== maps-site-gen Kurulum ==="

# Python kontrolü
if ! command -v python3 &>/dev/null; then
  echo "[!] Python 3 bulunamadı. Lütfen kurun: https://python.org"
  exit 1
fi

# pip ile bağımlılıkları yükle
echo "[1/3] Python bağımlılıkları yükleniyor..."
pip install -r requirements.txt

# Playwright tarayıcılarını yükle
echo "[2/3] Playwright Chromium yükleniyor..."
playwright install chromium

echo "[3/3] Kurulum tamamlandı!"
echo ""
echo "Kullanım örnekleri:"
echo ""
echo "  # Tüm pipeline (ara + site üret):"
echo "  python main.py run --query 'restoran' --location 'Kadıköy İstanbul' --max 10"
echo ""
echo "  # Sadece arama (JSON kaydet):"
echo "  python main.py search -q 'berber' -l 'Beşiktaş' -o isletmeler.json"
echo ""
echo "  # JSON'dan site üret:"
echo "  python main.py generate -j isletmeler.json -o output/"
echo ""
echo "  # Demo (scraping yapmadan test):"
echo "  python main.py demo --name 'Test Kafe' --category 'Kafe'"
echo ""
echo "  # GitHub Pages deploy:"
echo "  python deploy.py gh-pages --output output/ --repo kullanici/repo"
echo ""
echo "  # Yerel önizleme:"
echo "  python deploy.py serve --output output/"
