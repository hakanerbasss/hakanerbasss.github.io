# Namaz Vakitleri (com.wizaicorp.namazvakitleri)

Android uygulaması — Kotlin + Jetpack Compose. Termux'ta geliştirilir ve build alınır
(`~/namazvakitleri`), kaynak kodun ana kopyası bu depodadır.

## Özellikler (v2.6)

v2.1+: Zikirmatik sesi (TTS/kayıt) • dini gün + kaza bildirimleri • Esma sesli okuma
v2.2: Dini Kütüphane — 12 sure + 9 dua (Arapça/okunuş/meal, sesli + imleç takibi)
v2.3: API Anahtarları ekranı (Pexels/DeepSeek, BYOK) • Günün Sözü + görseli • Dini Haberler (Google News RSS) • AI Asistan (sesli) • kıblede Kabe simgesi
v2.4: Namaz Eğitimi — abdest/gusül/teyemmüm, kadın-erkek namaz kılınışı, rekât tablosu
v2.5: Hafız kıraati (everyayah stream, Alafasy) • Ramazan modu (iftar/imsak sayacı)
v2.6: Geri tuşu navigasyonu • App Open reklam korumaları • widget'a tarih/hicri satırı

### v2.0 tabanı

- Aladhan API'den (Diyanet metodu 13) şehir adına göre namaz vakitleri
- **Ana ekran widget'ı** — günün 6 vakti, sıradaki vakit vurgulu
- **Çevrimdışı mod** — vakitler önbelleğe alınır, internetsiz de gösterilir
- **Arka plan bildirim zinciri** — uygulama açılmasa da her gece 00:05'te
  yeni günün alarmları kurulur; telefon yeniden başlayınca geri yüklenir
- Hicri tarih (ana ekranda) + sıradaki vakte ilerleme çubuğu
- **Zikirmatik** — dokunmatik sayaç, titreşim, hedef 33/99/500/1000, toplam
- **Dini Günler** — kandiller/bayramlar hicri takvimden otomatik + geri sayım
- **Kaza Takibi** — vakit başına sayaç, +1 gün toplu ekleme
- **Esmaül Hüsna** — 99 isim + günün esması kartı
- **TR/EN dil desteği** (cihaz diline göre otomatik, ayarlardan seçilebilir)
- Aylık takvim (imsakiye), kıble pusulası
- Vakit bildirimleri: tam vakitte + X dk önce hatırlatma (ikisi birden)
- Firebase FCM (uzaktan bildirim)
- AdMob: banner (tüm ekranlar) + frekans korumalı interstitial + app open + UMP
- Paylaş / Play'de değerlendir / gizlilik politikası bağlantıları
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
