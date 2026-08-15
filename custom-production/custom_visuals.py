"""
custom_visuals.py — Stok fotoğraf yerine tamamen özel, marka tutarlı sahne
kartları üretir (Playwright ile HTML/CSS -> PNG render).

Neden: Pexels/Wikimedia/DALL-E'den gelen sahne görselleri çoğu zaman konuyla
alakasız (yanlış ülke, yanlış yaş grubu, alakasız obje) oluyor ve her video
farklı bir "stok fotoğraf" hissi veriyor — marka tutarlılığı yok. Bu modül
onun yerine HER sahne için aynı görsel dilde (koyu gradyan + rozet + büyük
metin + ilerleme noktaları + marka alt bilgisi), konuyla HER ZAMAN %100
alakalı (çünkü fotoğraf değil, doğrudan o sahnenin metni) bir kart üretir.

Kullanım: app.py içinden visual_mode == "custom_card" olduğunda,
fetch_scene_visual(...) çağrısı yerine render_scene_card(...) çağrılır.
Senkron (Playwright sync API) çalışır; app.py tarafında asyncio.to_thread
ile sarılmalı ki event loop bloklanmasın.

Bağımlılık: playwright (zaten kurulu değilse: pip install playwright &&
playwright install chromium). Sunucuda chromium indirilemiyorsa
CUSTOM_CARD_CHROMIUM_PATH ortam değişkeniyle var olan bir chromium binary
gösterilebilir.
"""
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

W, H = 1080, 1920

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

# Marka renk paletleri — sırayla döner, art arda aynı video/gün içinde bile
# çeşitlilik olsun diye sahne index'ine göre seçilir (rastgele değil,
# öngörülebilir ve testte tekrarlanabilir).
THEMES = [
    {"bg1": "#0b1220", "bg2": "#14213d", "accent": "#ffb100", "accent2": "#7fa3ff"},
    {"bg1": "#1a0b20", "bg2": "#3d1442", "accent": "#ff5fa2", "accent2": "#c084fc"},
    {"bg1": "#081a14", "bg2": "#0f3d2a", "accent": "#4ade80", "accent2": "#5eead4"},
    {"bg1": "#200b0b", "bg2": "#3d1414", "accent": "#ff6b4a", "accent2": "#ffb100"},
    {"bg1": "#0b1420", "bg2": "#142a3d", "accent": "#38bdf8", "accent2": "#a78bfa"},
]

BRAND_DEFAULT = "TÜRKİYE BİLGİ MERKEZİ"

_playwright_lock = threading.Lock()
_browser = None
_pw = None


def _get_browser():
    """Tek bir kalıcı Chromium instance'ı — her kart için ayrı ayrı başlatmak
    çok yavaş olurdu (video başına 5-7 sahne var)."""
    global _browser, _pw
    with _playwright_lock:
        if _browser is None:
            from playwright.sync_api import sync_playwright
            _pw = sync_playwright().start()
            launch_kwargs = {}
            chromium_path = os.environ.get("CUSTOM_CARD_CHROMIUM_PATH")
            if chromium_path:
                launch_kwargs["executable_path"] = chromium_path
            # Sunucu root olarak çalışıyor — Chromium'un kendi sandbox'ı root
            # altında --no-sandbox olmadan başlamayı reddediyor (Docker/root
            # sunucularda çok bilinen bir sorun). İçerik tamamen kendi
            # ürettiğimiz sabit HTML/CSS olduğu için (dış/güvenilmez sayfa
            # açılmıyor) sandbox'sız çalışmanın burada güvenlik riski yok.
            _browser = _pw.chromium.launch(headless=True, args=["--no-sandbox"], **launch_kwargs)
        return _browser


def close_browser():
    """İsteğe bağlı temizlik (uzun süre çalışan serviste genelde gerekmez)."""
    global _browser, _pw
    with _playwright_lock:
        if _browser is not None:
            try:
                _browser.close()
            except Exception:
                pass
            _browser = None
        if _pw is not None:
            try:
                _pw.stop()
            except Exception:
                pass
            _pw = None


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _emphasize_html(text: str, emphasis_word: str, accent_color: str) -> str:
    """emphasis_word metin içinde geçiyorsa o kelime(ler)i vurgulu renkte
    işaretler (HTML span). Geçmiyorsa metni olduğu gibi kaçışlı döner.
    (Sadece statik kart fallback'i için kullanılır — asıl klipte karaoke
    kelime animasyonu var, bkz. _karaoke_caption_html.)"""
    text_e = _esc(text)
    if not emphasis_word or not emphasis_word.strip():
        return text_e
    ew = emphasis_word.strip()
    ew_e = _esc(ew)
    pattern = re.compile(re.escape(ew_e), re.IGNORECASE)
    if not pattern.search(text_e):
        return text_e
    return pattern.sub(
        lambda m: f'<span style="color:{accent_color}">{m.group(0)}</span>',
        text_e, count=1,
    )


def _karaoke_caption_html(text: str, duration: float, emphasis_word: str, accent_color: str) -> str:
    """Standart 'tüm cümle bir anda görünür' altyazı yerine KELİME KELİME
    konuşmayla eşzamanlı beliren, her kelimede renk+boyut 'pop' eden altyazı
    (CapCut/Opus tarzı karaoke altyazı). 'yazılar konuştukça rengi değişse
    font büyüsü küçülse' isteği doğrudan bunu karşılıyor.

    Kelime zamanlaması ses dosyasından değil, karakter uzunluğuna orantılı
    tahminle hesaplanıyor (tam fonem hizası değil ama görsel olarak yeterince
    doğal akıyor — TTS motorundan kelime zaman damgası gelmiyor)."""
    words = [w for w in (text or "").split() if w]
    if not words:
        return ""
    emph = (emphasis_word or "").strip().upper()
    emph_words = set(emph.split()) if emph else set()

    total_chars = sum(len(w) for w in words) or 1
    usable = max(0.3, float(duration) * 0.90)  # son kelime bitmeden sahne değişmesin diye pay
    t = 0.0
    spans = []
    for w in words:
        w_clean = w.strip(".,!?;:").upper()
        is_emph = w_clean in emph_words
        frac = len(w) / total_chars
        wdur = max(0.10, frac * usable)
        cls = "word word-emph" if is_emph else "word"
        # animation-duration KENDİ konuşma payı (wdur) kadar — böylece kelime
        # SIRASI GELDİĞİNDE vurgulu (accent) renkte belirip o rengi kendi
        # konuşma süresi boyunca KORUYOR, ancak sıradaki kelimeye geçilirken
        # beyaza dönüyor (bkz. .word keyframes). Önceki halde animation-duration
        # sabit 0.32sn'ydi — vurgu rengi sadece kısa bir geçiş anında
        # görünüyordu, "şu an hangi kelime söyleniyor" belli olmuyordu.
        # 0.18-1.0sn arasında sınırlanıyor: çok kısa kelimede vurgu göz
        # açıp kapayana kadar geçmesin, çok uzun kelimede de gereksiz
        # yavaş kalmasın.
        anim_dur = max(0.18, min(1.0, wdur))
        spans.append(
            f'<span class="{cls}" style="animation-delay:{t:.2f}s;'
            f'animation-duration:{anim_dur:.2f}s;--accent:{accent_color}">{_esc(w)}</span>'
        )
        t += wdur
    return " ".join(spans)


def _progress_dots(index: int, total: int, accent_color: str) -> str:
    if total <= 1:
        return ""
    dots = []
    for i in range(total):
        on = i == index
        size = "14px" if on else "10px"
        color = accent_color if on else "rgba(255,255,255,0.25)"
        dots.append(
            f'<span style="display:inline-block;width:{size};height:{size};'
            f'border-radius:50%;background:{color};margin:0 6px;"></span>'
        )
    return "".join(dots)


_CARD_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background: {bg1}; }}
  body {{
    width: 1080px; height: 1920px;
    background: linear-gradient(160deg, {bg1} 0%, {bg2} 100%);
    font-family: 'DejaVu Sans', Arial, sans-serif;
    position: relative; overflow: hidden;
  }}
  /* Canlı hareket: grid yavaşça kayar, glow nefes alır, parçacıklar süzülür,
     rozet ve metin sahneye giriş animasyonuyla belirir. Playwright bunu
     screenshot değil VIDEO olarak kaydeder -- yani gerçek hareketli klip. */
  .grid {{
    position: absolute; inset: -60px; opacity: 0.06;
    background-image: linear-gradient(#fff 1px, transparent 1px),
                       linear-gradient(90deg, #fff 1px, transparent 1px);
    background-size: 64px 64px;
    animation: gridpan 14s linear infinite;
  }}
  @keyframes gridpan {{
    0% {{ transform: translate(0, 0); }}
    100% {{ transform: translate(64px, 64px); }}
  }}
  .glow {{
    position: absolute; top: -200px; left: 50%; margin-left: -450px;
    width: 900px; height: 900px; border-radius: 50%;
    background: radial-gradient(circle, {accent}40 0%, transparent 70%);
    animation: breathe 5s ease-in-out infinite;
  }}
  @keyframes breathe {{
    0%, 100% {{ opacity: 0.6; transform: scale(1); }}
    50% {{ opacity: 1; transform: scale(1.12); }}
  }}
  .particle {{
    position: absolute; border-radius: 50%; background: {accent2};
    opacity: 0.35; animation: drift 9s ease-in-out infinite;
  }}
  @keyframes drift {{
    0%   {{ transform: translateY(0) translateX(0); opacity: 0.15; }}
    50%  {{ transform: translateY(-90px) translateX(30px); opacity: 0.5; }}
    100% {{ transform: translateY(0) translateX(0); opacity: 0.15; }}
  }}
  .badge {{
    position: absolute; top: 96px; left: 60px;
    background: {accent}; color: #10131c;
    font-weight: 900; font-size: 32px;
    padding: 14px 34px; border-radius: 999px;
    letter-spacing: 0.5px; max-width: 620px;
    animation: popin 0.6s cubic-bezier(.2,1.4,.4,1) both;
  }}
  .brand {{
    position: absolute; top: 108px; right: 60px;
    color: {accent2}; font-weight: 800; font-size: 26px;
    opacity: 0.9; letter-spacing: 1px;
  }}
  @keyframes popin {{
    0% {{ transform: scale(0.6); opacity: 0; }}
    100% {{ transform: scale(1); opacity: 1; }}
  }}
  .caption {{
    position: absolute; left: 80px; right: 80px; top: 50%;
    transform: translateY(-50%);
    color: #f2f5fb; font-weight: 800; font-size: {font_size}px;
    line-height: 1.4; text-align: center;
  }}
  /* Karaoke kelime animasyonu: her kelime konuşma sırası geldiğinde
     yumuşakça belirir (fade + hafif yükselme), SIRASI SÜRESİNCE vurgulu
     (accent) renkte KALIR, sıradaki kelimeye geçilirken beyaza döner.
     ÖNCEDEN scale(0.4)->1.16->1.0 ile "büyüyüp küçülen" bir pop efekti
     vardı (kaldırıldı, "titreme" hissi veriyordu); ONDAN SONRAKİ halde de
     vurgu rengi sadece 0.32sn'lik kısa bir geçiş anında görünüyordu, hangi
     kelimenin o an söylendiği belli olmuyordu. animation-duration artık
     kelimenin kendi konuşma payı (_karaoke_caption_html'de hesaplanan
     wdur) kadar — yani vurgu, kelime "sırası boyunca" görünür kalıyor. */
  .word {{
    display: inline-block;
    margin: 0 10px 6px 0;
    opacity: 0; transform: translateY(14px);
    animation-name: wordpop;
    animation-timing-function: ease-out;
    animation-fill-mode: both;
  }}
  @keyframes wordpop {{
    0%   {{ opacity: 0; transform: translateY(14px); color: var(--accent); }}
    25%  {{ opacity: 1; transform: translateY(0);    color: var(--accent); }}
    80%  {{ opacity: 1; transform: translateY(0);    color: var(--accent); }}
    100% {{ opacity: 1; transform: translateY(0);    color: #f2f5fb; }}
  }}
  .word-emph {{
    animation-name: wordpop-emph;
  }}
  @keyframes wordpop-emph {{
    0%   {{ opacity: 0; transform: translateY(14px); color: var(--accent); }}
    25%  {{ opacity: 1; transform: translateY(0);    color: var(--accent); }}
    100% {{ opacity: 1; transform: translateY(0);    color: var(--accent); }}
  }}
  .dots {{
    position: absolute; bottom: 200px; left: 0; right: 0; text-align: center;
  }}
  .footer {{
    position: absolute; bottom: 110px; left: 0; right: 0;
    text-align: center; color: #6b7fa8; font-size: 24px; font-weight: 700;
    letter-spacing: 3px;
  }}
</style></head>
<body>
  <div class="grid"></div>
  <div class="glow"></div>
  {particles}
  <div class="badge">{badge}</div>
  <div class="brand">{brand}</div>
  <div class="caption">{caption_html}</div>
  <div class="dots">{dots}</div>
  <div class="footer">{footer}</div>
</body></html>"""


def _particles_html(theme_idx: int) -> str:
    """Sahne başına birkaç yavaşça süzülen parçacık — pozisyonları tema
    index'inden türetilir (sabit/tekrarlanabilir, rastgele değil)."""
    import random
    rnd = random.Random(theme_idx * 97 + 13)
    out = []
    for i in range(7):
        size = rnd.randint(8, 22)
        x = rnd.randint(5, 95)
        y = rnd.randint(10, 85)
        delay = round(rnd.uniform(0, 4), 2)
        dur = round(rnd.uniform(7, 12), 2)
        out.append(
            f'<div class="particle" style="width:{size}px;height:{size}px;'
            f'left:{x}%;top:{y}%;animation-delay:{delay}s;animation-duration:{dur}s;"></div>'
        )
    return "".join(out)


def _fit_font_size(text: str) -> int:
    """Kart tek bir sabit fontta HER metin uzunluğuna sığmayabilir — kaba bir
    sezgiyle (karakter sayısına göre) başlangıç boyutunu ayarlıyoruz. Playwright
    ile ölçüp yeniden render etmek yerine basit tutuyoruz çünkü scene metinleri
    zaten TTS için kısa (1-2 cümle) tutuluyor."""
    n = len(text)
    if n <= 60:
        return 78
    if n <= 100:
        return 64
    if n <= 150:
        return 54
    return 46


def render_scene_card(
    text: str,
    index: int,
    total: int,
    out_path,
    badge_text: str = None,
    emphasis_word: str = None,
    lang: str = "tr",
    brand: str = BRAND_DEFAULT,
    theme_idx: int = None,
) -> bool:
    """Bir sahne için 1080x1920 JPEG kart üretir. Başarılıysa True döner.
    Hata durumunda False döner (çağıran taraf koyu-arkaplan fallback'ine
    düşer — generator.py'deki mevcut davranışla aynı desende).
    theme_idx verilirse tema seçimi index yerine ondan yapılır — videonun
    tamamının (açılış kartı dahil) aynı, video'ya özel renk döngüsünden
    başlaması için (bkz. produce.py _theme_idx_for)."""
    try:
        theme = THEMES[(theme_idx if theme_idx is not None else index) % len(THEMES)]
        badge = _esc((badge_text or ("BİLGİ" if lang == "tr" else "INFO")).upper()[:40])
        caption_html = _emphasize_html(text, emphasis_word, theme["accent"])
        footer = _esc(brand)
        html = _CARD_TEMPLATE.format(
            bg1=theme["bg1"], bg2=theme["bg2"], accent=theme["accent"], accent2=theme["accent2"],
            badge=badge, brand=_esc(brand), caption_html=caption_html,
            dots=_progress_dots(index, total, theme["accent"]),
            particles=_particles_html(index),
            footer=footer, font_size=_fit_font_size(text or ""),
        )
        browser = _get_browser()
        page = browser.new_page(viewport={"width": W, "height": H})
        try:
            page.set_content(html, wait_until="load")
            out_path = Path(out_path)
            tmp_png = out_path.with_suffix(".card.png")
            page.screenshot(path=str(tmp_png))
        finally:
            page.close()

        # generator.py boru hattı .jpg bekliyor (ffmpeg adımları JPEG varsayıyor)
        from PIL import Image
        Image.open(tmp_png).convert("RGB").save(str(out_path), "JPEG", quality=92)
        tmp_png.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def render_scene_clip(
    text: str,
    index: int,
    total: int,
    duration: float,
    out_mp4_path,
    badge_text: str = None,
    emphasis_word: str = None,
    lang: str = "tr",
    brand: str = BRAND_DEFAULT,
    theme_idx: int = None,
) -> bool:
    """render_scene_card ile AYNI kart, ama tek kare yerine gerçek hareketli
    klip: grid kayması, nefes alan glow, süzülen parçacıklar, giriş animasyonu.
    Playwright'ın kendi video kaydını kullanır (gerçek zamanlı — `duration`
    saniye kadar sürer). Sonuç doğrudan bir .mp4 dosyasıdır, ffmpeg loop/zoom
    adımına gerek kalmaz; produce.py bu klibi olduğu gibi concat listesine
    ekler. Hata durumunda False döner (çağıran statik karta düşer).
    theme_idx: bkz. render_scene_card — verilirse tema index yerine ondan
    seçilir (video'ya özel renk döngüsü başlangıcı için)."""
    import time
    try:
        theme = THEMES[(theme_idx if theme_idx is not None else index) % len(THEMES)]
        badge = _esc((badge_text or ("BİLGİ" if lang == "tr" else "INFO")).upper()[:40])
        caption_html = _karaoke_caption_html(text, duration, emphasis_word, theme["accent"])
        footer = _esc(brand)
        html = _CARD_TEMPLATE.format(
            bg1=theme["bg1"], bg2=theme["bg2"], accent=theme["accent"], accent2=theme["accent2"],
            badge=badge, brand=_esc(brand), caption_html=caption_html,
            dots=_progress_dots(index, total, theme["accent"]),
            particles=_particles_html(index),
            footer=footer, font_size=_fit_font_size(text or ""),
        )
        out_mp4_path = Path(out_mp4_path)
        rec_dir = out_mp4_path.parent / (out_mp4_path.stem + "_rec")
        rec_dir.mkdir(parents=True, exist_ok=True)

        browser = _get_browser()
        # record_video_size sabitlenmeli, aksi halde Playwright viewport'tan türetir
        t0 = time.monotonic()
        context = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(rec_dir),
            record_video_size={"width": W, "height": H},
        )
        page = context.new_page()
        page.set_content(html, wait_until="load")
        # KRİTİK: context/page oluşturma ile set_content'in gerçekten boyanması
        # arasında ~300-450ms BOŞ/BEYAZ bir kayıt boşluğu oluyor (Chromium'un
        # video recorder'ı context açılır açılmaz kaydetmeye başlıyor, ama
        # sayfa henüz about:blank). Bu boşluğu ffmpeg'de -ss ile atlamazsak
        # klibin İLK karesi (=Instagram/YouTube'un otomatik kapak seçtiği kare)
        # boş/beyaz çıkıyor — canlı yayında tam olarak bu bug yaşandı.
        lead_in = time.monotonic() - t0
        # skip'i SLEEP'TEN ÖNCE hesaplıyoruz — çünkü taban değer (0.4sn) ölçülen
        # lead_in'den yüksek çıkabiliyor, o durumda ham kaydın da buna göre UZUN
        # sürmesi lazım. Aksi halde (bir önceki haliyle test edildi, gerçekten
        # yaşandı): sleep hep `duration` baz alınarak hesaplanıyordu, taban skip
        # bunu aştığında -t {duration} kırpması ham görüntüden TAŞIYOR ve klip
        # istenenden kısa çıkıyordu (2.2sn istenen hook kartı gerçekte 1.3-1.6sn
        # çıktı — 6 ardışık testte doğrulandı).
        skip = round(max(lead_in + 0.08, 0.4), 3)
        # Gerçek zamanlı kayıt — hedef süre + taban skip'in lead_in'i aşan kısmı
        # + küçük pay kadar bekle, ham kaydın -ss+-t için her zaman yeterli
        # olmasını garanti eder.
        time.sleep(max(0.6, float(duration)) + 0.15 + max(0.0, skip - lead_in))
        video = page.video
        page.close()
        context.close()  # dosya ancak context kapanınca diske yazılır

        raw_video = Path(video.path())
        # ffmpeg ile boş baş kısmını at (-ss) + hedef süreye kırp (-t) +
        # standart h264/yuv420p'ye çevir (concat aşaması tüm kliplerin aynı
        # codec/pix_fmt olmasını bekliyor). lead_in ÖLÇÜMÜ tek başına GÜVENİLİR
        # DEĞİL — test edildi, iki ardışık çalıştırmada 0.17sn ile 0.59sn arası
        # (3.5 kat fark) çıktı, sistem yüküne göre değişiyor. Bu yüzden sabit
        # bir taban (0.4sn) + ölçülen değer üstüne pay — düşük ölçülse bile
        # yetersiz kalmasın diye.
        result = subprocess.run([
            "ffmpeg", "-y", "-ss", str(skip), "-i", str(raw_video), "-t", str(duration),
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an", str(out_mp4_path),
        ], capture_output=True, timeout=60)
        shutil.rmtree(rec_dir, ignore_errors=True)
        if result.returncode != 0 or not out_mp4_path.exists() or out_mp4_path.stat().st_size == 0:
            return False
        return True
    except Exception:
        return False


_HOOK_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ background: {bg1}; }}
  body {{
    width: 1080px; height: 1920px;
    background: linear-gradient(160deg, {bg1} 0%, {bg2} 100%);
    font-family: 'DejaVu Sans', Arial, sans-serif;
    position: relative; overflow: hidden;
  }}
  .grid {{
    position: absolute; inset: -60px; opacity: 0.07;
    background-image: linear-gradient(#fff 1px, transparent 1px),
                       linear-gradient(90deg, #fff 1px, transparent 1px);
    background-size: 64px 64px;
  }}
  /* Köşeleri karartan vignette -- düz gradyanın "yassı/ucuz" hissini kırıp
     daha "fotoğraf gibi" derinlik hissi veriyor. */
  .vignette {{
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.55) 100%);
  }}
  .flash {{
    position: absolute; top: 50%; left: 50%; width: 1600px; height: 1600px;
    margin: -800px 0 0 -800px; border-radius: 50%;
    background: radial-gradient(circle, {accent}55 0%, transparent 65%);
    animation: flash 0.5s ease-out both;
  }}
  @keyframes flash {{
    0%   {{ opacity: 0; transform: scale(0.3); }}
    35%  {{ opacity: 1; transform: scale(1.1); }}
    100% {{ opacity: 0.55; transform: scale(1); }}
  }}
  .badge {{
    position: absolute; top: 96px; left: 60px;
    background: {accent}; color: #10131c;
    font-weight: 900; font-size: 32px;
    padding: 14px 34px; border-radius: 999px;
    letter-spacing: 0.5px; max-width: 620px;
    animation: badgein 0.35s ease-out 0.05s both;
  }}
  @keyframes badgein {{
    0% {{ transform: scale(0.5); opacity: 0; }}
    100% {{ transform: scale(1); opacity: 1; }}
  }}
  .brand {{
    position: absolute; top: 108px; right: 60px;
    color: {accent2}; font-weight: 800; font-size: 26px;
    opacity: 0.9; letter-spacing: 1px;
  }}
  .hook {{
    position: absolute; left: 60px; right: 60px; top: 42%;
    transform: translateY(-50%) scale(1.35);
    color: #ffffff; font-weight: 900; font-size: {font_size}px;
    line-height: 1.16; text-align: center;
    opacity: 0;
    animation: impact 0.4s cubic-bezier(.15,1.2,.35,1) 0.08s both;
    text-shadow: 0 4px 0 rgba(0,0,0,0.4), 0 10px 40px rgba(0,0,0,0.65);
    -webkit-text-stroke: 2px rgba(0,0,0,0.25);
  }}
  @keyframes impact {{
    0%   {{ opacity: 0; transform: translateY(-50%) scale(1.55); }}
    60%  {{ opacity: 1; transform: translateY(-50%) scale(0.96); }}
    100% {{ opacity: 1; transform: translateY(-50%) scale(1); }}
  }}
  .hook em {{ color: {accent}; font-style: normal; }}
  /* Eski sistemdeki kalın "SON DAKİKA/UYARI" bandının karşılığı: parlak
     renkli, koyu metinli bir şerit -- kapak/thumbnail otomatik seçilse
     bile tek başına anında okunur bir "çengel" olsun diye. ÖNCEDEN
     left:0;right:0 ile tam kenardan kenara gidiyordu -- kullanıcı geri
     bildirimi: bu haliyle "ham/çirkin" duruyordu. Artık badge/hook ile
     aynı hizada (60px) kenar boşluğu var ve köşeler yuvarlatılmış, hazır
     bir "rozet/etiket" gibi duruyor, ham bant gibi değil. */
  .ribbon {{
    position: absolute; left: 60px; right: 60px; bottom: 30%;
    background: {accent}; color: #10131c;
    font-weight: 900; font-size: 42px; letter-spacing: 1px;
    padding: 20px 30px; text-align: center; border-radius: 16px;
    transform: translateY(40px); opacity: 0;
    animation: ribbonin 0.35s ease-out 0.42s both;
    box-shadow: 0 10px 40px rgba(0,0,0,0.4);
  }}
  @keyframes ribbonin {{
    0%   {{ opacity: 0; transform: translateY(40px); }}
    100% {{ opacity: 1; transform: translateY(0); }}
  }}
</style></head>
<body>
  <div class="grid"></div>
  <div class="vignette"></div>
  <div class="flash"></div>
  <div class="badge">{badge}</div>
  <div class="brand">{brand}</div>
  <div class="ribbon">{ribbon}</div>
  <div class="hook">{hook_html}</div>
</body></html>"""


def _hook_font_size(text: str) -> int:
    n = len(text)
    if n <= 40:
        return 92
    if n <= 65:
        return 76
    if n <= 90:
        return 64
    return 54


def render_hook_card(
    title: str,
    out_mp4_path,
    badge_text: str = None,
    emphasis_word: str = None,
    duration: float = 2.2,
    lang: str = "tr",
    brand: str = BRAND_DEFAULT,
    theme_idx: int = 0,
    ribbon_text: str = None,
) -> bool:
    """Videonun İLK karesi = video kapağı/thumbnail (Instagram ve YouTube
    otomatik seçiminde). Bu yüzden GÜVENİLİRLİK burada her şeyden önemli.

    ÖNCEKİ YAKLAŞIM (kaldırıldı): Playwright'ın gerçek zamanlı video kaydı
    (record_video_dir) ile animasyonu "canlı" kaydedip sonra ffmpeg -ss ile
    başındaki boş kare aralığını kesmeye çalışıyordu. Bu üç ayrı bug'a yol
    açtı (hepsi canlıda yaşandı): (1) kayıt context açılışı ile sayfanın
    boyanması arasındaki ~300-450ms boşluk kapağın bomboş/beyaz çıkmasına,
    (2) bu boşluğun kendisi de ölçümden ölçüme 0.17-0.59sn arası değişip
    öngörülemez olmasına, (3) bunu düzeltmek için eklenen taban (floor)
    değeri de kayıt süresini hesaba katmayınca klibin istenenden KISA
    çıkmasına yol açtı. Kök sorun: GERÇEK ZAMANLI/WALL-CLOCK bir kayıt
    süreciyle "bu an tam olarak ne gösteriliyor" sorusuna güvenilir cevap
    vermeye çalışmak — zamanlama sandbox yüküne göre değişken.

    YENİ YAKLAŞIM: eski/güvenilir "Short Üret" sekmesiyle AYNI desen —
    canlı video kaydı YOK. Sayfa render edilir, animasyonların bitmesi için
    sabit bir süre beklenir (page.wait_for_timeout — bu bir SAYFA İÇİ
    zamanlayıcı, kayıt zamanlamasıyla ilgisi yok), SONRA tek bir
    page.screenshot() ile o anki (tamamen oturmuş, ribbon dahil) hâli JPEG
    olarak yakalanır, ffmpeg bu SABİT görüntüyü `duration` saniye boyunca
    -loop ile videoya çevirir (tıpkı render_scene_card'ın fallback yolunda
    ve eski sistemde olduğu gibi). Artık hiçbir zamanlama ölçümü/tahmini
    yok — screenshot alındığı anda sayfa kesin olarak o hâldedir, kayıt
    başlangıcı/boşluk/süre kısalması gibi bir risk kalmadı."""
    try:
        theme = THEMES[theme_idx % len(THEMES)]
        badge = _esc((badge_text or ("BİLGİ" if lang == "tr" else "INFO")).upper()[:40])
        ribbon = _esc((ribbon_text or badge_text or ("ÖNEMLİ BİLGİ" if lang == "tr" else "IMPORTANT")).upper()[:44])
        title_e = _esc(title or "")
        ew = (emphasis_word or "").strip()
        if ew:
            pattern = re.compile(re.escape(_esc(ew)), re.IGNORECASE)
            if pattern.search(title_e):
                title_e = pattern.sub(lambda m: f"<em>{m.group(0)}</em>", title_e, count=1)
        html = _HOOK_TEMPLATE.format(
            bg1=theme["bg1"], bg2=theme["bg2"], accent=theme["accent"], accent2=theme["accent2"],
            badge=badge, brand=_esc(brand), hook_html=title_e, ribbon=ribbon,
            font_size=_hook_font_size(title or ""),
        )
        out_mp4_path = Path(out_mp4_path)

        browser = _get_browser()
        page = browser.new_page(viewport={"width": W, "height": H})
        try:
            page.set_content(html, wait_until="load")
            # En geç biten eleman .ribbon: animation-delay 0.42s + duration
            # 0.35s = 0.77s'de tamamlanıyor. 900ms bekleyip screenshot almak
            # her elemanın kesin olarak final/durgun halinde olmasını sağlar
            # — bu bir "tahmin" değil, sayfanın kendi zamanlayıcısı, kayıt
            # zamanlamasıyla karışmıyor.
            page.wait_for_timeout(900)
            tmp_png = out_mp4_path.with_suffix(".hook.png")
            page.screenshot(path=str(tmp_png))
        finally:
            page.close()

        result = subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_png), "-t", str(duration),
            "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-an", str(out_mp4_path),
        ], capture_output=True, timeout=60)
        tmp_png.unlink(missing_ok=True)
        if result.returncode != 0 or not out_mp4_path.exists() or out_mp4_path.stat().st_size == 0:
            return False
        return True
    except Exception:
        return False
