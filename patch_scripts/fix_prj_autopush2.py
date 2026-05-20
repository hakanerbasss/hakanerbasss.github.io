#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_prj_autopush2.py — cmd_build'in else bloguna auto_push_error_zip ekler
# Turkce karakter sorunundan kacinmak icin structure-based yaklasim
# Calistir: python3 ~/fix_prj_autopush2.py

import sys

PRJ_FILE = "/storage/emulated/0/termux-otonom-sistem/prj.sh"

with open(PRJ_FILE, "r", encoding="utf-8") as f:
    content = f.read()

CALL = 'auto_push_error_zip "$OUTPUT"'

# Zaten eklenmis mi kontrol et (cmd_build icinde)
build_start = content.find("\ncmd_build() {")
if build_start == -1:
    build_start = content.find("cmd_build() {")

if build_start == -1:
    print("HATA: cmd_build() bulunamadi")
    sys.exit(1)

# cmd_build fonksiyonunun sonu (bir sonraki fonksiyon tanimine kadar)
build_end = content.find("\ncmd_", build_start + 10)
if build_end == -1:
    build_end = len(content)

build_fn = content[build_start:build_end]

if CALL in build_fn:
    print("Zaten ekli — cmd_build icinde auto_push_error_zip mevcut.")
    sys.exit(0)

if "auto_push_error_zip" not in content:
    print("HATA: auto_push_error_zip fonksiyonu tanimli degil.")
    print("Once: python3 ~/fix_prj_dg.py")
    sys.exit(1)

print(f"cmd_build bulundu ({len(build_fn)} karakter)")

# Son 'fi' satirini bul (else blogunu kapatan if/fi)
# Cok satir: "\n    fi\n" veya "\n        fi\n"
fi_candidates = []
search_pos = 0
while True:
    pos = build_fn.find("\n    fi\n", search_pos)
    if pos == -1:
        break
    fi_candidates.append(pos)
    search_pos = pos + 1

# Son fi'yi al (else blogunun kapanisi)
if not fi_candidates:
    # Alternatif: sadece fi\n dene
    pos = build_fn.rfind("\n    fi")
    if pos == -1:
        print("HATA: fi satiri bulunamadi. cmd_build icerigi:")
        print(build_fn[-300:])
        sys.exit(1)
    fi_candidates = [pos]

last_fi_in_build = fi_candidates[-1]
print(f"Son fi satiri: pozisyon {last_fi_in_build} (build_fn icinde)")

# Ekleme noktasi: son fi satirinin hemen oncesi
# build_start + last_fi_in_build = global konum
global_fi_pos = build_start + last_fi_in_build

# "\n    fi\n" = newline + "    fi" + newline
# Oncesine ekle: "        auto_push_error_zip "$OUTPUT"\n"
insert_text = '        ' + CALL + '\n'

new_content = content[:global_fi_pos + 1] + insert_text + content[global_fi_pos + 1:]

with open(PRJ_FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

print("OK — cmd_build'e auto_push_error_zip cagrisi eklendi.")
print("Artik 'prj d' basarisiz olunca zip otomatik GitHub'a push edilir.")

# Dogrulama
with open(PRJ_FILE, "r", encoding="utf-8") as f:
    verify = f.read()
new_build_end = verify.find("\ncmd_", verify.find("cmd_build() {") + 10)
new_build_fn = verify[verify.find("cmd_build() {"):new_build_end]
if CALL in new_build_fn:
    print("Dogrulandi: cmd_build icinde mevcut.")
else:
    print("UYARI: Dogrulama basarisiz, manuel kontrol gerekebilir.")
