# Gerçek Hesap Geçiş Kontrol Listesi

2 ay testnet çalıştırdıktan sonra bu adımları sırayla uygula.
**Her adımı tamamladıktan sonra işaretle — acele etme.**

---

## 1. Geçiş Kararını Ver (2 ay sonra)

Aşağıdaki soruları kendin cevapla. Hepsi "evet" değilse bekle.

- [ ] **Profit Factor ≥ 1.3** — haftalık özetlerde tutarlı mı?
- [ ] **En az 80-100 kapalı işlem** — yeterli veri var mı?
- [ ] **Hem yükseliş hem düşüş dönemini gördü** — sadece boğa piyasasında test etme.
- [ ] **En büyük kayıp tek işlem** ne kadar? Kabul edilebilir mi?
- [ ] **Max drawdown** (haftalık özetlerde görürsün) bütçeni zorluyor mu?

---

## 2. Binance Sub-Account Aç (ÇOK ÖNEMLİ)

Mevcut $8k manuel pozisyonların ve botun kesinlikle farklı hesaplarda olması gerekiyor.

- [ ] Binance → Profil → Sub-accounts → Yeni sub-account oluştur
- [ ] Sub-account'a bot sermayesini transfer et (başlangıç: ~10k TL / ~$300)
- [ ] Sub-account için yeni API key oluştur (sadece Spot + okuma izni, çekim izni AÇMA)
- [ ] Yeni API key ve Secret'ı not al

**Neden zorunlu?** Bot, config'deki API key ile bağlandığı hesaptaki TÜM işlemleri
kendi işlemi sanır. Ana hesabında BTC varsa bot onu da satmaya çalışabilir.

---

## 3. Bot Config'ini Güncelle

Ayarlar sayfasında (web dashboard):

- [ ] `Testnet` → KAPALI
- [ ] `Real API Key` → sub-account'ın API key'ini gir
- [ ] `Real API Secret` → sub-account'ın Secret'ını gir
- [ ] `Maks. Açık Pozisyon` → **3** yap (sermaye yeterince büyüyünce artırırsın)
- [ ] `SL Cooldown` → 4 saat (gerçek hesapta daha muhafazakâr)
- [ ] **Kaydet**

---

## 4. positions.json'ı Temizle (KESİNLİKLE YAPILMALI)

Testnet pozisyonları hâlâ positions.json'da duruyor. Gerçek hesaba geçince
bot bu testnet coinlerini gerçek hesapta elinde sanır — ama orada yok!
Satmaya çalışır, hatalar üretir.

- [ ] Web dashboard → **"Pozisyonları Temizle"** butonuna bas
  (ya da Telegram'dan `/temizle` komutu)
- [ ] Dashboard'da "Açık Pozisyon" sıfır gösterdiğini doğrula

---

## 5. Küçük Test Emri

- [ ] Ayarlar'da `max_positions: 1` yap
- [ ] Coin listesinde tek bir ucuz coin bırak (örn. DOGEUSDT, $10-15 tutar)
- [ ] Botu başlat, ilk alımı bekle
- [ ] Binance sub-account'ında gerçekten işlem göründüğünü doğrula
- [ ] İşlem başarılı → `max_positions: 3` yap, diğer coinleri ekle

---

## 6. İlk Hafta Kuralları

- [ ] Günlük Telegram raporlarını takip et
- [ ] Dashboard'daki **"Gerçekleşen K/Z"** kartını izle (kâğıt K/Z değil)
- [ ] Bir haftada -$50'den fazla gerçekleşmiş zarar olursa botu manuel durdur, incele
- [ ] Aceleyle sermaye ekleme — önce küçük miktarla sisteme güven

---

## Özet Tablo

| Adım | Açıklama | Kritiklik |
|------|----------|-----------|
| Sub-account aç | $8k ana hesabını koru | 🔴 Zorunlu |
| positions.json temizle | Testnet kalıntılarını sil | 🔴 Zorunlu |
| max_positions: 3 | Küçük sermayeye uygun | 🟡 Önemli |
| Test emri | Bağlantıyı doğrula | 🟡 Önemli |
| Profit Factor kontrolü | Geçişe gerçekten hazır mısın? | 🟢 Karar kriteri |
