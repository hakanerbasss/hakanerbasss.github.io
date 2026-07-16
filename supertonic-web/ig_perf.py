"""
Instagram kategori performans skorlama.

ig_analytics_cache.json'daki (fetch_full_analytics çıktısı) gerçek post
metriklerinden kategori bazlı skor çıkarır ve DeepSeek konu seçim prompt'una
eklenecek yönlendirme metni üretir.

Tasarım kararları (12.07.2026 analizinden, 292 post):
- Hava durumu (ort. 8.259 izlenme / 49.7 paylaşım) ve maaş/emekli (6.817)
  açık ara en iyi; uluslararası siyaset (1.296) en kötü performans.
- Sinyal sert filtre DEĞİL: skorlar prompt'a "tercih et" bilgisi olarak gider,
  %20 ihtimalle hiç gönderilmez (keşif payı — yeni kazanan kategoriler
  bulunabilsin diye).
- Tekrar koruması ayrı ve SERT: aynı kategoriden art arda en fazla
  MAX_CONSECUTIVE, günde en fazla DAILY_CAT_CAP post (kod tarafında
  check_hard_rules ile denetlenir).
"""

import json
import random
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

CACHE_FILE = Path("ig_analytics_cache.json")

HALF_LIFE_DAYS = 14      # skor ağırlığı her 14 günde yarıya iner (eski postlar az sayılır)
MAX_AGE_DAYS = 60        # 60 günden eski postlar skora hiç girmez
MIN_POSTS = 3            # kategori sıralamaya girmek için en az bu kadar post
DAILY_CAT_CAP = 4        # aynı kategoriden günde en fazla bu kadar post
MAX_CONSECUTIVE = 2      # aynı kategoriden art arda en fazla bu kadar post
EXPLORE_RATE = 0.20      # bu ihtimalle performans sıralaması prompt'a eklenmez

# Skor ne olursa olsun hiç seçilmesin — kişisel/skandal/cinayet haberleri sistematik
# olarak düşük performans gösteriyor ve hesabın "haber ve medya sitesi" imajına uymuyor.
HARD_EXCLUDE_CATS = ["ASAYİŞ"]

# Sıra önemli: ilk eşleşen kazanır (HAVA, AFET'ten önce gelmeli — "sıcaklık" ikisinde de olabilir)
_CATS = [
    ("HAVA", ["havadurumu", "hava durumu", "meteoroloji", "sıcaklık", "sıcak hava",
              "yağış", "sağanak", "kar yağışı", "fırtına", "dolu yağışı", "don olayı",
              "soğuk hava", "kavurucu", "hissedilen"]),
    ("GURBETÇİ", ["gurbetçi", "gurbetçiler", "yurtdışında yaşayan", "yurt dışında yaşayan",
                  "avrupa'daki türkler", "almanya'daki türkler", "diaspora", "bedelli askerlik",
                  "yurtdışı vatandaş", "yurtdışı türk", "avrupa türkleri"]),
    ("EKONOMİ", ["maaş", "zam", "emekli", "asgari ücret", "asgariücret", "enflasyon",
                 "dolar", "euro", "faiz", "borsa", "vergi", "kira", "sgk", "promosyon",
                 "ikramiye", "tazminat", "bağkur", "prim"]),
    ("AFET", ["deprem", "sel felaketi", "sel ", "yangın", "afet", "heyelan", "tsunami",
              "orman yangını"]),
    ("SPOR", ["futbol", "basketbol", "spor", "şampiyon", "lig ", "maç", "gol",
              "transfer", "milli takım", "formula", "galatasaray", "fenerbahçe",
              "beşiktaş", "trabzonspor"]),
    ("DÜNYA", ["iran", "i̇ran", "israil", "i̇srail", "abd", "amerika", "rusya",
               "ukrayna", "nato", "gazze", "savaş", "füze", "trump", "putin",
               "suriye", "katar", "venezuela", "hürmüz", "pentagon", "beyaz saray"]),
    ("SİYASET", ["chp", "akp", "belediye", "erdoğan", "erdogan", "bakan", "meclis",
                 "seçim", "parti", "imamoğlu", "özgür özel", "bahçeli", "mhp",
                 "cumhurbaşkanı"]),
    ("ASAYİŞ", ["cinayet", "gözaltı", "operasyon", "tutukla", "kaza", "uyuşturucu",
                "şehit", "saldırı", "patlama", "soygun", "dolandırıcı"]),
    ("TEKNOLOJİ", ["yapay zeka", "teknoloji", "nasa", "uzay", "chatgpt", "iphone",
                   "android", "robot", "bilim"]),
]
DEFAULT_CAT = "GÜNDEM"

# Prompt'ta kategori adının yanına eklenen İngilizce açıklama (DeepSeek promptları İngilizce)
_CAT_EN = {
    "HAVA": "weather/meteorology warnings",
    "GURBETÇİ": "Turkish diaspora abroad (military service, residency, benefits)",
    "EKONOMİ": "salary/pension/economy",
    "AFET": "disasters",
    "SPOR": "sports",
    "DÜNYA": "international/world politics",
    "SİYASET": "domestic politics",
    "ASAYİŞ": "crime/incidents",
    "TEKNOLOJİ": "tech/science",
    "GÜNDEM": "general",
}


def categorize(title: str, hashtags: list = None) -> str:
    """Başlık + hashtag'lerden kategori tahmini. İlk eşleşen kazanır."""
    text = (title or "").lower()
    if hashtags:
        text += " " + " ".join(str(h).lower() for h in hashtags)
    for cat, kws in _CATS:
        if any(k in text for k in kws):
            return cat
    return DEFAULT_CAT


def _load_posts() -> list:
    if not CACHE_FILE.exists():
        return []
    try:
        return json.loads(CACHE_FILE.read_text()).get("posts", [])
    except Exception:
        return []


def category_scores() -> list[dict]:
    """Kategori başına recency ağırlıklı ortalama metrikler, skora göre sıralı.

    skor = ort_izlenme + 80 × ort_paylaşım + 40 × ort_kaydetme
    (paylaşım keşfete düşmenin en güçlü sinyali, bu yüzden ağır basar)
    """
    posts = _load_posts()
    if not posts:
        return []

    now = datetime.now(timezone.utc)
    agg: dict[str, dict] = {}
    for p in posts:
        ts = p.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            continue
        age_days = (now - dt).total_seconds() / 86400
        if age_days > MAX_AGE_DAYS:
            continue
        w = 0.5 ** (age_days / HALF_LIFE_DAYS)
        cat = categorize(p.get("caption", ""), p.get("hashtags", []))
        a = agg.setdefault(cat, {"w": 0.0, "views": 0.0, "shares": 0.0, "saved": 0.0, "n": 0})
        a["w"] += w
        a["views"] += w * (p.get("views") or 0)
        a["shares"] += w * (p.get("shares") or 0)
        a["saved"] += w * (p.get("saved") or 0)
        a["n"] += 1

    rows = []
    for cat, a in agg.items():
        if a["n"] < MIN_POSTS or a["w"] <= 0:
            continue
        avg_views = a["views"] / a["w"]
        avg_shares = a["shares"] / a["w"]
        avg_saved = a["saved"] / a["w"]
        rows.append({
            "category": cat,
            "n": a["n"],
            "avg_views": round(avg_views),
            "avg_shares": round(avg_shares, 1),
            "avg_saved": round(avg_saved, 1),
            "score": round(avg_views + 80 * avg_shares + 40 * avg_saved),
        })
    rows.sort(key=lambda r: -r["score"])
    return rows


def _constraints(used_titles: list[str]) -> tuple[list[str], str]:
    """Bugünkü kullanılmış başlıklardan (sırayla) sert kural metinleri üretir.
    Döner: (kapasitesi dolan kategoriler, ardışık yasak kategori ya da "")"""
    cats_today = [categorize(t) for t in (used_titles or [])]
    capped = []
    counts: dict[str, int] = {}
    for c in cats_today:
        counts[c] = counts.get(c, 0) + 1
    for c, n in counts.items():
        if c != DEFAULT_CAT and n >= DAILY_CAT_CAP:
            capped.append(c)
    consecutive_ban = ""
    if len(cats_today) >= MAX_CONSECUTIVE:
        tail = cats_today[-MAX_CONSECUTIVE:]
        if len(set(tail)) == 1 and tail[0] != DEFAULT_CAT:
            consecutive_ban = tail[0]
    return capped, consecutive_ban


def build_instruction(used_titles: list[str] = None) -> str:
    """DeepSeek konu seçimi için performans + kısıt yönlendirmesi.
    Veri yoksa boş string döner — sistem eskisi gibi çalışır."""
    parts = []

    explore = random.random() < EXPLORE_RATE
    scores = category_scores()
    if scores and not explore:
        top = scores[:4]
        bottom = [r for r in scores[3:] if r["avg_views"] < scores[0]["avg_views"] / 3][-2:]
        rank_txt = "; ".join(
            f"{r['category']} ({_CAT_EN.get(r['category'], '')}): "
            f"avg {r['avg_views']} views, {r['avg_shares']} shares/post"
            for r in top
        )
        parts.append(
            "\nACCOUNT PERFORMANCE DATA (real audience metrics for THIS account, recency-weighted):\n"
            f"Best performing categories: {rank_txt}.\n"
            + ("".join(
                f"Weak category: {r['category']} ({_CAT_EN.get(r['category'], '')}) "
                f"averages only {r['avg_views']} views — pick topics from this category "
                f"ONLY if it is truly major breaking news.\n"
                for r in bottom
            ))
            + "When several trending topics are similarly newsworthy, prefer the "
              "higher-performing category. Do NOT invent or force a topic just to "
              "match a category — the topic must genuinely be in the trending list.\n"
        )
    elif explore and scores:
        print("[ig_perf] explore slot — performans sıralaması prompt'a eklenmedi", flush=True)

    capped, consecutive_ban = _constraints(used_titles or [])
    rules = []
    for c in HARD_EXCLUDE_CATS:
        rules.append(
            f"NEVER pick a {c} ({_CAT_EN.get(c, '')}) topic — celebrity scandals, arrests, "
            f"crimes and personal drama consistently underperform on this account and do not "
            f"fit its news-brand image. Skip these entirely, no exceptions."
        )
    if consecutive_ban:
        rules.append(
            f"The last {MAX_CONSECUTIVE} posts today were all {consecutive_ban} "
            f"({_CAT_EN.get(consecutive_ban, '')}) — you MUST pick a topic from a "
            f"DIFFERENT category now."
        )
    for c in capped:
        if c != consecutive_ban:
            rules.append(
                f"Daily limit reached for category {c} ({_CAT_EN.get(c, '')}) — "
                f"do NOT pick a {c} topic for this post."
            )
    if rules:
        parts.append("\nCATEGORY CONSTRAINTS (hard rules):\n- " + "\n- ".join(rules) + "\n")

    return "".join(parts)


def check_hard_rules(title: str, used_titles: list[str]) -> tuple[bool, str]:
    """Üretilen başlık sert kuralları ihlal ediyor mu? (True, "") = temiz."""
    cat = categorize(title)
    if cat in HARD_EXCLUDE_CATS:
        return False, f"{cat} kategorisi kalıcı olarak dışlandı"
    if cat == DEFAULT_CAT:
        return True, ""
    capped, consecutive_ban = _constraints(used_titles or [])
    if cat == consecutive_ban:
        return False, f"ardışık {MAX_CONSECUTIVE} {cat} sonrası yine {cat}"
    if cat in capped:
        return False, f"{cat} günlük {DAILY_CAT_CAP} post tavanına ulaştı"
    return True, ""
