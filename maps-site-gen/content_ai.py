"""
Claude API ile işletme için web sitesi içeriği üretir.
ANTHROPIC_API_KEY yoksa şablon içerik kullanır.
"""

import anthropic
import config
from scraper import BusinessInfo

_client = None


def _get_client():
    global _client
    if _client is None and config.ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def generate_content(business: BusinessInfo) -> dict:
    """
    İşletme için SEO uyumlu web sitesi içeriği üretir.
    Dönen dict: headline, tagline, about, services, cta_text
    """
    client = _get_client()

    if client:
        return _generate_with_ai(client, business)
    else:
        return _generate_fallback(business)


def _generate_with_ai(client, business: BusinessInfo) -> dict:
    hours_text = ""
    if business.hours:
        hours_text = "\n".join(f"  {k}: {v}" for k, v in business.hours.items())

    prompt = f"""Bir işletme için Türkçe web sitesi içeriği oluştur.

İşletme Bilgileri:
- Ad: {business.name}
- Kategori: {business.category}
- Adres: {business.address}
- Telefon: {business.phone}
- Puan: {business.rating}/5 ({business.review_count} yorum)
- Çalışma Saatleri:
{hours_text or "  Belirtilmemiş"}

Şu alanları JSON olarak üret (başka şey yazma):
{{
  "headline": "Ana başlık (kısa, dikkat çekici, 5-10 kelime)",
  "tagline": "Alt başlık/slogan (15-20 kelime)",
  "about": "Hakkında bölümü (3-4 cümle, samimi ve profesyonel, işletme adı ve konumu içersin)",
  "services": ["Hizmet 1", "Hizmet 2", "Hizmet 3", "Hizmet 4", "Hizmet 5"],
  "cta_text": "Harekete geçirici metin (kısa, örn: Hemen Arayın, Rezervasyon Yapın)"
}}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = message.content[0].text.strip()
        # JSON bloğunu ayıkla
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"[AI] İçerik üretilemedi, fallback kullanılıyor: {e}")
        return _generate_fallback(business)


def _generate_fallback(business: BusinessInfo) -> dict:
    """API olmadan şablon içerik üretir."""
    category = business.category or "İşletme"
    name = business.name or "İşletmemiz"

    service_map = {
        "restoran": ["Öğle Yemeği", "Akşam Yemeği", "Paket Servis", "Catering", "Özel Günler"],
        "kafe": ["Sıcak İçecekler", "Soğuk İçecekler", "Atıştırmalıklar", "Kahvaltı", "Wi-Fi"],
        "market": ["Gıda Ürünleri", "Temizlik Ürünleri", "Kişisel Bakım", "İçecekler", "Şarküteri"],
        "berber": ["Saç Kesimi", "Sakal Tıraşı", "Saç Boyama", "Bakım", "Styling"],
        "kuaför": ["Saç Kesimi", "Boyama", "Manikür", "Pedikür", "Cilt Bakımı"],
        "eczane": ["Reçeteli İlaçlar", "OTC Ürünler", "Kozmetik", "Bebek Ürünleri", "Takviye"],
        "tamirci": ["Onarım", "Bakım", "Yedek Parça", "Servis", "Danışmanlık"],
        "doktor": ["Muayene", "Teşhis", "Tedavi", "Kontrol", "Danışmanlık"],
    }

    services = ["Kaliteli Hizmet", "Profesyonel Kadro", "Uygun Fiyat", "Hızlı Servis", "Güvenilir"]
    for key, val in service_map.items():
        if key in category.lower():
            services = val
            break

    city = business.city or business.address.split(",")[-1].strip() if business.address else "şehrimizde"

    return {
        "headline": f"{name} — {category} Hizmetleri",
        "tagline": f"Kaliteli ve güvenilir {category.lower()} hizmetleri için doğru adres.",
        "about": (
            f"{name} olarak {city} bölgesinde {category.lower()} alanında hizmet vermekteyiz. "
            f"Müşteri memnuniyetini her zaman ön planda tutarak profesyonel ekibimizle "
            f"sizlere en iyi hizmeti sunmaya çalışıyoruz. "
            f"Bizi arayın veya adresimize gelin, sizinle tanışmaktan mutluluk duyarız."
        ),
        "services": services,
        "cta_text": "Hemen Arayın",
    }
