"""Botun TEK AI sağlayıcı katmanı — tüm modüller buradan geçer.

Neden ayrı dosya: aynı mantık app.py, news_ranker.py ve lv_worker.py'de
gerekiyor. app.py zaten news_ranker'ı import ettiği için tersi döngüsel import
olurdu; ortak modül bunu çözüyor ve "tek yerden kontrol" isteğini karşılıyor.

Çalışma mantığı: sabit model seçmek yerine uygun modellerin HEPSİNE aynı anda
istek atılır, ilk cevap veren üretimi yapar, kalanlar iptal edilir. Böylece
hangi sağlayıcının müsait olduğunu bilmek gerekmez — kotaya takılan (429),
açılmayan (404) veya bakiyesi biten (402) modeller yarışı kaybeder, üretim
durmaz.
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
# daha deniyor. Yarışta bunun anlamı yok — cevap vermeyen model beklemesin,
# hızlı olan zaten kazanır.
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

# Otomatik yarışa SADECE bunlar girer. Yukarıdaki liste panelden elle
# seçilebilenlerin tamamı; yarışa hepsini sokmak kotayı boşa yakıyor.
#
# Sebep (30.08.2026 canlı hatası): ücretsiz kota ~40 istek/DAKİKA ve HESAP
# bazlı. Yarış her LLM çağrısında liste kadar istek atıyor — 5 model demek,
# tek bir video üretiminde 15 çağrı × 5 = 75 istek demek. Üstüne haber jürisi
# 4 parçayı paralel işliyor (4 × 5 = 20 istek tek seferde). Sonuç: kota
# saniyeler içinde doluyor ve HER model 429 veriyor.
#
# Listedeki ikisi canlıda gerçekten cevap veren modeller. Diğer üçü aynı
# hatada 90 saniye boyunca cevap vermeyip zaman aşımına düştü — yani kotadan
# yiyor ama üretime katkısı yok. Yeni bir model ücretsiz katmanda hızlı cevap
# veriyorsa buraya eklenebilir.
NVIDIA_RACE_MODELS = [
    "moonshotai/kimi-k3",
    "minimaxai/minimax-m3",
]

# Hepsi başarısız olduğunda kotanın yenilenmesi için beklenecek süre.
# 429 dakika bazlı bir sınır olduğu için kısa bir bekleme çoğu zaman yetiyor.
KOTA_BEKLEME = 25.0


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
    """Yarışı kazanan modeli diske yazar — panel bunu gösteriyor."""
    try:
        AI_LAST_USED.write_text(json.dumps(
            {"model": etiket, "nerede": nerede, "ts": time.time()},
            ensure_ascii=False))
    except Exception:
        pass


def son_kullanilan() -> dict:
    if AI_LAST_USED.exists():
        try:
            return json.loads(AI_LAST_USED.read_text())
        except Exception:
            pass
    return {}


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
    """Tek turluk yarış — llm_create bunu (gerekirse iki kez) çağırır."""
    async def _dene(client, model, etiket):
        resp = await asyncio.to_thread(
            client.chat.completions.create, model=model, **kwargs)
        return resp, etiket

    isler = {asyncio.create_task(_dene(c, m, e)): e for c, m, e in zincir}
    hatalar = []
    bekleyen = set(isler)
    try:
        while bekleyen:
            biten, bekleyen = await asyncio.wait(
                bekleyen, return_when=asyncio.FIRST_COMPLETED)
            for is_ in biten:
                etiket = isler[is_]
                try:
                    resp, etiket = is_.result()
                except Exception as e:
                    hatalar.append(f"{etiket}: {hata_ozeti(e)}")
                    continue
                log_kullanim(resp, etiket, nerede)
                kaydet_son_kullanilan(etiket, nerede)
                print(f"[AI] {nerede} · yarışı '{etiket}' kazandı", flush=True)
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
    # (testte 0,2 sn'lik kazanan için 1,5 sn beklendi). Jüri 4 parçayı paralel
    # işlediği için bu gecikme katlanarak büyürdü.
    ex = ThreadPoolExecutor(max_workers=max(1, len(zincir)))
    try:
        isler = {
            ex.submit(c.chat.completions.create, model=m, **kwargs): e
            for c, m, e in zincir
        }
        bekleyen = set(isler)
        while bekleyen:
            biten, bekleyen = wait(bekleyen, return_when=FIRST_COMPLETED)
            for is_ in biten:
                etiket = isler[is_]
                try:
                    resp = is_.result()
                except Exception as e:
                    hatalar.append(f"{etiket}: {hata_ozeti(e)}")
                    continue
                log_kullanim(resp, etiket, nerede)
                kaydet_son_kullanilan(etiket, nerede)
                print(f"[AI] {nerede} · yarışı '{etiket}' kazandı", flush=True)
                return resp, etiket
    finally:
        # Kazanan belli olunca kalanları bekleme; henüz başlamamışları iptal et.
        ex.shutdown(wait=False, cancel_futures=True)

    raise RuntimeError(
        f"Hiçbir AI modeli cevap vermedi ({nerede}). Denenenler → "
        + " | ".join(hatalar))
