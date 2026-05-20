#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_04c.py — Bozuk loadLeaderboard() fonksiyonunu string-bazli yontemle duzeltir
# fix_04b.py'nin regex'i calismadiginda kullan
# Calistir: python3 ~/fix_04c.py

import os, sys

KT_FILE = "/data/data/com.termux/files/home/tank-siege/app/src/main/java/com/wizaicorp/tanksiege/MainActivity.kt"
SNIPPET_FILE = os.path.expanduser("~/loadLeaderboard_snippet.kt")

if not os.path.exists(SNIPPET_FILE):
    print(f"HATA: snippet bulunamadi: {SNIPPET_FILE}")
    sys.exit(1)

with open(SNIPPET_FILE, "r", encoding="utf-8") as f:
    snippet = f.read().strip()

with open(KT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# Fonksiyon baslangici
FN_START = "    fun loadLeaderboard(boardId: String, kind: String)"

start_pos = content.find(FN_START)
if start_pos == -1:
    print("BULUNAMADI: loadLeaderboard fonksiyonu yok — import/bridge duzeltilmis ama fonksiyon eklenmemis")
    # Dogrudan ekle
    target = "    fun signOut() {"
    if target in content:
        content = content.replace(target, snippet + "\n\n    fun signOut() {", 1)
        with open(KT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("Eklendi (yeni). Simdi: prj dg")
    else:
        print("HATA: fun signOut() de bulunamadi")
        sys.exit(1)
    sys.exit(0)

print(f"Fonksiyon bulundu (pozisyon {start_pos})")

# Fonksiyon sonu: fun signOut once
end_pos = None
for marker in ["\n\n    fun signOut()", "\n    fun signOut()"]:
    p = content.find(marker, start_pos)
    if p != -1:
        end_pos = p
        break

if end_pos is None:
    print("HATA: fun signOut() siniri bulunamadi")
    sys.exit(1)

old_fn = content[start_pos:end_pos]
print(f"Eski fonksiyon: {len(old_fn)} karakter")
print(f"Yeni snippet:   {len(snippet)} karakter")

if old_fn.strip() == snippet.strip():
    print("Fonksiyon zaten dogru, degisiklik yok.")
    sys.exit(0)

new_content = content[:start_pos] + snippet + content[end_pos:]

with open(KT_FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Kaydedildi. Simdi: prj dg")
