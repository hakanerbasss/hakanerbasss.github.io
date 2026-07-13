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
else
    cd "$SYNC_DIR"
fi

git sparse-checkout set \
    namaz-vakitleri/app/src/main/java \
    namaz-vakitleri/app/src/main/res/values \
    namaz-vakitleri/app/src/main/res/drawable \
    namaz-vakitleri/app/src/main/res/mipmap-anydpi-v26 \
    namaz-vakitleri/app/src/main/res/mipmap-mdpi \
    namaz-vakitleri/app/src/main/res/mipmap-hdpi \
    namaz-vakitleri/app/src/main/res/mipmap-xhdpi \
    namaz-vakitleri/app/src/main/res/mipmap-xxhdpi \
    namaz-vakitleri/app/src/main/res/mipmap-xxxhdpi \
    namaz-vakitleri/app/src/main/res/xml \
    namaz-vakitleri/app/src/main/AndroidManifest.xml \
    namaz-vakitleri/app/build.gradle

git fetch origin "$BRANCH" --depth=1
git reset --hard "origin/$BRANCH"

echo ">>> Dosyalar kopyalanıyor..."
SRC="$SYNC_DIR/namaz-vakitleri"

# Java kaynak dosyaları
cp -r "$SRC/app/src/main/java/"* "$BUILD_DIR/app/src/main/java/"

# Manifest ve build.gradle
cp "$SRC/app/src/main/AndroidManifest.xml" "$BUILD_DIR/app/src/main/AndroidManifest.xml"
cp "$SRC/app/build.gradle" "$BUILD_DIR/app/build.gradle"

# Res klasörleri
for dir in values drawable xml; do
    if [ -d "$SRC/app/src/main/res/$dir" ]; then
        mkdir -p "$BUILD_DIR/app/src/main/res/$dir"
        cp -r "$SRC/app/src/main/res/$dir/"* "$BUILD_DIR/app/src/main/res/$dir/"
    fi
done

# Adaptive icon XML (mipmap-anydpi-v26)
if [ -d "$SRC/app/src/main/res/mipmap-anydpi-v26" ]; then
    mkdir -p "$BUILD_DIR/app/src/main/res/mipmap-anydpi-v26"
    cp "$SRC/app/src/main/res/mipmap-anydpi-v26/"* \
       "$BUILD_DIR/app/src/main/res/mipmap-anydpi-v26/"
fi

# Launcher foreground PNG (her density)
for density in mdpi hdpi xhdpi xxhdpi xxxhdpi; do
    fg="$SRC/app/src/main/res/mipmap-$density/ic_launcher_foreground.png"
    if [ -f "$fg" ]; then
        mkdir -p "$BUILD_DIR/app/src/main/res/mipmap-$density"
        cp "$fg" "$BUILD_DIR/app/src/main/res/mipmap-$density/ic_launcher_foreground.png"
    fi
done

# Çakışan vector drawable'ı kaldır
rm -f "$BUILD_DIR/app/src/main/res/drawable/ic_launcher_foreground.xml"
rm -f "$BUILD_DIR/app/src/main/res/drawable/ic_launcher_background.xml"

echo ">>> Build başlıyor..."
bash -i -c "cd $BUILD_DIR && prj d"
