"""
Claude API ile Instagram caption üretici.
API yoksa şablon tabanlı caption kullanır.
"""

import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_caption_with_claude(
    title: str,
    price: str,
    sold_count: Optional[str],
    niche: str,
    api_key: str,
) -> str:
    """Claude API ile özgün Instagram caption üretir."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Write a short, punchy Instagram caption for this viral product post.\n"
            f"Product: {title}\n"
            f"Price: {price}\n"
            f"Sold: {sold_count or 'thousands'}\n"
            f"Niche: {niche}\n\n"
            f"Requirements:\n"
            f"- 2-3 lines max\n"
            f"- Start with a hook emoji\n"
            f"- Include a call-to-action\n"
            f"- Add 5 relevant hashtags at the end\n"
            f"- Keep it conversational and exciting\n"
            f"- No markdown, plain text only"
        )
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Claude API hatası, şablon kullanılıyor: {e}")
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
    """Ana caption üretici. API anahtarı varsa Claude kullanır."""
    if api_key:
        return generate_caption_with_claude(title, price, sold_count, niche, api_key)
    return generate_template_caption(title, price, sold_count, niche)
