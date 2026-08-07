# Geri Dönüş Noktaları (Rollback)

Bir şey bozulursa buradaki commit'e dönülür. **En üstteki her zaman en son
bilinen-çalışan sürümdür.**

## Nasıl geri dönülür

Sunucuda:

```bash
cd /root/hakanerbasss.github.io
git fetch origin
git reset --hard <COMMIT>
systemctl restart tts
```

Sadece arayüzü geri almak istersen (backend değişikliklerini korur):

```bash
cd /root/hakanerbasss.github.io
git checkout <COMMIT> -- supertonic-web/static/index.html
systemctl restart tts
```

> Tarayıcı eski arayüzü göstermeye devam ederse sayfayı 2 kez yenile —
> servis çalışanı (PWA) önce yeni HTML'i çekiyor, sonra gösteriyor.

---

## Noktalar

### `c6f6ece` — Ayarlar modalı blob hatası ÇÖZÜLDÜ (gerçek kaynak)
**Tarih:** 07.08.2026
**Durum:** Playwright ile modal açılıp blob yeniden üretildi, düzeltme
doğrulandı (hem açık hem koyu tema). Bilinen-çalışan.

- Sebep: "Ses Klonu" bölümündeki "Doğal ses motorunu kullan" toggle'ı
  `class="toggle"` kullanıyordu, olması gereken `class="toggle-switch"`
  (diğer 5 toggle'da doğru). `.toggle-slider` (position:absolute;inset:0)
  konumlandırma referansını `.toggle-switch`'in position:relative'inden
  alıyordu; yanlış class'ta bu hiç uygulanmadığından en yakın
  position:fixed ata olan modal kutusuna göre tüm modalı kaplıyordu,
  border-radius:999px de bunu oval/yumurta şekline çeviriyordu.
- `fbb8f3e`'deki sürükle-bırak ve mobil `button{width:100%}` teorileri
  yanlıştı ama zararsız olduğundan geri alınmadı.

### `fbb8f3e` — Telegram tekrar-gönderim + Ayarlar modalı blob/geniş buton düzeltmesi
**Tarih:** 07.08.2026
**Durum:** Bilinen-çalışan (bekleniyor: kullanıcı sunucuda doğrulayacak).

- `app.py`: TR Instagram-Only job'u Telegram cevabı beklerken (5 dk) artık
  "running" değil "waiting_telegram" damgası kullanıyor — sık deploy'larda
  `_rescue_interrupted_jobs_task` job'u tekrar tetikleyip Telegram'a haber
  listesini art arda göndermesin diye.
- `index.html`: Ayarlar modalındaki (`#yt-modal`) butonlar artık mobil
  `button{width:100%}` kuralından muaf — ✕ kapat butonu tüm satırı kaplayan
  geniş gri çubuğa dönüşüyordu. Ayrıca tüm elemanlarda
  `-webkit-tap-highlight-color: transparent` eklendi (olası MIUI/WebView
  dokunma-vurgulama kaynaklı blob'lara karşı).
- Bir önceki commit'teki (`441e572`) sürükle-bırak teorisi YANLIŞTI —
  kullanıcı deploy sonrası hatanın sürdüğünü bildirdi. O değişiklik zararsız
  olduğu için geri alınmadı ama asıl blob sebebi bu commit'teki buton kuralı.

### `893ff66` — arayüz yeniden düzenlemesi TAMAMLANDI
**Tarih:** 06.08.2026
**Durum:** Arayüz 6096 → 4857 satır. 5 adımın hepsi bitti.

- Açık/karanlık tema (header'daki 🌙 düğmesi)
- Alt nav: Short Üret / Instagram / Canlı Yayın / Analitik YT / Daha Fazla
- Ayarlar header'daki ⚙ düğmesinde, sadece 4 gerçek ayar bölümü kaldı
- Silinen sekmeler: Trend Haber LV, Bilgi Shorts, Komik Haber,
  Çeviri+Seslendir, Video Seslendirme, Uzun Video
- Kapatılan zamanlayıcılar (app.py startup): `_rebuild_tnlv_scheduler`,
  `_rebuild_lv_scheduler`, `_rebuild_lv_en_scheduler` — geri istenirse
  yorum satırlarını açmak yeterli, kodları duruyor.

### `97e1b7a` — arayüz yeniden düzenlemesi ÖNCESİ son çalışan sürüm
**Tarih:** 06.08.2026
**Durum:** Bilinen-çalışan. Arayüz karışık ama tüm özellikler işliyor.

Bu sürümde çalışan/düzeltilmiş olanlar:
- Haber üretimi engelsiz (tüm 422 doğrulama kapıları kaldırılmış durumda)
- Edge TTS 7.2.8'e güncellendi (403 handshake hatası düzeltildi)
- Kapak paletlerinde kırmızı başlık okunabilirlik sorunu düzeltildi
- venv izolasyonu tamam, PWA önbelleği ağ-öncelikli
- Canlı yayın OAuth/redirect_uri düzeltmeleri

**Bundan sonrası:** Arayüz yeniden düzenlemesi (tema, sekme taşımaları,
Ayarlar sadeleştirmesi). Sadece `static/index.html` değişiyor, backend'e
dokunulmuyor — yani sorun çıkarsa yukarıdaki "sadece arayüzü geri al"
komutu yeterli.
