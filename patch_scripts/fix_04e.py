#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_04e.py — MainActivity.kt'ye loadLeaderboard bridge'ini temiz ekler
# Onceki fix'lerin birikimli sorunlarina karsi sifirdan yazar
# Calistir: python3 ~/fix_04e.py

import sys, os

KT_FILE = "/data/data/com.termux/files/home/tank-siege/app/src/main/java/com/wizaicorp/tanksiege/MainActivity.kt"
SNIPPET  = os.path.expanduser("~/loadLeaderboard_snippet.kt")

# ── Snippet dosyasini oku ──────────────────────────────────────────
if not os.path.exists(SNIPPET):
    print(f"HATA: {SNIPPET} bulunamadi")
    print("Once: wget .../loadLeaderboard_snippet.kt -O ~/loadLeaderboard_snippet.kt")
    sys.exit(1)

with open(SNIPPET, encoding="utf-8") as f:
    snippet_clean = f.read().strip()   # "    fun loadLeaderboard(...) {\n    ... \n    }"

# ── MainActivity.kt oku ──────────────────────────────────────────
with open(KT_FILE, encoding="utf-8") as f:
    src = f.read()

orig = src
changed = []

# ══════════════════════════════════════════════════════════════════
# PATCH 1: LeaderboardVariant import
# ══════════════════════════════════════════════════════════════════
IMPORT_NEW = "import com.google.android.gms.games.leaderboard.LeaderboardVariant"
if IMPORT_NEW in src:
    print("  SKIP P1: LeaderboardVariant import zaten var")
else:
    IMPORT_ANCHOR = "import com.google.android.gms.games.snapshot.Snapshot"
    if IMPORT_ANCHOR in src:
        src = src.replace(IMPORT_ANCHOR,
                          IMPORT_ANCHOR + "\n" + IMPORT_NEW, 1)
        changed.append("P1: LeaderboardVariant import eklendi")
        print("  OK P1: import eklendi")
    else:
        print("  WARN P1: Snapshot import bulunamadi, P1 atlandi")

# ══════════════════════════════════════════════════════════════════
# PATCH 2: loadLeaderboard() fonksiyonu
# -- once mevcut (bozuk veya dogru) versiyonu sil, sonra temizi ekle
# ══════════════════════════════════════════════════════════════════
FN_SIG = "    fun loadLeaderboard(boardId: String, kind: String)"
SIGN_OUT = "    fun signOut()"

occurrences = []
pos = 0
while True:
    i = src.find(FN_SIG, pos)
    if i == -1:
        break
    occurrences.append(i)
    pos = i + 1

print(f"  loadLeaderboard sayisi: {len(occurrences)}")

if len(occurrences) > 0:
    # Mevcut tum ornekleri sil (dogru da olsa, snippet ile replace ederek temizle)
    # En son olandan baslayarak sil (index kaymasi olmasin)
    for fn_start in reversed(occurrences):
        # Fonksiyon sonu: bir sonraki "    fun " veya "    @" veya "    }" (class kapanisi)
        end_markers = []
        for marker in ["\n    fun ", "\n    @JavascriptInterface", "\n    private fun",
                       "\n    inner class", "\n    companion"]:
            p = src.find(marker, fn_start + len(FN_SIG))
            if p != -1:
                end_markers.append(p)
        if not end_markers:
            print("  WARN P2: Fonksiyon sonu bulunamadi, atlandi")
            continue
        fn_end = min(end_markers)
        removed = src[fn_start:fn_end]
        print(f"  Siliniyor: pozisyon {fn_start}-{fn_end} ({len(removed)} karakter)")
        src = src[:fn_start] + src[fn_end:]

    # Bos satir birikimini temizle
    import re
    src = re.sub(r'\n{3,}', '\n\n', src)
    changed.append("P2: eski loadLeaderboard silindi")

# signOut'tan once snippet ekle
if SIGN_OUT not in src:
    print("  WARN P2: fun signOut() bulunamadi")
else:
    # snippet'i signOut'un tam basina ekle
    insert_before = src.index(SIGN_OUT)
    # Oncesinde zaten iki bos satir var mi?
    prefix = src[max(0, insert_before-2):insert_before]
    sep = "\n" if prefix.endswith("\n\n") else "\n\n"
    src = src[:insert_before] + snippet_clean + sep + src[insert_before:]
    changed.append("P2: loadLeaderboard eklendi")
    print("  OK P2: loadLeaderboard eklendi")

# ══════════════════════════════════════════════════════════════════
# PATCH 3: AndroidBridge @JavascriptInterface
# ══════════════════════════════════════════════════════════════════
BRIDGE_SIG  = "@JavascriptInterface fun loadLeaderboard(boardId: String, kind: String)"
BRIDGE_NEXT = "@JavascriptInterface fun trySilentSignIn()"

if BRIDGE_SIG in src:
    print("  SKIP P3: AndroidBridge loadLeaderboard zaten var")
else:
    if BRIDGE_NEXT in src:
        bridge_block = (
            "    @JavascriptInterface fun loadLeaderboard(boardId: String, kind: String) {\n"
            "        handler.post { activity.loadLeaderboard(boardId, kind) }\n"
            "    }\n"
            "    "
        )
        src = src.replace("    " + BRIDGE_NEXT, bridge_block + BRIDGE_NEXT, 1)
        changed.append("P3: AndroidBridge loadLeaderboard eklendi")
        print("  OK P3: AndroidBridge eklendi")
    else:
        print("  WARN P3: trySilentSignIn bulunamadi, P3 atlandi")

# ══════════════════════════════════════════════════════════════════
# Kaydet
# ══════════════════════════════════════════════════════════════════
if src == orig:
    print("\nDegisiklik yapilmadi.")
    sys.exit(0)

with open(KT_FILE, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nKaydedildi ({len(changed)} degisiklik):")
for c in changed:
    print(f"  - {c}")
print("\nSimdi: prj dg")
