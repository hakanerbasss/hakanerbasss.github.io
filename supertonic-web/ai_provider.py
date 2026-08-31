"""Botun TEK AI sağlayıcı katmanı — tüm modüller buradan geçer.

Neden ayrı dosya: aynı mantık app.py, news_ranker.py ve lv_worker.py'de
gerekiyor. app.py zaten news_ranker'ı import ettiği için tersi döngüsel import
olurdu; ortak modül bunu çözüyor ve "tek yerden kontrol" isteğini karşılıyor.

Çalışma mantığı: sabit model seçmek yerine GECİKMELİ YARIŞ. Önce tek modele
istek gider; HEDGE_GECIKME kadar cevap gelmezse sıradaki model de devreye
girer ve ilk cevap veren üretimi yapar. Hızlı hata verenler (429/402/404)
beklenmez, sıradaki hemen başlar. Böylece hangi sağlayıcının müsait olduğunu
bilmek gerekmez, ama normal durumda çağrı başına tek istek harcanır.
"""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from pathlib import Path

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

NVIDIA_CONFIG = Path("nvidia_config.json")
AI_RACE_CONFIG = Path("ai_race_config.json")     # DeepSeek yarışa katılsın mı
AI_LAST_USED = Path("ai_last_used.json")         # en son hangi model üretti

# Zaman aşımı: openai SDK'sının varsayılanı 600 saniye ve kendi içinde 2 kez
# daha deniyor — cevap vermeyen bir model üretimi 10 dakika asılı bırakıyordu.
# 90 sn bilerek yüksek: uzun JSON üreten çağrılar kesilmesin. Takılan modelin
# yol açtığı gecikmeyi HEDGE_GECIKME çözüyor, bu değeri düşürmek değil.
LLM_TIMEOUT = 90.0

# Panelde gösterilen ve yarışa giren ücretsiz modeller. NVIDIA kataloğunda
# 100'den fazla model var ama hepsi ücretsiz katmanda açılmıyor; burası
# çalıştığı görülenlerin listesi. Yeni model denemek için tek satır eklemek
# yeterli — açılmazsa yarışı kaybeder, başka bir şeyi bozmaz.
NVIDIA_MODELS = {
    "moonshotai/kimi-k3": "Kimi K3",
    "minimaxai/minimax-m3": "MiniMax M3",
    "deepseek-ai/deepseek-v4-flash-0731": "DeepSeek V4 Flash",
    "deepseek-ai/deepseek-v4-pro-0813": "DeepSeek V4 Pro",
    "meta/llama-3.2-90b-vision-instruct": "Llama 3.2 90B",
}

# Otomatik akışa SADECE bunlar girer, YAZILDIĞI SIRAYLA: ilk sıradaki asıl
# model, ikincisi yalnızca o takılırsa (HEDGE_GECIKME) veya hata verirse
# devreye giren yedek. Yukarıdaki NVIDIA_MODELS listesi panelden elle
# seçilebilenlerin tamamı; oradaki her modeli otomatik akışa sokmak kotayı
# boşa yakıyor.
#
# Sebep (30-31.08.2026 canlı hataları): ücretsiz kota ~40 istek/DAKİKA, hesap
# bazlı ve NVIDIA'nın açıklamasına göre o an modele gelen genel trafiğe göre
# daralıyor. Eskiden liste 5 modeldi ve HEPSİNE aynı anda istek atılıyordu:
# tek videoda 15 çağrı × 5 = 75 istek, üstüne haber jürisi 4 parçayı paralel
# işlerken tek seferde 20 istek. Kota saniyeler içinde doluyor, sonrasında HER
# model 429 veriyordu.
#
# Listedeki ikisi canlıda gerçekten cevap veren modeller. Elenen üçü aynı
# hatada 90 saniye boyunca susup zaman aşımına düştü — kotadan yiyor ama
# üretime katkısı yok. Yeni bir model ücretsiz katmanda hızlı cevap veriyorsa
# buraya eklenebilir; sıraya EKLEMEK istek sayısını artırmaz, çünkü sıradakiler
# ancak öncekiler takıldığında/hata verdiğinde başlar.
NVIDIA_RACE_MODELS = [
    "moonshotai/kimi-k3",
    "minimaxai/minimax-m3",
]

# Hepsi başarısız olduğunda kotanın yenilenmesi için beklenecek süre.
# 429 dakika bazlı bir sınır olduğu için kısa bir bekleme çoğu zaman yetiyor.
KOTA_BEKLEME = 25.0

# GECİKMELİ YARIŞ: ilk modelden bu kadar saniye cevap gelmezse ikinci model de
# devreye sokulur. Amaç istek sayısını yarıya indirmek.
#
# Neden (31.08.2026): NVIDIA'nın ücretsiz katmanı dakikada ~40 istek veriyor ve
# NVIDIA'nın kendi açıklamasına göre bu sınır sabit değil, o an modele gelen
# genel trafiğe göre daralıyor. Her çağrıyı iki modele birden atmak — yani
# istek sayısını ikiye katlamak — tam da kaçınmak istediğimiz 429'u üretiyordu.
#
# Düz sıralı denemenin sorunu şu olurdu: ilk model cevap vermeden asılı kalırsa
# (canlıda 90 saniye boyunca susan modeller görüldü) ikinciye sıra gelmesi çok
# gecikirdi. Gecikmeli yarış ikisinin ortası: normal durumda tek istek gider,
# ilk model takılırsa yarış kendiliğinden başlar.
#
# 20 sn seçildi çünkü çalışan çağrılar tipik olarak bunun altında dönüyor;
# LLM_TIMEOUT'u (90 sn) düşürmek yerine bu eklendi — zaman aşımını kısaltmak
# uzun JSON üreten çağrıları kesme riski taşıyordu.
HEDGE_GECIKME = 20.0


def get_nvidia_key() -> str:
    if NVIDIA_CONFIG.exists():
        try:
            return json.loads(NVIDIA_CONFIG.read_text()).get("api_key", "")
        except Exception:
            pass
    return ""


def get_deepseek_in_race() -> bool:
    """DeepSeek ücretsiz modellerle birlikte yarışsın mı? (varsayılan: hayır)

    Bakiye bittiğinde kapatılır, yüklendiğinde panelden açılır — kod
    değişikliği gerekmesin diye ayar olarak duruyor.
    """
    if AI_RACE_CONFIG.exists():
        try:
            return bool(json.loads(AI_RACE_CONFIG.read_text()).get("deepseek_in_race"))
        except Exception:
            pass
    return False


def kaydet_son_kullanilan(etiket: str, nerede: str) -> None:
    """Yarışı kazanan modeli diske yazar — panel bunu gösteriyor.

    ADIM BAZLI tutuluyor: tek bir videoda 15 ayrı LLM çağrısı var (senaryo,
    haber jürisi, başlık, etiketler…) ve yarışı her adımda başka bir model
    kazanabiliyor. Sadece "en son çağrı" saklansaydı, panelde çoğu zaman
    başlık/etiket adımının modeli görünürdü — videoyu yazan model değil.
    """
    try:
        d = son_kullanilan_hepsi()
        adimlar = d.get("adimlar") or {}
        adimlar[nerede] = {"model": etiket, "ts": time.time()}
        if len(adimlar) > 40:   # dosya sınırsız büyümesin
            adimlar = dict(sorted(adimlar.items(),
                                  key=lambda kv: kv[1].get("ts", 0))[-40:])
        AI_LAST_USED.write_text(json.dumps(
            {"model": etiket, "nerede": nerede, "ts": time.time(),
             "adimlar": adimlar},
            ensure_ascii=False))
    except Exception:
        pass


def son_kullanilan_hepsi() -> dict:
    if AI_LAST_USED.exists():
        try:
            return json.loads(AI_LAST_USED.read_text())
        except Exception:
            pass
    return {}


def son_kullanilan() -> dict:
    return son_kullanilan_hepsi()


def son_kullanilan_adim(nerede: str, en_fazla_saniye: float = 3600.0) -> str:
    """Belirli bir adımı (ör. 'haber-senaryo') en son hangi model yaptı.

    en_fazla_saniye: bundan eski kayıt "bu üretime ait değil" sayılıp boş
    dönülür — eski bir kaydı yeni videonun modeliymiş gibi göstermek,
    hiç göstermemekten daha kötü.
    """
    kayit = (son_kullanilan_hepsi().get("adimlar") or {}).get(nerede) or {}
    if not kayit.get("model"):
        return ""
    if time.time() - kayit.get("ts", 0) > en_fazla_saniye:
        return ""
    return kayit["model"]


def model_adi(etiket: str) -> str:
    """'nvidia/moonshotai/kimi-k3' → 'Kimi K3 (NVIDIA · ücretsiz)'"""
    if not etiket:
        return ""
    if etiket == "deepseek":
        return "DeepSeek V4 Flash (ücretli)"
    if etiket.startswith("nvidia/"):
        model = etiket.split("/", 1)[1]
        return f"{NVIDIA_MODELS.get(model, model)} (NVIDIA · ücretsiz)"
    return etiket


def hata_ozeti(hata: Exception) -> str:
    """Sağlayıcı hatasını tek kelimeyle sınıflandırır (log ve panel mesajı için)."""
    m = str(hata).lower()
    if "429" in m or "too many requests" in m:
        return "kota dolu (429)"
    if "402" in m or "insufficient balance" in m:
        return "BAKİYE YOK (402)"
    if "404" in m or "not found" in m:
        return "model yok (404)"
    if "401" in m or "403" in m or "unauthorized" in m:
        return "anahtar geçersiz"
    if "timeout" in m or "timed out" in m:
        return "zaman aşımı"
    return type(hata).__name__


def log_kullanim(resp, etiket: str, nerede: str) -> None:
    """Çağrı başına token tüketimi — fatura hangi adımda yanıyor, ölçülebilsin."""
    try:
        u = getattr(resp, "usage", None)
        if u:
            print(f"[AI-TOKEN] {nerede} · {etiket} · giriş={u.prompt_tokens} "
                  f"çıkış={u.completion_tokens} toplam={u.total_tokens}", flush=True)
    except Exception:
        pass


def make_llm_chain(provider: str, deepseek_key: str) -> list:
    """Yarışa girecek [(client, model, etiket)] listesi.

    provider:
      ""/"auto"           → tüm ücretsiz NVIDIA modelleri (+ ayar açıksa DeepSeek)
      "deepseek"          → sadece DeepSeek
      "nvidia:<model_id>" → sadece o model
    """
    from openai import OpenAI

    def _nv(model):
        return (OpenAI(api_key=nv_key, base_url=NVIDIA_BASE_URL,
                       timeout=LLM_TIMEOUT, max_retries=1),
                model, f"nvidia/{model}")

    def _ds():
        return (OpenAI(api_key=deepseek_key, base_url=DEEPSEEK_BASE_URL,
                       timeout=LLM_TIMEOUT, max_retries=1),
                DEEPSEEK_MODEL, "deepseek")

    nv_key = get_nvidia_key()
    provider = (provider or "").strip()

    if provider == "deepseek" or not nv_key:
        return [_ds()]
    if provider.startswith("nvidia:"):
        model = provider.split(":", 1)[1].strip()
        if model:
            return [_nv(model)]

    yaris = [_nv(m) for m in NVIDIA_RACE_MODELS]
    if get_deepseek_in_race():
        yaris.append(_ds())
    return yaris


async def llm_create(zincir: list, nerede: str, **kwargs):
    """Tüm modellere aynı anda istek atar, ilk cevap vereni kullanır (async).

    Hepsi başarısız olursa KOTA_BEKLEME kadar bekleyip bir kez daha dener:
    429 dakika bazlı bir sınır olduğu için kısa bir bekleme çoğu zaman
    yetiyor. Beklemeden tekrar denemek (çağıran taraftaki döngülerin yaptığı
    gibi) aynı duvara toslamaktan başka işe yaramıyordu.
    """
    try:
        return await _llm_create_bir_tur(zincir, nerede, **kwargs)
    except RuntimeError as ilk:
        if "kota dolu" not in str(ilk):
            raise
        print(f"[AI] {nerede} · tüm modeller kota dolu — {KOTA_BEKLEME:.0f}sn "
              f"beklenip bir kez daha denenecek", flush=True)
        await asyncio.sleep(KOTA_BEKLEME)
        return await _llm_create_bir_tur(zincir, nerede, **kwargs)


async def _llm_create_bir_tur(zincir: list, nerede: str, **kwargs):
    """Tek turluk GECİKMELİ yarış — llm_create bunu (gerekirse iki kez) çağırır.

    Önce sadece ilk model çağrılır. HEDGE_GECIKME kadar cevap gelmezse ikinci
    model de devreye sokulur ve oradan sonrası gerçek yarıştır: ilk cevap veren
    kazanır. Model hızlı hata verirse (429/402) beklenmez, sıradaki hemen başlar.
    """
    async def _dene(client, model, etiket):
        resp = await asyncio.to_thread(
            client.chat.completions.create, model=model, **kwargs)
        return resp, etiket

    isler, hatalar, bekleyen = {}, [], set()
    kalan = list(zincir)
    try:
        while kalan or bekleyen:
            if kalan:
                c, m, e = kalan.pop(0)
                gorev = asyncio.create_task(_dene(c, m, e))
                isler[gorev] = e
                bekleyen.add(gorev)
            # Sırada model varsa en fazla HEDGE_GECIKME bekle, sonra onu da başlat.
            # Sıra bittiyse süresiz bekle (SDK'nın kendi timeout'u zaten var).
            biten, bekleyen = await asyncio.wait(
                bekleyen, timeout=(HEDGE_GECIKME if kalan else None),
                return_when=asyncio.FIRST_COMPLETED)
            for is_ in biten:
                etiket = isler[is_]
                try:
                    resp, etiket = is_.result()
                except Exception as e:
                    hatalar.append(f"{etiket}: {hata_ozeti(e)}")
                    continue
                log_kullanim(resp, etiket, nerede)
                kaydet_son_kullanilan(etiket, nerede)
                print(f"[AI] {nerede} · '{etiket}' cevap verdi", flush=True)
                return resp, etiket
    finally:
        for is_ in isler:
            if not is_.done():
                is_.cancel()

    raise RuntimeError(
        f"Hiçbir AI modeli cevap vermedi ({nerede}). Denenenler → "
        + " | ".join(hatalar))


def llm_create_sync(zincir: list, nerede: str, **kwargs):
    """llm_create'in senkron sürümü (kota dolarsa bir kez daha dener)."""
    try:
        return _llm_create_sync_bir_tur(zincir, nerede, **kwargs)
    except RuntimeError as ilk:
        if "kota dolu" not in str(ilk):
            raise
        print(f"[AI] {nerede} · tüm modeller kota dolu — {KOTA_BEKLEME:.0f}sn "
              f"beklenip bir kez daha denenecek", flush=True)
        time.sleep(KOTA_BEKLEME)
        return _llm_create_sync_bir_tur(zincir, nerede, **kwargs)


def _llm_create_sync_bir_tur(zincir: list, nerede: str, **kwargs):
    """Tek turluk senkron yarış.

    news_ranker'ın AI jürisi ThreadPoolExecutor içinde senkron çalışıyor;
    orayı async'e çevirmek geniş bir değişiklik olurdu. Aynı yarış mantığı,
    thread'lerle.
    """
    hatalar = []
    # "with ThreadPoolExecutor(...)" KULLANILMIYOR: with çıkışında shutdown(wait=True)
    # çağrılıyor ve kazanan bulunsa bile en yavaş modelin bitmesi bekleniyordu
    # (testte 0,2 sn'lik kazanan için 1,5 sn beklendi).
    ex = ThreadPoolExecutor(max_workers=max(1, len(zincir)))
    isler, bekleyen = {}, set()
    kalan = list(zincir)
    try:
        while kalan or bekleyen:
            if kalan:
                c, m, e = kalan.pop(0)
                is_yeni = ex.submit(c.chat.completions.create, model=m, **kwargs)
                isler[is_yeni] = e
                bekleyen.add(is_yeni)
            biten, bekleyen = wait(
                bekleyen, timeout=(HEDGE_GECIKME if kalan else None),
                return_when=FIRST_COMPLETED)
            for is_ in biten:
                etiket = isler[is_]
                try:
                    resp = is_.result()
                except Exception as e:
                    hatalar.append(f"{etiket}: {hata_ozeti(e)}")
                    continue
                log_kullanim(resp, etiket, nerede)
                kaydet_son_kullanilan(etiket, nerede)
                print(f"[AI] {nerede} · '{etiket}' cevap verdi", flush=True)
                return resp, etiket
    finally:
        # Kazanan belli olunca kalanları bekleme; henüz başlamamışları iptal et.
        ex.shutdown(wait=False, cancel_futures=True)

    raise RuntimeError(
        f"Hiçbir AI modeli cevap vermedi ({nerede}). Denenenler → "
        + " | ".join(hatalar))
