# Türkiye Bilgi Merkezi — Devir Notu (Cowork oturumları için)

## GÜNCEL DURUM (2026-08-13 akşam — KRİTİK BUG FIX, önce burayı oku)

**ÖZET: Cron 15:00 UTC'de otomatik çalıştı, YouTube+Instagram'a birer video
attı, ama kapak/thumbnail KRİTİK bir teknik bug yüzünden bozuk çıktı —
Instagram'ın kendi seçtiği kapak BOMBOŞ BEYAZ, YouTube'unki de cümle
ortasından anlamsız bir kırıntıydı. Kullanıcı ekran görüntüsüyle şikayet
etti ("kapaklar görünmüyor bile"). Kök neden bulundu ve düzeltildi —
detay ve kanıt aşağıda. Cron şu an yine DEVRE DIŞI, bu fix server'a
gitmeden tekrar açılmamalı.**

### Bug'ın kök nedeni (kanıtlanmış, frame-by-frame test edildi)
`custom_visuals.py`'deki `render_scene_clip` ve `render_hook_card`,
Playwright `record_video_dir` ile context açıp SONRA `page.set_content()`
çağırıyordu. Chromium'un video kaydı context açılır açılmaz başlıyor —
ama sayfa o an hâlâ `about:blank` (boş/beyaz). Context açılışı ile
`set_content()`'in gerçekten boyanması arasında ölçülen gecikme
**~350-450ms**. ffmpeg trim adımı klibi hep t=0'dan kesiyordu
(`-t {duration}`, `-ss` YOK) — yani her klibin/hook kartının İLK karesi
her zaman bu boş/beyaz aralıktan geliyordu. Video kapağı/thumbnail'i
otomatik seçen algoritmalar (özellikle Instagram) tam olarak bu kareyi
yakalıyor → bomboş kapak. YouTube'unki farklı bir sezgiyle "az bilgili"
kareleri atlıyor, bu da onu hook kartının tamamını atlayıp sahne
altyazısının ortasına düşürüyordu.

### Düzeltme (uygulandı, test edildi, kanıt: frame extraction)
1. `render_scene_clip` ve `render_hook_card` artık context açılışından
   `set_content()`'in dönüşüne kadar geçen gerçek süreyi (`lead_in`)
   `time.monotonic()` ile ölçüyor, ffmpeg trim'e `-ss {lead_in+0.08}`
   ekleyip bu boş baş kısmını kesin olarak atlıyor. Test: t=0 karesi
   artık asla blank/beyaz değil.
2. `render_hook_card` görsel olarak da güçlendirildi: süre 1.35s→**2.2s**
   (otomatik kapak seçici hangi kareyi seçerse seçsin hâlâ dolu bir
   karede kalsın diye), eski sistemdeki kalın renkli "SON DAKİKA/UYARI"
   bandının karşılığı olan **`.ribbon` şeridi** eklendi (parlak renk
   blok + koyu bold metin, tam genişlik), hafif vignette eklendi (düz
   gradyanın "yassı" hissini kırmak için). Script JSON'a yeni **opsiyonel
   `ribbon_text` alanı** eklendi (yoksa `badge_text`'e düşer).
3. `produce()` artık hook kartının 1.0s'deki (tam oturmuş, ribbon dahil)
   karesinden ekstra bir **statik JPEG kapak** çıkarıyor
   (`_cache["thumb_path"]`), `produce_dual()` bunu kopyalayıp 3. dönüş
   değeri olarak veriyor (`yt_path, ig_path, thumb_path`). Bu, YouTube'un
   otomatik kapak seçimine hiç güvenmemek için — `/api/yt/upload`'un
   zaten var olan `thumbnail_filename` parametresine verilecek.
4. **DÜZELTME (2026-08-13 akşam, Claude Code tarafından): bu endpoint ZATEN
   VAR, farklı isim ve farklı (doğru) klasörle.** `/api/upload-raw-video`
   ile aynı desende ama adı `POST /api/upload-raw-thumbnail` ve `image=@...`
   parametresi alıyor (`video=@...` değil). Ayrıca hedef klasör OUTPUT_DIR
   DEĞİL — `THUMB_DIR` (`thumbnails/`), çünkü `/api/yt/upload`'un
   `thumbnail_filename` parametresi dosyayı gerçekte THUMB_DIR'da arıyor
   (app.py satır ~7946, doğrulandı). OUTPUT_DIR'a atsaydı `thumbnail_filename`
   dosyayı asla bulamazdı. `upload_thumbnail_patch.py` diye ayrı bir dosya
   YOK, kod doğrudan app.py'ye eklendi. Dönen JSON `{"ok": true, "filename":
   "raw_<hex>.jpg"}` (`thumb_xxx.jpg` değil, ama isim önemli değil — sadece
   dönen filename'i `thumbnail_filename=` olarak kullan). NOT: "Bilgi
   Merkezi" panel butonu (bkz. bölüm 8) bu endpoint'i bile kullanmıyor —
   aynı process içinde çalıştığı için THUMB_DIR'a doğrudan dosya kopyalıyor,
   HTTP'ye hiç gerek yok.
5. Instagram tarafında ayrı bir "kapak yükle" API'si yok (Graph API'de
   sadece videonun içinden bir an seçen `thumb_offset` var, dosya
   yükleme değil) — o yüzden Instagram için asıl/tek düzeltme zaten
   yukarıdaki blank-frame fix'i.

### Yeni oturum ne yapmalı (sırayla)
1. Yukarıdaki fix'in `custom-production/custom_visuals.py` ve
   `produce.py`'de gerçekten commit edilmiş olduğunu doğrula (frame
   extraction ile test et — bkz. yöntem: `ffmpeg -i clip.mp4 -vf
   "select='eq(n\\,0)'" -vsync vfr frame0.png` sonra görüntüyü aç, blank
   OLMAMALI).
2. ~~`upload_thumbnail_patch.py`'deki endpoint'in eklenip eklenmediğini
   kontrol et~~ — GEREKSİZ, zaten `/api/upload-raw-thumbnail` olarak
   sunucuda canlı (bkz. yukarıdaki düzeltme notu).
3. Yayın akışına thumbnail adımını ekle: `produce_dual()`'ın 3. dönüş
   değeri (thumb_path) varsa → `POST /api/upload-raw-thumbnail`'a
   `image=@thumb_path` ile yükle → dönen filename'i `/api/yt/upload`'a
   `thumbnail_filename=` olarak ver.
4. Ancak TÜM bunlar doğrulandıktan sonra cron'u (`trig_01Lm6ja1sfk5ZgTL7QxmDQAj`)
   yeni bir prompt'la tekrar `enabled: true` yap.

---

## ÖNCEKİ DURUM NOTLARI (2026-08-13 öğlen, hâlâ geçerli)

- `produce.py` artık **gerçek Edge TTS (E-Ahmet)** kullanıyor, `/api/tts-only`
  endpoint'i üzerinden (`PANEL_COOKIE` ortam değişkeni ile — her oturumda
  yeniden login olup taze cookie almak gerekir, cookie'ler süreli). Supertonic
  (M1) sadece sahne bazlı fallback, artık varsayılan değil.
- `produce_dual(script, out_youtube, out_instagram, ...)` eklendi: aynı
  senaryoyu TEK SEFER seslendirip render eder, sadece kapanış kartı farklı
  iki final video üretir (TTS/render maliyeti 2 katına çıkmaz). **GÜNCEL:
  artık 3 değer döndürüyor, bkz. yukarısı.**
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
- İkinci otomatik yayın (cron, 2026-08-13 ~15:45 UTC) kapak bug'ıyla gitti —
  YouTube video `_BdNCgQga-I`, Instagram media (permalink
  instagram.com/reel/Db_IuJHDNvh/). **Kullanıcı isterse bu ikisinin
  kapağını manuel değiştirebilir** (YouTube Studio / Instagram app), ama
  kritik değil, video içeriği düzgün.
- **Cron/scheduled task `trig_01Lm6ja1sfk5ZgTL7QxmDQAj` ŞU AN DEVRE DIŞI
  (`enabled: false`).** Yukarıdaki kapak bug'ı yüzünden tekrar kapatıldı —
  fix server'a gidip doğrulanmadan tekrar açılmamalı.
- Kullanıcı yayın sıklığını kendisi kontrol etmek istiyor şu an — otomatik/
  sık yayın YAPMA, açıkça istenmeden yayınlama.
- **Açık soru (kullanıcıya soruldu, henüz cevap yok):** kullanıcı eski
  sistemdeki GERÇEK FOTOĞRAF arka planlı (Pexels tarzı) tasarımı, yeni
  düz-gradyan tasarımdan daha güçlü/ilgi çekici buluyor. Şu anki fix
  (ribbon + daha uzun hook + vignette) bunu kısmen telafi ediyor ama
  gerçek fotoğraf eklemek (Pexels API key gerekir) sonraki iterasyon
  olarak masada duruyor — kullanıcı onaylarsa yapılmalı.


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

## 7. 14 Ağustos 2026 — 6 maddelik geri bildirim turu (hepsi kod tarafında uygulandı)

Kullanıcı test videosunu izledikten sonra 6 spesifik ürün/tasarım geri
bildirimi verdi. 5 tanesi kod ile çözüldü, 1 tanesi (madde 5) cron
prompt'unda ele alınmalı:

1. **Açılışta sessizlik → scroll riski**: `render_hook_card` artık SESSİZ
   değil. `produce.py` içinde `_synth_one()` ile hook metni (varsa
   `script["hook_text"]`, yoksa `title`) seslendiriliyor, hook süresi
   `max(2.0, konuşma_süresi + 0.3)` olarak ayarlanıyor. TTS başarısız
   olursa sessiz 2.2s'e fallback var.
2. **Kapanışta teşvik edici konuşma yok**: `_finish()` içine platform'a
   özel bir CTA cümlesi eklendi (YouTube: abone ol; Instagram: takip et +
   yorumlarda buluşalım), `script["closing_text_youtube"/"_instagram"]`
   ile override edilebilir. Seslendirilip endcard'dan ÖNCE ayrı bir sahne
   klibi olarak render ediliyor (`_render_scene(..., name=f"clip_cta_{platform}")`).
3. **Bant rengi her videoda aynı**: `_theme_idx_for(script)` eklendi —
   `title + badge_text`'in MD5 hash'inden deterministik ama videoya özel
   bir tema index'i üretiyor (`hashlib.md5`, `hash()` DEĞİL — process'e
   göre rastgele olurdu). Hook, tüm sahneler ve CTA aynı temayı kullanıyor
   (video içi tutarlılık), videolar arası farklı (çeşitlilik). Test:
   SGDP videosu altın/lacivert, kısmi-süreli-çalışma videosu yeşil çıktı.
4. **Bant boydan boya çirkin**: `.ribbon` CSS'i `left/right: 60px` inset +
   `border-radius: 16px` ile güncellendi (önce edge-to-edge'di).
5. **Son 4 video hep emekli/SGK — çeşitlilik lazım**: ÇÖZÜLDÜ — cron'un
   (trig_01Lm6ja1sfk5ZgTL7QxmDQAj) prompt'u `update_trigger` ile
   güncellendi (14 Ağustos 2026). Artık 9 kategorilik bir havuz var
   (emeklilik/SGK, sağlık hakları, e-Devlet, trafik/ehliyet, tüketici
   hakları, vergi, miras/veraset, iş hukuku, bankacılık/finans) ve
   talimat açıkça "son 4 videoda kullanılan kategorileri tespit et,
   art arda aynı kategoriden üretme" diyor. Fresh session her seferinde
   SISTEM_BILGI.md'deki "Son üretilen konular" listesine (bkz. altta,
   ADIM 8 ile her üretimde eklenmesi isteniyor) veya panel geçmişine
   bakıp karar veriyor.
6. **Kelime vurgusu net değil (rengi çok hızlı beyaza dönüyor)**: `.word`
   keyframe'leri yeniden yazıldı — kelime artık kendi "sırası" boyunca
   (0%-80% arası) accent rengini KORUYOR, sadece 80%-100% arasında beyaza
   geçiyor. Emphasis kelimeler (`.word-emph`) hiç beyaza dönmüyor, kalıcı
   accent renginde kalıyor. Frame-extraction ile doğrulandı (t=7.6s/7.9s,
   "kısmi süreli" ifadesi yeşil accent'te tutulurken önceki kelimeler
   beyaz).

Tüm değişiklikler uçtan uca `produce_dual()` ile test edildi (farklı bir
konu: "Emeklilikte Kısmi Süreli Çalışma Hakkı Nedir?"), ses varlığı
`ffmpeg -af volumedetect` ile doğrulandı (hook ve CTA bölümlerinde
~-20dB ortalama, sessizlik değil), tema farkı ve kelime-tutma davranışı
frame extraction ile görsel olarak doğrulandı.

**Durum**: Bu round'un kodu (`custom_visuals.py`, `produce.py`) local'de
tam test edildi ama HENÜZ repoya push edilmedi — kullanıcıya iletilip
Claude Code'a (Termux) aktarılmayı bekliyor. Madde 5 (konu çeşitliliği)
ayrıca cron prompt güncellemesi gerektiriyor, kod değişikliği değil.

## 8. 14 Ağustos 2026 (akşam) — Panel içi manuel "Şimdi Üret" butonu

Cron bugün 15:00 UTC'de tetiklendi (last_fired_at kaydedildi) ama
sonrasında NE YouTube'a NE Instagram'a video düşmedi — muhtemelen bir
hatayla sessizce yarıda kaldı (Claude Code'un o oturumunun logu Cowork'ten
görülemiyor, tek bilinen: sonuç yok). Cowork bunu manuel `fire_trigger`
ile tekrar tetikledi ama kullanıcı bunun yerine kalıcı bir çözüm istedi:
**Claude Code cron'una bağımlı olmadan, panelin kendi içinden tek tıkla
üretim+yayın.**

### Ne yapıldı
Cowork, gerçek `app.py`'yi (public repo, salt-okunur clone ile) inceleyip
mevcut "IG-Only-TR" otomatiğinin (`auto_ig_only_tr_job`, ~satır 9163)
BİREBİR aynı desenini kopyalayan yeni bir özellik tasarladı:

- **Yeni panel sekmesi "📰 Bilgi Merkezi"**: "▶ Şimdi Üret ve Yayınla"
  butonu — basınca ~3-6 dakikada kategori seçer, gerçek haber tarar,
  senaryo yazar, video üretir, YouTube+Instagram'a yayınlar.
- **Kategori rotasyonu**: 9 kategori (bkz. bölüm 7 madde 5), son 4
  videoda kullanılmayanlardan rastgele seçiliyor — `custom_bilgi_history.json`.
- **Fact-check zemini — ÖNEMLİ mimari karar**: DeepSeek V4 Flash kendi
  başına canlı internet taraması YAPAMIYOR (resmi dokümandan doğrulandı).
  Yeni bir ücretli arama API'si (Serper/Bing) BAĞLAMADIK — bunun yerine
  app.py'de ZATEN kanıtlanmış, ücretsiz bir yöntem var: Google News RSS
  (`news.google.com/rss/search?q=...&hl=tr&gl=TR`, aynı desen "gurbetçi
  trends" fonksiyonunda ~satır 1891'de kullanılıyor). Yeni fonksiyon
  `_custom_bilgi_fetch_headlines()` kategoriye özel sorgularla gerçek
  başlık+özet çekiyor, DeepSeek'e SADECE bu metinlerden senaryo yazdırıyor
  ("kaynakta yoksa rakam/tarih uydurma" talimatı prompt'ta açık şekilde
  var). Sıfır yeni API key/maliyet.
- **Model değiştirilebilir**: `custom_bilgi_config.json` → `model` alanı,
  panelde dropdown (deepseek-v4-flash / deepseek-v4-pro). Bu SADECE bu
  yeni özelliği etkiliyor — app.py'nin geri kalanındaki ~15 hardcode
  edilmiş `"deepseek-v4-flash"` çağrısına dokunulmadı (istenirse ayrı bir
  iş olarak genişletilebilir).
- **Video üretimi**: mevcut `custom-production/produce.py` (bu oturumun
  geliştirdiği görsel motor — karaoke altyazı, seslendirilmiş hook/CTA,
  tema rotasyonu) `sys.path` ile import edilip `produce_dual()` doğrudan
  çağrılıyor, `asyncio.to_thread` ile event loop bloklanmıyor.
- **Yayın**: YouTube için mevcut `/api/yt/upload`'a iç HTTP çağrısı
  (`category_id=27` — Eğitim, diğer job'larla aynı kural), Instagram için
  mevcut `_post_to_instagram_bg()` fonksiyonu DOĞRUDAN çağrılıyor (aynı
  process içinde olduğumuz için HTTP'ye gerek yok, IG-Only-TR job'unun
  yaptığı gibi).

### Teslim edilen dosyalar (kullanıcıya SendUserFile ile iletildi)
- `custom_bilgi_backend_patch.py` — app.py'ye eklenecek Python kodu +
  TAM olarak nereye ekleneceğinin açıklaması (auto_ig_only_tr_job'un
  bittiği yer ile /api/ig/failed-uploads arası, ~satır 9600 civarı).
- `custom_bilgi_frontend_patch.html` — index.html'e eklenecek nav
  butonu + panel + JS, 3 ayrı yapıştırma noktası açıkça işaretli.

### KURULUM UYARISI — Claude Code MUTLAKA kontrol etmeli
`custom-production/produce.py` şu ana kadar SADECE Claude Code'un kendi
geçici cron oturumu sandbox'ında çalıştı, GERÇEK panel sunucusunda HİÇ
ÇALIŞMADI. Bu yamanın çalışması için sunucuda Playwright+Chromium
(`playwright install chromium --with-deps`, `CUSTOM_CARD_CHROMIUM_PATH`
env var), ffmpeg ve edge-tts/supertonic erişimi olmalı — bunlardan biri
eksikse üretim adımı hata verir (panel çökmez, sadece log'a "error"
yazılır, buton tekrar denenebilir hale döner) ama özellik çalışmaz.
Claude Code bu patch'i uygulamadan önce sunucuda bu bağımlılıkları
doğrulamalı/kurmalı ve BİR test çalıştırması yapıp sonucu (video gerçekten
üretildi mi, YouTube+Instagram'a gerçekten gitti mi) doğrulamalı.

### DÜZELTME (2026-08-14, Claude Code tarafından uygulandı)

**Kritik güvenlik düzeltmesi — hardcoded şifre kaldırıldı.** Backend
patch'inde `os.environ.get("PANEL_PASSWORD", "413856")` ile bir fallback
şifre PUBLIC repoya commitlenmek üzereydi — bu yapılmadı. Bunun yerine:
zaten AYNI process içinde çalıştığımız için hiçbir ağ turuna/kimlik
bilgisine gerek yok. `custom_produce._synth_edge`, gerçek/yerel
`_synth_edge()` fonksiyonunu doğrudan çağıran bir sürümle monkey-patch
edildi (`asyncio.run(_synth_edge(text, voice, 1.0, out_path))`). Ayrıca
bu, produce.py'nin `PANEL_COOKIE`'yi import ANINDA (modül seviyesinde,
bir daha okumadan) sabitlediği bir zamanlama hatasını da (env var'ı
import'tan SONRA set etmenin etkisi olmazdı) baştan ortadan kaldırdı.
Thumbnail için de aynı mantık zaten patch'te vardı (THUMB_DIR'a doğrudan
dosya kopyalama, HTTP yok) — sadece TTS tarafı tutarlı hale getirildi.

**Frontend — patch'teki 2 varsayım gerçek koda uymuyordu, düzeltildi:**
- Yeni sekme bottom-nav'a 6. doğrudan ikon olarak DEĞİL, mevcut "Daha
  Fazla" taşma menüsüne eklendi (`more-item-custombilgi` + `MORE_TABS`
  dizisine ekleme) — bottom-nav zaten 5 öğeyle tasarlanmıştı, 6.
  ikon sığmazdı/düzeni bozardı.
- `loadIGOnlyTRStatus()` sayfa yüklenince (DOMContentLoaded) DEĞİL,
  `switchTab('instagram')` çağrılınca (`loadInstagramTab()` üzerinden)
  tembel yükleniyormuş — gerçek koda bakıp doğrulandı. `loadCustomBilgiConfig()`
  de aynı desende, sadece `switchTab()`'a `if (name==='custombilgi')` satırı
  eklendi, ayrı bir init hook'a gerek kalmadı.

**Hâlâ doğrulanmadı (sunucu erişimim yok, sadece git push yetkim var):**
Playwright/Chromium/ffmpeg'in sunucuda kurulu olup olmadığını BEN test
edemedim. `supertonic-web/requirements.txt`'e `playwright==1.47.0` eklendi
(kod tarafı hazır) ama şunlar kullanıcının/sunucudaki birinin elle
yapması gereken adımlar: venv'e kurulum (`supertonic-web/.venv/bin/pip
install -r requirements.txt`), `playwright install chromium --with-deps`,
`ffmpeg` PATH kontrolü, gerekiyorsa `CUSTOM_CARD_CHROMIUM_PATH` env var'ı.
Bunlar tamamlanmadan "Şimdi Üret ve Yayınla" butonu hata verir (panel
çökmez, log'a "error" yazar, buton tekrar denenebilir).

### Not
Bu özellik Claude Code'un günlük cron'unu İPTAL ETMİYOR — ona ek, daha
hızlı/güvenilir bir manuel alternatif. Cron'un neden bugün sessizce
yarım kaldığı hâlâ bilinmiyor (Cowork'ün o oturumun loguna erişimi yok);
tekrarlarsa Claude Code'un kendi tarafında (Termux/cron ortamı) bir
inceleme gerekebilir.
