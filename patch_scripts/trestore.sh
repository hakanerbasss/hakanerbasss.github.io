#!/bin/bash
# trestore — tank_siege.html commit geçmişinden geri yükle
# v1.1 — git pull ile remote senkron, Claude commitleri [Claude] etiketiyle gösterir

REPO=~/hakanerbasss.github.io
FILE=tank-siege/tank_siege.html
TARGET=~/tank_siege.html

cd "$REPO" || { echo "❌ Repo bulunamadı: $REPO"; exit 1; }

# Remote'dan güncel commit listesini çek
git fetch origin --quiet 2>/dev/null
git merge --ff-only origin/HEAD --quiet 2>/dev/null

# Git log — son 30 commit
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   TANK SİEGE — KOMİT GEÇMİŞİ                       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

mapfile -t HASHES  < <(git log --oneline -30 -- "$FILE" | awk '{print $1}')
mapfile -t MSGS    < <(git log --oneline -30 -- "$FILE" | cut -d' ' -f2-)
mapfile -t DATES   < <(git log --format="%ad" --date=format:"%d.%m %H:%M" -30 -- "$FILE")
mapfile -t AUTHORS < <(git log --format="%an" -30 -- "$FILE")

if [ ${#HASHES[@]} -eq 0 ]; then
  echo "❌ Bu dosya için commit geçmişi bulunamadı."
  exit 1
fi

for i in "${!HASHES[@]}"; do
  MARK=""
  [[ "${AUTHORS[$i]}" != "hakanerbasss" ]] && MARK=" [Claude]"
  printf "  %2d. [%s] %s%s\n" "$((i+1))" "${DATES[$i]}" "${MSGS[$i]}" "$MARK"
done

echo ""
echo "  0. İptal"
echo ""
read -p "Seçim: " choice

if [[ "$choice" == "0" || -z "$choice" ]]; then
  echo "İptal edildi."
  cd ~
  exit 0
fi

if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#HASHES[@]}" ]; then
  echo "❌ Geçersiz seçim."
  cd ~
  exit 1
fi

idx=$((choice-1))
hash="${HASHES[$idx]}"
msg="${MSGS[$idx]}"
date="${DATES[$idx]}"

echo ""
echo "  Seçilen: [$date] $msg ($hash)"
echo "  [e] Yukle  -> ~/tank_siege.html'e kopyala"
echo "  [i] Indir  -> /sdcard/Download/tank_siege.html'e kaydet"
echo "  [h] Iptal"
echo ""
read -p "  Secim (e/i/h): " confirm

if [[ "$confirm" == "h" || "$confirm" == "H" || -z "$confirm" ]]; then
  echo "Iptal edildi."
  cd ~
  exit 0
fi

if [[ "$confirm" != "e" && "$confirm" != "E" && "$confirm" != "i" ]]; then
  echo "Gecersiz secim."
  cd ~
  exit 1
fi

if [[ "$confirm" == "i" ]]; then
  DEST="/sdcard/Download/tank_siege.html"
else
  DEST="$TARGET"
fi

git show "$hash:$FILE" > "$DEST"

if [ $? -eq 0 ]; then
  echo ""
  if [[ "$confirm" == "i" ]]; then
    echo "  ✅ Indirildi: $DEST"
  else
    echo "  ✅ Yuklendi: ~/tank_siege.html"
    echo "     Simdi 'tank' ile push edebilirsin."
  fi
  echo "   Versiyon: [$date] $msg"
  echo ""
else
  echo "❌ Dosya alinamadi."
fi
