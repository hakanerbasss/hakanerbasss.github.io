#!/usr/bin/env python3
"""NVIDIA ücretsiz katmanındaki modelleri TARAR ve ÖLÇER.

Neden var: otomatik akışa hangi modellerin gireceğine tahminle karar
vermek yanlış. Bir model 429 verirse zincir hemen ilerler (ucuz), ama
SUSARSA sıradakine geçmek HEDGE_GECIKME kadar (20 sn) bekler. Videoda ~15
LLM çağrısı olduğu için susan bir modeli listeye koymak üretime dakikalar
ekler. Bu yüzden listeye ancak ölçülmüş, gerçekten hızlı cevap veren
modeller alınmalı.

Çalıştırma (sunucuda):

    cd /root/hakanerbasss.github.io/supertonic-web
    python3 nvidia_tara.py

Anahtar `nvidia_config.json`'dan okunur (panelde kayıtlı olan). Sadece
standart kütüphane kullanır — venv/pip gerekmez.

Çıktı: her modelin durumu + en sona ai_provider.py'ye yapıştırılabilecek
hazır NVIDIA_RACE_MODELS listesi.
"""

import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TABAN = "https://integrate.api.nvidia.com/v1"
AYAR = Path(__file__).with_name("nvidia_config.json")

# Test isteği: kısa tutuluyor ki tarama kotayı yakmasın. Gerçek üretim
# istekleri daha uzun, o yüzden buradaki süreler ALT SINIR sayılmalı —
# "burada yavaşsa üretimde daha da yavaş" diye okunmalı.
TEST_MESAJ = [{"role": "user",
               "content": "Tek kelimeyle cevap ver: Türkiye'nin başkenti neresi?"}]
TEST_MAX_TOKEN = 16

ZAMAN_ASIMI = 30.0      # bunu geçen model "susuyor" sayılır
ISTEK_ARASI = 2.0       # kotayı (dakikada ~40 istek) yakmamak için
HIZLI_SINIR = 8.0       # bu sürenin altı "listeye alınabilir"

# Kataloğu tararken bakılacak aileler. Katalogda embedding/rerank/görüntü
# modelleri de var; hepsini denemek hem kotayı yakar hem anlamsız olur.
AILELER = ("kimi", "minimax", "deepseek", "qwen", "llama", "nemotron",
           "gpt-oss", "glm", "mistral", "gemma", "phi")

# Bu kelimeleri içeren modeller sohbet modeli değil, atlanır.
ATLA = ("embed", "rerank", "guard", "ocr", "speech", "tts", "asr",
        "vision", "vila", "clip", "diffusion", "riva", "parakeet")


def anahtar() -> str:
    if AYAR.exists():
        try:
            return json.loads(AYAR.read_text()).get("api_key", "").strip()
        except Exception:
            pass
    return ""


def istek(yol: str, govde: dict | None, key: str, zaman_asimi: float):
    veri = json.dumps(govde).encode() if govde is not None else None
    r = urllib.request.Request(
        f"{TABAN}{yol}", data=veri,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Accept": "application/json"},
        method="POST" if veri else "GET")
    with urllib.request.urlopen(r, timeout=zaman_asimi,
                                context=ssl.create_default_context()) as c:
        return json.loads(c.read().decode())


def hata_ozeti(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        kod = e.code
        return {429: "kota dolu (429)", 404: "model yok (404)",
                401: "anahtar geçersiz (401)", 403: "erişim yok (403)",
                402: "bakiye yok (402)"}.get(kod, f"HTTP {kod}")
    m = str(e).lower()
    if "timed out" in m or "timeout" in m:
        return f"SUSTU (>{ZAMAN_ASIMI:.0f}sn)"
    return type(e).__name__


def katalog(key: str) -> list[str]:
    """Hesabın erişebildiği modeller. Kimlik uydurmamak için tek doğru kaynak."""
    try:
        d = istek("/models", None, key, 30.0)
    except Exception as e:
        print(f"  ! katalog okunamadı ({hata_ozeti(e)}) — gömülü liste kullanılacak")
        return []
    return sorted(m.get("id", "") for m in d.get("data", []) if m.get("id"))


def adaylar(hepsi: list[str]) -> list[str]:
    from ai_provider import NVIDIA_MODELS          # panelde duranlar hep denensin
    secili = list(NVIDIA_MODELS)
    for mid in hepsi:
        dusuk = mid.lower()
        if any(a in dusuk for a in ATLA):
            continue
        if any(a in dusuk for a in AILELER) and mid not in secili:
            secili.append(mid)
    return secili


def dene(model: str, key: str) -> tuple[str, float]:
    t0 = time.time()
    try:
        istek("/chat/completions",
              {"model": model, "messages": TEST_MESAJ,
               "max_tokens": TEST_MAX_TOKEN, "temperature": 0.2},
              key, ZAMAN_ASIMI)
        return "ok", time.time() - t0
    except Exception as e:
        return hata_ozeti(e), time.time() - t0


def main() -> int:
    key = anahtar()
    if not key:
        print("HATA: nvidia_config.json içinde api_key yok. "
              "Panelde Ayarlar → NVIDIA API key kısmından kaydet.")
        return 1

    print(f"Katalog okunuyor… ({TABAN}/models)")
    hepsi = katalog(key)
    print(f"  hesabın erişebildiği model sayısı: {len(hepsi) or 'okunamadı'}")
    if hepsi:
        Path("nvidia_katalog.txt").write_text("\n".join(hepsi))
        print("  tam liste → nvidia_katalog.txt")

    liste = adaylar(hepsi)
    en_fazla = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    liste = liste[:en_fazla]
    print(f"\n{len(liste)} aday denenecek "
          f"(istek arası {ISTEK_ARASI:.0f}sn — kota yanmasın diye)\n")

    sonuc = []
    for i, model in enumerate(liste, 1):
        durum, sure = dene(model, key)
        isaret = "✅" if durum == "ok" and sure <= HIZLI_SINIR else (
            "🐢" if durum == "ok" else "❌")
        print(f"{isaret} [{i:2}/{len(liste)}] {model:<52} "
              f"{durum:<20} {sure:5.1f}sn", flush=True)
        sonuc.append((model, durum, sure))
        if i < len(liste):
            time.sleep(ISTEK_ARASI)

    calisan = sorted([s for s in sonuc if s[1] == "ok"], key=lambda x: x[2])
    hizli = [m for m, _, sn in calisan if sn <= HIZLI_SINIR]
    yavas = [(m, sn) for m, _, sn in calisan if sn > HIZLI_SINIR]
    kotada = [m for m, d, _ in sonuc if "429" in d]
    olmayan = [m for m, d, _ in sonuc if "404" in d or "403" in d]
    susan = [m for m, d, _ in sonuc if "SUSTU" in d]

    print("\n" + "=" * 70)
    print(f"ÇALIŞAN ve HIZLI (≤{HIZLI_SINIR:.0f}sn): {len(hizli)}")
    print(f"ÇALIŞAN ama YAVAŞ: {len(yavas)}" +
          (f" → {', '.join(f'{m} ({sn:.0f}sn)' for m, sn in yavas)}" if yavas else ""))
    print(f"KOTA DOLU (429): {len(kotada)}   "
          f"— hesap şu an kısıtlıysa hepsi böyle çıkar, taramayı sonra tekrarla")
    print(f"ERİŞİM YOK (404/403): {len(olmayan)}")
    print(f"SUSAN (>{ZAMAN_ASIMI:.0f}sn): {len(susan)} — bunlar listeye ALINMAMALI, "
          f"her biri zinciri {20} sn bekletir")

    print("\nai_provider.py'ye yapıştır (en hızlıdan yavaşa sıralı):\n")
    if hizli:
        print("NVIDIA_RACE_MODELS = [")
        for m, _, sn in calisan:
            if sn <= HIZLI_SINIR:
                print(f'    "{m}",'.ljust(56) + f"# {sn:.1f}sn")
        print("]")
    else:
        print("# Hiçbir model hızlı cevap vermedi. Hepsi 429 ise hesap şu an")
        print("# kısıtlı demektir — birkaç saat sonra taramayı tekrarla.")
        print("# Liste değiştirilmemeli; DeepSeek yedeği üretimi ayakta tutar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
