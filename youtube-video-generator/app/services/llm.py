"""DeepSeek ile metni sahnelere böler, her sahne için Pexels keywords üretir."""

import json
import re
from typing import List

import httpx

from app.config import settings

_PROMPT = """\
Sen bir YouTube video yapımcısısın. Aşağıdaki Türkçe hikaye/roman metnini \
YouTube Shorts veya uzun video için uygun SAHNELERE böl.

KURALLAR:
1. Her sahne 2-5 cümle içersin.
2. Ardışık cümleler anlamlı bir bütün oluştursun.
3. Her sahne için 3-5 İngilizce Pexels arama terimi üret. \
   Terimler görsel ve duygusal olmalı (örn: "rainy night city street", \
   "old man reading letter").
4. atmosphere alanı şunlardan biri olsun: \
   dramatic, peaceful, mysterious, romantic, sad, action, tense, joyful, neutral

Yanıtı SADECE aşağıdaki JSON formatında ver, başka hiçbir şey ekleme:
{
  "scenes": [
    {
      "text": "Sahne metni burada yer alır.",
      "keywords": ["keyword phrase 1", "keyword phrase 2", "keyword phrase 3"],
      "atmosphere": "dramatic"
    }
  ]
}

METİN:
"""


async def split_into_scenes(text: str) -> List[dict]:
    """Metni sahnelere böler. Liste of dicts: text, keywords, atmosphere."""
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY ayarlanmamış.")

    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.deepseek_model,
                "messages": [{"role": "user", "content": _PROMPT + text}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    # Bazen LLM JSON dışında markdown bloğu ekler, temizle
    content = re.sub(r"```json\s*", "", content)
    content = re.sub(r"```\s*", "", content)

    data = json.loads(content)
    scenes = data.get("scenes", [])
    if not scenes:
        raise ValueError("LLM sahne üretemedi. Metni kontrol edin.")
    return scenes
