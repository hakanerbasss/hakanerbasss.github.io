#!/bin/bash
# Oturum başı durum raporu.
#
# Her yeni Claude oturumu açıldığında otomatik çalışır ve şunu yazar:
#   - bu oturum hangi dalda ve main'in kaç commit gerisinde
#   - InsTube'a (ve diğer projelere) EN SON kim ne yaptı
#   - günlüğün en üstündeki kayıt
#   - üzerine yazma riski varsa NE YAPILACAĞI
#
# Amaç: farklı oturumların birbirinin işini ezmesini önlemek.
# Elle de çalıştırılabilir:  bash .claude/hooks/session-start.sh
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0

# Ağ yoksa/yavaşsa oturumu bekletme — rapor eksik çıkar, oturum yine açılır.
timeout 25 git fetch --quiet origin main 2>/dev/null

DAL="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
GERIDE="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)"
ILERIDE="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"

echo "════════ OTURUM DURUMU (kim ne yaptı) ════════"
echo "Dal: $DAL   |   main'in $GERIDE commit gerisinde, $ILERIDE commit ilerisinde"
echo

if [ "$GERIDE" -gt 0 ]; then
  echo "⚠️  BU KOPYA ESKİ. Başka bir oturum main'e $GERIDE commit push etmiş."
  echo "    Tek satırlık çözüm (kod yazmadan ÖNCE çalıştır):"
  echo "        git fetch origin main && git reset --hard origin/main"
  echo "    Bunu yapmadan dosya değiştirirsen o $GERIDE commit'i ezersin."
  echo
  echo "    Sen uyurken main'e ne girmiş:"
  git log --format='      %h  %ad  %s' --date=short HEAD..origin/main 2>/dev/null | head -15
  echo
fi

echo "── main'de InsTube'a en son yapılanlar ──"
IG_LOG="$(git log --format='  %h  %ad  %s' --date=short -6 origin/main -- instube/ 2>/dev/null)"
if [ -n "$IG_LOG" ]; then
  echo "$IG_LOG"
else
  echo "  (main'de instube/ klasörüne dokunan commit yok — iş başka dalda kalmış olabilir)"
fi
echo

echo "── Günlüğün en üstü = en son yapılan iş (instube/DEGISIKLIK-GUNLUGU.md) ──"
if [ -f instube/DEGISIKLIK-GUNLUGU.md ]; then
  # "## Kayıtlar" bölümündeki ilk "### " başlığı = en yeni kayıt
  # (üstteki şablon da "### " ile başladığı için önce Kayıtlar'a iniyoruz).
  sed -n '/^## Kayıtlar/,$p' instube/DEGISIKLIK-GUNLUGU.md 2>/dev/null \
    | sed -n '/^### /,$p' | head -12 | sed 's/^/  /'
else
  echo "  (günlük dosyası yok)"
fi
echo

DURTY="$(git status --porcelain 2>/dev/null | head -10)"
if [ -n "$DURTY" ]; then
  echo "── Commit edilmemiş, havada kalmış değişiklikler ──"
  echo "$DURTY" | sed 's/^/  /'
  echo "  (Önceki oturumdan kalmış olabilir — ezmeden önce 'git diff' ile bak.)"
  echo
fi

# main dışında açık kalmış claude/* dalları — işin nereye kaybolduğunu gösterir.
ACIK="$(timeout 15 git ls-remote --heads origin 'refs/heads/claude/*' 2>/dev/null | wc -l | tr -d ' ')"
if [ "${ACIK:-0}" -gt 0 ]; then
  echo "ℹ️  Uzakta $ACIK adet claude/* dalı duruyor. main'e girmemiş iş bunların"
  echo "    içinde kalmış olabilir:  git log origin/main..origin/<dal> -- instube/"
  echo
fi

echo "KURAL: iş bitince (1) instube/DEGISIKLIK-GUNLUGU.md'ye kayıt ekle,"
echo "       (2) main'e al, (3) dalı sil. Ayrıntı: CLAUDE.md → 'Oturum çakışmaları'."
echo "══════════════════════════════════════════════"
exit 0
