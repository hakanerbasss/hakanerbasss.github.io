"""
Claude API ile SEO uyumlu içerik üretir. API yoksa şablon kullanır.
"""

import json
import config
from scraper import BusinessInfo

_client = None


def _get_client():
    global _client
    if _client is None and config.ANTHROPIC_API_KEY:
        import anthropic
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def generate_content(business: BusinessInfo) -> dict:
    client = _get_client()
    return _with_ai(client, business) if client else _fallback(business)


def _with_ai(client, b: BusinessInfo) -> dict:
    hours_str = "\n".join(f"  {k}: {v}" for k, v in b.hours.items()) if b.hours else "  Belirtilmemiş"
    reviews_str = "\n".join(f'  - "{r}"' for r in b.reviews_snippet[:3]) if b.reviews_snippet else "  Yok"

    prompt = f"""Bir işletme için Türkçe web sitesi içeriği oluştur.

İşletme:
- Ad: {b.name}
- Kategori: {b.category}
- Adres: {b.address}
- Telefon: {b.phone}
- Puan: {b.rating}/5 ({b.review_count} yorum)
- Hakkında: {b.about or 'Belirtilmemiş'}
- Çalışma saatleri:\n{hours_str}
- Müşteri yorumları:\n{reviews_str}

Sadece JSON döndür, başka hiçbir şey yazma:
{{
  "headline": "Ana başlık (dikkat çekici, 6-10 kelime)",
  "tagline": "Alt başlık/slogan (15-25 kelime, özgün)",
  "about": "Hakkımızda paragrafı (4-5 cümle, işletme adını ve konumu belirt, samimi ton)",
  "services": ["Hizmet/Ürün 1", "Hizmet/Ürün 2", "Hizmet/Ürün 3", "Hizmet/Ürün 4", "Hizmet/Ürün 5", "Hizmet/Ürün 6"],
  "cta_text": "Harekete geçirici buton metni (kısa, max 4 kelime)",
  "seo_description": "Meta description (max 155 karakter, SEO uyumlu)"
}}"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f"[AI] Hata: {e}")
        return _fallback(b)


def _fallback(b: BusinessInfo) -> dict:
    cat = b.category or "İşletme"
    name = b.name or "İşletmemiz"

    service_map = {
        "restoran": ["Öğle Yemeği", "Akşam Yemeği", "Paket Servis", "Catering", "Özel Günler", "Taze Malzeme"],
        "kafe": ["Kahve Çeşitleri", "Soğuk İçecekler", "Atıştırmalıklar", "Kahvaltı", "Tatlılar", "Wi-Fi"],
        "berber": ["Saç Kesimi", "Sakal Tıraşı", "Saç Yıkama", "Fön", "Sakal Şekillendirme", "Cilt Bakımı"],
        "kuaför": ["Saç Kesimi", "Boyama", "Röfle", "Manikür", "Fön", "Keratin"],
        "market": ["Gıda Ürünleri", "Temizlik", "İçecekler", "Şarküteri", "Ekmek & Unlu", "Ev Ürünleri"],
        "eczane": ["Reçeteli İlaçlar", "Takviyeler", "Kozmetik", "Bebek Ürünleri", "Ölçüm Hizmetleri", "Danışmanlık"],
        "tamirci": ["Arıza Tespiti", "Onarım", "Yedek Parça", "Periyodik Bakım", "Servis", "Garanti"],
        "doktor": ["Muayene", "Teşhis", "Tedavi", "Takip", "Raporlama", "Online Randevu"],
        "fırın": ["Ekmek", "Börek & Poğaça", "Pasta & Kek", "Simit", "Kurabiye", "Özel Sipariş"],
        "güzellik": ["Makyaj", "Cilt Bakımı", "Kaş Tasarımı", "İpek Kirpik", "Manikür", "Pedikür"],
    }

    services = ["Kaliteli Hizmet", "Profesyonel Ekip", "Uygun Fiyat", "Hızlı Servis", "Güvenilir", "Müşteri Odaklı"]
    for key, val in service_map.items():
        if key in cat.lower():
            services = val
            break

    if b.services:
        services = b.services[:6] or services

    city_parts = b.address.split(",") if b.address else []
    city = city_parts[-1].strip() if city_parts else "şehrimizde"

    return {
        "headline": f"{name} — {cat} Hizmetleri",
        "tagline": f"{city} bölgesinde güvenilir ve profesyonel {cat.lower()} hizmetleri.",
        "about": (
            f"{name} olarak {city} bölgesinde {cat.lower()} alanında hizmet vermekteyiz. "
            f"Müşteri memnuniyetini ön planda tutarak, deneyimli ekibimizle en iyi hizmeti sunuyoruz. "
            f"Kalite ve güven ilkesiyle hareket ediyor, her müşterimize özel çözümler üretiyoruz. "
            f"Bizi aramaktan veya ziyaret etmekten çekinmeyin, sizinle tanışmak isteriz."
        ),
        "services": services,
        "cta_text": "Hemen Arayın",
        "seo_description": f"{name} | {cat} | {b.address[:100]}",
    }
