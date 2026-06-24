#!/usr/bin/env bash
set -e

# Gradle wrapper yoksa sistem gradlew'i kullan
if [ -f "./gradlew" ]; then
    GRADLE="./gradlew"
elif command -v gradle &>/dev/null; then
    GRADLE="gradle"
else
    echo "Hata: gradle veya gradlew bulunamadı."
    echo "Termux: pkg install gradle"
    exit 1
fi

ACTION="${1:-debug}"

case "$ACTION" in
    debug)
        $GRADLE assembleDebug
        echo ""
        echo "APK: app/build/outputs/apk/debug/app-debug.apk"
        ;;
    release)
        $GRADLE assembleRelease
        echo ""
        echo "APK: app/build/outputs/apk/release/app-release-unsigned.apk"
        ;;
    install)
        $GRADLE assembleDebug
        adb install -r app/build/outputs/apk/debug/app-debug.apk
        echo "Kurulum tamamlandı."
        ;;
    install-release)
        $GRADLE assembleRelease
        adb install -r app/build/outputs/apk/release/app-release-unsigned.apk
        ;;
    clean)
        $GRADLE clean
        echo "Temizlendi."
        ;;
    *)
        echo "Kullanım: $0 [debug|release|install|install-release|clean]"
        exit 1
        ;;
esac
