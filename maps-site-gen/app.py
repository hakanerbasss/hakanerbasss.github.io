"""
Flask web uygulaması — Google Maps işletme bulucu + site üretici.
"""

import json
import os
import threading
import csv
import io
import traceback

# .env dosyasını yükle (varsa)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
import config
from scraper import BusinessInfo, find_businesses_without_website, save_json, load_json
from generator import generate_business_site
import instagram as ig

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET

_state = {
    "searching": False,
    "progress": {"current": 0, "total": 0, "name": ""},
    "businesses": [],
    "error": "",
    "last_search": None,  # Son arama bilgisi
    "log": [],            # Debug log satırları
}

DATA_FILE = os.path.join(config.OUTPUT_DIR, "businesses.json")


def _log(msg: str):
    print(msg)
    _state["log"].append(msg)
    if len(_state["log"]) > 100:
        _state["log"] = _state["log"][-100:]


def _load_businesses():
    if os.path.exists(DATA_FILE):
        try:
            return load_json(DATA_FILE)
        except Exception:
            pass
    return []


def _save_businesses(businesses):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    save_json(businesses, DATA_FILE)


# ─── SAYFALAR ─────────────────────────────────────────────────────

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

    query    = request.form.get("query", "").strip()
    location = request.form.get("location", "").strip()
    max_n    = int(request.form.get("max", config.MAX_BUSINESSES))

    if not query:
        return jsonify({"error": "Arama terimi gerekli"}), 400

    _state["searching"]   = True
    _state["error"]       = ""
    _state["businesses"]  = []
    _state["log"]         = []
    _state["last_search"] = {"query": query, "location": location, "max": max_n}
    _state["progress"]    = {"current": 0, "total": 0, "name": "Başlatılıyor..."}

    def run():
        def progress_cb(cur, tot, name):
            _state["progress"] = {"current": cur, "total": tot, "name": name or "..."}

        try:
            _log(f"[Arama] '{query}' @ '{location}', max={max_n}")
            results = find_businesses_without_website(query, location, max_n, progress_cb)
            _log(f"[Arama] Tamamlandı — {len(results)} işletme bulundu")
            _state["businesses"] = results
            if results:
                _save_businesses(results)
            else:
                _state["error"] = (
                    f"'{query}' araması için '{location or 'belirtilmemiş konum'}' "
                    f"yakınında web sitesi olmayan işletme bulunamadı. "
                    f"Farklı bir kategori veya konum deneyin."
                )
        except Exception as e:
            err = traceback.format_exc()
            _log(f"[HATA] {err}")
            _state["error"] = f"Arama hatası: {str(e)}"
        finally:
            _state["searching"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    return jsonify({
        "searching": _state["searching"],
        "progress":  _state["progress"],
        "count":     len(_state["businesses"]),
        "error":     _state["error"],
        "log_tail":  _state["log"][-5:],
    })


@app.route("/businesses")
def businesses():
    biz = _state["businesses"] or _load_businesses()
    _state["businesses"] = biz
    last = _state.get("last_search")
    return render_template("app/businesses.html", businesses=biz, last_search=last)


@app.route("/business/<slug>")
def business_detail(slug):
    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return "İşletme bulunamadı", 404

    if b.instagram_handle and not b.instagram_posts:
        try:
            ig_profile = ig.fetch_profile(b.instagram_handle)
            b.instagram_posts    = ig_profile.posts
            b.instagram_bio      = ig_profile.bio
            b.instagram_followers = ig_profile.followers
            _save_businesses(businesses)
        except Exception:
            pass

    site_exists = os.path.exists(os.path.join(config.OUTPUT_DIR, slug, "index.html"))
    return render_template("app/business_detail.html", business=b, site_exists=site_exists)


@app.route("/generate/<slug>", methods=["POST"])
def generate(slug):
    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404
    try:
        tpl_dir = os.path.join(os.path.dirname(__file__), "templates", "site")
        generate_business_site(b, config.OUTPUT_DIR, tpl_dir)
        return jsonify({"ok": True, "slug": slug})
    except Exception as e:
        return jsonify({"error": traceback.format_exc()}), 500


@app.route("/preview/<slug>")
def preview(slug):
    path = os.path.join(config.OUTPUT_DIR, slug, "index.html")
    if not os.path.exists(path):
        return "Site henüz üretilmedi.", 404
    with open(path, encoding="utf-8") as f:
        return f.read()


@app.route("/deploy/<slug>", methods=["POST"])
def deploy(slug):
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN ve GITHUB_REPO .env dosyasında eksik"}), 400
    businesses = _state["businesses"] or _load_businesses()
    b = next((x for x in businesses if x.slug == slug), None)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404
    if not os.path.exists(os.path.join(config.OUTPUT_DIR, slug, "index.html")):
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
    businesses = _state["businesses"] or _load_businesses()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["İşletme Adı", "Kategori", "Adres", "Telefon", "Instagram", "Google Maps"])
    for b in businesses:
        w.writerow([b.name, b.category, b.address, b.phone,
                    f"@{b.instagram_handle}" if b.instagram_handle else "",
                    b.google_maps_url])
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
    _state["last_search"] = None
    _state["error"] = ""
    if os.path.exists(DATA_FILE):
        os.remove(DATA_FILE)
    return redirect(url_for("index"))


# ─── DEBUG ────────────────────────────────────────────────────────

@app.route("/debug")
def debug():
    """Bağlantı ve scraper testleri."""
    results = {}

    # Overpass bağlantısı
    try:
        import requests as req
        r = req.get("https://overpass-api.de/api/status", timeout=8)
        results["overpass"] = f"✓ Bağlı (HTTP {r.status_code})"
    except Exception as e:
        results["overpass"] = f"✗ BAĞLANAMADI: {e}"

    # Nominatim bağlantısı
    try:
        import requests as req
        r = req.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": "Istanbul", "format": "json", "limit": 1},
            headers={"User-Agent": "maps-site-gen/1.0"},
            timeout=8,
        )
        data = r.json()
        results["nominatim"] = f"✓ Bağlı — Istanbul: {data[0]['lat'] if data else 'veri yok'}"
    except Exception as e:
        results["nominatim"] = f"✗ BAĞLANAMADI: {e}"

    # Küçük Overpass sorgusu
    try:
        import requests as req
        q = '[out:json][timeout:10];node["amenity"="cafe"][!"website"](around:2000,41.0082,28.9784);out body 3;'
        r = req.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=15)
        els = r.json().get("elements", [])
        results["overpass_query"] = f"✓ Test sorgusu — {len(els)} kafe bulundu (İstanbul merkezi)"
    except Exception as e:
        results["overpass_query"] = f"✗ SORGU HATASI: {e}"

    results["log"] = _state["log"][-20:] or ["(log boş)"]
    results["last_search"] = _state.get("last_search")
    results["business_count"] = len(_state["businesses"])

    html = "<h2>Debug</h2><pre style='font-family:monospace;font-size:14px;background:#111;color:#eee;padding:1.5rem;border-radius:8px;'>"
    for k, v in results.items():
        if isinstance(v, list):
            html += f"\n{k}:\n"
            for line in v:
                html += f"  {line}\n"
        else:
            html += f"{k}: {v}\n"
    html += "</pre>"
    html += '<br><a href="/" style="color:#4f6ef7;">← Ana Sayfa</a>'
    return html


if __name__ == "__main__":
    print(f"\n✅ maps-site-gen başlatıldı → http://127.0.0.1:{config.FLASK_PORT}/")
    print(f"   Debug: http://127.0.0.1:{config.FLASK_PORT}/debug\n")
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)
