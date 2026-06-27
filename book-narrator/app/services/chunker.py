"""Kitap metnini TTS için uygun parçalara böler.

Strateji:
  1. Paragraflara böl (doğal duraklar)
  2. Her paragrafı MAX_CHARS'a sığdır — cümle ortasında kesmez
  3. Çok kısa ardışık paragrafları birleştir (MIN_CHARS)

Sonuç: her chunk 150-400 karakter arası, doğal cümle sınırlarında.
"""

import re
from typing import List

MAX_CHARS = 400
MIN_CHARS = 80


def split(text: str) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[str] = []
    buffer = ""

    for para in paragraphs:
        # Paragraf MAX_CHARS'tan büyükse cümlelere böl
        if len(para) > MAX_CHARS:
            sentences = _split_sentences(para)
            for sent in sentences:
                if not sent:
                    continue
                if len(buffer) + len(sent) + 1 <= MAX_CHARS:
                    buffer = (buffer + " " + sent).strip()
                else:
                    if buffer:
                        chunks.append(buffer)
                    # Tek cümle bile büyükse karaktere göre kes (son çare)
                    if len(sent) > MAX_CHARS:
                        chunks.extend(_hard_split(sent))
                        buffer = ""
                    else:
                        buffer = sent
        else:
            if len(buffer) + len(para) + 1 <= MAX_CHARS:
                buffer = (buffer + " " + para).strip() if buffer else para
            else:
                if buffer:
                    chunks.append(buffer)
                buffer = para

    if buffer:
        chunks.append(buffer)

    # Çok kısa chunk'ları bir sonrakiyle birleştir
    merged: List[str] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if len(c) < MIN_CHARS and i + 1 < len(chunks):
            merged.append((c + " " + chunks[i + 1]).strip())
            i += 2
        else:
            merged.append(c)
            i += 1

    return [_clean_for_tts(c) for c in merged if c.strip()]


def _split_sentences(text: str) -> List[str]:
    """Türkçe uyumlu cümle bölücü."""
    # Nokta, !, ? sonrası büyük harf veya satır sonu = cümle sonu
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ"«—])', text)
    return [p.strip() for p in parts if p.strip()]


def _hard_split(text: str) -> List[str]:
    """Son çare: karakter sayısına göre kes."""
    result = []
    while len(text) > MAX_CHARS:
        # En yakın boşluğa git
        cut = text.rfind(" ", 0, MAX_CHARS)
        if cut < 0:
            cut = MAX_CHARS
        result.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        result.append(text)
    return result


def _clean_for_tts(text: str) -> str:
    """TTS'e gitmeden önce sembol temizliği — instube/generator.py'deki pattern."""
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)   # **bold**
    text = re.sub(r'#{1,6}\s*', '', text)                    # # başlık
    text = re.sub(r'`[^`]*`', '', text)                      # `kod`
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)     # [link](url)
    text = re.sub(r'https?://\S+', '', text)                  # URL
    text = re.sub(r'[#@|_~^\\<>{}[\]]', ' ', text)           # özel semboller
    # Türkçe sayı/yüzde
    text = re.sub(r'%\s*(\d+)', r'yüzde \1', text)
    text = re.sub(r'(\d+)°', r'\1 derece', text)
    return re.sub(r'\s+', ' ', text).strip()
