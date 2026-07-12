"""
Supertonic bot → Ses Klonu Space entegrasyonu.

Space yayına girdikten sonra bot sunucusunda (Hetzner) bu fonksiyon
kullanılarak Supertonic sesi yerine kendi klonlanmış sesin alınabilir.

Kurulum (bot sunucusunda):
    pip install gradio_client

Kullanım:
    from bot_entegrasyon import kendi_sesimle_seslendir
    wav_yolu = kendi_sesimle_seslendir("Bugün Meteoroloji'den kritik uyarı geldi...")

Not: HF ücretsiz Space 48 saat kullanılmazsa uykuya geçer; ilk istek
soğuk başlatma yüzünden birkaç dakika sürebilir. Bot tarafında timeout'u
yüksek tut (aşağıda 600 sn).
"""

import os
import shutil

from gradio_client import Client

# Space adresin: https://huggingface.co/spaces/KULLANICI_ADIN/ses-klonu
SPACE_ID = "KULLANICI_ADIN/ses-klonu"  # ← kendi HF kullanıcı adınla değiştir

# Space PRIVATE olduğu için token şart. Token'ı https://huggingface.co/settings/tokens
# adresinden 'Read' yetkisiyle oluştur ve SADECE sunucudaki secrets.json'a ya da
# ortam değişkenine koy — asla koda/chat'e yapıştırma.
HF_TOKEN = os.environ.get("HF_TOKEN", "")

_client = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(SPACE_ID, hf_token=HF_TOKEN or None)
    return _client


def kendi_sesimle_seslendir(metin: str, hedef_dosya: str = "kendi_sesim_cikti.wav",
                            hiz: float = 1.0) -> str:
    """Metni Space'teki klonlanmış sesle seslendirir, wav yolunu döndürür.

    Referans ses Space'e 'referans_sesim.wav' olarak yüklendiği için
    burada ses dosyası göndermeye gerek yok (ref_audio=None → Space
    kendi referansını kullanır).
    """
    client = _get_client()
    sonuc = client.predict(
        text=metin,
        ref_audio=None,
        language="tr",
        speed=hiz,
        api_name="/speak",
    )
    shutil.copy(sonuc, hedef_dosya)
    return hedef_dosya


if __name__ == "__main__":
    yol = kendi_sesimle_seslendir(
        "Merhaba, ben Hakan. Bu ses yapay zeka ile klonlanmış kendi sesim. "
        "Bugünün öne çıkan haberlerine birlikte bakalım."
    )
    print(f"Ses üretildi: {yol}")
