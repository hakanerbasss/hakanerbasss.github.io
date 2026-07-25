from __future__ import annotations

import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


TARGETED_QUERIES = [
    '"emekli" ödeme when:1d',
    '"emekli maaşı" when:1d',
    '"maaş farkı" when:1d',
    '"SGK" açıklama when:1d',
    '"erken emeklilik" when:1d',
    '"en düşük emekli aylığı" when:1d',
    '"dul ve yetim aylığı" when:1d',
    '"asgari ücret" when:1d',
    '"memur maaşı" when:1d',
    '"hesaplara yatacak" when:1d',
    '"ödeme başladı" when:1d',
    '"son ödeme tarihi" when:1d',
    '"vergi" son tarih when:1d',
    '"doğalgaz" zam when:1d',
    '"elektrik" zam when:1d',
    '"akaryakıt" zam when:1d',
    '"Meteoroloji" uyarı when:1d',
    '"AKOM" uyarı when:1d',
    '"deprem" uyarısı when:1d',
    '"fay haritası" when:1d',
    '"dövizle askerlik" when:2d',
    '"yurt dışı borçlanması" when:2d',
    '"Türkiye’ye araçla giriş" when:2d',
    # Emekli/SGK/maaş dışındaki genel kategoriler — havuz sadece cüzdan/emeklilik
    # haberleriyle sınırlı kalmasın, ÖSYM, ehliyet, eğitim, genel gündem gibi
    # geniş kitleyi ilgilendiren başka güncel konular da havuza girsin.
    '"ehliyet" when:1d',
    '"YKS" when:1d',
    '"ÖSYM" when:1d',
    '"üniversite tercih" when:1d',
    '"MEB" açıklama when:1d',
    '"trafik cezası" when:1d',
    '"Resmi Gazete" when:1d',
    '"TBMM" kabul when:1d',
    '"Bakanlık" açıklama when:1d',
]

WALLET_TERMS = {
    "maaş": 16,
    "emekli": 18,
    "sgk": 18,
    "ödeme": 15,
    "hesaplara": 14,
    "fark ödemesi": 18,
    "zam": 12,
    "ücret": 10,
    "ikramiye": 14,
    "promosyon": 14,
    "tazminat": 15,
    "vergi": 10,
    "prim": 11,
    "destek": 9,
    "indirim": 8,
    "borç": 8,
    "doğalgaz": 9,
    "elektrik": 9,
    "akaryakıt": 9,
    "asgari ücret": 16,
    "memur": 11,
    "işsizlik maaşı": 15,
    "dul ve yetim": 16,
}

SAFETY_TERMS = {
    "deprem": 15,
    "fay": 13,
    "akom": 14,
    "meteoroloji": 12,
    "uyarı": 9,
    "alarm": 7,
    "sel": 10,
    "fırtına": 10,
    "dolu": 9,
    "sıcaklık": 8,
    "soğuk hava": 9,
    "kar yağışı": 9,
}

RIGHTS_TERMS = {
    "erken emeklilik": 18,
    "başvuru": 8,
    "hak sahibi": 10,
    "yürürlüğe girdi": 12,
    "resmi gazete": 13,
    "meclis": 5,
    "son tarih": 13,
    "süre uzatıldı": 13,
    "kimler yararlanabilir": 12,
    "şartları belli oldu": 11,
}

DIASPORA_TERMS = {
    "gurbetçi": 14,
    "yurt dışındaki türkler": 14,
    "almanya'daki türkler": 13,
    "dövizle askerlik": 17,
    "yurt dışı borçlanması": 17,
    "çifte vatandaşlık": 12,
    "konsolosluk": 10,
    "türkiye'ye araçla giriş": 15,
    "yurt dışından araç": 14,
}

LOW_VALUE_TERMS = {
    "açıklamalarda bulundu": -10,
    "görüş alışverişinde bulundu": -14,
    "toplantı gerçekleştirdi": -15,
    "ziyaret etti": -12,
    "mesaj yayımladı": -12,
    "değerlendirmelerde bulundu": -11,
    "iddia edildi": -12,
    "kulis": -14,
    "gündeme gelebilir": -10,
    "masada": -7,
    "analiz": -5,
    "yorum": -5,
    # Parti/politikacı kulis-tarzı haberler gerçek verilerde çok düşük
    # izlenme alıyor (6-50 görüntüleme) — emeklilik/maaş haberlerinin
    # (600-1900) çok altında.
    "partiden istifa": -14,
    "istifa etti": -10,
    "yeni parti kurdu": -10,
    "genel başkan": -6,
}

BLOCK_TERMS = (
    "maç sonucu",
    "transfer",
    "futbolcu",
    "gol attı",
    "magazin",
    "boşandı",
    "aşk yaşıyor",
    "evlilik teklifi",
    "hayatını kaybetti",
    "ölü bulundu",
    "cinayet",
    "gözaltına alındı",
)

TRUSTED_SOURCES = {
    "Sosyal Güvenlik Kurumu": 18,
    "SGK": 18,
    "Resmi Gazete": 18,
    "Türkiye Büyük Millet Meclisi": 17,
    "TBMM": 17,
    "Meteoroloji Genel Müdürlüğü": 17,
    "Gelir İdaresi Başkanlığı": 17,
    "Çalışma ve Sosyal Güvenlik Bakanlığı": 17,
    "Hazine ve Maliye Bakanlığı": 17,
    "Anadolu Ajansı": 15,
    "AA": 15,
    "Reuters": 15,
    "TRT Haber": 12,
    "NTV": 10,
    "BBC Türkçe": 10,
}

def _clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize(value: str) -> str:
    value = value.casefold()
    # Türkçe büyük "İ" harfi casefold() ile "i" + görünmez birleşik nokta
    # karakterine (U+0307) ayrılıyor; bu karakter \w'ye uymadığı için
    # aşağıdaki regex onu boşluğa çevirip kelimenin ortasını bölüyordu
    # (ör. "İstifa" -> "i̇stifa" -> "i stifa"), bu da o kelimeyi içeren
    # terimlerin (örn. "istifa etti") sessizce eşleşmemesine yol açıyordu.
    value = value.replace("̇", "")
    value = re.sub(r"[^\wçğıöşü\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_date(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _freshness_score(published_at: datetime | None) -> int:
    if not published_at:
        return 0

    hours = max(
        0.0,
        (datetime.now(timezone.utc) - published_at).total_seconds() / 3600,
    )

    if hours <= 3:
        return 20
    if hours <= 6:
        return 17
    if hours <= 12:
        return 14
    if hours <= 24:
        return 10
    if hours <= 48:
        return 3
    return -20

def _number_score(title: str) -> int:
    score = 0
    low = _normalize(title)

    if re.search(r"\b\d{1,3}(?:[.\s]\d{3})+\b", title):
        score += 9
    elif re.search(r"\b\d+\b", title):
        score += 5

    if any(x in low for x in ("tl", "lira", "yüzde")) or "%" in title:
        score += 7

    if any(x in low for x in (
        "bugün",
        "yarın",
        "son gün",
        "son tarih",
        "hesaplara yattı",
        "ödemeler başladı",
        "yürürlüğe girdi",
        "belli oldu",
    )):
        score += 8

    return score


def _source_score(source: str) -> int:
    source_low = _normalize(source)
    best = 0

    for name, points in TRUSTED_SOURCES.items():
        if _normalize(name) in source_low:
            best = max(best, points)

    return best

def score_candidate(item: dict[str, Any]) -> tuple[int, list[str]]:
    title = _clean(item.get("title", ""))
    source = _clean(item.get("source", ""))
    low = _normalize(title)

    if not title:
        return -999, ["boş başlık"]

    if any(_normalize(term) in low for term in BLOCK_TERMS):
        return -999, ["yasak veya düşük değerli konu"]

    score = 0
    reasons: list[str] = []

    fresh = _freshness_score(item.get("published_at"))
    score += fresh
    if fresh > 0:
        reasons.append(f"güncellik +{fresh}")

    for terms, label in (
        (WALLET_TERMS, "cebe etkisi"),
        (SAFETY_TERMS, "güvenlik"),
        (RIGHTS_TERMS, "hak ve başvuru"),
        (DIASPORA_TERMS, "gurbetçi"),
    ):
        subtotal = 0

        for term, points in terms.items():
            if _normalize(term) in low:
                subtotal += points

        subtotal = min(subtotal, 35)

        if subtotal:
            score += subtotal
            reasons.append(f"{label} +{subtotal}")

    for term, points in LOW_VALUE_TERMS.items():
        if _normalize(term) in low:
            score += points
            reasons.append(f"soyut veya iddia {points}")

    number_points = _number_score(title)
    if number_points:
        score += number_points
        reasons.append(f"net rakam veya tarih +{number_points}")

    trusted = _source_score(source)
    if trusted:
        score += trusted
        reasons.append(f"kaynak +{trusted}")

    if "emekli" in low and any(
        x in low for x in ("ödeme", "maaş", "zam", "fark")
    ):
        score += 20
        reasons.append("emekli ve para +20")

    if any(
        x in low for x in ("meteoroloji", "akom", "deprem", "fay")
    ) and "uyarı" in low:
        score += 15
        reasons.append("acil uyarı +15")

    if any(
        x in low for x in (
            "kimler yararlanabilir",
            "kimleri kapsıyor",
            "şartları",
        )
    ):
        score += 9
        reasons.append("kişisel uygunluk +9")

    return score, reasons

def _event_key(title: str) -> set[str]:
    stop_words = {
        "ve",
        "ile",
        "için",
        "son",
        "dakika",
        "yeni",
        "bugün",
        "yarın",
        "açıkladı",
        "açıklaması",
        "belli",
        "oldu",
        "geldi",
        "dikkat",
        "kritik",
        "detayları",
        "duyuruldu",
        "gündemde",
        "haber",
    }

    words = {
        word
        for word in _normalize(title).split()
        if len(word) >= 4 and word not in stop_words
    }

    return words


def _is_same_event(title_a: str, title_b: str) -> bool:
    words_a = _event_key(title_a)
    words_b = _event_key(title_b)

    if not words_a or not words_b:
        return False

    shared = words_a & words_b
    smaller_size = min(len(words_a), len(words_b))

    if len(shared) >= 3:
        return True

    if smaller_size > 0 and len(shared) / smaller_size >= 0.65:
        return True

    return False


def _fetch_query(
    query: str,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=tr&gl=TR&ceid=TR:tr"
    )

    try:
        response = httpx.get(
            url,
            timeout=12,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            },
        )

        response.raise_for_status()
        root = ET.fromstring(response.text)

        results: list[dict[str, Any]] = []

        for item in root.findall(".//item")[:max_items]:
            raw_title = _clean(item.findtext("title", ""))
            link = _clean(item.findtext("link", ""))
            pub_date = _clean(item.findtext("pubDate", ""))
            description = _clean(item.findtext("description", ""))

            source_element = item.find("source")
            source = ""

            if source_element is not None and source_element.text:
                source = _clean(source_element.text)

            title = raw_title

            # Google News çoğu başlığın sonuna kaynak adını ekliyor.
            if " - " in title:
                possible_title, possible_source = title.rsplit(" - ", 1)

                if not source:
                    source = possible_source.strip()

                title = possible_title.strip()

            if not title:
                continue

            published_at = _parse_date(pub_date)

            results.append({
                "title": title,
                "source": source,
                "link": link,
                "description": description[:500],
                "published_at": published_at,
                "query": query,
            })

        return results

    except Exception as error:
        print(
            f"[news-ranker] sorgu hatası: {query} | {error}",
            flush=True,
        )
        return []


def _deduplicate_exact(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []

    seen_titles: set[str] = set()
    seen_links: set[str] = set()

    for item in items:
        title_key = _normalize(item.get("title", ""))
        link_key = item.get("link", "").strip()

        if not title_key:
            continue

        if title_key in seen_titles:
            continue

        if link_key and link_key in seen_links:
            continue

        seen_titles.add(title_key)

        if link_key:
            seen_links.add(link_key)

        unique.append(item)

    return unique

def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    raw_items: list[dict[str, Any]] = []

    # İlk keşif katmanı: Google News üzerinde hedefli sorgular.
    # Sonraki adımda resmî kurum ve haber RSS kaynakları da buraya eklenecek.
    for query in TARGETED_QUERIES:
        raw_items.extend(
            _fetch_query(
                query=query,
                max_items=per_query,
            )
        )

    unique_items = _deduplicate_exact(raw_items)

    scored_items: list[dict[str, Any]] = []

    for item in unique_items:
        score, reasons = score_candidate(item)

        item["score"] = score
        item["reasons"] = reasons
        item["confirming_sources"] = []

        if item.get("source"):
            item["confirming_sources"].append(item["source"])

        scored_items.append(item)

    scored_items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []

    for item in scored_items:
        if item.get("score", -999) < 12:
            continue

        matching_event = None

        for existing in selected:
            if _is_same_event(
                existing.get("title", ""),
                item.get("title", ""),
            ):
                matching_event = existing
                break

        if matching_event:
            source = item.get("source", "")

            if (
                source
                and source
                not in matching_event["confirming_sources"]
            ):
                matching_event["confirming_sources"].append(source)
                matching_event["score"] += 4
                matching_event["reasons"].append(
                    "başka kaynakta da yayımlandı +4"
                )

            continue

        selected.append(item)

        if len(selected) >= max_candidates:
            break

    selected.sort(
        key=lambda item: item.get("score", -999),
        reverse=True,
    )

    return selected


def format_candidates_for_prompt(
    candidates: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    for index, item in enumerate(candidates, start=1):
        published_at = item.get("published_at")

        if published_at:
            published_text = published_at.astimezone(
                timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
        else:
            published_text = "yayın tarihi alınamadı"

        sources = ", ".join(
            item.get("confirming_sources", [])
        )

        if not sources:
            sources = item.get("source", "") or "kaynak bilinmiyor"

        reasons = ", ".join(
            item.get("reasons", [])[:6]
        )

        lines.append(
            f"{index}. "
            f"PUAN={item.get('score')} | "
            f"BAŞLIK={item.get('title')} | "
            f"KAYNAK={sources} | "
            f"YAYIN={published_text} | "
            f"NEDEN={reasons}"
        )

    return "\n".join(lines)

OFFICIAL_FEEDS = [
    {
        "name": "Sosyal Güvenlik Kurumu",
        "url": "https://www.sgk.gov.tr/rss",
        "bonus": 20,
    },
]


def _find_feed_items(root: ET.Element) -> list[ET.Element]:
    items = root.findall(".//item")

    if items:
        return items

    # Atom formatındaki akışlar için yedek yöntem.
    return root.findall(".//{http://www.w3.org/2005/Atom}entry")


def _first_text(
    node: ET.Element,
    paths: tuple[str, ...],
) -> str:
    for path in paths:
        value = node.findtext(path)

        if value:
            return _clean(value)

    return ""


def _fetch_rss_feed(
    feed_name: str,
    feed_url: str,
    source_bonus: int = 15,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    try:
        response = httpx.get(
            feed_url,
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64)"
                )
            },
        )

        response.raise_for_status()
        root = ET.fromstring(response.text)

        results: list[dict[str, Any]] = []

        for node in _find_feed_items(root)[:max_items]:
            title = _first_text(
                node,
                (
                    "title",
                    "{http://www.w3.org/2005/Atom}title",
                ),
            )

            description = _first_text(
                node,
                (
                    "description",
                    "summary",
                    "{http://www.w3.org/2005/Atom}summary",
                    "{http://www.w3.org/2005/Atom}content",
                ),
            )

            published_raw = _first_text(
                node,
                (
                    "pubDate",
                    "published",
                    "updated",
                    "{http://www.w3.org/2005/Atom}published",
                    "{http://www.w3.org/2005/Atom}updated",
                ),
            )

            link = _first_text(node, ("link",))

            # Atom linkleri metin değil href niteliği taşıyabilir.
            if not link:
                atom_link = node.find(
                    "{http://www.w3.org/2005/Atom}link"
                )

                if atom_link is not None:
                    link = _clean(atom_link.attrib.get("href", ""))

            if not title:
                continue

            published_at = _parse_date(published_raw)

            score, reasons = score_candidate({
                "title": title,
                "source": feed_name,
                "published_at": published_at,
            })

            score += source_bonus
            reasons.append(
                f"doğrudan resmî kurum +{source_bonus}"
            )

            results.append({
                "title": title,
                "source": feed_name,
                "link": link,
                "description": description[:700],
                "published_at": published_at,
                "query": f"official:{feed_name}",
                "score": score,
                "reasons": reasons,
                "confirming_sources": [feed_name],
                "is_official": True,
            })

        return results

    except Exception as error:
        print(
            f"[news-ranker] resmî kaynak hatası: "
            f"{feed_name} | {feed_url} | {error}",
            flush=True,
        )
        return []


def fetch_official_news(
    max_items_per_feed: int = 20,
) -> list[dict[str, Any]]:
    official_items: list[dict[str, Any]] = []

    for feed in OFFICIAL_FEEDS:
        official_items.extend(
            _fetch_rss_feed(
                feed_name=feed["name"],
                feed_url=feed["url"],
                source_bonus=feed.get("bonus", 15),
                max_items=max_items_per_feed,
            )
        )

    return official_items

SGK_OFFICIAL_PAGES = [
    {
        "name": "Sosyal Güvenlik Kurumu Haberler",
        "url": "https://www.sgk.gov.tr/haber",
        "bonus": 20,
    },
    {
        "name": "Sosyal Güvenlik Kurumu Duyurular",
        "url": "https://www.sgk.gov.tr/duyuru",
        "bonus": 22,
    },
]


def _fetch_official_html_page(
    page_name: str,
    page_url: str,
    source_bonus: int = 20,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    try:
        response = httpx.get(
            page_url,
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            },
        )

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        candidates: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        seen_titles: set[str] = set()

        for link_element in soup.find_all("a", href=True):
            title = _clean(
                link_element.get_text(" ", strip=True)
            )

            href = urljoin(
                page_url,
                link_element.get("href", ""),
            )

            if not title or len(title) < 12:
                continue

            title_low = _normalize(title)
            href_low = href.casefold()

            # Menü, sosyal medya ve genel sayfa bağlantılarını ele.
            if any(
                blocked in href_low
                for blocked in (
                    "javascript:",
                    "facebook.com",
                    "twitter.com",
                    "instagram.com",
                    "youtube.com",
                    "/iletisim",
                    "/kurumsal",
                    "/mevzuat",
                    "/arama",
                    "#",
                )
            ):
                continue

            # SGK haber veya duyuru detay bağlantısı olmalı.
            if (
                "/haber/" not in href_low
                and "/duyuru/" not in href_low
                and "/haber?" not in href_low
                and "/duyuru?" not in href_low
            ):
                continue

            title_key = _normalize(title)

            if title_key in seen_titles:
                continue

            if href in seen_links:
                continue

            seen_titles.add(title_key)
            seen_links.add(href)

            parent_text = ""
            parent = link_element.parent

            if parent is not None:
                parent_text = _clean(
                    parent.get_text(" ", strip=True)
                )

            date_match = re.search(
                r"\b([0-3]?\d[./-][01]?\d[./-]20\d{2})\b",
                parent_text,
            )

            published_at = None

            if date_match:
                raw_date = date_match.group(1)

                for date_format in (
                    "%d.%m.%Y",
                    "%d/%m/%Y",
                    "%d-%m-%Y",
                ):
                    try:
                        parsed = datetime.strptime(
                            raw_date,
                            date_format,
                        )
                        published_at = parsed.replace(
                            tzinfo=timezone.utc
                        )
                        break
                    except ValueError:
                        continue

            score, reasons = score_candidate({
                "title": title,
                "source": page_name,
                "published_at": published_at,
            })

            score += source_bonus
            reasons.append(
                f"doğrudan resmî kurum +{source_bonus}"
            )

            candidates.append({
                "title": title,
                "source": page_name,
                "link": href,
                "description": parent_text[:700],
                "published_at": published_at,
                "query": f"official-html:{page_name}",
                "score": score,
                "reasons": reasons,
                "confirming_sources": [page_name],
                "is_official": True,
            })

            if len(candidates) >= max_items:
                break

        return candidates

    except Exception as error:
        print(
            f"[news-ranker] resmî HTML sayfası hatası: "
            f"{page_name} | {page_url} | {error}",
            flush=True,
        )
        return []


# Önceki RSS tabanlı fonksiyonun yerine geçer.
def fetch_official_news(
    max_items_per_feed: int = 20,
) -> list[dict[str, Any]]:
    official_items: list[dict[str, Any]] = []

    for page in SGK_OFFICIAL_PAGES:
        official_items.extend(
            _fetch_official_html_page(
                page_name=page["name"],
                page_url=page["url"],
                source_bonus=page.get("bonus", 20),
                max_items=max_items_per_feed,
            )
        )

    official_items.sort(
        key=lambda item: item.get("score", -999),
        reverse=True,
    )

    return official_items

def _title_and_date_from_sgk_url(url: str) -> tuple[str, datetime | None]:
    """
    Örnek URL:
    /haber/detay/SGK-Baskani-Elitastan-15-Temmuz-...-2026-07-17-07-44-41
    """
    from urllib.parse import unquote

    slug = unquote(url.rstrip("/").split("/")[-1])

    date_match = re.search(
        r"-(20\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})$",
        slug,
    )

    published_at = None

    if date_match:
        year, month, day, hour, minute, second = map(
            int,
            date_match.groups(),
        )

        try:
            published_at = datetime(
                year,
                month,
                day,
                hour,
                minute,
                second,
                tzinfo=timezone.utc,
            )
        except ValueError:
            published_at = None

        slug = slug[:date_match.start()]

    title = slug.replace("-", " ")
    title = re.sub(r"\s+", " ", title).strip()

    return title, published_at


def _fetch_official_html_page(
    page_name: str,
    page_url: str,
    source_bonus: int = 20,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    try:
        response = httpx.get(
            page_url,
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36"
                )
            },
        )

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        candidates: list[dict[str, Any]] = []
        seen_links: set[str] = set()

        for link_element in soup.find_all("a", href=True):
            href = urljoin(
                page_url,
                link_element.get("href", ""),
            )

            href_low = href.casefold()

            # Sadece gerçek haber veya duyuru detay sayfaları.
            if (
                "/haber/detay/" not in href_low
                and "/duyuru/detay/" not in href_low
            ):
                continue

            if href in seen_links:
                continue

            seen_links.add(href)

            visible_title = _clean(
                link_element.get_text(" ", strip=True)
            )

            url_title, published_at = _title_and_date_from_sgk_url(
                href
            )

            # "Devamını Oku" gibi kart butonlarını başlık olarak kullanma.
            if (
                not visible_title
                or len(visible_title) < 12
                or _normalize(visible_title) in {
                    "devamını oku",
                    "detay",
                    "incele",
                    "tıklayınız",
                }
            ):
                title = url_title
            else:
                title = visible_title

            # URL’den çıkan başlık daha açıklayıcıysa onu tercih et.
            if len(url_title) > len(title) + 8:
                title = url_title

            if not title or len(title) < 15:
                continue

            score, reasons = score_candidate({
                "title": title,
                "source": page_name,
                "published_at": published_at,
            })

            score += source_bonus
            reasons.append(
                f"doğrudan resmî kurum +{source_bonus}"
            )

            candidates.append({
                "title": title,
                "source": page_name,
                "link": href,
                "description": "",
                "published_at": published_at,
                "query": f"official-html:{page_name}",
                "score": score,
                "reasons": reasons,
                "confirming_sources": [page_name],
                "is_official": True,
            })

            if len(candidates) >= max_items:
                break

        return candidates

    except Exception as error:
        print(
            f"[news-ranker] resmî HTML sayfası hatası: "
            f"{page_name} | {page_url} | {error}",
            flush=True,
        )
        return []

# Önceki sürümün üzerine yazılır:
# Resmî kaynaklardan yalnızca son 48 saat içindeki içerikleri kabul eder.
def fetch_official_news(
    max_items_per_feed: int = 20,
    max_age_hours: int = 48,
) -> list[dict[str, Any]]:
    official_items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for page in SGK_OFFICIAL_PAGES:
        page_items = _fetch_official_html_page(
            page_name=page["name"],
            page_url=page["url"],
            source_bonus=page.get("bonus", 20),
            max_items=max_items_per_feed,
        )

        for item in page_items:
            published_at = item.get("published_at")

            # Tarihi belirlenemeyen resmî içerikleri otomatik havuza alma.
            if published_at is None:
                continue

            age_hours = (
                now - published_at
            ).total_seconds() / 3600

            if age_hours < 0:
                # Sunucu veya kaynak saat farkı nedeniyle küçük gelecek
                # tarihleri olabilir; sıfır kabul edilir.
                age_hours = 0

            if age_hours > max_age_hours:
                continue

            item["age_hours"] = round(age_hours, 1)
            official_items.append(item)

    official_items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return official_items

# Önceki build_ranked_news_pool fonksiyonunun üzerine yazılır.
# Google News adayları ile güncel resmî kurum içeriklerini aynı havuzda birleştirir.
def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    raw_items: list[dict[str, Any]] = []

    # 1. Hedefli Google News sorguları — paralel çalıştırılıyor. Sıralı halde
    # 32 sorgu × 12sn timeout ile en kötü durumda 6+ dakika sürebiliyordu ve
    # "Telegram'a test gönder" çok geç geliyor/hiç gelmiyor şikayetinin asıl
    # sebebi buydu (DeepSeek değil, bu RSS çekme adımı).
    with ThreadPoolExecutor(max_workers=min(10, len(TARGETED_QUERIES))) as executor:
        futures = [
            executor.submit(_fetch_query, query=query, max_items=per_query)
            for query in TARGETED_QUERIES
        ]
        for future in futures:
            raw_items.extend(future.result())

    # 2. Son 48 saatteki resmî SGK haber ve duyuruları
    official_items = fetch_official_news(
        max_items_per_feed=30,
        max_age_hours=48,
    )

    raw_items.extend(official_items)

    unique_items = _deduplicate_exact(raw_items)
    scored_items: list[dict[str, Any]] = []

    for item in unique_items:
        # Resmî içerikler daha önce puanlandı.
        if item.get("is_official") and "score" in item:
            score = item["score"]
            reasons = item.get("reasons", [])
        else:
            score, reasons = score_candidate(item)

        item["score"] = score
        item["reasons"] = reasons

        if not item.get("confirming_sources"):
            item["confirming_sources"] = []

        source = item.get("source", "")

        if source and source not in item["confirming_sources"]:
            item["confirming_sources"].append(source)

        scored_items.append(item)

    scored_items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []

    for item in scored_items:
        if item.get("score", -999) < 12:
            continue

        matching_event = None

        for existing in selected:
            if _is_same_event(
                existing.get("title", ""),
                item.get("title", ""),
            ):
                matching_event = existing
                break

        if matching_event:
            source = item.get("source", "")

            if (
                source
                and source
                not in matching_event["confirming_sources"]
            ):
                matching_event["confirming_sources"].append(source)
                matching_event["score"] += 4
                matching_event["reasons"].append(
                    "başka kaynakta da yayımlandı +4"
                )

            # Aynı olayın resmî kaynağı varsa resmî bağlantıyı tercih et.
            if item.get("is_official") and not matching_event.get("is_official"):
                matching_event["link"] = item.get("link", matching_event.get("link"))
                matching_event["source"] = item.get("source", matching_event.get("source"))
                matching_event["is_official"] = True
                matching_event["score"] += 8
                matching_event["reasons"].append(
                    "resmî kaynakla doğrulandı +8"
                )

            continue

        selected.append(item)

        if len(selected) >= max_candidates:
            break

    selected.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return selected

SPECULATIVE_TERMS = (
    "ne zaman çıkacak",
    "çıkacak mı",
    "meclis'ten geçti mi",
    "meclisten geçti mi",
    "kesinleşti mi",
    "son durum gelişmeleri",
    "gündemde mi",
    "olacak mı",
    "şartları ne",
    "bekleniyor",
    "iddiası",
)

SEO_REPEAT_TERMS = (
    "özgün haberler",
    "son durum",
    "işte en güncel",
    "merak ediliyor",
    "araştırılıyor",
    "sorgulama ekranı",
)


def _credibility_penalty(item: dict[str, Any]) -> tuple[int, list[str]]:
    title = _normalize(item.get("title", ""))
    source = _normalize(item.get("source", ""))
    penalty = 0
    reasons: list[str] = []

    speculative_count = sum(
        1 for term in SPECULATIVE_TERMS
        if _normalize(term) in title
    )

    if speculative_count:
        points = min(30, speculative_count * 10)
        penalty -= points
        reasons.append(f"belirsiz veya soru haberi -{points}")

    if any(_normalize(term) in title for term in SEO_REPEAT_TERMS):
        penalty -= 12
        reasons.append("SEO tekrar haberi -12")

    # Erken emeklilikte resmî karar yoksa güçlü ceza.
    if "erken emeklilik" in title:
        official_markers = (
            "sosyal güvenlik kurumu",
            "sgk",
            "resmi gazete",
            "tbmm",
            "türkiye büyük millet meclisi",
            "çalışma ve sosyal güvenlik bakanlığı",
        )

        trusted_source = any(
            marker in source for marker in official_markers
        )

        confirmed_language = any(
            phrase in title
            for phrase in (
                "yürürlüğe girdi",
                "resmi gazetede yayımlandı",
                "kanun kabul edildi",
                "sgk duyurdu",
            )
        )

        if not trusted_source and not confirmed_language:
            penalty -= 25
            reasons.append("erken emeklilik resmî değil -25")

    # Soru işaretli para haberlerinde kesinlik riski.
    if "?" in item.get("title", ""):
        penalty -= 5
        reasons.append("soru başlığı -5")

    return penalty, reasons


# Önceki score_candidate fonksiyonunun üzerine yazılır.
_original_score_candidate = score_candidate


def score_candidate(
    item: dict[str, Any],
) -> tuple[int, list[str]]:
    score, reasons = _original_score_candidate(item)

    if score <= -900:
        return score, reasons

    penalty, penalty_reasons = _credibility_penalty(item)
    score += penalty
    reasons.extend(penalty_reasons)

    return score, reasons

def _apply_source_confirmation_bonus(
    item: dict[str, Any],
) -> None:
    sources = list(dict.fromkeys(
        item.get("confirming_sources", [])
    ))

    item["confirming_sources"] = sources

    # En fazla 3 ek kaynak puanlansın.
    extra_source_count = max(0, len(sources) - 1)
    capped_count = min(extra_source_count, 3)
    bonus = capped_count * 4

    # Eski sınırsız bonusları temizle.
    cleaned_reasons = [
        reason
        for reason in item.get("reasons", [])
        if "başka kaynakta da yayımlandı" not in reason
    ]

    item["reasons"] = cleaned_reasons

    if bonus:
        item["score"] += bonus
        item["reasons"].append(
            f"çoklu kaynak doğrulaması +{bonus}"
        )


# Önceki build_ranked_news_pool fonksiyonunun üzerine yazılır.
_previous_build_ranked_news_pool = build_ranked_news_pool


def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    items = _previous_build_ranked_news_pool(
        max_candidates=max_candidates,
        per_query=per_query,
    )

    for item in items:
        # Eski fonksiyon her kaynak için +4 eklemiş olabilir.
        old_bonus_count = sum(
            1
            for reason in item.get("reasons", [])
            if "başka kaynakta da yayımlandı" in reason
        )

        if old_bonus_count:
            item["score"] -= old_bonus_count * 4

        _apply_source_confirmation_bonus(item)

    items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return items[:max_candidates]

REPETITIVE_PAYMENT_TERMS = (
    "ne zaman yatacak",
    "ne zaman hesaplara geçecek",
    "hangi tarihte ödenecek",
    "ödemeler ne zaman",
    "maaş farkı ne zaman",
)

UNCONFIRMED_WAGE_TERMS = (
    "ara zam gelecek mi",
    "zam kesinleşti mi",
    "ne kadar olacak",
    "netleşiyor",
    "masada",
)

FOREIGN_IRRELEVANT_SOURCES = (
    "vietnam.vn",
)

OFFICIAL_CONFIRMATION_MARKERS = (
    "sosyal güvenlik kurumu",
    "sgk",
    "resmi gazete",
    "türkiye büyük millet meclisi",
    "tbmm",
    "çalışma ve sosyal güvenlik bakanlığı",
    "hazine ve maliye bakanlığı",
    "gelir idaresi başkanlığı",
)


def _financial_reliability_penalty(
    item: dict[str, Any],
) -> tuple[int, list[str]]:
    title_raw = item.get("title", "")
    title = _normalize(title_raw)
    source = _normalize(item.get("source", ""))

    confirming_sources = " ".join(
        _normalize(source_name)
        for source_name in item.get("confirming_sources", [])
    )

    penalty = 0
    reasons: list[str] = []

    is_official = bool(item.get("is_official"))

    has_official_confirmation = (
        is_official
        or any(
            marker in source or marker in confirming_sources
            for marker in OFFICIAL_CONFIRMATION_MARKERS
        )
    )

    is_wallet_news = any(
        term in title
        for term in (
            "emekli",
            "maaş",
            "ödeme",
            "zam",
            "asgari ücret",
            "ikramiye",
            "promosyon",
            "tazminat",
        )
    )

    has_money_amount = bool(
        re.search(
            r"\b\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?\s*(?:tl|lira)?\b",
            title_raw.casefold(),
        )
    )

    if (
        is_wallet_news
        and has_money_amount
        and not has_official_confirmation
    ):
        penalty -= 25
        reasons.append("rakam resmî kaynakla doğrulanmadı -25")

    if any(
        _normalize(term) in title
        for term in REPETITIVE_PAYMENT_TERMS
    ):
        penalty -= 18
        reasons.append("tekrar ödeme tarihi haberi -18")

    if any(
        _normalize(term) in title
        for term in UNCONFIRMED_WAGE_TERMS
    ):
        penalty -= 18
        reasons.append("kesinleşmemiş ücret haberi -18")

    # Temmuz ve sonrasında 5 aylık enflasyon üzerinden hazırlanan
    # maaş haberleri güncel sonuç haberi değildir.
    current_month = datetime.now(timezone.utc).month

    if current_month >= 7 and "5 aylık enflasyon" in title:
        penalty -= 30
        reasons.append("eski enflasyon hesabı -30")

    if any(
        bad_source in source
        for bad_source in FOREIGN_IRRELEVANT_SOURCES
    ):
        penalty -= 80
        reasons.append("Türkiye hedef kitlesiyle ilgisiz kaynak -80")

    # Yabancı ülkeye ait asgari ücret haberi, Türkiye açıkça
    # belirtilmiyorsa otomatik havuza girmesin.
    if (
        "asgari ücret" in title
        and any(
            country in title
            for country in (
                "vietnam",
                "almanya",
                "fransa",
                "amerika",
                "japonya",
                "ingiltere",
            )
        )
        and "türkiye" not in title
    ):
        penalty -= 60
        reasons.append("Türkiye dışı ücret haberi -60")

    return penalty, reasons


_previous_score_candidate_v2 = score_candidate


def score_candidate(
    item: dict[str, Any],
) -> tuple[int, list[str]]:
    score, reasons = _previous_score_candidate_v2(item)

    if score <= -900:
        return score, reasons

    penalty, penalty_reasons = _financial_reliability_penalty(item)

    score += penalty
    reasons.extend(penalty_reasons)

    return score, reasons


_previous_build_ranked_news_pool_v2 = build_ranked_news_pool


def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    items = _previous_build_ranked_news_pool_v2(
        max_candidates=max_candidates,
        per_query=per_query,
    )

    # Önceki fonksiyon bazı adayları eski score_candidate ile
    # puanlamış olabilir. Son güvenilirlik kapısını burada tekrar uygula.
    for item in items:
        penalty, penalty_reasons = _financial_reliability_penalty(item)

        already_applied = any(
            reason in item.get("reasons", [])
            for reason in penalty_reasons
        )

        if penalty and not already_applied:
            item["score"] += penalty
            item["reasons"].extend(penalty_reasons)

    items = [
        item
        for item in items
        if item.get("score", -999) >= 12
    ]

    items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return items[:max_candidates]

PROTOCOL_TERMS = (
    "ziyaret etti",
    "ziyarette bulundu",
    "kabul etti",
    "bir araya geldi",
    "toplantı yaptı",
    "heyeti ağırladı",
    "mesaj yayımladı",
    "başkanı elitaş",
    "başkani elitas",
)

PAYMENT_QUESTION_TERMS = (
    "ne zaman yatacak",
    "ne zaman yatırılacak",
    "ne zaman ödenecek",
    "ne zaman hesaplara geçecek",
    "hangi tarihte ödenecek",
    "ödeme tarihi belli mi",
)

FALSE_CERTAINTY_TERMS = (
    "ödeme tarihi netleşti",
    "tarih kesinleşti",
    "hesaplara yatıyor",
    "ödemeler başladı",
)

FOREIGN_SOURCE_MARKERS = (
    "vietnam vn",
    "vietnam.vn",
)

LOCAL_BREAKING_TERMS = (
    "akom",
    "meteoroloji",
    "istanbul",
    "trakyа",
    "sağanak",
    "fırtına",
    "sel",
)


def _final_candidate_penalty(
    item: dict[str, Any],
) -> tuple[int, list[str]]:
    title = _normalize(item.get("title", ""))
    source = _normalize(item.get("source", ""))

    penalty = 0
    reasons: list[str] = []

    # Resmî olması tek başına haber değeri oluşturmaz.
    if any(_normalize(term) in title for term in PROTOCOL_TERMS):
        penalty -= 45
        reasons.append("protokol ve ziyaret haberi -45")

    has_payment_question = any(
        _normalize(term) in title
        for term in PAYMENT_QUESTION_TERMS
    )

    has_false_certainty = any(
        _normalize(term) in title
        for term in FALSE_CERTAINTY_TERMS
    )

    if has_payment_question:
        penalty -= 18
        reasons.append("ödeme tarihi soru haberi -18")

    # Başlık aynı anda hem kesinleşti diyor hem soru soruyorsa güvenilmez.
    if has_payment_question and has_false_certainty:
        penalty -= 30
        reasons.append("başlık kendi içinde çelişkili -30")

    if any(marker in source for marker in FOREIGN_SOURCE_MARKERS):
        penalty -= 100
        reasons.append("Türkiye dışı ve ilgisiz kaynak -100")

    # Türkiye açıkça geçmeyen yabancı ücret haberlerini engelle.
    if (
        "asgari ücret" in title
        and "türkiye" not in title
        and any(
            marker in title or marker in source
            for marker in (
                "vietnam",
                "almanya",
                "fransa",
                "japonya",
                "amerika",
                "ingiltere",
            )
        )
    ):
        penalty -= 80
        reasons.append("Türkiye dışı ücret gelişmesi -80")

    # Yerel hava haberi gerçekten bugünkü hayatı etkiliyorsa küçük destek.
    if (
        any(term in title for term in LOCAL_BREAKING_TERMS)
        and any(term in title for term in ("uyarı", "bu akşam", "saatli"))
    ):
        penalty += 8
        reasons.append("bugünkü yerel acil gelişme +8")

    return penalty, reasons


_previous_build_ranked_news_pool_v3 = build_ranked_news_pool


def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    items = _previous_build_ranked_news_pool_v3(
        max_candidates=max_candidates,
        per_query=per_query,
    )

    final_items: list[dict[str, Any]] = []

    for item in items:
        penalty, reasons = _final_candidate_penalty(item)

        item["score"] = item.get("score", -999) + penalty
        item.setdefault("reasons", []).extend(reasons)

        if item["score"] >= 12:
            final_items.append(item)

    final_items.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return final_items[:max_candidates]

CLICKBAIT_PAYMENT_TERMS = (
    "çifte değil üçlü ödeme",
    "üçlü ödeme",
    "müjde",
    "hesaplara para yağacak",
    "cepleri dolacak",
    "servet değerinde ödeme",
)

TURKEY_LOCAL_MARKERS = (
    "istanbul",
    "ankara",
    "izmir",
    "trakyа",
    "trakya",
    "türkiye",
    "akom",
    "afad",
)


def _last_quality_gate(
    item: dict[str, Any],
) -> tuple[int, list[str]]:
    title = _normalize(item.get("title", ""))
    source = _normalize(item.get("source", ""))

    penalty = 0
    reasons: list[str] = []

    # Yerel acil durum bonusu yalnızca Türkiye bağlantısı varsa geçerli olsun.
    has_local_bonus = any(
        "bugünkü yerel acil gelişme" in reason
        for reason in item.get("reasons", [])
    )

    has_turkey_context = any(
        marker in title or marker in source
        for marker in TURKEY_LOCAL_MARKERS
    )

    if has_local_bonus and not has_turkey_context:
        penalty -= 8
        reasons.append("Türkiye ile ilgisiz yerel bonus geri alındı -8")

    # Abartılı ödeme başlıkları resmî doğrulama yoksa aşağı düşsün.
    if any(
        _normalize(term) in title
        for term in CLICKBAIT_PAYMENT_TERMS
    ):
        if not item.get("is_official"):
            penalty -= 35
            reasons.append("doğrulanmamış clickbait ödeme başlığı -35")

    # Şehir adıyla daraltılmış emekli ödeme haberlerinde resmî kaynak yoksa ceza.
    if (
        "emekli" in title
        and "ödeme" in title
        and any(
            city in title
            for city in (
                "vanlı",
                "adanalı",
                "bursalı",
                "izmirli",
                "ankaralı",
                "istanbullu",
            )
        )
        and not item.get("is_official")
    ):
        penalty -= 20
        reasons.append("yerel ve doğrulanmamış ödeme haberi -20")

    return penalty, reasons


_previous_build_ranked_news_pool_v4 = build_ranked_news_pool


def build_ranked_news_pool(
    max_candidates: int = 20,
    per_query: int = 6,
) -> list[dict[str, Any]]:
    items = _previous_build_ranked_news_pool_v4(
        max_candidates=max_candidates,
        per_query=per_query,
    )

    cleaned: list[dict[str, Any]] = []

    for item in items:
        penalty, reasons = _last_quality_gate(item)

        item["score"] = item.get("score", -999) + penalty
        item.setdefault("reasons", []).extend(reasons)

        if item["score"] >= 12:
            cleaned.append(item)

    cleaned.sort(
        key=lambda item: (
            item.get("score", -999),
            item.get("published_at")
            or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )

    return cleaned[:max_candidates]


# ═══════════════════════════════════════════════════════════════════════
# AI JÜRİSİ — kural tabanlı sıralamanın ÜSTÜNE eklenen ikinci katman.
#
# Kod kendi kendini değiştirmez; AI yalnızca aday değerlendirir, son karar
# ve sınırlar bu dosyadaki Python kodunda kalır. Herhangi bir AI çağrısı
# hata/timeout/bozuk JSON verirse run_ai_jury() sessizce kural tabanlı
# sıralamaya döner — çağıran taraf (app.py) hiçbir şey yapmasa bile akış
# durmaz.
# ═══════════════════════════════════════════════════════════════════════

AI_JURY_CACHE_FILE = Path("ai_jury_cache.json")
AI_JURY_CACHE_TTL_HOURS = 18

# AI alt puanlarının (0-100) kural puanı ölçeğine katkısı. Ağırlıklar ve
# ölçek okunabilir sabitler olarak tutuluyor, ileride kolayca ayarlanabilir.
_AI_SCALE = 30
_AI_WEIGHT_CONCRETE = 0.30
_AI_WEIGHT_VERIFIABILITY = 0.15
_AI_WEIGHT_AUDIENCE = 0.20
_AI_WEIGHT_WALLET_RIGHTS = 0.20
_AI_WEIGHT_URGENCY = 0.10
_AI_PENALTY_CLICKBAIT = 0.35
_AI_PENALTY_DUPLICATE = 0.30

# Sert eleme eşikleri — yüksek ilgi puanı olsa bile bunlardan biri
# doğruysa haber listeye alınmaz.
_AI_CLICKBAIT_HARD_LIMIT = 75
_AI_CONCRETE_HARD_FLOOR = 20


def _ai_jury_extract_json(text: str) -> Any:
    """LLM yanıtından JSON dizisini veya nesnesini güvenilir şekilde çıkarır."""
    t = (text or "").strip()

    if "```json" in t:
        t = t.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in t:
        t = t.split("```", 1)[1].split("```", 1)[0]

    t = t.strip()

    start_obj = t.find("{")
    start_arr = t.find("[")

    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        start, end = start_arr, t.rfind("]") + 1
    else:
        start, end = start_obj, t.rfind("}") + 1

    if start >= 0 and end > start:
        t = t[start:end]

    t = re.sub(r",\s*([}\]])", r"\1", t)
    t = re.sub(r"(?<!\\)\n", " ", t)
    t = re.sub(r"(?<!\\)\r", "", t)

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        t2 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", t)
        return json.loads(t2)


def _ai_jury_cache_key(item: dict) -> str:
    base = _normalize(item.get("title", "")) + "|" + (item.get("link", "") or "").strip()[:150]
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _load_ai_jury_cache() -> dict:
    if not AI_JURY_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(AI_JURY_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_ai_jury_cache(cache: dict) -> None:
    # Süresi geçmiş kayıtları temizleyerek dosyanın sınırsız büyümesini önle.
    cutoff = time.time() - AI_JURY_CACHE_TTL_HOURS * 3600
    pruned = {k: v for k, v in cache.items() if v.get("ts", 0) > cutoff}
    try:
        AI_JURY_CACHE_FILE.write_text(json.dumps(pruned, ensure_ascii=False))
    except Exception as error:
        print(f"[ai-jury] cache yazılamadı: {error}", flush=True)


def _ai_jury_assign_clusters(candidates: list[dict]) -> list[int]:
    """Aynı olayı anlatan adaylara aynı küme numarasını verir (mevcut
    _is_same_event mantığını kullanır) — AI'ya olası tekrarları işaret
    etmek için, kesin dedup kararı yine AI/turnuva aşamasında verilir."""
    cluster_ids = [-1] * len(candidates)
    next_id = 0

    for i, item in enumerate(candidates):
        if cluster_ids[i] != -1:
            continue

        cluster_ids[i] = next_id

        for j in range(i + 1, len(candidates)):
            if cluster_ids[j] != -1:
                continue
            if _is_same_event(item.get("title", ""), candidates[j].get("title", "")):
                cluster_ids[j] = next_id

        next_id += 1

    return cluster_ids


_AI_JURY_STAGE2_RULES = """SEN BİR HABER JÜRİSİSİN. Hedef kitle: Türkiye'de 45 yaş üstü ağırlıklı,
kadın çoğunluklu geniş bir Instagram/YouTube Shorts kitlesi. Aşağıdaki haber adaylarını bu kitle
için değerlendir.

KATEGORİ ÖNCELİĞİ (zorunlu sınır değil, ilk taramada uygun aday yoksa kısıtı kaldır):
1. Emeklilik/SGK/SSK/Bağ-Kur, maaş, zam farkı, ödeme tarihi, prim, erken/malulen emeklilik,
   e-Devlet, sosyal destekler
2. Deprem, diri fay, Meteoroloji/AKOM uyarıları, sel, dolu, fırtına, sıcaklık — geniş bölgeyi
   etkileyen resmi afet/hava uyarıları
3. Trafik kuralları/cezaları, akaryakıt, vergi, banka, elektrik-doğalgaz, tüketici hakları,
   noter, ulaşım — milyonların cebine veya hakkına doğrudan dokunan resmi kararlar
Gurbetçi haberlerini sadece hak/ödeme/askerlik/araç/sınır/emeklilik/e-Devlet etkisi varsa öne
al. Siyaset/adli olay/magazin SADECE ülke çapında güçlü etkili ve tam doğrulanmış büyük bir
gelişmeyse kabul edilebilir — sıradan kulis/sansasyon haberi elensin.

GERÇEK PERFORMANS VERİSİYLE DOĞRULANMIŞ EK KURAL: parti/politikacı haberleri (istifa, kulis,
açıklama, karşılıklı suçlama) ve salt merak amaçlı bilimsel/akademik haberler (izleyiciye
doğrudan bir fayda, uygulama veya karar sunmayan) kanalın gerçek verilerinde tutarlı biçimde
çok düşük izlenme alıyor (6-50 görüntüleme), emeklilik/maaş/gündelik ekonomi haberleri ise
600-1900 görüntüleme alıyor. Bu yüzden audience_relevance_score'u bu tür haberlerde düşük tut;
istisna SADECE somut ekonomik/pratik bir etkisi olan (ör. petrol fiyatına yansıyan bir
jeopolitik gelişme) veya gerçekten ülke gündemini domine eden büyük bir olay ise mümkündür.

DOĞRULUK SEVİYESİ (her aday için belirlemen ZORUNLU — taslak/teklif/beklenti haberi doğru
biçimde "henüz resmileşmedi" diyerek aktarmak sahte haber DEĞİLDİR; sahte haber riski bunu
kesinleşmiş karar gibi sunmaktan doğar):
- A — RESMİLEŞMİŞ: kanun kabul edilmiş, Resmi Gazete'de yayımlanmış veya uygulama fiilen
  başlamış/ödeme yatmış.
- B — RESMİ DUYURU/HAZIRLIK: bakanlık, SGK, TBMM, belediye, şirket veya yetkili bir kişi
  doğrudan taslak/teklif/çalışma/pilot uygulamayı duyurmuş. Haber yapılabilir.
- C — ERKEN SİNYAL/HENÜZ RESMİ DEĞİL: en az iki bağımsız güvenilir kaynak aynı somut gelişmeyi
  tutarlı biçimde aktarıyor (OLAY_KUMESI'nde aynı numaralı başka adaylar varsa bu bir sinyaldir),
  konu ülke çapında önemli. FAKAT emeklilik/SGK/maaş/ödeme günü/trafik cezası/vergi/sağlık
  tedavisi/hukuki haklar gibi parayı veya hakkı doğrudan etkileyen konularda C YETERSİZDİR —
  bu kategorilerde en az B seviyesi (resmi kaynaklı duyuru) gerekir.
- D — SÖYLENTİ: tek anonim kaynak, sosyal medya iddiası, kaynağı belirsiz ekran görüntüsü veya
  birbirini kopyalayan siteler — birincil kaynak yok.

DEĞERLENDİRME KURALLARI:
- Sadece ilgi çekici olduğu için haber seçme.
- Yeni bir olay, karar, tarih, tutar, resmi açıklama, taslak/teklif veya doğrulanabilir gelişme yoksa ele.
- "Çıkacak mı?", "gelecek mi?", "belli oldu mu?", "zam var mı?" gibi sadece soru soran ve cevap vermeyen başlıkları ele.
- Başlık kesin konuşup (örn. "yatırıldı", "kesinleşti") içerik aslında B/C seviyesindeyse (taslak/teklif/iddia) clickbait puanını yükselt — asıl sorun taslak/beklenti haberi işlemek değil, onu kesinleşmiş gibi sunmaktır.
- "Kritik uyarı", "son dakika", "milyonları ilgilendiriyor" gibi kalıplar tek başına haber değeri sayılmasın.
- Aynı olayın yeniden yazılmış sürümlerinden yalnızca en güvenilir ve somut olanı bırak (OLAY_KUMESI numarası aynı olanlar muhtemelen aynı olaydır). Eski bir karar/çalışma yeniden haberleştirilmişse ve gerçekten yeni bir gelişme yoksa duplicate_or_rehash_score'u yüksek ver.
- KAYNAK GÜCÜ (verifiability_score): certainty_level A/B ise ve resmi kaynağa dayanıyorsa yüksek puan; C ise ve birden fazla bağımsız kaynak/OLAY_KUMESI eşleşmesi varsa orta puan; D ise çok düşük puan.
- SOMUTLUK (concrete_development_score): Aday şu sorulardan en az birine kaynaklı, somut cevap veriyor mu? "Ne kadar? Kimler? Ne zaman yatacak? Hangi iller? Ne değişti? Ne zaman başlayacak?" — cevap vermiyorsa düşük puan ver.
- Resmi kurum duyurusu olsa bile vatandaş üzerindeki etkisi açıklanmıyorsa audience_relevance_score düşük olsun.
- PERFORMANS SİNYALİ (urgency_score'a yansıt): deprem/hava uyarıları paylaşım ve takipçi kazandırma potansiyeli yüksek olduğu için; emekli/ödeme haberleri yüksek görüntülenme potansiyeli olduğu için avantajlıdır — ikisi de öncelikli değerlendirilsin.
- Köşe yazısı, yalnızca SEO trafiği hedefleyen içerikler ve D seviyesi (söylenti) her zaman elensin.
- ZORUNLU RET: certainty_level D olan HER adayı decision="REJECT" yap. certainty_level C olup emeklilik/SGK/maaş/ödeme günü/trafik cezası/vergi/sağlık tedavisi/hukuki haklar kategorisinde olan adayları da decision="REJECT" yap (bu kategorilerde en az B gerekir).

Her aday için TAM OLARAK bu alanları içeren bir JSON nesnesi üret:
{"index": <numara>, "certainty_level": "A veya B veya C veya D", "clickbait_score": 0-100, "concrete_development_score": 0-100, "verifiability_score": 0-100, "audience_relevance_score": 0-100, "wallet_or_rights_impact_score": 0-100, "urgency_score": 0-100, "duplicate_or_rehash_score": 0-100, "decision": "KEEP" veya "REJECT", "reason": "en fazla 8 kelimelik kısa Türkçe gerekçe"}

SADECE bu nesnelerin bir JSON DİZİSİ olarak yanıt ver. Başka hiçbir açıklama, markdown veya metin ekleme."""


def _ai_jury_format_batch_prompt(batch: list[dict], cluster_ids: list[int]) -> str:
    lines = []

    for i, item in enumerate(batch, start=1):
        published_at = item.get("published_at")

        if published_at:
            published_text = published_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:
            published_text = "bilinmiyor"

        description = (item.get("description") or "").strip()

        if len(description) > 300:
            description = description[:300].rstrip() + "…"

        lines.append(
            f"{i}. BAŞLIK: {item.get('title', '')}\n"
            f"   KAYNAK: {item.get('source', '') or 'bilinmiyor'}\n"
            f"   YAYIN: {published_text}\n"
            f"   AÇIKLAMA: {description or 'yok'}\n"
            f"   URL: {item.get('link', '') or 'yok'}\n"
            f"   KURAL_PUANI: {item.get('score', 0)}\n"
            f"   OLAY_KUMESI: {cluster_ids[i - 1]}"
        )

    return "\n\n".join(lines)


# Partiyi bu boyutta parçalara böleriz — tek çağrıda 20-25 haberin tamamını
# puanlamak DeepSeek yanıtını max_tokens sınırında yarıda kesebiliyordu
# (gözlemlenen hata: "Unterminated string" — JSON yarıda kopuyordu). Küçük
# parçalar bu riski ortadan kaldırır; paralel çalıştırıldığı için toplam
# gecikme tek büyük çağrıyla neredeyse aynı kalır.
_AI_JURY_STAGE2_CHUNK_SIZE = 8


def _ai_jury_call_stage2_chunk(
    chunk: list[dict],
    chunk_cluster_ids: list[int],
    api_key: str,
    timeout_seconds: float,
) -> list | None:
    """Küçük bir parçayı (en fazla _AI_JURY_STAGE2_CHUNK_SIZE haber) tek
    DeepSeek çağrısıyla puanlar. En fazla bir kez yeniden dener, ikisi de
    başarısız olursa None döner (bu parçanın haberleri nötr geçer)."""
    from openai import OpenAI

    prompt = _AI_JURY_STAGE2_RULES + "\n\nADAYLAR:\n" + _ai_jury_format_batch_prompt(chunk, chunk_cluster_ids)
    last_error: Any = None

    for attempt in range(2):
        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout_seconds)
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1500,
            )
            data = _ai_jury_extract_json(resp.choices[0].message.content or "")

            if isinstance(data, list):
                return data

            last_error = "beklenmeyen yanıt biçimi (dizi değil)"
        except Exception as error:
            last_error = error
            print(f"[ai-jury] aşama-2 parça denemesi {attempt + 1} hatası: {error}", flush=True)

    print(f"[ai-jury] aşama-2 parçası tamamen başarısız (bu parçadaki haberler nötr geçer): {last_error}", flush=True)
    return None


def _ai_jury_call_stage2(
    batch: list[dict],
    cluster_ids: list[int],
    api_key: str,
    timeout_seconds: float = 20.0,
) -> list | None:
    """batch'i _AI_JURY_STAGE2_CHUNK_SIZE'lık parçalara bölüp paralel olarak
    değerlendirir, sonuçları (global index'e çevrilmiş olarak) birleştirir.
    Bir parça başarısız olursa sadece o parçanın haberleri değerlendirmesiz
    kalır — tüm aşama çökmez."""
    chunks = [
        (i, batch[i:i + _AI_JURY_STAGE2_CHUNK_SIZE], cluster_ids[i:i + _AI_JURY_STAGE2_CHUNK_SIZE])
        for i in range(0, len(batch), _AI_JURY_STAGE2_CHUNK_SIZE)
    ]

    if not chunks:
        return None

    all_evaluations: list = []

    with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as executor:
        future_map = {
            executor.submit(_ai_jury_call_stage2_chunk, chunk, chunk_clusters, api_key, timeout_seconds): (offset, len(chunk))
            for offset, chunk, chunk_clusters in chunks
        }

        for future in as_completed(future_map):
            offset, chunk_len = future_map[future]
            try:
                chunk_evaluations = future.result()
            except Exception as error:
                print(f"[ai-jury] aşama-2 parçası (offset={offset}) beklenmeyen hata: {error}", flush=True)
                continue

            if not chunk_evaluations:
                continue

            for ev in chunk_evaluations:
                try:
                    local_idx = int(ev.get("index", 0)) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= local_idx < chunk_len:
                    ev = dict(ev)
                    ev["index"] = offset + local_idx + 1
                    all_evaluations.append(ev)

    return all_evaluations or None


_AI_JURY_STAGE3_RULES = """AŞAĞIDAKİ {n} HABER arasında bir turnuva yap. Amaç SADECE aynı olayı
anlatan tekrarları elemek — farklı, gerçek haberleri ASLA sebepsiz düşürme.
Aynı listede iki benzer emeklilik spekülasyonu veya iki aynı İstanbul hava
haberi gibi TEKRARLAR olmasın; ama birbirinden farklı konular (emeklilik,
hava durumu, akaryakıt, sağlık, ulaşım vb.) hepsi FARKLI haberdir, aralarında
denge kurarak MÜMKÜN OLDUĞUNCA ÇOĞUNU tut. Havuzda gerçekten {max_output}
kadar farklı/tekrarsız haber varsa listeyi yapay şekilde kısaltma.

ZORUNLU KURAL: 1'den {n}'e kadar HER numara ya selected_indices'te ya da
rejected'te olmalı — hiçbir numarayı sessizce atlama. Bir haberi elerken
mutlaka rejected'e bir sebep ile ekle; sebepsiz eleme YOK.

SADECE şu JSON nesnesini döndür, başka hiçbir şey yazma:
{{"selected_indices": [numaralar], "rejected": [{{"index": numara, "reason": "kısa Türkçe gerekçe"}}]}}"""


def _ai_jury_format_tournament_prompt(survivors: list[dict]) -> str:
    lines = []

    for i, item in enumerate(survivors, start=1):
        ev = item.get("ai_eval") or {}
        lines.append(
            f"{i}. BAŞLIK: {item.get('title', '')}\n"
            f"   KAYNAK: {item.get('source', '') or 'bilinmiyor'}\n"
            f"   NİHAİ_PUAN: {round(item.get('final_score', 0), 1)}\n"
            f"   AI_GEREKÇE: {ev.get('reason', '')}"
        )

    return "\n\n".join(lines)


def _ai_jury_call_stage3(
    survivors: list[dict],
    api_key: str,
    max_output: int,
    timeout_seconds: float = 20.0,
) -> dict | None:
    from openai import OpenAI

    prompt = (
        _AI_JURY_STAGE3_RULES.format(max_output=max_output, n=len(survivors))
        + "\n\nHABERLER:\n"
        + _ai_jury_format_tournament_prompt(survivors)
    )
    last_error: Any = None

    for attempt in range(2):
        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout_seconds)
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1200,
            )
            data = _ai_jury_extract_json(resp.choices[0].message.content or "")

            if isinstance(data, dict) and "selected_indices" in data:
                return data

            last_error = "beklenmeyen yanıt biçimi"
        except Exception as error:
            last_error = error
            print(f"[ai-jury] aşama-3 deneme {attempt + 1} hatası: {error}", flush=True)

    print(f"[ai-jury] aşama-3 tamamen başarısız: {last_error}", flush=True)
    return None


def _ai_hard_reject(evaluation: dict) -> bool:
    if evaluation.get("decision") == "REJECT":
        return True
    if evaluation.get("clickbait_score", 0) >= _AI_CLICKBAIT_HARD_LIMIT:
        return True
    if evaluation.get("concrete_development_score", 100) <= _AI_CONCRETE_HARD_FLOOR:
        return True
    # Söylenti seviyesi (D) — AI "decision" alanını doğru set etmeyi unutsa bile
    # kod seviyesinde ek güvenlik: hiçbir söylenti haberi üretime geçmesin.
    if (evaluation.get("certainty_level") or "").strip().upper()[:1] == "D":
        return True
    return False


def _ai_final_score(rule_score: float, evaluation: dict) -> float:
    def _pct(key: str, default: float = 50) -> float:
        try:
            return max(0.0, min(100.0, float(evaluation.get(key, default))))
        except (TypeError, ValueError):
            return default

    boost = _AI_SCALE * (
        _AI_WEIGHT_CONCRETE * _pct("concrete_development_score") / 100
        + _AI_WEIGHT_VERIFIABILITY * _pct("verifiability_score") / 100
        + _AI_WEIGHT_AUDIENCE * _pct("audience_relevance_score") / 100
        + _AI_WEIGHT_WALLET_RIGHTS * _pct("wallet_or_rights_impact_score") / 100
        + _AI_WEIGHT_URGENCY * _pct("urgency_score") / 100
    )
    penalty = _AI_SCALE * (
        _AI_PENALTY_CLICKBAIT * _pct("clickbait_score", 0) / 100
        + _AI_PENALTY_DUPLICATE * _pct("duplicate_or_rehash_score", 0) / 100
    )

    return rule_score + boost - penalty


_SEO_TAIL_PATTERN = re.compile(r"\s*\|.*$")
_TRAILING_QUESTION_PATTERN = re.compile(
    r"[,\-–—]\s*[^,\-–—]{0,60}\b(mi|mı|mu|mü)\?\s*$", re.IGNORECASE
)


def clean_display_title(title: str) -> str:
    """Telegram'da GÖRÜNTÜLENECEK başlığı SEO kuyruğundan arındırır. Yeni bir
    gerçek uydurmaz — sadece görüntüleme metnini kısaltır; asıl işlenen/
    üretilen video başlığı bu fonksiyondan etkilenmez."""
    cleaned = _clean(title)
    cleaned = _SEO_TAIL_PATTERN.sub("", cleaned).strip()

    for _ in range(3):
        new_cleaned = _TRAILING_QUESTION_PATTERN.sub("", cleaned).strip()
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned

    return cleaned or _clean(title)


def run_ai_jury(
    candidates: list[dict],
    api_key: str,
    max_input: int = 25,
    max_output: int = 12,
) -> list[dict]:
    """Kural tabanlı sıralamanın (candidates, zaten puana göre sıralı)
    üstüne AI jürisi ekler: aşama 2 (tek tek puanlama + sert eleme) ve
    aşama 3 (turnuva ile olay bazlı dedup, en fazla max_output aday).

    Herhangi bir hata/timeout/bozuk JSON durumunda candidates'ın İLK
    max_output kadarını DEĞİŞTİRMEDEN döner — bu fonksiyon asla exception
    fırlatmaz, çağıran tarafın (app.py) otomatik akışı hiçbir zaman durmaz.
    """
    if not candidates or not api_key:
        return candidates[:max_output]

    fallback = candidates[:max_output]

    try:
        batch = candidates[:max_input]
        cluster_ids = _ai_jury_assign_clusters(batch)

        cache = _load_ai_jury_cache()
        now = time.time()
        cutoff = now - AI_JURY_CACHE_TTL_HOURS * 3600

        cache_keys = [_ai_jury_cache_key(item) for item in batch]
        to_fetch = []
        to_fetch_indices = []

        for i, key in enumerate(cache_keys):
            cached = cache.get(key)
            if cached and cached.get("ts", 0) > cutoff:
                continue
            to_fetch.append(batch[i])
            to_fetch_indices.append(i)

        if to_fetch:
            fetch_cluster_ids = [cluster_ids[i] for i in to_fetch_indices]
            evaluations = _ai_jury_call_stage2(to_fetch, fetch_cluster_ids, api_key)

            if evaluations:
                for ev in evaluations:
                    try:
                        local_idx = int(ev.get("index", 0)) - 1
                    except (TypeError, ValueError):
                        continue
                    if 0 <= local_idx < len(to_fetch):
                        real_idx = to_fetch_indices[local_idx]
                        cache[cache_keys[real_idx]] = {"eval": ev, "ts": now}

        _save_ai_jury_cache(cache)

        evaluated = []
        for i, item in enumerate(batch):
            cached = cache.get(cache_keys[i])
            ev = cached.get("eval") if cached else None

            if not ev:
                # AI bu haber için değerlendirme üretemedi (kısmi hata) —
                # kural puanını koru, cezalandırma.
                evaluated.append({**item, "ai_eval": None, "final_score": item.get("score", 0)})
                continue

            evaluated.append({
                **item,
                "ai_eval": ev,
                "final_score": _ai_final_score(item.get("score", 0), ev),
            })

        survivors = [
            item for item in evaluated
            if not item.get("ai_eval") or not _ai_hard_reject(item["ai_eval"])
        ]

        if not survivors:
            print("[ai-jury] tüm adaylar elendi, kural tabanlı yedek kullanılıyor", flush=True)
            return fallback

        survivors.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        print(
            f"[ai-jury] aşama-2 sonrası: {len(batch)} girdi → {len(survivors)} survivor (hard-reject: {len(batch) - len(survivors)}) — "
            + " | ".join(f"{i+1}:{s.get('title', '')[:40]}" for i, s in enumerate(survivors)),
            flush=True,
        )

        tournament = _ai_jury_call_stage3(survivors, api_key, max_output)
        print(f"[ai-jury] aşama-3 ham yanıt: {tournament}", flush=True)

        if tournament and tournament.get("selected_indices"):
            try:
                selected_positions: set = set()
                selected = []
                for idx in tournament["selected_indices"]:
                    pos = int(idx) - 1
                    if 0 <= pos < len(survivors) and pos not in selected_positions:
                        selected.append(survivors[pos])
                        selected_positions.add(pos)

                rejected_positions: set = set()
                for rej in tournament.get("rejected", []):
                    try:
                        rejected_positions.add(int(rej.get("index", 0)) - 1)
                    except (TypeError, ValueError):
                        pass

                # AI'nin ne seçtiği ne reddettiği (kuralı unuttuğu) haberler
                # sessizce kaybolmasın — gözlemlenen gerçek hata: turnuva 20
                # haberden sadece 4'ünü selected_indices'e koyup 3'ünü rejected
                # yapmış, geri kalan 13 haber hiç hesaba katılmadan düşmüştü.
                # Puana göre sıralı survivors listesinden, hesaba katılmamış
                # olanları max_output'a kadar geri ekliyoruz.
                for pos, item in enumerate(survivors):
                    if len(selected) >= max_output:
                        break
                    if pos in selected_positions or pos in rejected_positions:
                        continue
                    selected.append(item)
                    selected_positions.add(pos)
                    print(
                        f"[ai-jury] turnuva bu haberi hesaba katmamış, geri eklendi: {item.get('title', '')[:70]}",
                        flush=True,
                    )

                if selected:
                    for rej in tournament.get("rejected", []):
                        print(f"[ai-jury] turnuva elemesi: {rej}", flush=True)
                    return selected[:max_output]
            except Exception as merge_error:
                print(f"[ai-jury] turnuva sonucu işlenemedi: {merge_error}", flush=True)

        # Turnuva AI'sı başarısız olduysa, mevcut olay-tekrarı mantığıyla
        # (_is_same_event) yerel dedup yap — ikinci bir güvenli geri dönüş.
        deduped: list[dict] = []
        for item in survivors:
            if any(
                _is_same_event(existing.get("title", ""), item.get("title", ""))
                for existing in deduped
            ):
                continue
            deduped.append(item)
            if len(deduped) >= max_output:
                break

        return deduped or fallback

    except Exception as error:
        print(f"[ai-jury] beklenmeyen hata, kural tabanlı yedek kullanılıyor: {error}", flush=True)
        return fallback
