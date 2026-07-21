# Namaz Vakitleri (com.wizaicorp.namazvakitleri)

Android uygulaması — Kotlin + Jetpack Compose. Termux'ta geliştirilir ve build alınır
(`~/namazvakitleri`), kaynak kodun ana kopyası bu depodadır.

## Özellikler

- Aladhan API'den (Diyanet metodu 13) şehir adına göre namaz vakitleri
- Aylık takvim (imsakiye) ekranı
- Kıble pusulası
- Vakit bildirimleri — tamamen yerel (AlarmManager, exact alarm)
- Firebase FCM (uzaktan bildirim)
- AdMob (banner + interstitial + app open) ve UMP consent
- Gizlilik politikası: depo kökündeki `namaz-gizlilik.html`
  → https://hakanerbasss.github.io/namaz-gizlilik.html

## Depoda OLMAYAN dosyalar (Termux'ta kalır / git'e girmez)

| Dosya | Durum |
|-------|-------|
| `local.properties` | `sdk.dir` + API anahtarları — gitignore'da |
| `*.keystore / *.jks` | İmza anahtarı — ASLA git'e koyma, ayrıca yedekle |
| `gradlew`, `gradle/wrapper/gradle-wrapper.jar` | Wrapper binary'leri — Termux'ta mevcut |
| `.gradle/`, `build/` | Build çıktıları — gitignore'da |

`google-services.json`, launcher ikonları ve `mosque_logo.png` depodadır —
depo Termux projesinin tam yedeğidir (yukarıdaki satırlar hariç).

## Termux ↔ GitHub akışı

Build GitHub'da ALINMAZ — build her zaman Termux'ta. GitHub yedekleme +
senkronizasyon içindir: Claude branch'e push eder, Termux'ta çekilip
`~/namazvakitleri` üzerine yazılır.

Termux'ta `namaz` komutu kuruludur (`tools/namaz` scripti,
`$PREFIX/bin/namaz` olarak). Tek komutla GitHub'dan son sürümü çekip
`~/namazvakitleri` üzerine yazar:

```bash
namaz          # GitHub'dan guncelle
tos 15 d       # APK build (test)
tos 15 2       # imzali AAB (release)
```

Script kaybolursa yeniden kurulum:
`cp ~/repo-sync/namazvakitleri/tools/namaz $PREFIX/bin/namaz && chmod +x $PREFIX/bin/namaz`

Kural: Termux'ta elle kod değişikliği yapılmaz — `namaz` komutu depodaki
halin üzerine yazar. Tüm kod değişiklikleri GitHub (Claude) üzerinden gelir.

## Sürüm

- versionCode 3, versionName 1.1
- compileSdk/targetSdk 35, minSdk 26, Java 17, Kotlin 1.9.24, AGP 8.5.1 (16 KB uyumlu)
