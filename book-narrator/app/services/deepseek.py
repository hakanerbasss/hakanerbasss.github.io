"""DeepSeek API client — çeviri, içerik filtreleme, YouTube metadata."""

import json
import httpx
from app.config import LANG_NAMES_EN

_BASE = "https://api.deepseek.com/v1"
_MODEL = "deepseek-chat"
_TIMEOUT = 120.0


async def _chat(api_key: str, messages: list[dict], temperature: float = 0.3) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(
            f"{_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": _MODEL, "messages": messages, "temperature": temperature},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


async def find_content_start(text: str, api_key: str) -> int:
    """Gerçek kitap içeriğinin başladığı karakter pozisyonunu döner."""
    sample = text[:4000]
    prompt = (
        "The following is the beginning of a book. It may contain publishing info, "
        "copyright notices, table of contents, or other non-story metadata.\n\n"
        f"TEXT:\n{sample}\n\n"
        "Return ONLY the first sentence/phrase where the actual book story or content begins. "
        "Max 80 characters. No explanation."
    )
    try:
        snippet = await _chat(api_key, [{"role": "user", "content": prompt}])
        snippet = snippet.strip('"\'').strip()
        idx = text.find(snippet[:60])
        return max(0, idx) if idx != -1 else 0
    except Exception:
        return 0


async def translate_chunks(
    chunks: list[str],
    source_lang: str,
    target_lang: str,
    api_key: str,
    batch_size: int = 8,
) -> tuple[list[str], list[str]]:
    """Chunk listesini çevirir. (translated_chunks, pexels_keywords) döner."""
    src = LANG_NAMES_EN.get(source_lang, source_lang)
    tgt = LANG_NAMES_EN.get(target_lang, target_lang)
    translated: list[str] = []
    keywords: list[str] = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        numbered = "\n".join(f"[{j+1}] {c}" for j, c in enumerate(batch))
        prompt = (
            f"Translate these text segments from {src} to {tgt}. "
            "Also give 2-3 English Pexels image search keywords per segment (scene/nature/emotion based).\n\n"
            f"{numbered}\n\n"
            "Respond ONLY with this JSON:\n"
            '{"items":[{"t":"translated text","k":"keyword1 keyword2"},...]}\n'
            "Same number of items as input. Keywords: simple English nouns only."
        )
        try:
            raw = await _chat(api_key, [{"role": "user", "content": prompt}])
            s = raw.find("{"); e = raw.rfind("}") + 1
            data = json.loads(raw[s:e])
            for item in data.get("items", []):
                translated.append(item.get("t", ""))
                keywords.append(item.get("k", "nature landscape"))
        except Exception:
            for c in batch:
                translated.append(c)
                keywords.append("nature landscape")

    return translated, keywords


async def generate_metadata(
    title: str,
    content_sample: str,
    target_lang: str,
    api_key: str,
) -> dict:
    """YouTube başlık, açıklama, etiket ve hashtag üretir."""
    tgt = LANG_NAMES_EN.get(target_lang, "Turkish")
    prompt = (
        f"Generate YouTube audiobook metadata in {tgt}.\n"
        f"Book title: {title}\n"
        f"Sample:\n{content_sample[:1500]}\n\n"
        "Respond ONLY with this JSON:\n"
        '{"title":"...","description":"...","tags":["..."],"hashtags":["#..."]}\n'
        "title: max 80 chars | description: 250-400 words | tags: 12 items | hashtags: 8 items"
    )
    try:
        raw = await _chat(api_key, [{"role": "user", "content": prompt}], temperature=0.7)
        s = raw.find("{"); e = raw.rfind("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return {
            "title": title,
            "description": f"{title} - Sesli Kitap / Audiobook",
            "tags": ["sesli kitap", "audiobook", title],
            "hashtags": ["#seslikitap", "#audiobook"],
        }
