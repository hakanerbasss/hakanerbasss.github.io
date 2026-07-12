#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO="https://github.com/hakanerbasss/hakanerbasss.github.io"
BRANCH="claude/arduino-smart-home-uj82ef"
SYNC_DIR=~/namaz-repo-sync
BUILD_DIR=~/namazvakitleri

echo ">>> Repo senkronize ediliyor..."

if [ ! -d "$SYNC_DIR/.git" ]; then
    git clone --depth=1 --branch "$BRANCH" \
        --filter=blob:none --sparse "$REPO" "$SYNC_DIR"
    cd "$SYNC_DIR"
    git sparse-checkout set \
        namaz-vakitleri/app/src/main/java \
        namaz-vakitleri/app/src/main/res/values \
        namaz-vakitleri/app/src/main/res/drawable \
        namaz-vakitleri/app/src/main/res/xml \
        namaz-vakitleri/app/src/main/AndroidManifest.xml \
        namaz-vakitleri/app/build.gradle
else
    cd "$SYNC_DIR"
    git fetch origin "$BRANCH" --depth=1
    git reset --hard "origin/$BRANCH"
fi

echo ">>> Dosyalar kopyalanıyor..."
SRC="$SYNC_DIR/namaz-vakitleri"

# Java kaynak dosyaları
cp -r "$SRC/app/src/main/java/"* "$BUILD_DIR/app/src/main/java/"

# Manifest ve build.gradle
cp "$SRC/app/src/main/AndroidManifest.xml" "$BUILD_DIR/app/src/main/AndroidManifest.xml"
cp "$SRC/app/build.gradle" "$BUILD_DIR/app/build.gradle"

# Res (mipmap hariç — apk-factory ikonlarını ezme)
for dir in values drawable xml; do
    if [ -d "$SRC/app/src/main/res/$dir" ]; then
        mkdir -p "$BUILD_DIR/app/src/main/res/$dir"
        cp -r "$SRC/app/src/main/res/$dir/"* "$BUILD_DIR/app/src/main/res/$dir/"
    fi
done

echo ">>> Build başlıyor..."
bash -i -c "cd $BUILD_DIR && prj d"
