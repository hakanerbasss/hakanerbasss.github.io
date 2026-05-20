#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# MainActivity.kt WebView performans ayarlari
# Calistir: python3 ~/fix_03_webview_perf.py

FILE = "/data/data/com.termux/files/home/tank-siege/app/src/main/java/com/wizaicorp/tanksiege/MainActivity.kt"

patches = [
    # 1. setSupportZoom, builtInZoomControls, displayZoomControls ekle
    #    setRenderPriority kaldir (deprecated, etkisiz)
    (
        "            setRenderPriority(WebSettings.RenderPriority.HIGH)\n"
        "            databaseEnabled = true",

        "            setSupportZoom(false)\n"
        "            builtInZoomControls = false\n"
        "            displayZoomControls = false\n"
        "            databaseEnabled = true"
    ),

    # 2. setContentView'dan once arka plan rengini siyah yap
    #    (beyaz flash onler, compositing maliyetini dusurir)
    (
        "        setContentView(webView)",
        "        webView.setBackgroundColor(android.graphics.Color.BLACK)\n"
        "        setContentView(webView)"
    ),
]

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

original = content
for i, (old, new) in enumerate(patches, 1):
    count = content.count(old)
    if count == 0:
        print(f"  BULUNAMADI - Patch {i}")
    else:
        content = content.replace(old, new, 1)
        print(f"  OK - Patch {i}")

if content == original:
    print("Degisiklik yapilmadi.")
    import sys; sys.exit(1)

try:
    content.encode("utf-8")
except UnicodeEncodeError as e:
    print(f"Unicode hatasi: {e}")
    import sys; sys.exit(1)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)
print("Kaydedildi. -> prj dg")
