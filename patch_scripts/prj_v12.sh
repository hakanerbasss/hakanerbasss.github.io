#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# PRJ — Android Proje Kisayollari v1.2
# Kullanim: proje klasoründeyken  dg / dd / t / b / c / h  yaz
# dg = build + basarili ise Android push + site success klasoru
#           basarisiz ise hata zip + site error klasoru
# ═══════════════════════════════════════════════════════════════════════════════

set +e

G='\033[0;32m'; Y='\033[1;33m'; B='\033[0;34m'; R='\033[0;31m'
C='\033[0;36m'; M='\033[0;35m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

DOWNLOAD="/sdcard/Download"
SISTEM_DIR="/storage/emulated/0/termux-otonom-sistem"
CONF_FILE="$SISTEM_DIR/projeler.conf"

# ══════════════════════════════════════════════════════════════════
# Yardimci: site repo bul
# ══════════════════════════════════════════════════════════════════
_find_site_repo() {
    for c in \
        "$HOME/hakanerbasss.github.io" \
        "/data/data/com.termux/files/home/hakanerbasss.github.io"; do
        [ -d "$c/.git" ] && echo "$c" && return
    done
}

# ══════════════════════════════════════════════════════════════════
# Yardimci: basarili build'i site repo'ya push et
# ══════════════════════════════════════════════════════════════════
_site_push_success() {
    local SITE_REPO ORIG_DIR="$(pwd)"
    SITE_REPO=$(_find_site_repo)
    if [ -z "$SITE_REPO" ]; then
        echo -e "  ${DIM}Site repo bulunamadi, success push atlandi${NC}"
        return
    fi

    local DIR="$SITE_REPO/build-success"
    mkdir -p "$DIR"

    local FNAME="${P_NAME}-v${V_NAME}-${V_CODE}-$(date +%Y%m%d-%H%M).txt"
    printf "BUILD BASARILI\nProje   : %s\nVersiyon: v%s (%s)\nTarih   : %s\n" \
        "$P_NAME" "$V_NAME" "$V_CODE" "$(date '+%d.%m.%Y %H:%M')" > "$DIR/$FNAME"

    # Eski kayitlari temizle (5'ten fazla olursa)
    ls -t "$DIR"/*.txt 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true

    cd "$SITE_REPO"
    git add "build-success/$FNAME" 2>/dev/null
    if git commit -m "build-ok: $P_NAME v$V_NAME [auto]" --quiet 2>/dev/null; then
        if git push origin HEAD --quiet 2>&1; then
            echo -e "  ${G}Site: build-success klasoru guncellendi${NC}"
        else
            echo -e "  ${Y}Site push basarisiz${NC}"
        fi
    fi
    cd "$ORIG_DIR"
}

# ══════════════════════════════════════════════════════════════════
# Yardimci: hata zip'ini site repo'ya push et
# ══════════════════════════════════════════════════════════════════
_site_push_error() {
    local OUTPUT="$1" ORIG_DIR="$(pwd)"
    local SITE_REPO
    SITE_REPO=$(_find_site_repo)

    local TIMESTAMP PKG_NAME TMP_DIR
    TIMESTAMP=$(date +%Y%m%d-%H%M)
    PKG_NAME="${P_NAME}-hatali-${TIMESTAMP}"
    TMP_DIR="$HOME/${PKG_NAME}"
    mkdir -p "$TMP_DIR"

    local ERROR_LINES
    ERROR_LINES=$(echo "$OUTPUT" | grep -E "^e: file:///|^ERROR: .*\.xml|error: resource|AAPT: error" || true)
    [ -z "$ERROR_LINES" ] && ERROR_LINES=$(echo "$OUTPUT" | grep -A 10 "What went wrong:" | head -12 || true)

    # HATALAR.txt
    {
        printf "HATA RAPORU\nProje   : %s  v%s (%s)\nTarih   : %s\n" \
            "$P_NAME" "$V_NAME" "$V_CODE" "$(date '+%d.%m.%Y %H:%M')"
        echo "======================================================"
        echo ""
        echo "$ERROR_LINES" | while IFS= read -r line; do
            local BNAME LINE_INFO MSG
            BNAME=$(echo "$line" | sed 's|^e: file:///||;s|:[0-9]*:[0-9]*.*||' | xargs basename 2>/dev/null || true)
            LINE_INFO=$(echo "$line" | grep -oP ':\d+:\d+' | head -1 | tr ':' ' ' | awk '{print "satir "$2", sutun "$3}')
            MSG=$(echo "$line" | sed 's|.*[0-9]: ||')
            if [ -n "$BNAME" ]; then
                echo "* $BNAME ($LINE_INFO)"
                echo "  $MSG"
            else
                echo "  $line"
            fi
            echo ""
        done
        echo "Toplam hata: $(echo "$ERROR_LINES" | grep -c .)"
    } > "$TMP_DIR/HATALAR.txt"

    # Hatali kaynak dosyalari kopyala
    local DIRECT_FILES
    DIRECT_FILES=$(echo "$OUTPUT" | grep -oP "(?<=^e: file:///).*(?=:[0-9]+:[0-9]+)" | sort -u || true)
    while IFS= read -r fpath; do
        fpath=$(echo "$fpath" | tr -d '\r' | xargs 2>/dev/null || true)
        [ -z "$fpath" ] || [ ! -f "$fpath" ] && continue
        cp "$fpath" "$TMP_DIR/$(basename "$fpath")" 2>/dev/null || true
    done <<< "$DIRECT_FILES"

    [ -f "$SISTEM_DIR/CLAUDE_README.md" ] && cp "$SISTEM_DIR/CLAUDE_README.md" "$TMP_DIR/CLAUDE_README.md"

    # ZIP olustur
    local ZIP_NAME="${PKG_NAME}.zip" ZIP_PATH
    ZIP_PATH="$DOWNLOAD/${PKG_NAME}.zip"
    (cd "$HOME" && zip -r "$ZIP_PATH" "$PKG_NAME" > /dev/null 2>&1)
    rm -rf "$TMP_DIR"

    if [ ! -f "$ZIP_PATH" ]; then
        echo -e "  ${R}ZIP olusturulamadi${NC}"
        cd "$ORIG_DIR"; return
    fi

    local SIZE; SIZE=$(ls -lh "$ZIP_PATH" | awk '{print $5}')
    echo -e "  ${Y}Hata zip: $ZIP_NAME ($SIZE)${NC}"

    if [ -n "$SITE_REPO" ]; then
        local ERRORS_DIR="$SITE_REPO/build-errors"
        mkdir -p "$ERRORS_DIR"
        # Eski zip'leri temizle (10'dan fazla olursa)
        ls -t "$ERRORS_DIR"/*.zip 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null || true
        cp "$ZIP_PATH" "$ERRORS_DIR/$ZIP_NAME"
        cd "$SITE_REPO"
        git add "build-errors/$ZIP_NAME" 2>/dev/null
        if git commit -m "build-error: $P_NAME $TIMESTAMP [auto]" --quiet 2>/dev/null; then
            if git push origin HEAD --quiet 2>&1; then
                echo -e "  ${G}Site: build-errors/$ZIP_NAME push edildi${NC}"
            else
                echo -e "  ${Y}Site push basarisiz. ZIP Download'da: $ZIP_PATH${NC}"
            fi
        fi
    else
        echo -e "  ${Y}Site repo bulunamadi. ZIP Download'da: $ZIP_PATH${NC}"
    fi

    cd "$ORIG_DIR"
}

# ══════════════════════════════════════════════════════════════════
# Proje bul
# ══════════════════════════════════════════════════════════════════
detect_project() {
    CWD=$(pwd -P)
    if [ -f "$CONF_FILE" ]; then
        while IFS='|' read -r name dir ks alias pass pkg; do
            [[ "$name" =~ ^#.*$ ]] && continue
            [[ -z "$name" ]] && continue
            EXPANDED="${dir/#\~/$HOME}"
            EXPANDED=$(realpath "$EXPANDED" 2>/dev/null || echo "$EXPANDED")
            if [[ "$CWD" == "$EXPANDED"* ]]; then
                P_NAME="$name"; P_DIR="$EXPANDED"; P_KEYSTORE="$ks"
                P_ALIAS="$alias"; P_PASS="$pass"; P_PKG="$pkg"
                GRADLE_FILE="$P_DIR/app/build.gradle"
                return 0
            fi
        done < "$CONF_FILE"
    fi
    SEARCH="$CWD"
    for i in 1 2 3; do
        if [ -f "$SEARCH/gradlew" ] && [ -f "$SEARCH/settings.gradle" ]; then
            P_DIR="$SEARCH"; P_NAME=$(basename "$SEARCH")
            GRADLE_FILE="$P_DIR/app/build.gradle"
            P_KEYSTORE=""; P_ALIAS=""; P_PASS=""; P_PKG=""
            return 0
        fi
        SEARCH=$(dirname "$SEARCH")
    done
    return 1
}

# ══════════════════════════════════════════════════════════════════
# Versiyon
# ══════════════════════════════════════════════════════════════════
get_version() {
    V_CODE=$(grep "versionCode" "$GRADLE_FILE" | grep -v "//" | head -1 | grep -oP '\d+' | head -1)
    V_NAME=$(grep "versionName" "$GRADLE_FILE" | grep -v "//" | head -1 | tr -d '"\n\r ' | grep -oP '[\d\.]+' | head -1)
    [ -z "$V_CODE" ] && V_CODE=1
    [ -z "$V_NAME" ] && V_NAME="1.0"
}

bump_version() {
    get_version
    local NEW_CODE=$((V_CODE + 1))
    local MAJOR MINOR
    MAJOR=$(echo "$V_NAME" | cut -d. -f1)
    MINOR=$(echo "$V_NAME" | cut -d. -f2)
    [ -z "$MINOR" ] && MINOR=0
    local NEW_NAME="$MAJOR.$((MINOR + 1))"
    sed -i "s/versionCode.*/versionCode $NEW_CODE/" "$GRADLE_FILE"
    sed -i "s/versionName.*/versionName \"$NEW_NAME\"/" "$GRADLE_FILE"
    V_CODE=$NEW_CODE; V_NAME=$NEW_NAME
    echo -e "  ${DIM}v$V_NAME ($V_CODE)${NC}"
}

# ══════════════════════════════════════════════════════════════════
# dg — Build + push (ana komut)
# ══════════════════════════════════════════════════════════════════
cmd_build_git() {
    echo -e "\n${BOLD}${B}Build aliniyor...${NC}"
    bump_version
    cd "$P_DIR"
    local OUTPUT
    OUTPUT=$(./gradlew assembleDebug --no-daemon 2>&1)

    if echo "$OUTPUT" | grep -q "BUILD SUCCESSFUL"; then
        local APK DEST SIZE
        APK=$(find "$P_DIR/app/build/outputs/apk/debug/" -name "*.apk" 2>/dev/null | head -1)
        if [ -n "$APK" ]; then
            DEST="$DOWNLOAD/${P_NAME}-v${V_NAME}(${V_CODE})-debug.apk"
            cp "$APK" "$DEST"
            SIZE=$(ls -lh "$DEST" | awk '{print $5}')
            echo -e "  ${G}APK hazir!${NC}  $SIZE"
            echo -e "  ${DIM}$DEST${NC}"
        fi

        # Android repo push
        if git rev-parse --git-dir > /dev/null 2>&1; then
            local REMOTE; REMOTE=$(git remote get-url origin 2>/dev/null)
            if [ -n "$REMOTE" ]; then
                echo -e "\n${B}Android repo push...${NC}"
                git add -A
                if ! git diff --cached --quiet; then
                    git commit -m "tank $(date +%H:%M) - v${V_NAME}" 2>&1 | tail -1
                    local PUSH_OUT; PUSH_OUT=$(git push origin HEAD 2>&1)
                    if echo "$PUSH_OUT" | grep -qE "\->|Everything up-to-date|up-to-date"; then
                        echo -e "  ${G}Push tamam${NC}"
                    else
                        echo -e "  ${R}Push hatasi:${NC}"; echo "$PUSH_OUT" | tail -2
                    fi
                else
                    echo -e "  ${DIM}Degisiklik yok, push atlandi${NC}"
                fi
            else
                echo -e "  ${DIM}Git remote yok, push atlandi${NC}"
            fi
        fi

        # Site repo: basarili klasoru guncelle
        _site_push_success

    else
        echo -e "  ${R}Build basarisiz!${NC}"
        local ERRORS; ERRORS=$(echo "$OUTPUT" | grep -E "^e: " | head -5)
        [ -n "$ERRORS" ] && echo "$ERRORS" | while read -r l; do
            echo -e "  ${R}->  $(echo "$l" | sed 's|e: file:///.*\.kt||')${NC}"
        done

        # Site repo: hata klasorune zip push
        _site_push_error "$OUTPUT"
    fi
}

# ══════════════════════════════════════════════════════════════════
# d — Sadece local build (push yok)
# ══════════════════════════════════════════════════════════════════
cmd_build() {
    echo -e "\n${BOLD}${B}Build aliniyor (local)...${NC}"
    bump_version
    cd "$P_DIR"
    local OUTPUT
    OUTPUT=$(./gradlew assembleDebug --no-daemon 2>&1)
    if echo "$OUTPUT" | grep -q "BUILD SUCCESSFUL"; then
        local APK DEST SIZE
        APK=$(find "$P_DIR/app/build/outputs/apk/debug/" -name "*.apk" 2>/dev/null | head -1)
        if [ -n "$APK" ]; then
            DEST="$DOWNLOAD/${P_NAME}-v${V_NAME}(${V_CODE})-debug.apk"
            cp "$APK" "$DEST"
            SIZE=$(ls -lh "$DEST" | awk '{print $5}')
            echo -e "  ${G}APK hazir!${NC}  $SIZE"
            echo -e "  ${DIM}$DEST${NC}"
        fi
    else
        echo -e "  ${R}Build basarisiz!${NC}"
        local ERRORS; ERRORS=$(echo "$OUTPUT" | grep -E "^e: " | head -5)
        [ -n "$ERRORS" ] && echo "$ERRORS" | while read -r l; do
            echo -e "  ${R}->  $(echo "$l" | sed 's|e: file:///.*\.kt||')${NC}"
        done
        echo -e "  ${DIM}Hata zip icin: prj dg${NC}"
    fi
}

# ══════════════════════════════════════════════════════════════════
# t — APK'yi Download'a tasi
# ══════════════════════════════════════════════════════════════════
cmd_transfer() {
    local APK; APK=$(find "$P_DIR/app/build/outputs/apk/debug/" -name "*.apk" 2>/dev/null | head -1)
    if [ -z "$APK" ]; then
        echo -e "  ${R}APK bulunamadi. Once build al (dg).${NC}"; return
    fi
    get_version
    local DEST="$DOWNLOAD/${P_NAME}-v${V_NAME}(${V_CODE})-debug.apk"
    cp "$APK" "$DEST"
    local SIZE; SIZE=$(ls -lh "$DEST" | awk '{print $5}')
    echo -e "  ${G}APK tasindi!${NC}  $SIZE"
    echo -e "  ${DIM}$DEST${NC}"
}

# ══════════════════════════════════════════════════════════════════
# dd — Build + hata dosyalarini interaktif indir
# ══════════════════════════════════════════════════════════════════
cmd_build_errors() {
    echo -e "\n${BOLD}${B}Build aliniyor...${NC}"
    cd "$P_DIR"
    local OUTPUT
    OUTPUT=$(./gradlew assembleDebug --no-daemon 2>&1)

    if echo "$OUTPUT" | grep -q "BUILD SUCCESSFUL"; then
        local APK; APK=$(find "$P_DIR/app/build/outputs/apk/debug/" -name "*.apk" 2>/dev/null | head -1)
        if [ -n "$APK" ]; then
            get_version
            local DEST="$DOWNLOAD/${P_NAME}-v${V_NAME}(${V_CODE})-debug.apk"
            cp "$APK" "$DEST"
            local SIZE; SIZE=$(ls -lh "$DEST" | awk '{print $5}')
            echo -e "  ${G}Build basarili! APK hazir.${NC}  $SIZE"
        fi
        return
    fi

    local ERROR_LINES
    ERROR_LINES=$(echo "$OUTPUT" | grep -E "^e: file:///|^ERROR: .*\.xml|error: resource|AAPT: error" || true)
    if [ -z "$ERROR_LINES" ]; then
        echo -e "  ${R}BUILD FAILED — Hata detayi:${NC}"
        echo "$OUTPUT" | grep -A 25 "What went wrong:" | head -30
        return
    fi

    echo -e "\n  ${G}1.${NC} ZIP  ${DIM}(varsayilan)${NC}"
    echo -e "  ${G}2.${NC} Klasor"
    printf "  Format (enter=zip): "; read -r fmt; fmt=${fmt:-1}

    local TIMESTAMP PKG_NAME TMP_DIR
    TIMESTAMP=$(date +%Y%m%d-%H%M)
    PKG_NAME="${P_NAME}-hatali-${TIMESTAMP}"
    TMP_DIR="$HOME/${PKG_NAME}"
    mkdir -p "$TMP_DIR"
    local SRC_DIR="$P_DIR/app/src/main/java"

    local DIRECT_FILES
    DIRECT_FILES=$(echo "$ERROR_LINES" \
        | sed 's|^e: file://||;s|: ([0-9].*||;s|:[0-9]*:[0-9]*.*||' \
        | sort -u)

    local UNRESOLVED; UNRESOLVED=$(echo "$ERROR_LINES" | grep -oP 'Unresolved reference: \K\w+' | sort -u || true)
    declare -A RELATED_MAP
    if [ -n "$UNRESOLVED" ]; then
        while IFS= read -r ref; do
            [ -z "$ref" ] && continue
            local DEFINING; DEFINING=$(grep -rl \
                -e "class $ref" -e "fun $ref(" \
                -e "object $ref" -e "interface $ref" \
                "$SRC_DIR" 2>/dev/null | head -1 || true)
            [ -n "$DEFINING" ] && RELATED_MAP["$DEFINING"]=1
        done <<< "$UNRESOLVED"
    fi

    {
        printf "HATA RAPORU\nProje   : %s\nTarih   : %s\n" "$P_NAME" "$(date '+%d.%m.%Y %H:%M')"
        echo "======================================================"
        echo ""
        echo "$ERROR_LINES" | while IFS= read -r line; do
            local BNAME LINE_INFO MSG
            BNAME=$(echo "$line" | sed 's|^e: file:///||;s|:[0-9]*:[0-9]*.*||' | xargs basename 2>/dev/null)
            LINE_INFO=$(echo "$line" | grep -oP ':\d+:\d+' | head -1 | tr ':' ' ' | awk '{print "satir "$2", sutun "$3}')
            MSG=$(echo "$line" | sed 's|.*[0-9]: ||')
            echo "* $BNAME ($LINE_INFO)"; echo "  $MSG"; echo ""
        done
        echo "Toplam hata: $(echo "$ERROR_LINES" | grep -c .)"
    } > "$TMP_DIR/HATALAR.txt"

    local COPIED=0
    echo -e "\n  ${Y}Hatali dosyalar:${NC}"
    while IFS= read -r fpath; do
        fpath=$(echo "$fpath" | tr -d '\r' | xargs)
        [ -z "$fpath" ] || [ ! -f "$fpath" ] && continue
        cp "$fpath" "$TMP_DIR/$(basename "$fpath")"
        echo -e "  ${R}->  $(basename "$fpath")${NC}"
        COPIED=$((COPIED+1))
    done <<< "$DIRECT_FILES"

    if [ ${#RELATED_MAP[@]} -gt 0 ]; then
        echo -e "\n  ${Y}Ilgili dosyalar:${NC}"
        for rfile in "${!RELATED_MAP[@]}"; do
            local BNAME; BNAME=$(basename "$rfile")
            [ ! -f "$TMP_DIR/$BNAME" ] && cp "$rfile" "$TMP_DIR/$BNAME" && \
                echo -e "  ${C}->  $BNAME${NC}" && COPIED=$((COPIED+1))
        done
    fi

    [ -f "$SISTEM_DIR/CLAUDE_README.md" ] && cp "$SISTEM_DIR/CLAUDE_README.md" "$TMP_DIR/CLAUDE_README.md"

    echo ""
    if [ "$fmt" = "1" ]; then
        local ZIP_PATH="$DOWNLOAD/${PKG_NAME}.zip"
        (cd "$HOME" && zip -r "$ZIP_PATH" "$PKG_NAME" > /dev/null 2>&1)
        rm -rf "$TMP_DIR"
        [ -f "$ZIP_PATH" ] && SIZE=$(ls -lh "$ZIP_PATH" | awk '{print $5}') && \
            echo -e "  ${G}ZIP: $ZIP_PATH  ($SIZE)${NC}" || \
            echo -e "  ${R}ZIP olusturulamadi${NC}"
    else
        mv "$TMP_DIR" "$DOWNLOAD/"
        echo -e "  ${G}Klasor: $DOWNLOAD/$PKG_NAME${NC}"
    fi
}

# ══════════════════════════════════════════════════════════════════
# b — AAB build + imzala
# ══════════════════════════════════════════════════════════════════
cmd_bundle() {
    echo -e "\n${BOLD}${B}AAB build ediliyor...${NC}"
    bump_version
    cd "$P_DIR"
    ./gradlew bundleRelease --no-daemon 2>&1 | tail -4
    local AAB="$P_DIR/app/build/outputs/bundle/release/app-release.aab"
    if [ ! -f "$AAB" ]; then echo -e "  ${R}AAB olusturulamadi!${NC}"; return; fi
    local KS_PATH="$SISTEM_DIR/keystores/$P_KEYSTORE"
    if [ -n "$P_KEYSTORE" ] && [ -f "$KS_PATH" ] && [ -n "$P_ALIAS" ] && [ -n "$P_PASS" ]; then
        jarsigner -sigalg SHA256withRSA -digestalg SHA256 \
            -keystore "$KS_PATH" -storepass "$P_PASS" -keypass "$P_PASS" \
            "$AAB" "$P_ALIAS" 2>&1 | tail -2
        echo -e "  ${G}Imzalandi${NC}"
    else
        echo -e "  ${Y}Keystore bulunamadi, imzalanmadi${NC}"
    fi
    local DEST="$DOWNLOAD/${P_NAME}-v${V_NAME}(${V_CODE}).aab"
    cp "$AAB" "$DEST"
    local SIZE; SIZE=$(ls -lh "$DEST" | awk '{print $5}')
    echo -e "  ${G}AAB hazir!${NC}  $SIZE"
    echo -e "  ${DIM}$DEST${NC}"
}

# ══════════════════════════════════════════════════════════════════
# c — Tum kodlari .txt indir
# ══════════════════════════════════════════════════════════════════
cmd_code() {
    local TIMESTAMP; TIMESTAMP=$(date +%Y%m%d-%H%M)
    local OUTPUT_FILE="$DOWNLOAD/${P_NAME}-tum-kod-${TIMESTAMP}.txt"
    find "$P_DIR/app/src/main/java" -name "*.kt" \
        -exec echo "// === FILE: {} ===" \; -exec cat {} \; > "$OUTPUT_FILE"
    local FILES; FILES=$(grep -c "^// === FILE:" "$OUTPUT_FILE")
    local SIZE; SIZE=$(ls -lh "$OUTPUT_FILE" | awk '{print $5}')
    echo -e "  ${G}$FILES dosya -> $OUTPUT_FILE  ($SIZE)${NC}"
}

# ══════════════════════════════════════════════════════════════════
# cl — Clean
# ══════════════════════════════════════════════════════════════════
cmd_clean() {
    echo -e "\n${Y}Clean...${NC}"
    cd "$P_DIR"
    ./gradlew clean --no-daemon 2>&1 | tail -3
    echo -e "  ${G}Temizlendi${NC}"
}

# ══════════════════════════════════════════════════════════════════
# log — Build gecmisi
# ══════════════════════════════════════════════════════════════════
cmd_log() {
    local log_file="$SISTEM_DIR/build-logs/${P_NAME}.log"
    if [ ! -f "$log_file" ]; then
        echo -e "  ${Y}Henuz build gecmisi yok.${NC}"; return
    fi
    local count; count=$(wc -l < "$log_file")
    echo -e "\n  ${BOLD}${B}BUILD GECMISI — $P_NAME  (son $count build)${NC}\n"
    while IFS= read -r line; do
        [[ "$line" == *"OK"*   ]] && echo -e "  ${G}$line${NC}" && continue
        [[ "$line" == *"FAIL"* ]] && echo -e "  ${R}$line${NC}" && continue
        echo -e "  $line"
    done < "$log_file"
    echo -e "\n  ${DIM}Log: $log_file${NC}"
}

# ══════════════════════════════════════════════════════════════════
# builds — Test APK arsivi
# ══════════════════════════════════════════════════════════════════
cmd_builds() {
    local archive_dir="$SISTEM_DIR/test-builds/$P_NAME"
    if [ ! -d "$archive_dir" ] || [ -z "$(ls -A "$archive_dir" 2>/dev/null)" ]; then
        echo -e "  ${Y}Henuz arsivlenmis APK yok.${NC}"; return
    fi
    echo -e "\n  ${BOLD}${B}TEST APK ARSIVI — $P_NAME${NC}\n"
    ls -lt "$archive_dir"/*.apk 2>/dev/null | while read -r _ _ _ _ size month day time fname; do
        echo -e "  ${G}->${NC} $(basename "$fname" .apk)  ${DIM}($size)${NC}"
    done
    local cnt; cnt=$(ls "$archive_dir"/*.apk 2>/dev/null | wc -l)
    echo -e "\n  ${DIM}Toplam: $cnt APK | $archive_dir${NC}"
}

# ══════════════════════════════════════════════════════════════════
# h — Yardim
# ══════════════════════════════════════════════════════════════════
cmd_help() {
    echo ""
    echo -e "${BOLD}${B}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${B}║   PRJ Kisayollari v1.2                      ║${NC}"
    echo -e "${BOLD}${B}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${G}dg${NC}     Build + push (ANA KOMUT)"
    echo -e "         Basarili: APK + Android git push + site success"
    echo -e "         Basarisiz: hata zip + site build-errors push"
    echo -e "  ${G}d${NC}      Sadece local build (push yok)"
    echo -e "  ${G}t${NC}      Son APK'yi Download'a tasi"
    echo -e "  ${G}dd${NC}     Build + hata zip interaktif indir"
    echo -e "  ${G}b${NC}      AAB build + imzala"
    echo -e "  ${G}c${NC}      Tum .kt kodlarini .txt indir"
    echo -e "  ${G}cl${NC}     Clean"
    echo -e "  ${G}af${NC}     AI ile otomatik duzelt"
    echo -e "  ${G}e${NC}      Gorev ver"
    echo -e "  ${G}log${NC}    Build gecmisi"
    echo -e "  ${G}builds${NC} Test APK arsivi"
    echo -e "  ${G}h${NC}      Bu ekran"
    echo -e "  ${G}install${NC} Kendini kur"
    echo -e "  ${G}q${NC}      Cikis"
    echo ""
    echo -e "  ${DIM}Site repo: hakanerbasss.github.io (home dizininde olmali)${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════
# install — Kendini kur
# ══════════════════════════════════════════════════════════════════
cmd_install() {
    local PRJ_TARGET="$SISTEM_DIR/prj.sh"
    local SELF; SELF=$(realpath "$0")
    echo -e "\n${BOLD}${B}PRJ Kurulumu${NC}\n"
    mkdir -p "$SISTEM_DIR"
    if [ "$SELF" != "$PRJ_TARGET" ]; then
        cp "$SELF" "$PRJ_TARGET"
        chmod +x "$PRJ_TARGET"
        echo -e "  ${G}Kopyalandi: $PRJ_TARGET${NC}"
    else
        echo -e "  ${G}Zaten dogru konumda${NC}"
    fi
    grep -q "alias prj=" ~/.bashrc 2>/dev/null && sed -i "/alias prj=/d" ~/.bashrc
    echo "alias prj=\"bash $SISTEM_DIR/prj.sh\"" >> ~/.bashrc
    source ~/.bashrc 2>/dev/null || true
    echo -e "  ${G}alias 'prj' eklendi${NC}"
    echo -e "\n  ${DIM}Kullanim: prj dg${NC}"
}

# ══════════════════════════════════════════════════════════════════
# BASLANGIC
# ══════════════════════════════════════════════════════════════════
if ! detect_project; then
    echo -e "${R}Android projesi bulunamadi.${NC}"
    echo -e "${DIM}Proje klasoründen calistir.${NC}"
    exit 1
fi

echo -e "\n${BOLD}${G}◆ ${P_NAME}${NC}  ${DIM}$P_DIR${NC}"

if [ -n "$1" ]; then
    case "$1" in
        dg)  cmd_build_git ;;
        d)   cmd_build ;;
        t)   cmd_transfer ;;
        dd)  cmd_build_errors ;;
        b)   cmd_bundle ;;
        c)   cmd_code ;;
        cl)  cmd_clean ;;
        h)   cmd_help ;;
        log) cmd_log ;;
        builds) cmd_builds ;;
        install) cmd_install ;;
        s)   bash "$SISTEM_DIR/sistem.sh" ;;
        af|autofix)
            AUTOFIX_SCRIPT="$SISTEM_DIR/autofix.sh"
            [ -f "$AUTOFIX_SCRIPT" ] && bash "$AUTOFIX_SCRIPT" run "$P_DIR" || \
                echo "autofix.sh bulunamadi."
            ;;
        e)
            [ -z "$2" ] && echo -e "${R}Ornek: prj e \"gorev\"${NC}" || \
                bash "$SISTEM_DIR/autofix.sh" task "$2" "$P_DIR"
            ;;
        *)   echo -e "${R}Bilinmeyen: $1${NC}"; cmd_help ;;
    esac
    exit 0
fi

# Argumansiz: interaktif
cmd_help
while true; do
    printf "  ${BOLD}-> ${NC}"
    read -r cmd
    case "$cmd" in
        dg)  cmd_build_git ;;
        d)   cmd_build ;;
        t)   cmd_transfer ;;
        dd)  cmd_build_errors ;;
        b)   cmd_bundle ;;
        c)   cmd_code ;;
        cl)  cmd_clean ;;
        h)   cmd_help ;;
        log) cmd_log ;;
        builds) cmd_builds ;;
        install) cmd_install ;;
        s)   bash "$SISTEM_DIR/sistem.sh"; break ;;
        af|autofix)
            AUTOFIX_SCRIPT="$SISTEM_DIR/autofix.sh"
            [ -f "$AUTOFIX_SCRIPT" ] && bash "$AUTOFIX_SCRIPT" run "$P_DIR" || \
                echo "autofix.sh bulunamadi."
            ;;
        e)
            read -r -p "Gorev nedir?: " user_task
            [ -n "$user_task" ] && bash "$SISTEM_DIR/autofix.sh" task "$user_task" "$P_DIR"
            ;;
        q|Q|"") echo -e "${G}Gorusuruz!${NC}"; exit 0 ;;
        *)   echo -e "  ${DIM}? -> h yazarak komutlari gor${NC}" ;;
    esac
    echo ""
done
