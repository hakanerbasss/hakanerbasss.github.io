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
