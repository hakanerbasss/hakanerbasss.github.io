"""
Flask web uygulaması — Google Maps işletme bulucu + site üretici.
"""

import json
import os
import threading
import csv
import io

# .env dosyasını yükle (varsa)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import datetime
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, send_file, session
)
import config
from scraper import BusinessInfo, find_businesses_without_website, save_json, load_json
from generator import generate_all, generate_business_site
import instagram as ig

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET

# Uygulama genelinde durum (hafızada, yeniden başlatmada sıfırlanır)
_state = {
    "searching": False,
    "progress": {"current": 0, "total": 0, "name": ""},
    "businesses": [],   # BusinessInfo listesi
    "error": "",
}

DATA_FILE = os.path.join(config.OUTPUT_DIR, "businesses.json")


def _load_businesses() -> list[BusinessInfo]:
    if os.path.exists(DATA_FILE):
        try:
            return load_json(DATA_FILE)
        except Exception:
            pass
    return []


def _save_businesses(businesses: list[BusinessInfo]):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    save_json(businesses, DATA_FILE)


# ─── SAYFALAR ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    businesses = _state["businesses"] or _load_businesses()
    _state["businesses"] = businesses
    return render_template(
        "app/index.html",
        businesses=businesses,
        searching=_state["searching"],
        error=_state["error"],
    )


@app.route("/search", methods=["POST"])
def search():
    if _state["searching"]:
        return jsonify({"error": "Arama zaten devam ediyor"}), 400

    query = request.form.get("query", "").strip()
    location = request.form.get("location", "").strip()
    max_n = int(request.form.get("max", config.MAX_BUSINESSES))

    if not query:
        return jsonify({"error": "Arama terimi gerekli"}), 400

    _state["searching"] = True
    _state["error"] = ""
    _state["progress"] = {"current": 0, "total": 0, "name": "Başlatılıyor..."}

    def run():
        def progress_cb(cur, tot, name):
            _state["progress"] = {"current": cur, "total": tot, "name": name or "..."}

        try:
            results = find_businesses_without_website(query, location, max_n, progress_cb)
            _state["businesses"] = results
            _save_businesses(results)
        except Exception as e:
            _state["error"] = str(e)
            print(f"[App] Arama hatası: {e}")
        finally:
            _state["searching"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    return jsonify({
        "searching": _state["searching"],
        "progress": _state["progress"],
        "count": len(_state["businesses"]),
        "error": _state["error"],
    })


@app.route("/businesses")
def businesses():
    biz = _state["businesses"] or _load_businesses()
    _state["businesses"] = biz
    return render_template("app/businesses.html", businesses=biz)


@app.route("/business/<slug>")
def business_detail(slug):
    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return "İşletme bulunamadı", 404

    # Instagram bilgisi henüz yoksa çek
    ig_profile = None
    if b.instagram_handle and not b.instagram_posts:
        ig_profile = ig.fetch_profile(b.instagram_handle)
        b.instagram_posts = ig_profile.posts
        b.instagram_bio = ig_profile.bio
        b.instagram_followers = ig_profile.followers
        _save_businesses(businesses)

    # Site üretildi mi?
    site_dir = os.path.join(config.OUTPUT_DIR, slug)
    site_exists = os.path.exists(os.path.join(site_dir, "index.html"))

    return render_template(
        "app/business_detail.html",
        business=b,
        ig=ig_profile,
        site_exists=site_exists,
    )


@app.route("/generate/<slug>", methods=["POST"])
def generate(slug):
    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404

    try:
        template_dir = os.path.join(os.path.dirname(__file__), "templates", "site")
        site_dir = generate_business_site(b, config.OUTPUT_DIR, template_dir)
        return jsonify({"ok": True, "slug": slug})
    except Exception as e:
        print(f"[App] Site üretim hatası: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/preview/<slug>")
def preview(slug):
    """Üretilmiş siteyi iframe içinde önizle."""
    site_path = os.path.join(config.OUTPUT_DIR, slug, "index.html")
    if not os.path.exists(site_path):
        return "Site henüz üretilmedi. Önce 'Site Üret' butonunu kullanın.", 404
    with open(site_path, encoding="utf-8") as f:
        return f.read()


@app.route("/deploy/<slug>", methods=["POST"])
def deploy(slug):
    """GitHub Pages'e push et."""
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN ve GITHUB_REPO gerekli (.env dosyasını kontrol edin)"}), 400

    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404

    site_path = os.path.join(config.OUTPUT_DIR, slug, "index.html")
    if not os.path.exists(site_path):
        return jsonify({"error": "Önce site üretin"}), 400

    try:
        from deploy import push_to_github_pages
        url = push_to_github_pages(
            site_dir=os.path.join(config.OUTPUT_DIR, slug),
            repo=config.GITHUB_REPO,
            token=config.GITHUB_TOKEN,
            branch=f"site/{slug}",
            subdir=slug,
        )
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/csv")
def export_csv():
    """İşletmeleri iletişim bilgileriyle CSV olarak indir."""
    businesses = _state["businesses"] or _load_businesses()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["İşletme Adı", "Kategori", "Adres", "Telefon", "Instagram", "Puan", "Yorum Sayısı", "Google Maps"])

    for b in businesses:
        writer.writerow([
            b.name, b.category, b.address, b.phone,
            f"@{b.instagram_handle}" if b.instagram_handle else "",
            b.rating, b.review_count, b.google_maps_url,
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"isletmeler_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    )


@app.route("/clear", methods=["POST"])
def clear():
    _state["businesses"] = []
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)
