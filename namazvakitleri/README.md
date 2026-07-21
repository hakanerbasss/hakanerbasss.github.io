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
| `app/google-services.json` | Firebase config — build için zorunlu, Termux'tan alınacak |
| `app/src/main/res/mipmap-*/` | Launcher ikonları (binary) — Termux'tan alınacak |
| `app/src/main/res/drawable/mosque_logo.*` | MainScreen logosu (binary) — Termux'tan alınacak |
| `local.properties` | `sdk.dir` + API anahtarları — gitignore'da |
| `*.keystore / *.jks` | İmza anahtarı — ASLA git'e koyma, ayrıca yedekle |
| `gradlew`, `gradle/wrapper/gradle-wrapper.jar` | Wrapper binary'leri — Termux'ta mevcut |

## Termux ↔ GitHub akışı

```bash
# Termux'ta ilk kurulum (mevcut klasörü git'e bağla):
cd ~/namazvakitleri
git init && git remote add origin https://github.com/hakanerbasss/hakanerbasss.github.io.git
# Not: bu depo monorepo — namazvakitleri/ alt klasöründe yaşar.
# Pratik yol: depoyu ayrı klasöre klonla, namazvakitleri/ içeriğini rsync ile eşitle.

# Build (Termux):
cd ~/namazvakitleri && gp        # veya: prj d (debug) / prj b (release)
```

## Sürüm

- versionCode 3, versionName 1.1
- compileSdk/targetSdk 35, minSdk 26, Java 17, Kotlin 1.9.24, AGP 8.5.1 (16 KB uyumlu)
