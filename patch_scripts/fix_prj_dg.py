#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# fix_prj_dg.py — prj.sh'e otomatik hata-zip + GitHub push ekler
# Calistir: python3 ~/fix_prj_dg.py
# Sonuc: prj d basarisiz olunca zip otomatik olusur ve site repo'ya push edilir
#        prj dg = build + basarili ise Android git push, basarisiz ise hata push

import os, sys

PRJ_FILE = "/storage/emulated/0/termux-otonom-sistem/prj.sh"

if not os.path.exists(PRJ_FILE):
    print(f"HATA: {PRJ_FILE} bulunamadi")
    sys.exit(1)

with open(PRJ_FILE, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# ─────────────────────────────────────────────────────────────
# PATCH 1: auto_push_error_zip() fonksiyonu ekle
# (cmd_build_errors'dan sonra, cmd_bundle'dan önce)
# ─────────────────────────────────────────────────────────────

AUTO_FN = r'''
# ══════════════════════════════════════════════════════════════════
# auto_push_error_zip — Hata zip'ini otomatik yarat ve GitHub'a push et
# ══════════════════════════════════════════════════════════════════
auto_push_error_zip() {
    local OUTPUT="$1"
    local ORIG_DIR="$(pwd)"

    # Site repo bul (hakanerbasss.github.io)
    local SITE_REPO=""
    for candidate in \
        "$HOME/hakanerbasss.github.io" \
        "/data/data/com.termux/files/home/hakanerbasss.github.io" \
        "$HOME/site"; do
        if [ -d "$candidate/.git" ]; then
            SITE_REPO="$candidate"; break
        fi
    done

    local TIMESTAMP=$(date +%Y%m%d-%H%M)
    local PKG_NAME="${P_NAME}-hatali-${TIMESTAMP}"
    local TMP_DIR="$HOME/${PKG_NAME}"
    mkdir -p "$TMP_DIR"
    local SRC_DIR="$P_DIR/app/src/main/java"

    local ERROR_LINES
    ERROR_LINES=$(echo "$OUTPUT" | grep -E "^e: file:///|^ERROR: .*\.xml|error: resource|AAPT: error" || true)

    # Hata yoksa Gradle mesajını al
    if [ -z "$ERROR_LINES" ]; then
        ERROR_LINES=$(echo "$OUTPUT" | grep -A 10 "What went wrong:" | head -12 || true)
    fi

    # HATALAR.txt
    {
        echo "HATA RAPORU — $(date '+%d.%m.%Y %H:%M')  |  Proje: $P_NAME"
        echo "══════════════════════════════════════════════"
        echo ""
        echo "$ERROR_LINES" | while IFS= read -r line; do
            BNAME=$(echo "$line" | sed 's|^e: file:///||' | sed 's|:[0-9]*:[0-9]*.*||' | xargs basename 2>/dev/null || true)
            LINE_INFO=$(echo "$line" | grep -oP ':\d+:\d+' | head -1 | tr ':' ' ' | awk '{print "satir "$2", sutun "$3}')
            MSG=$(echo "$line" | sed 's|.*[0-9]: ||')
            if [ -n "$BNAME" ]; then
                echo "📄 $BNAME ($LINE_INFO)"
                echo "   $MSG"
            else
                echo "   $line"
            fi
            echo ""
        done
        echo "Toplam hata: $(echo "$ERROR_LINES" | wc -l)"
    } > "$TMP_DIR/HATALAR.txt"

    # Hatalı dosyaları kopyala
    local DIRECT_FILES
    DIRECT_FILES=$(echo "$OUTPUT" | grep -oP "(?<=^e: file:///).*(?=:[0-9]+:[0-9]+)" | sort -u || true)
    while IFS= read -r fpath; do
        fpath=$(echo "$fpath" | tr -d '\r' | xargs 2>/dev/null || true)
        [ -z "$fpath" ] || [ ! -f "$fpath" ] && continue
        cp "$fpath" "$TMP_DIR/$(basename "$fpath")" 2>/dev/null || true
    done <<< "$DIRECT_FILES"

    # CLAUDE_README ekle
    [ -f "$SISTEM_DIR/CLAUDE_README.md" ] && cp "$SISTEM_DIR/CLAUDE_README.md" "$TMP_DIR/CLAUDE_README.md"

    # ZIP oluştur
    local ZIP_NAME="${PKG_NAME}.zip"
    local ZIP_PATH="$DOWNLOAD/$ZIP_NAME"
    (cd "$HOME" && zip -r "$ZIP_PATH" "$PKG_NAME" > /dev/null 2>&1)
    rm -rf "$TMP_DIR"

    if [ ! -f "$ZIP_PATH" ]; then
        echo -e "  ${R}❌ ZIP oluşturulamadı${NC}"
        cd "$ORIG_DIR"; return
    fi

    local SIZE; SIZE=$(ls -lh "$ZIP_PATH" | awk '{print $5}')
    echo -e "  ${Y}📦 Hata zip: $ZIP_NAME  ($SIZE)${NC}"

    # GitHub'a push et
    if [ -n "$SITE_REPO" ]; then
        local ERRORS_DIR="$SITE_REPO/build-errors"
        mkdir -p "$ERRORS_DIR"

        # Eski zipleri temizle (10'dan fazla varsa en eskiyi sil)
        local COUNT; COUNT=$(ls "$ERRORS_DIR"/*.zip 2>/dev/null | wc -l)
        if [ "$COUNT" -ge 10 ]; then
            ls -t "$ERRORS_DIR"/*.zip | tail -n +10 | xargs rm -f 2>/dev/null || true
        fi

        cp "$ZIP_PATH" "$ERRORS_DIR/$ZIP_NAME"
        cd "$SITE_REPO"
        git add "build-errors/$ZIP_NAME" 2>/dev/null
        if git commit -m "build-error: $P_NAME $TIMESTAMP [auto]" --quiet 2>/dev/null; then
            if git push origin HEAD --quiet 2>&1; then
                echo -e "  ${G}📤 GitHub'a yüklendi → build-errors/$ZIP_NAME${NC}"
                echo -e "  ${DIM}https://raw.githubusercontent.com/hakanerbasss/hakanerbasss.github.io/main/build-errors/$ZIP_NAME${NC}"
            else
                echo -e "  ${Y}⚠️  Git push başarısız, zip sadece Download'da${NC}"
            fi
        else
            echo -e "  ${Y}⚠️  Git commit başarısız${NC}"
        fi
    else
        echo -e "  ${Y}⚠️  Site repo bulunamadı (hakanerbasss.github.io), zip Download'da: $ZIP_PATH${NC}"
    fi

    cd "$ORIG_DIR"
}

'''

BUNDLE_MARKER = "# ══════════════════════════════════════════════════════════════════\n# b  — AAB üret + imzala"

if "auto_push_error_zip" in content:
    print("  OK - Patch 1: auto_push_error_zip zaten var")
elif BUNDLE_MARKER in content:
    content = content.replace(BUNDLE_MARKER, AUTO_FN + BUNDLE_MARKER, 1)
    print("  OK - Patch 1: auto_push_error_zip eklendi")
else:
    print("  BULUNAMADI - Patch 1: cmd_bundle başlangıcı bulunamadı")

# ─────────────────────────────────────────────────────────────
# PATCH 2: cmd_build'de başarısız durumda auto_push_error_zip çağır
# ─────────────────────────────────────────────────────────────

OLD_BUILD_FAIL = '        echo -e "  ${DIM}dd yazarak hata dosyalarını indirebilirsin${NC}"\n        fi\n}'
NEW_BUILD_FAIL = '        echo -e "  ${DIM}dd yazarak hata dosyalarını indirebilirsin${NC}"\n        auto_push_error_zip "$OUTPUT"\n        fi\n}'

if "auto_push_error_zip" in content and "auto_push_error_zip" in content.split("auto_push_error_zip() {")[0] + content.split("auto_push_error_zip() {")[-1]:
    # Zaten cmd_build içinde çağrılıyor
    print("  OK - Patch 2: cmd_build zaten auto_push çağırıyor")
elif OLD_BUILD_FAIL in content:
    content = content.replace(OLD_BUILD_FAIL, NEW_BUILD_FAIL, 1)
    print("  OK - Patch 2: cmd_build'e auto_push_error_zip çağrısı eklendi")
else:
    # Alternatif pattern dene
    OLD2 = 'echo -e "  ${DIM}dd yazarak hata dosyalarını indirebilirsin${NC}"'
    NEW2 = 'echo -e "  ${DIM}dd yazarak hata dosyalarını indirebilirsin${NC}"\n        auto_push_error_zip "$OUTPUT"'
    if content.count(OLD2) == 1:
        content = content.replace(OLD2, NEW2, 1)
        print("  OK - Patch 2: cmd_build'e auto_push_error_zip eklendi (alternatif)")
    else:
        print(f"  BULUNAMADI - Patch 2: dd hint satiri bulunamadi ({content.count(OLD2)} eslesme)")

# ─────────────────────────────────────────────────────────────
# PATCH 3: dg komutu ekle (build + Android git push)
# ─────────────────────────────────────────────────────────────

DG_FN = '''
# ══════════════════════════════════════════════════════════════════
# dg — Build debug APK + Android repo'ya git push
# ══════════════════════════════════════════════════════════════════
cmd_build_git() {
    cmd_build
    # Build başarılı oldu mu? APK var mı kontrol et
    local APK_CHECK
    APK_CHECK=$(find "$P_DIR/app/build/outputs/apk/debug/" -name "*.apk" 2>/dev/null | head -1)
    if [ -n "$APK_CHECK" ]; then
        echo -e "\n${BOLD}${B}⏳ Git push...${NC}"
        cd "$P_DIR"
        git add -A 2>/dev/null
        get_version
        if git commit -m "build v$V_NAME ($V_CODE)" --quiet 2>/dev/null; then
            if git push origin HEAD --quiet 2>&1; then
                echo -e "  ${G}✅ Android repo push tamam${NC}"
            else
                echo -e "  ${Y}⚠️  Git push başarısız${NC}"
            fi
        else
            echo -e "  ${DIM}Commit edilecek değişiklik yok${NC}"
        fi
    fi
}

'''

TRANSFER_MARKER = "# ══════════════════════════════════════════════════════════════════\n# t  — APK'yı Download'a taşı (build almadan)"

if "cmd_build_git" in content:
    print("  OK - Patch 3: cmd_build_git zaten var")
elif TRANSFER_MARKER in content:
    content = content.replace(TRANSFER_MARKER, DG_FN + TRANSFER_MARKER, 1)
    print("  OK - Patch 3: cmd_build_git (dg) eklendi")
else:
    print("  BULUNAMADI - Patch 3: cmd_transfer başlangıcı bulunamadı")

# ─────────────────────────────────────────────────────────────
# PATCH 4: case bloklarına dg ekle
# ─────────────────────────────────────────────────────────────

OLD_CASE1 = "        d)   cmd_build ;;\n        t)   cmd_transfer ;;"
NEW_CASE1 = "        d)   cmd_build ;;\n        dg)  cmd_build_git ;;\n        t)   cmd_transfer ;;"

OLD_CASE2 = "        d)   cmd_build ;;\n        t)   cmd_transfer ;;\n        dd)  cmd_build_errors ;;"
NEW_CASE2 = "        d)   cmd_build ;;\n        dg)  cmd_build_git ;;\n        t)   cmd_transfer ;;\n        dd)  cmd_build_errors ;;"

# help satırı
OLD_HELP = '    echo -e "  ${G}d${NC}   🔨 Build debug APK → Download\'a taşı"'
NEW_HELP = ('    echo -e "  ${G}d${NC}   🔨 Build debug APK → Download\'a taşı"\n'
            '    echo -e "  ${G}dg${NC}  🔨 Build + Android git push (hata→GitHub)"')

p4_count = 0
if "dg)  cmd_build_git" in content:
    print("  OK - Patch 4: dg case zaten var")
else:
    if content.count(OLD_CASE1) >= 1:
        content = content.replace(OLD_CASE1, NEW_CASE1, 1)
        p4_count += 1
    if content.count(OLD_CASE2) >= 1:
        content = content.replace(OLD_CASE2, NEW_CASE2, 1)
        p4_count += 1
    if p4_count > 0:
        print(f"  OK - Patch 4: dg case eklendi ({p4_count} yerde)")
    else:
        print("  UYARI - Patch 4: case blogu bulunamadi, manuel ekle: dg) cmd_build_git ;;")

if OLD_HELP in content:
    content = content.replace(OLD_HELP, NEW_HELP, 1)
    print("  OK - Patch 4b: help metni guncellendi")

# ─────────────────────────────────────────────────────────────
# .gitignore'a build-errors klasörünü EKLEME (takip edilsin)
# prj.sh ile alakasiz ama hatirlatma olarak yorum
# ─────────────────────────────────────────────────────────────

if content == original:
    print("\nDegisiklik yapilmadi. Zaten uygulanmis olabilir.")
    sys.exit(0)

with open(PRJ_FILE, "w", encoding="utf-8") as f:
    f.write(content)
print(f"\nKaydedildi: {PRJ_FILE}")
print("Artik 'prj d' basarisiz olunca zip otomatik olusur ve GitHub'a push edilir.")
print("'prj dg' = build + Android git push")
