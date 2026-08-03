"""PDF/görsel sayfalarından metin çıkarma (OCR)."""
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path

LANG = 'tur'


def ocr_image_path(path):
    img = Image.open(path)
    return pytesseract.image_to_string(img, lang=LANG).strip()


def pdf_to_page_images(pdf_path, out_dir, dpi=200):
    os.makedirs(out_dir, exist_ok=True)
    images = convert_from_path(pdf_path, dpi=dpi)
    paths = []
    for i, img in enumerate(images, start=1):
        p = os.path.join(out_dir, f'page-{i}.jpg')
        img.convert('RGB').save(p, 'JPEG', quality=85)
        paths.append(p)
    return paths
