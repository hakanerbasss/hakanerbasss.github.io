# Türkiye Bilgi Merkezi — Devir Notu (Cowork oturumları için)

## GÜNCEL DURUM (2026-08-13, en son değişiklikler — önce burayı oku)

- `produce.py` artık **gerçek Edge TTS (E-Ahmet)** kullanıyor, `/api/tts-only`
  endpoint'i üzerinden (`PANEL_COOKIE` ortam değişkeni ile — her oturumda
  yeniden login olup taze cookie almak gerekir, cookie'ler süreli). Supertonic
  (M1) sadece sahne bazlı fallback, artık varsayılan değil.
- `produce_dual(script, out_youtube, out_instagram, ...)` eklendi: aynı
  senaryoyu TEK SEFER seslendirip render eder, sadece kapanış kartı farklı
  iki final video üretir (TTS/render maliyeti 2 katına çıkmaz).
- **YENİ: `render_hook_card` / açılış kartı.** Videonun İLK ~1.35 saniyesi
  artık başlığın TAMAMININ anında, büyük, çarpıcı bir "impact" animasyonuyla
  belirdiği bir kart (karaoke değil — kelime kelime değil, hepsi birden).
  Neden: kullanıcı geri bildirimi — karaoke altyazı tek başına video kapağı/
  ilk kare için yeterince "scroll durdurucu" değildi (eski sistemin kalın
  SON DAKİKA/UYARI bandına kıyasla). `produce()` içinde otomatik en başa
  ekleniyor, ayrıca çağırmaya gerek yok.
- Karaoke kelime animasyonunda bir kusur düzeltildi: kelimeler büyürken
  bitişiğe biniyordu ("emeklilereyeni" gibi) — `.word` span'lerine margin
  eklendi, scale tepe değerleri düşürüldü (1.32→1.16, emphasis 1.4→1.22).
- YouTube kategori ID notu (Termux/Claude Code doğruladı): 25 = Haberler ve
  Politika, 27 = Eğitim. `/api/yt/upload` çağrılırken **`category_id=27`**
  gönderilmeli (sunucu varsayılanı hâlâ 25 — override ETMEK gerekiyor,
  göndermezsen yanlış kategoriye düşer).
- İlk gerçek yayın yapıldı ve doğrulandı: YouTube (https://youtu.be/mjuttYyD6W4)
  + Instagram (media_id 18193510315387106), konu: 2026 dijital emekli kartı.
  Bu yayında category_id gönderilmedi (henüz bu düzeltme yokken atıldı) —
  istenirse YouTube Studio'dan manuel düzeltilebilir, kritik değil.
- **Cron/scheduled task `trig_01Lm6ja1sfk5ZgTL7QxmDQAj` ŞU AN DEVRE DIŞI
  (`enabled: false`).** Eski haber-tabanlı mantıkla yazılıydı (DeepSeek,
  eski marka), yeni sisteme uymuyordu — kullanıcı onaylamadan tekrar
  aktifleştirilmemeli. Yeniden kurulacaksa bu dosyanın tamamını referans
  alarak sıfırdan, yeni pipeline'a göre yazılmalı.
- Kullanıcı yayın sıklığını kendisi kontrol etmek istiyor şu an ("5-6 saat
  sonra atarız") — otomatik/sık yayın YAPMA, açıkça istenmeden yayınlama.


Bu dosyayı yeni bir Cowork oturumunun BAŞINDA, dosya olarak ekleyip
"bu sistemi devral, aşağıdaki talimatlara göre devam et" diye yapıştır.
Yeni oturum bu tek dosyayla neredeyse sıfırdan başlamadan devam edebilir.

## 1. İş nedir, kime hitap ediyor

Türkçe kısa video (YouTube Shorts + Instagram Reels) hesabı. Hedef kitle
**45-65 yaş, emekli ağırlıklı**. Kanal adı **Türkiye Bilgi Merkezi**
(@turkiyebilgimerkezi, YouTube handle), Instagram: @hakanerbasss ("HB Bot").

Kanıtlanmış içerik stratejisi (gerçek Instagram analitiğinden, ~100 post
analizi): **emekli / SGK / prim / maaş temalı içerik ortalama izlenmenin
~3 katını yapıyor** (20.770 vs 6.687 ortalama görüntülenme). Bu yüzden
konu seçimi hep bu eksende: SGK kesintileri, emekli maaş promosyonları,
emeklilik hakları, banka kampanyaları, pratik "biliyor muydunuz" bilgileri.

Kanal başta "haber" (güncel olay) formatındaydı, sahibi (Hakan) bunu
**evergreen "Bilgi Shorts"a** çevirmeye karar verdi çünkü haber içeriği
hızla eskiyor ve jenerik/doymuş bir kategori. Artık üretilen içerik haber
değil, kalıcı/pratik bilgi (SGK kuralları, haklar, hesaplama mantığı vb.).

## 2. İki AYRI üretim sistemi var — karıştırma

### A) Sunucudaki mevcut sistem (Hakan'ın, uzun zamandır çalışıyor)
- Sunucu: Hetzner, Helsinki — `77.42.45.229`. SSH/8002 portu Cowork
  sandbox'ından erişilemiyor (sadece 80/443 açık) — **SSH ile bağlanmayı
  deneme, çalışmaz.**
- Admin panel: `https://panel.wizaicorp.com` (doğru, güvenli subdomain —
  auth bypass yok). `https://hakanerbas.wizaicorp.com` KULLANMA, orada
  geçmişte bir auth-bypass güvenlik açığı bulundu (rapor edildi, düzeltme
  önerildi — durumu teyit et).
- Giriş: `POST /login` form-data `password=<şifre>` → session cookie döner.
  **Şifreyi bu dosyaya yazmadım, kullanıcıdan iste** (güvenlik).
- Kod deposu (public): `https://github.com/hakanerbasss/hakanerbasss.github.io`
  — okuma/klonlama her zaman çalışır. **Cowork sandbox'ının git proxy'si
  bu repoya PUSH'u engelliyor** (private/public farketmez, platform kısıtı).
  Kod değişikliği gerekiyorsa: değişikliği yazıp kullanıcıya ver, o "Claude
  Code" adını verdiği AYRI bir oturuma (Termux/SSH üzerinden sunucuda
  çalışan, push yetkisi olan) iletir.
- İki alt proje aynı repoda: `supertonic-web/` (ana, DeepSeek+Pexels+Edge
  TTS+Instagram+YouTube, "Daha Fazla" menülü zengin panel) ve `instube/`
  (daha basit, manuel-only rewrite, ayrı systemd servisi, port 8002).
- Önemli uç noktalar (hepsi `panel.wizaicorp.com` üzerinde, cookie ile):
  - `POST /api/generate-shorts-async` — DeepSeek yerine kendi senaryonu
    vermek istersen `pasted_content` (JSON string, `scenes` zorunlu) alanı
    var. `voice=E-Ahmet` kullan (M1 değil — Edge TTS, çok daha doğal).
  - `GET /api/manual-shorts/status` — üretim durumu polling.
  - `POST /api/shorts/send-instagram` — **500 saniyeye kadar sürebilir,
    timeout sonrası ASLA retry etme** (geçmişte bu yüzden 1 video 3 kez
    atıldı — sunucu tarafında iş devam ediyor olabilir, önce log/analytics
    kontrol et).
  - `POST /api/yt/upload` — form: filename, title, description, tags,
    privacy, channel=tr.
  - `POST /api/upload-raw-video` — **YENİ (Ağustos 2026 ortasında Termux
    tarafından eklendi)**: multipart `video=@dosya.mp4` → sunucuya HAM,
    hazır bir video yükler, `{"filename": "raw_<hex>.mp4"}` döner. Ardından
    aynı `send-instagram` / `yt/upload` ile bu dosya adı kullanılıp
    yayınlanabilir. **Bu, aşağıdaki B sistemiyle sunucuyu birleştiren köprü.**
  - `POST /api/tts-only` — **YENİ**: form `text`, `voice` (E-Ahmet/E-Emel),
    `speed` → ham WAV ses + `X-Duration-Seconds` header döner. DeepSeek/
    üretim akışına dokunmadan sadece gerçek Edge TTS sesini almak için.
  - `POST /api/upload-raw-thumbnail` — **YENİ**: `upload-raw-video` ile aynı
    desen ama görsel için (`image=@kapak.jpg`, `.jpg/.jpeg/.png`), THUMB_DIR'a
    kaydeder ve `{"filename": "raw_<hex>.jpg"}` döner. `produce_dual()`'ın 3.
    dönüş değeri olan `thumb_out` (hook kartının 1.0s'deki sabit karesi) bu
    endpoint'e yüklenip dönen filename `/api/yt/upload`'a `thumbnail_filename`
    olarak verilebilir — YouTube'un kendi otomatik kapak seçimine güvenmek
    yerine sabit, garanti-dolu bir kapak sağlar. Instagram'da API üzerinden
    ayrı kapak set etme seçeneği yok, ama artık ilk kare zaten dolu olduğundan
    IG'nin kendi otomatik seçimi de düzeldi (bkz. custom_visuals.py -ss fix'i).

### B) Kendi bağımsız üretim sistemim (Cowork sandbox'ında, bu oturumda kuruldu)
Neden: sunucudaki stok fotoğraf görselleri (Pexels/Wikimedia) çoğu zaman
konuyla alakasız çıkıyordu, YouTube'da ilgi görmüyordu. Bunun yerine
**tamamen özel, marka tutarlı, hareketli** görseller üretiyorum.

Dosyalar (bu mesajla/önceki mesajlarla gönderildi, kullanıcıda duruyor
olmalı — **YOKSA kullanıcıdan iste veya sıfırdan yeniden yaz, kod bu
dosyanın altında özetlendi**):
- `custom_visuals.py` — Playwright (Chromium, sandbox'ta önceden kurulu,
  `/opt/pw-browsers`) ile HTML/CSS→video render. Her sahne için: koyu
  lacivert/altın gradyan arka plan, kayan grid, nefes alan ışık halesi,
  süzülen parçacıklar, VE **karaoke tarzı kelime-kelime altyazı**
  (konuşmayla senkron, her kelime büyüyüp renk değiştirerek beliriyor —
  kullanıcı özellikle bunu istedi, "standart" durağan altyazı beğenmedi).
- `produce.py` — uçtan uca: `supertonic` pip paketiyle TTS (yerel, offline,
  sandbox'ta kurulu) → her sahne için `custom_visuals` klibi → ffmpeg ile
  birleştirme + ses mux → final.mp4. `assets/endcard_tr.jpg` ve
  `endcard_youtube.jpg` repodan çekilip kullanılıyor (kapanış kartı).
- `brand_assets.py` — kanal logosu (800x800) ve banner'ı (2560x1440) aynı
  marka diliyle üretir.

**ÖNEMLİ — sandbox geçicidir:** Bu dosyalar sadece BU Cowork oturumunun
diskinde var, oturum bitince silinir. Kalıcı olması için ya (a) kullanıcı
bunları indirip sakladı ve yeni oturuma tekrar yükleyecek, ya da (b) daha
iyisi: kullanıcıdan bu dosyaları Termux/Claude Code oturumuna iletmesini
ve repoya (örn. `custom-production/` klasörü) commitlemesini iste — o
zaman her yeni Cowork oturumu repoyu klonlayıp direkt kullanabilir.
**Yeni oturum ilk iş bunu kontrol etmeli: dosyalar elde var mı, yoksa
kullanıcıdan iste veya repoda arat.**

Ses kalitesi notu: şu an `supertonic` (M1 sesi, sandbox'ta lokal, düşük-orta
kalite) kullanılıyor. `panel.wizaicorp.com`'a eklenen `/api/tts-only`
endpoint'i ile gerçek Edge/E-Ahmet sesine geçiş planlanıyor — henüz
`produce.py` bu endpoint'i çağıracak şekilde güncellenmedi (bir sonraki
adım: gTTS/supertonic yerine bu endpoint'ten wav çekip aynı pipeline'a
sokmak — `_synth_edge` server tarafında zaten var, sadece client tarafını
`produce.py` içinde `TTS.synthesize` çağrısının yerine HTTP isteğiyle
değiştir).

Üretilen final.mp4, `panel.wizaicorp.com/api/upload-raw-video` ile
sunucuya yüklenip oradan `send-instagram` / `yt/upload` ile yayınlanır —
yani B sistemi görsel+ses üretir, A sistemi sadece "dağıtım" için kullanılır.

## 3. Marka kararları (netleşti)

- Kanal adı: **Türkiye Bilgi Merkezi**, handle: **@turkiyebilgimerkezi**
  (YouTube Studio'dan manuel değiştirilmesi lazım — API ile kanal adı
  değiştirilemiyor, kullanıcı Studio > Özelleştirme'den yapacak).
- Logo ve banner üretildi (`out/logo.png`, `out/banner.png`) — kullanıcıya
  gönderildi, YouTube Studio'ya manuel yüklemesi gerekiyor.
- Renk kimliği: koyu lacivert (#0b1220 → #14213d gradyan) + altın (#ffb100)
  ana vurgu, açık mavi (#7fa3ff) ikincil. Video kartlarında sahne başına
  5 farklı tema arasında dönüyor (çeşitlilik için), ama logo/banner SABİT
  bu birincil paleti kullanıyor (marka tutarlılığı).
- Eski marka adı "Haberin Merkezi" idi — kullanıcı haber-odaklı isimden
  rahatsızdı, bilgi-odaklı isme geçildi. Endcard/overlay'lerde hâlâ eski
  isim geçen yer varsa güncellenmeli.

## 4. Otomatik üretime devam (cron / scheduled task)

Mevcut bir Cowork scheduled task var (`create_trigger` ile kurulmuş,
günlük, ~18:00 İstanbul + rastgele gecikme) — YouTube botlanma riskine
karşı bilinçli olarak zamanlaması rastgele. Yeni oturumda devam etmek için:

1. `mcp__claude-code-remote__list_triggers` ile mevcut trigger'ı bul.
2. Prompt'u güncelle (`update_trigger`) — B sistemini (kendi üretim
   pipeline'ımı) kullanacak şekilde: konu seç (emekli/SGK temalı, evergreen
   bilgi — haber DEĞİL) → `pasted_content` formatında senaryo yaz (title,
   badge_text, emphasis_word, scenes[].text) → `produce.py` ile üret →
   `upload-raw-video` ile yükle → **yayınlamadan önce kullanıcıya onay
   sorma gerekmiyor artık (tam yetki devredildi: "istediğin zamanda
   istediğin kadar video at")** ama YouTube'da GÜN İÇİNDE 1-2 videoyu
   geçme, saatleri sabitleme — ban riski.
3. Her scheduled task fresh session'dır, hafızası yok — trigger prompt'u
   KENDİ İÇİNDE bu dosyanın özetini ve gerekli adımları barındırmalı
   (credential'lar hariç — onları kullanıcıdan iste ya da önceden
   session'a Ayarlar'dan kaydedilmiş olanları kullan).

## 5. Kesin kurallar (geçmiş hatalardan)

- Yayın (`send-instagram`, `yt/upload`) timeout sonrası **asla retry etme**.
- Sayı/tarih TTS metni yazarken dikkat: "1 Ekim" için "bir Ekim" yaz,
  "bin Ekim" YAZMA (bir/bin karışıklığı — bir kez hata yapıldı).
- Instagram'a "Instagram için" üretileni YouTube'a atma (farklı kapanış
  tasarımı) ama YouTube için üretileni Instagram'a atmak sorun değil.
- API maliyeti için: aynı gün hem YouTube hem Instagram gerekiyorsa önce
  YouTube'a üret/yükle, sonra AYNI dosyayı Instagram'a da gönder.

## 6. Şu anki durum / sıradaki adımlar

- [x] Özel görsel+animasyon+karaoke altyazı sistemi çalışıyor, test edildi.
- [x] `/api/upload-raw-video` ve `/api/tts-only` sunucuda canlı.
- [x] Marka adı/logo/banner üretildi, kullanıcı onayı bekliyor / Studio'ya
      manuel yükleyecek.
- [ ] `produce.py`'ı `supertonic` yerine `/api/tts-only` (E-Ahmet) kullanacak
      şekilde güncelle (ses kalitesi yükseltme).
- [ ] Pipeline dosyalarını (custom_visuals.py, produce.py, assets/) repoya
      kalıcı olarak ekletmek için kullanıcıdan Termux/Claude Code'a iletmesini
      iste.
- [ ] Scheduled task'ı yeni B-sistemine göre güncelle.
- [ ] ~Ekim 2026 sonu: YouTube Partner Program eski eşiklerini (1000 abone
      + 4000 saat İZLENME ya da 10M Shorts görüntülenme/90 gün) 1 Şubat
      2027'den ÖNCE karşılamayı hedefle (mevcut üyeler eski eşiklerde
      kalıyor, sadece yeni başvuranlar yeni/daha yüksek eşiğe tabi).
