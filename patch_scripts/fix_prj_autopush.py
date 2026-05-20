#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_prj_autopush.py — prj.sh cmd_build'e eksik auto_push_error_zip cagrisi ekler
# fix_prj_dg.py'nin Patch 2'si yanlis calistiginda kullan
# Calistir: python3 ~/fix_prj_autopush.py

import re, sys

PRJ_FILE = "/storage/emulated/0/termux-otonom-sistem/prj.sh"

with open(PRJ_FILE, "r", encoding="utf-8") as f:
    content = f.read()

CALL = 'auto_push_error_zip "$OUTPUT"'

if CALL in content:
    # Kontrol et: cmd_build icinde mi yoksa sadece fonksiyon tanimi mi?
    # cmd_build fonksiyonu "cmd_build()" ile baslar ve bir sonraki fonksiyona kadar devam eder
    build_start = content.find("cmd_build() {")
    build_end = content.find("\ncmd_", build_start + 1) if build_start != -1 else -1

    if build_start != -1 and build_end != -1:
        build_body = content[build_start:build_end]
        if CALL in build_body:
            print("Zaten ekli — cmd_build icinde auto_push_error_zip mevcut.")
            sys.exit(0)
    print("Fonksiyon tanimli ama cmd_build'de cagrilmiyor, ekleniyor...")

if "auto_push_error_zip" not in content:
    print("HATA: auto_push_error_zip fonksiyonu prj.sh'de bulunamadi.")
    print("Once fix_prj_dg.py'yi calistir.")
    sys.exit(1)

# cmd_build'in else blogunda, dd yazarak satirinin hemen altina ekle
# Turkce karaktersiz eslesme: "dd yazarak" iceren satir
pattern = re.compile(
    r'([ \t]*echo -e[^\n]*dd yazarak[^\n]*\n)([ \t]+fi\b)',
    re.MULTILINE
)

m = pattern.search(content)
if not m:
    # Alternatif: herhangi bir "dd " referansi
    pattern2 = re.compile(
        r'([ \t]*echo -e[^\n]*indirebilirsin[^\n]*\n)([ \t]+fi\b)',
        re.MULTILINE
    )
    m = pattern2.search(content)

if not m:
    print("HATA: dd yazarak / indirebilirsin satiri bulunamadi.")
    print("prj.sh'i manuel kontrol et.")
    sys.exit(1)

# Ekleme: dd satirinin altina, fi satirinin ustune
indent = m.group(2).rstrip("fi").rstrip()  # fi onundeki bosluk
new_block = m.group(1) + indent + '        ' + CALL + '\n' + m.group(2)
new_content = content[:m.start()] + new_block + content[m.end():]

with open(PRJ_FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

print("OK — cmd_build'e auto_push_error_zip cagrisi eklendi.")
print("Artik 'prj d' basarisiz olunca zip otomatik GitHub'a push edilir.")
