# 🎙 Ses Klonu Stüdyosu

Kendi sesinle Türkçe haber seslendirme (XTTS-v2) + kendi fotoğrafını
konuşturma (Wav2Lip). Ücretsiz HuggingFace Spaces üzerinde çalışır —
Hetzner sunucusuna yük bindirmez (4 GB RAM oraya yetmez).

## Bölüm 1 — Kendi sesinle TTS (ücretsiz, bugün kurulur)

### 1. Referans ses kaydet
- **20-30 saniye**, sessiz odada, telefon mikrofonu yeterli
- Haber sunar gibi doğal ve akıcı konuş (klon, kayıttaki tonu taklit eder)
- `referans_sesim.wav` adıyla kaydet (mp3 ise dönüştür: `ffmpeg -i kayit.mp3 referans_sesim.wav`)

### 2. HuggingFace Space aç (ücretsiz)
1. https://huggingface.co → ücretsiz hesap aç
2. Profil → **New Space** → isim: `ses-klonu`
   - SDK: **Gradio** · Hardware: **CPU basic (free)** · Visibility: **Private** (sesin başkasının eline geçmesin)
3. Space'in **Files** sekmesinden şu 3 dosyayı yükle:
   - `app.py` (bu klasördeki)
   - `requirements.txt` (bu klasördeki)
   - `referans_sesim.wav` (senin kaydın)
4. Space otomatik derlenir. İlk açılış 5-10 dk sürer (2 GB model iniyor) — sonrasında hazır.

### 3. Dene
Space sayfasında metni yapıştır → **Seslendir**. Ücretsiz CPU'da 60 saniyelik
haber metni yaklaşık **1-4 dakikada** üretilir (planlı paylaşım için sorun değil).

### 4. Bota bağla (istersen)
Bot sunucusunda `pip install gradio_client`, sonra `bot_entegrasyon.py`
dosyasındaki `SPACE_ID`yi kendi kullanıcı adınla güncelle. Test:

```bash
python3 bot_entegrasyon.py
```

> Not: Ücretsiz Space 48 saat kullanılmayınca uykuya geçer; ilk istek
> birkaç dakika soğuk başlatma bekler. Bot her gün kullanacağı için
> pratikte hep sıcak kalır.

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
