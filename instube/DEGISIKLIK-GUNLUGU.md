# InsTube — Değişiklik Günlüğü

**Bu dosya "kim en son ne yaptı?" sorusunun tek cevabıdır.** En üstteki kayıt
her zaman en yenisidir. Kod okuyup tahmin etme — önce buraya bak.

## Her oturumun uyacağı 3 kural

1. **Başlarken:** `git fetch origin main && git reset --hard origin/main`
   (Oturum açılırken bu otomatik kontrol ediliyor — uyarı çıkarsa görmezden gelme.)
2. **İş biterken:** aşağıya **en üste** bir kayıt ekle, sonra commit et.
3. **Commit'i main'e al ve dalı sil.** main'e girmeyen iş yok sayılır;
   sunucu (`git pull`) sadece main'i çeker.

Kayıt şablonu — kopyala, doldur, **en üste** yapıştır:

```
### GG.AA.YYYY — <tek cümlelik özet>
**Commit:** `<hash>` · **Dal:** `<dal adı veya main>` · **Durum:** sunucuda test edildi / edilmedi

- Ne değişti (dosya adıyla): ...
- Neden: ...
- Dikkat: bir sonraki oturumun bilmesi gereken şey (yarım kalan iş, riskli yer)
```

---

## Kayıtlar

### 22.08.2026 — Sıfırdan sunucu kurulumu (deploy/) — InsTube artık kendi venv'inde
**Commit:** `bu commit` · **Dal:** `main` · **Durum:** sunucuda ÇALIŞTIRILMADI (yeni sunucu için hazırlandı)

- Yeni: `deploy/bootstrap.sh` — boş bir Ubuntu'yu tek komutla çalışır hâle
  getirir (sistem paketleri, swap, venv'ler, Playwright, TTS modelleri,
  systemd, nginx, opsiyonel HTTPS). Token/API key gerekmez.
- Yeni: `deploy/systemd/instube.service` — **InsTube artık sistem Python'u
  değil, kendi `.venv`'ini kullanıyor** (`instube/.venv/bin/python`).
  Sebep: aynı sunucudaki başka bir proje sistem paketlerini düşürdüğünde
  InsTube kırılıyordu (supertonic-web'de 05.08'de httpx yüzünden yaşandı).
- Depodaki eski `instube/instube.service` (sistem Python'lu) DURUYOR ve
  **mevcut sunucuda hâlâ o çalışıyor** — bootstrap yalnızca yeni kurulumda
  yenisini yazıyor. Mevcut sunucuyu venv'e geçirmek istersen:
  `bash deploy/bootstrap.sh` tekrar çalıştırılabilir (idempotent).
- **Dikkat:** InsTube bağımlılıkları boş bir venv'de test edildi, sorunsuz
  kuruldu (`supertonic 1.3.1` dahil — torch değil, onnxruntime çekiyor) ve
  `app.py` ayar dosyası olmadan import edilebiliyor. Ama bootstrap'ın TAMAMI
  gerçek bir sunucuda hiç çalıştırılmadı; ilk çalıştıran sonucu buraya yazsın.

### 17.08.2026 — Oturumların birbirini ezmesini önleyen düzen kuruldu
**Commit:** `bu commit` · **Dal:** `claude/instube-session-conflicts-6kwi9r` · **Durum:** sunucu gerektirmez (sadece depo düzeni)

- Yeni: bu günlük dosyası (`instube/DEGISIKLIK-GUNLUGU.md`).
- Yeni: `.claude/hooks/session-start.sh` + `.claude/settings.json` — her yeni
  oturum açıldığında otomatik olarak "bu kopya main'in kaç commit gerisinde,
  InsTube'a en son ne yapıldı" raporunu yazar ve eski kopyayla çalışmayı
  engeller.
- Güncellendi: `CLAUDE.md` → "Oturum çakışmaları" bölümü (tek dal kuralı).
- **Tespit edilen asıl sebep:** InsTube kodu 05.08.2026'daki ilk commit'ten
  sonra main'e hiç girmemiş. Oturumlar `claude/*` dallarına push ediyor,
  o dallar main'e alınmadan bırakılıyor; uzakta 26 tane böyle dal birikmiş.
  Bir sonraki oturum eski main'den başlayınca öncekinin işini görmüyor ve
  üzerine yazıyor.
- **Dikkat / yarım kalan iş:** `claude/*` dallarının içinde main'e girmemiş
  InsTube işi olabilir. Kontrol:
  `git ls-remote --heads origin 'refs/heads/claude/*'` ile dalları listele,
  sonra her biri için `git log origin/main..origin/<dal> -- instube/`.
  Değerli olan varsa main'e al, kalanları sil.
