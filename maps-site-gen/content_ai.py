"""
AI ile web sitesi içeriği üretir.

Öncelik sırası:
1. DEEPSEEK_API_KEY  → DeepSeek (ucuz, hızlı, sadece requests kullanır)
2. ANTHROPIC_API_KEY → Claude (kuruluysa)
3. Fallback          → Şablon içerik (key olmadan da çalışır)
"""

import json
import requests as _req
import config
from scraper import BusinessInfo


def generate_content(business: BusinessInfo) -> dict:
    if config.DEEPSEEK_API_KEY:
        result = _with_deepseek(business)
        if result:
            return result
    if config.ANTHROPIC_API_KEY:
        result = _with_anthropic(business)
        if result:
            return result
    return _fallback(business)


# ─── DeepSeek ─────────────────────────────────────────────────────

def _with_deepseek(business: BusinessInfo) -> dict | None:
    prompt = _build_prompt(business)
    try:
        r = _req.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 900,
                "temperature": 0.7,
            },
            timeout=20,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return _parse_json(text)
    except Exception as e:
        print(f"[AI/DeepSeek] Hata: {e}")
        return None


# ─── Anthropic (opsiyonel) ────────────────────────────────────────

def _with_anthropic(business: BusinessInfo) -> dict | None:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": _build_prompt(business)}],
        )
        return _parse_json(msg.content[0].text)
    except ImportError:
        print("[AI/Anthropic] anthropic paketi kurulu değil, atlanıyor.")
        return None
    except Exception as e:
        print(f"[AI/Anthropic] Hata: {e}")
        return None


# ─── Prompt ───────────────────────────────────────────────────────

def _build_prompt(b: BusinessInfo) -> str:
    hours_str = "\n".join(f"  {k}: {v}" for k, v in b.hours.items()) if b.hours else "  Belirtilmemiş"
    reviews_str = "\n".join(f'  - "{r}"' for r in b.reviews_snippet[:3]) if b.reviews_snippet else "  Yok"
    return f"""Bir işletme için Türkçe web sitesi içeriği oluştur.

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
  "tagline": "Alt başlık (15-25 kelime, özgün)",
  "about": "Hakkımızda (4-5 cümle, işletme adı ve konum geçsin, samimi ton)",
  "services": ["Hizmet 1", "Hizmet 2", "Hizmet 3", "Hizmet 4", "Hizmet 5", "Hizmet 6"],
  "cta_text": "Buton metni (max 4 kelime)",
  "seo_description": "Meta description (max 155 karakter)"
}}"""


def _parse_json(text: str) -> dict | None:
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return None


# ─── Fallback (key olmadan) ────────────────────────────────────────

def _fallback(b: BusinessInfo) -> dict:
    cat = b.category or "İşletme"
    name = b.name or "İşletmemiz"

    service_map = {
        "kuaför": ["Saç Kesimi", "Boyama", "Röfle", "Manikür", "Fön", "Keratin"],
        "berber": ["Saç Kesimi", "Sakal Tıraşı", "Saç Yıkama", "Fön", "Sakal Şekillendirme", "Cilt Bakımı"],
        "restoran": ["Öğle Yemeği", "Akşam Yemeği", "Paket Servis", "Catering", "Özel Günler", "Taze Malzeme"],
        "kafe": ["Kahve Çeşitleri", "Soğuk İçecekler", "Kahvaltı", "Tatlılar", "Atıştırmalıklar", "Wi-Fi"],
        "eczane": ["Reçeteli İlaçlar", "Takviyeler", "Kozmetik", "Bebek Ürünleri", "Ölçüm Hizmetleri", "Danışmanlık"],
        "market": ["Gıda Ürünleri", "Temizlik", "İçecekler", "Şarküteri", "Ekmek & Unlu", "Ev Ürünleri"],
        "fırın": ["Ekmek", "Börek & Poğaça", "Pasta & Kek", "Simit", "Kurabiye", "Özel Sipariş"],
        "güzellik": ["Makyaj", "Cilt Bakımı", "Kaş Tasarımı", "İpek Kirpik", "Manikür", "Pedikür"],
        "spor": ["Fitness", "Pilates", "Yoga", "Kişisel Antrenman", "Beslenme", "Grup Dersleri"],
        "tamirci": ["Arıza Tespiti", "Onarım", "Yedek Parça", "Periyodik Bakım", "Servis", "Garanti"],
    }

    services = b.services[:6] if b.services else None
    if not services:
        for key, val in service_map.items():
            if key in cat.lower():
                services = val
                break
    if not services:
        services = ["Kaliteli Hizmet", "Profesyonel Ekip", "Uygun Fiyat", "Hızlı Servis", "Güvenilir", "Müşteri Odaklı"]

    city = b.address.split(",")[-1].strip() if b.address else "şehrimizde"

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
