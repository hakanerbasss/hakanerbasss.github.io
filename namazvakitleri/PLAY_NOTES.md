# Play Console Metinleri

## Sürüm Notları — v2.6 (versionCode 10)

### tr-TR (500 karakter siniri)

```
Büyük güncelleme! 🎉
• Ana ekran widget'ı ve çevrimdışı çalışma
• Uygulama kapalıyken bile vakit bildirimi
• Zikirmatik (sesli/titreşimli), kaza takibi, Esmaül Hüsna
• Sureler ve dualar: Arapça, okunuş, meal + hafız kıraati (sesli takip)
• Namaz eğitimi: abdest, gusül, kadın/erkek kılınış adım adım
• Kandil ve bayram bildirimleri, dini günler takvimi
• Dini haberler, günün sözü ve görseli
• Kıble pusulasında Kabe simgesi, hicri tarih, Ramazan modu
• Türkçe + İngilizce dil desteği
```

### en-US

```
Major update! 🎉
• Home screen widget and offline mode
• Prayer notifications even when the app is closed
• Tasbih counter (with sound), missed prayer tracker, 99 Names of Allah
• Surahs & duas: Arabic, transliteration, meaning + real recitation with auto-follow
• Prayer guide: wudu, ghusl, step-by-step salah for men & women
• Islamic day alerts and calendar
• Religious news, daily quote and photo
• Kaaba icon on qibla compass, hijri date, Ramadan mode
• Turkish + English support
```

## Kısa Açıklama (80 karakter)

TR: `Namaz vakitleri, ezan bildirimi, kıble, zikirmatik, sureler ve dini takvim`
EN: `Prayer times, adhan alerts, qibla, tasbih, surahs and Islamic calendar`

## Uzun Açıklama — özellik bloğu

```
🕌 Diyanet uyumlu namaz vakitleri (dünyanın her şehri)
🔔 Uygulama kapalıyken bile vakit bildirimi + vakitten önce hatırlatma
📱 Ana ekran widget'ı — vakitler her an gözünün önünde
📿 Zikirmatik: sesli, titreşimli, hedefli (33/99/500/1000)
🕋 Kıble pusulası — Kabe simgeli, mesafe göstergeli
📖 Sureler ve dualar: Arapça + okunuş + meal, hafız kıraati ile takipli okuma
🎓 Namaz eğitimi: abdest, gusül, kadın/erkek namaz kılınışı adım adım
📅 Dini günler takvimi — kandil ve bayram bildirimleri
🗓️ Aylık imsakiye, hicri tarih, kaza takibi, Esmaül Hüsna
📰 Dini haberler • 💬 Günün hadisi/sözü ve görseli
🌙 Ramazan modu: iftar ve imsak geri sayımı
🌍 Türkçe ve İngilizce
```

## İzin Beyanları (Play Console sorarsa)

- POST_NOTIFICATIONS: Namaz vakti bildirimleri için
- SCHEDULE_EXACT_ALARM: Ezan vaktinde dakik bildirim için (uygulamanın temel işlevi)
- ACCESS_COARSE_LOCATION: Kıble yönü hesaplamak için (yalnızca cihazda kullanılır)
- RECORD_AUDIO: Zikirmatikte isteğe bağlı kişisel ses kaydı için (kayıt cihazda kalır)
- RECEIVE_BOOT_COMPLETED: Telefon yeniden başlayınca bildirim alarmlarını geri kurmak için

## Veri Güvenliği formu özeti

- Konum: cihazda işlenir, paylaşılmaz (kıble)
- Ses kaydı: cihazda saklanır, paylaşılmaz (zikirmatik)
- API anahtarları: yalnızca cihazda (kullanıcının kendi anahtarları)
- Reklam: AdMob (Google) — reklam kimliği toplanır
- FCM: bildirim için anonim topic aboneliği
