#!/usr/bin/env python3
"""
maps-site-gen — Google Maps'ten web sitesi olmayan işletmeleri bulur ve onlara site üretir.

Kullanım:
  python main.py search --query "restoran" --location "Kadıköy İstanbul" --max 10
  python main.py generate --json businesses.json
  python main.py run --query "kafe" --location "Beşiktaş" --max 5 --output output/
"""

import asyncio
import json
import os
import sys
import click
from scraper import find_businesses_without_website, save_businesses_json, load_businesses_json
from generator import generate_all
import config


@click.group()
def cli():
    """Google Maps'ten web sitesi olmayan işletmeleri bulur ve statik site üretir."""
    pass


@cli.command()
@click.option("--query", "-q", required=True, help='Arama terimi (örn: "restoran", "berber")')
@click.option("--location", "-l", default="", help='Konum (örn: "Kadıköy İstanbul")')
@click.option("--max", "-m", "max_results", default=config.MAX_BUSINESSES, type=int, help="Maksimum sonuç sayısı")
@click.option("--output", "-o", default="businesses.json", help="Çıktı JSON dosyası")
def search(query, location, max_results, output):
    """Google Maps'i tarar, web sitesiz işletmeleri JSON'a kaydeder."""
    click.echo(f"[maps-site-gen] Arama: '{query}' @ '{location}', max={max_results}")

    businesses = asyncio.run(
        find_businesses_without_website(query, location, max_results)
    )

    if not businesses:
        click.echo("[!] Hiç işletme bulunamadı.")
        sys.exit(1)

    save_businesses_json(businesses, output)
    click.echo(f"\n✓ {len(businesses)} işletme kaydedildi: {output}")


@cli.command()
@click.option("--json", "-j", "json_file", required=True, help="İşletme JSON dosyası")
@click.option("--output", "-o", default=config.OUTPUT_DIR, help="Çıktı klasörü")
@click.option("--title", "-t", default="İşletme Rehberi", help="Site başlığı")
@click.option("--location", "-l", default="", help="Konum etiketi")
def generate(json_file, output, title, location):
    """JSON'daki işletmeler için statik HTML siteleri üretir."""
    if not os.path.exists(json_file):
        click.echo(f"[!] Dosya bulunamadı: {json_file}")
        sys.exit(1)

    businesses = load_businesses_json(json_file)
    click.echo(f"[maps-site-gen] {len(businesses)} işletme için site üretiliyor...")

    generate_all(businesses, output, title, location)
    click.echo(f"\n✓ Siteler hazır: {os.path.abspath(output)}/")


@cli.command()
@click.option("--query", "-q", required=True, help='Arama terimi (örn: "restoran")')
@click.option("--location", "-l", default="", help='Konum (örn: "Üsküdar İstanbul")')
@click.option("--max", "-m", "max_results", default=config.MAX_BUSINESSES, type=int)
@click.option("--output", "-o", default=config.OUTPUT_DIR, help="Çıktı klasörü")
@click.option("--title", "-t", default=None, help="Site başlığı")
@click.option("--save-json", is_flag=True, default=False, help="businesses.json'ı da kaydet")
def run(query, location, max_results, output, title, save_json):
    """Tüm pipeline'ı çalıştır: Ara → Veri topla → Site üret."""
    if title is None:
        title = f"{query.title()} — {location}" if location else f"{query.title()} Rehberi"

    click.echo(f"[maps-site-gen] Pipeline başlıyor...")
    click.echo(f"  Sorgu   : {query}")
    click.echo(f"  Konum   : {location or 'belirtilmemiş'}")
    click.echo(f"  Maks.   : {max_results}")
    click.echo(f"  Çıktı   : {output}/")
    click.echo("")

    # 1. Scrape
    businesses = asyncio.run(
        find_businesses_without_website(query, location, max_results)
    )

    if not businesses:
        click.echo("[!] Web sitesiz işletme bulunamadı.")
        sys.exit(1)

    # 2. Opsiyonel JSON kaydet
    if save_json:
        json_path = os.path.join(output, "businesses.json")
        os.makedirs(output, exist_ok=True)
        save_businesses_json(businesses, json_path)

    # 3. Site üret
    generate_all(businesses, output, title, location)

    click.echo(f"\n✅ Tamamlandı!")
    click.echo(f"   {len(businesses)} işletme için site oluşturuldu.")
    click.echo(f"   Çıktı: {os.path.abspath(output)}/")
    click.echo(f"   Önizleme: python -m http.server 8080 -d {output}")


@cli.command()
@click.option("--name", required=True, help="İşletme adı")
@click.option("--category", default="Restoran", help="Kategori")
@click.option("--address", default="İstanbul, Türkiye", help="Adres")
@click.option("--phone", default="+90 212 000 0000", help="Telefon")
@click.option("--output", "-o", default=config.OUTPUT_DIR, help="Çıktı klasörü")
def demo(name, category, address, phone, output):
    """Gerçek scraping yapmadan demo veriyle site üret."""
    from scraper import BusinessInfo
    business = BusinessInfo(
        name=name,
        category=category,
        address=address,
        phone=phone,
        rating=4.5,
        review_count=87,
        hours={
            "Pazartesi": "09:00–22:00",
            "Salı": "09:00–22:00",
            "Çarşamba": "09:00–22:00",
            "Perşembe": "09:00–22:00",
            "Cuma": "09:00–23:00",
            "Cumartesi": "10:00–23:00",
            "Pazar": "10:00–21:00",
        },
        photos=[],
        slug=name.lower().replace(" ", "-"),
    )
    generate_all([business], output, f"{name} Web Sitesi", address)
    click.echo(f"\n✅ Demo site hazır: {os.path.abspath(output)}/")
    click.echo(f"   Önizleme: python -m http.server 8080 -d {output}")


if __name__ == "__main__":
    cli()
