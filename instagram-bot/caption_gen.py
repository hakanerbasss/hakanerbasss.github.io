"""
DeepSeek API ile Instagram caption üretici.
API yoksa şablon tabanlı caption kullanır.

DeepSeek API, OpenAI SDK ile uyumludur (base_url farklı).
"""

import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek-V3; akıl yürütme için "deepseek-reasoner"

CAPTION_PROMPT = """\
Write a short, punchy Instagram caption for this viral product post.
Product: {title}
Price: {price}
Sold: {sold_count}
Niche: {niche}

Requirements:
- 2-3 lines max
- Start with a hook emoji
- Include a call-to-action
- Add 5 relevant hashtags at the end
- Keep it conversational and exciting
- No markdown, plain text only"""


def generate_caption_with_deepseek(
    title: str,
    price: str,
    sold_count: Optional[str],
    niche: str,
    api_key: str,
) -> str:
    """DeepSeek API ile özgün Instagram caption üretir."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": CAPTION_PROMPT.format(
                        title=title,
                        price=price,
                        sold_count=sold_count or "thousands",
                        niche=niche,
                    ),
                }
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"DeepSeek API hatası, şablon kullanılıyor: {e}")
        return generate_template_caption(title, price, sold_count, niche)


def generate_template_caption(
    title: str,
    price: str,
    sold_count: Optional[str],
    niche: str,
) -> str:
    """API olmadan şablon tabanlı caption üretir."""
    hooks = [
        "🔥 This product is EVERYWHERE right now!",
        "💥 Everyone's buying this and here's why...",
        "⚡ The viral product you didn't know you needed!",
        "🚨 Sold out multiple times — back in stock!",
        "👀 Why is this product going SO viral?",
    ]
    ctas = [
        "👇 Link in bio to grab yours!",
        "💬 Tag someone who needs this!",
        "🛒 Get it before it sells out again!",
        "📦 Ships worldwide — link in bio!",
    ]
    sold_line = f"✅ {sold_count} already sold!\n" if sold_count else ""
    hashtags = (
        f"#{niche.replace(' ', '')} #viral #trending #mustbuy "
        "#deals #onlineshopping #amazonfinds #tiktokmademebuyit"
    )
    return (
        f"{random.choice(hooks)}\n\n"
        f"{title}\n"
        f"💰 Only {price}!\n"
        f"{sold_line}"
        f"{random.choice(ctas)}\n\n"
        f"{hashtags}"
    )


def get_caption(
    title: str,
    price: str,
    sold_count: Optional[str] = None,
    niche: str = "gadgets",
    api_key: Optional[str] = None,
) -> str:
    """Ana caption üretici. API anahtarı varsa DeepSeek kullanır."""
    if api_key:
        return generate_caption_with_deepseek(title, price, sold_count, niche, api_key)
    return generate_template_caption(title, price, sold_count, niche)
