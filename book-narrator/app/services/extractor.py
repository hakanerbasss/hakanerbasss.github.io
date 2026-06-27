"""Kitap dosyasından düz metin çıkarır.

Desteklenen formatlar: PDF, EPUB, TXT, DOCX
PDF için taranmış görüntü (OCR gereken) vs metin bazlı ayrımı yapılır.
"""

import re
from pathlib import Path


SUPPORTED = {".pdf", ".epub", ".txt", ".docx"}


def detect_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Desteklenmeyen format: {ext}. Kabul edilenler: PDF, EPUB, TXT, DOCX")
    return ext


def extract(path: str) -> str:
    """Dosyadan ham metin çıkarır. Boş metin döndürürse hata fırlatır."""
    ext = detect_format(path)
    if ext == ".pdf":
        text = _from_pdf(path)
    elif ext == ".epub":
        text = _from_epub(path)
    elif ext == ".txt":
        text = _from_txt(path)
    elif ext == ".docx":
        text = _from_docx(path)
    else:
        raise ValueError(f"Bilinmeyen format: {ext}")

    text = _clean(text)
    if len(text) < 200:
        raise ValueError(
            "Metin çıkarılamadı veya çok kısa. "
            "PDF taranmış görüntü ise metin tabanlı PDF gerekiyor."
        )
    return text


# ── Format okuyucuları ───────────────────────────────────────────────────────

def _from_pdf(path: str) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pip install pdfplumber")

    pages = []
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            raise ValueError("PDF sayfa içermiyor.")

        # İlk 3 sayfa örneğine bakarak taranmış mı kontrol et
        sample_chars = 0
        for page in pdf.pages[:3]:
            t = page.extract_text() or ""
            sample_chars += len(t.strip())
        if sample_chars < 50:
            raise ValueError(
                "Bu PDF taranmış görüntü içeriyor, metin yok. "
                "OCR uygulanmış veya metin tabanlı bir PDF yükleyin."
            )

        for page in pdf.pages:
            t = page.extract_text()
            if t:
                pages.append(t)

    return "\n\n".join(pages)


def _from_epub(path: str) -> str:
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("pip install EbookLib beautifulsoup4")

    book = epub.read_epub(path, options={"ignore_ncx": True})
    parts = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        # Navigasyon/TOC sayfalarını atla
        if soup.find("nav") or soup.find(attrs={"epub:type": "toc"}):
            continue
        text = soup.get_text(separator="\n")
        if len(text.strip()) > 100:
            parts.append(text)

    return "\n\n".join(parts)


def _from_txt(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "windows-1254", "iso-8859-9", "latin-1"):
        try:
            return Path(path).read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("TXT dosyası okunamadı — desteklenmeyen karakter kodlaması.")


def _from_docx(path: str) -> str:
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("pip install python-docx")

    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


# ── Metin temizleme ──────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    # Fazla boşluk ve satır sonu temizliği
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    # 3'ten fazla boş satırı 2'ye indir
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Satır içi fazla boşlukları tek boşluğa indir
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Sayfa numarası gibi tek başına duran rakamları kaldır
    text = re.sub(r"(?m)^\s*\d+\s*$", "", text)
    return text.strip()
