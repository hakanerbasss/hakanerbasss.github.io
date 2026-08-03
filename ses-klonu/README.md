# 🎙 Ses Klonu Stüdyosu

Kendi sesinle Türkçe haber seslendirme (XTTS-v2) + kendi fotoğrafını
konuşturma (Wav2Lip). Ücretsiz HuggingFace Spaces üzerinde çalışır —
Hetzner sunucusuna yük bindirmez (4 GB RAM oraya yetmez).

---

## ⚠️ "Gradio ücretli" göründüyse — Space oluştururken GPU seçtiyseniz

HuggingFace Spaces'te **CPU Basic katmanı tamamen ücretsizdir.** Space
oluştururken doğru donanımı seçmek gerekiyor:

```
New Space sayfasında:
  Space Hardware → CPU Basic (Free)   ← BU seçilmeli
                   CPU Upgrade        ← ücretli
                   T4 Small           ← ücretli GPU
                   A10G Small         ← ücretli GPU
```

GPU seçildiyse ya da ücretli ekran çıktıysa Space'i silin ve aşağıdaki
Bölüm 1'deki adımlarla sıfırdan oluşturun — bu sefer **CPU Basic (Free)**
seçin.

---

## Bölüm 1 — Kendi sesinle TTS (ücretsiz, bugün kurulur)

### 1. Referans ses kaydet
- **20-30 saniye**, sessiz odada, telefon mikrofonu yeterli
- Haber sunar gibi doğal ve akıcı konuş (klon, kayıttaki tonu taklit eder)
- `referans_sesim.wav` adıyla kaydet (mp3 ise dönüştür: `ffmpeg -i kayit.mp3 referans_sesim.wav`)

### 2. HuggingFace Space aç (ücretsiz CPU)

1. https://huggingface.co → ücretsiz hesap aç (varsa giriş yap)
2. Sol üstten **Profil → New Space**
3. Doldur:
   - **Space name:** `ses-klonu`
   - **SDK:** Gradio
   - **Space Hardware:** ⚠️ **CPU Basic (Free)** — Bu satırda `$0.00/hour` yazar
   - **Visibility:** Private (sesin başkasının eline geçmesin)
4. **Create Space** — boş Space oluşur
5. **Files** sekmesine gir → **Add file → Upload files**
6. Şu 3 dosyayı yükle:
   - `ses-klonu/app.py`
   - `ses-klonu/requirements.txt`
   - `referans_sesim.wav` (senin ses kaydın — repo'ya ekleme, sadece Space'e yükle)
7. Space otomatik derlenir. **İlk açılış 5-10 dakika sürer** — 2 GB XTTS-v2 modeli indirilir.

### 3. Dene

Space sayfasındaki Gradio arayüzüne gir → metni yapıştır → **Seslendir**.

Ücretsiz CPU'da:
- 60 saniyelik haber metni ≈ **1-4 dakika** üretim süresi (planlı paylaşım için sorun değil)
- Modeli RAM'de tutar — ikinci istekten itibaren daha hızlı

### 4. Bota bağla

Bot sunucusunda:
```bash
pip install gradio_client
```

`bot_entegrasyon.py` dosyasında `SPACE_ID`yi güncelle:
```python
SPACE_ID = "senin-hf-kullanici-adin/ses-klonu"
```

HF_TOKEN'ı (Private Space için zorunlu) sunucudaki `secrets.json`'a ekle:
```json
{ "HF_TOKEN": "hf_..." }
```

Test:
```bash
HF_TOKEN=hf_... python3 bot_entegrasyon.py
```

> Not: Ücretsiz Space 48 saat kullanılmayınca uykuya geçer; ilk istek
> birkaç dakika soğuk başlatma bekler. Bot her gün kullanacağı için
> pratikte hep sıcak kalır.

---

## Alternatif: Hetzner'e doğrudan kurulum

HF Spaces yerine kendi Hetzner sunucusuna kurmak istersen, mevcut CX23'ün
4 GB RAM'i XTTS-v2 için yetmez. **CX33 (8 GB RAM, ~7 €/ay)** gerekir.
Bu tercih edilirse `supertonic-web/app.py`'e doğrudan TTS endpoint
eklenebilir — ama önce ücretsiz HF Spaces yolunu dene.

---

## Bölüm 2 — Konuşan fotoğraf (`konusan-foto/`)

Fotoğrafın + klonlanmış ses → dudakları oynayan sunucu videosu.

**Dürüst durum tespiti:** bu iş GPU sever. Seçenekler:

| Yol | Maliyet | Hız | Kalite |
|---|---|---|---|
| **Kaggle Notebook** (önerilen) | Ücretsiz (haftada 30 saat GPU) | 60 sn video ≈ 1-2 dk | İyi |
| Google Colab (ücretsiz T4) | Ücretsiz (günlük kota) | 60 sn ≈ 1-2 dk | İyi |
| Kendi PC (NVIDIA varsa) | Ücretsiz | Hızlı | İyi |
| HF Space ücretsiz CPU | Ücretsiz | 60 sn ≈ 15-40 dk ⚠️ | İyi ama çok yavaş |

Kurulum (Kaggle/Colab/PC hepsinde aynı):

```bash
cd konusan-foto
bash setup_wav2lip.sh
python3 make_talking_photo.py --foto ben.jpg --ses haber.wav --cikti video.mp4
```

Çıkan videoyu FFmpeg ile Reels şablonuna oturtabilirsin (köşede konuşan
sen + arkada haber görselleri — botun mevcut sahne sistemine köşe overlay
olarak eklenebilir, istenirse o entegrasyonu ayrıca yaparız).

Daha doğal kafa hareketi istersen: **SadTalker** (GPU şart) — Wav2Lip ağzı
oynatır, SadTalker kafayı da hafifçe hareket ettirir. Önce Wav2Lip ile
başla, beğenirsen SadTalker'a geçeriz.

---

## Önemli notlar

- **Lisans:** XTTS-v2 model lisansı (CPML) **ticari olmayan** kullanım
  içindir. Hesap para kazanmaya başlarsa MIT lisanslı alternatife geçmek
  gerekir (örn. Chatterbox Multilingual — Türkçe destekli); bu repo yapısıyla
  app.py içinde model değişimi yeterlidir.
- **Etik:** yalnızca **kendi sesini ve kendi fotoğrafını** klonla. Profildeki
  "🤖 Yapay zeka içerik üreticisi" ibaresi bu içerikler için de doğru ve
  yerinde — kalsın.
- **Gizlilik:** Space'i **Private** yap ki referans ses dosyanı ve API'yi
  başkası kullanamasın.
