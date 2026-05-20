#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_04b.py — MainActivity.kt'deki bozuk loadLeaderboard() fonksiyonunu düzeltir
# Calistir: python3 ~/fix_04b.py
# Not: loadLeaderboard_snippet.kt ile ayni dizinde olmali

import re, os, sys

KT_FILE = "/data/data/com.termux/files/home/tank-siege/app/src/main/java/com/wizaicorp/tanksiege/MainActivity.kt"
SNIPPET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loadLeaderboard_snippet.kt")

# --- snippet dosyasini oku ---
if not os.path.exists(SNIPPET_FILE):
    SNIPPET_FILE = os.path.expanduser("~/loadLeaderboard_snippet.kt")
if not os.path.exists(SNIPPET_FILE):
    print(f"HATA: snippet dosyasi bulunamadi: {SNIPPET_FILE}")
    sys.exit(1)

with open(SNIPPET_FILE, "r", encoding="utf-8") as f:
    snippet_raw = f.read().strip()

# snippet'ten sadece fonksiyon gövdesini al (fun loadLeaderboard ... son '}' kadar)
# snippet dosyasi sadece fonksiyon içeriyor, leading 4-space indent ile
snippet_fn = snippet_raw  # 4-space ile başlıyor

print(f"Snippet okundu: {len(snippet_fn)} karakter")

# --- MainActivity.kt oku ---
with open(KT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# --- Patch 1: LeaderboardVariant import eksikse ekle ---
import_marker = "import com.google.android.gms.games.leaderboard.LeaderboardVariant"
if import_marker not in content:
    old_import = "import com.google.android.gms.games.snapshot.Snapshot\n"
    new_import = ("import com.google.android.gms.games.snapshot.Snapshot\n"
                  "import com.google.android.gms.games.leaderboard.LeaderboardVariant\n")
    if old_import in content:
        content = content.replace(old_import, new_import, 1)
        print("  OK - Patch 1: LeaderboardVariant import eklendi")
    else:
        print("  UYARI - Patch 1: Snapshot import bulunamadi, import eklenmedi")
else:
    print("  OK - Patch 1: LeaderboardVariant import zaten var")

# --- Patch 2: Bozuk loadLeaderboard() fonksiyonunu doğru olanla değiştir ---
# Regex: fun loadLeaderboard(...) { ... } — iki satir bos + fun signOut baslangicina kadar
pattern = re.compile(
    r'([ \t]*)fun loadLeaderboard\(boardId: String, kind: String\)\s*\{.*?\n(\s*)\}(\s*\n\s*fun signOut)',
    re.DOTALL
)

match = pattern.search(content)
if match:
    # Mevcut bozuk fonksiyonu sil ve yerine doğruyu koy
    content = pattern.sub(
        snippet_fn + r'\3',
        content,
        count=1
    )
    print("  OK - Patch 2: loadLeaderboard() fonksiyonu duzeltildi")
else:
    # Belki fonksiyon hiç yok, fun signOut() öncesine ekle
    if "fun loadLeaderboard(boardId: String, kind: String)" not in content:
        target = "    fun signOut() {"
        if target in content:
            content = content.replace(target, snippet_fn + "\n\n    fun signOut() {", 1)
            print("  OK - Patch 2: loadLeaderboard() fonksiyonu eklendi")
        else:
            print("  BULUNAMADI - Patch 2: fun signOut() bulunamadi")
    else:
        print("  UYARI - Patch 2: Fonksiyon var ama regex eslesemedi, manuel kontrol gerekli")

# --- Patch 3: AndroidBridge @JavascriptInterface ekle (yoksa) ---
bridge_check = "@JavascriptInterface fun loadLeaderboard(boardId: String, kind: String)"
if bridge_check not in content:
    bridge_target = "    @JavascriptInterface fun trySilentSignIn() {"
    bridge_new = (
        "    @JavascriptInterface fun loadLeaderboard(boardId: String, kind: String) {\n"
        "        handler.post { activity.loadLeaderboard(boardId, kind) }\n"
        "    }\n"
        "    @JavascriptInterface fun trySilentSignIn() {"
    )
    if bridge_target in content:
        content = content.replace(bridge_target, bridge_new, 1)
        print("  OK - Patch 3: AndroidBridge loadLeaderboard() eklendi")
    else:
        print("  BULUNAMADI - Patch 3: trySilentSignIn bulunamadi")
else:
    print("  OK - Patch 3: AndroidBridge loadLeaderboard() zaten var")

# --- Kaydet ---
if content == original:
    print("\nDegisiklik yapilmadi.")
    sys.exit(1)

with open(KT_FILE, "w", encoding="utf-8") as f:
    f.write(content)
print("\nKaydedildi. Simdi: cd ~/tank-siege && prj dg")
