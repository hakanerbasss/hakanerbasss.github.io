"""
Flask web uygulaması — Google Maps işletme bulucu + site üretici.
"""

import json, os, threading, csv, io, traceback, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config
from scraper import BusinessInfo, find_businesses_without_website, save_json, load_json
from generator import generate_business_site

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET

_state = {
    "searching":   False,
    "progress":    {"current": 0, "total": 0, "name": ""},
    "businesses":  [],
    "error":       "",
    "last_search": None,
    "log":         [],
}

DATA_FILE = os.path.join(config.OUTPUT_DIR, "businesses.json")


def _log(msg):
    print(msg)
    _state["log"].append(msg)
    if len(_state["log"]) > 200:
        _state["log"] = _state["log"][-200:]


def _load():
    if os.path.exists(DATA_FILE):
        try:
            return load_json(DATA_FILE)
        except Exception:
            pass
    return []


def _save(businesses):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    save_json(businesses, DATA_FILE)


def _get_biz(slug=None):
    biz = _state["businesses"] or _load()
    _state["businesses"] = biz
    if slug:
        return biz, next((b for b in biz if b.slug == slug), None)
    return biz


# ─── ANA SAYFALAR ─────────────────────────────────────────────────

@app.route("/")
def index():
    biz = _get_biz()
    return render_template("app/index.html", businesses=biz,
                           searching=_state["searching"], error=_state["error"])


@app.route("/businesses")
def businesses():
    biz = _get_biz()
    return render_template("app/businesses.html", businesses=biz,
                           last_search=_state.get("last_search"))


@app.route("/business/<slug>")
def business_detail(slug):
    biz, b = _get_biz(slug)
    if not b:
        return "İşletme bulunamadı", 404
    site_exists = os.path.exists(os.path.join(config.OUTPUT_DIR, slug, "index.html"))
    return render_template("app/business_detail.html", business=b, site_exists=site_exists)


# ─── ARAMA ────────────────────────────────────────────────────────

@app.route("/search", methods=["POST"])
def search():
    if _state["searching"]:
        return jsonify({"error": "Arama zaten devam ediyor"}), 400

    query    = request.form.get("query", "").strip()
    location = request.form.get("location", "").strip()
    max_n    = int(request.form.get("max", config.MAX_BUSINESSES))

    if not query:
        return jsonify({"error": "Arama terimi gerekli"}), 400

    _state.update({"searching": True, "error": "", "businesses": [],
                   "log": [], "last_search": {"query": query, "location": location},
                   "progress": {"current": 0, "total": 0, "name": "Başlatılıyor..."}})

    def run():
        def cb(cur, tot, name):
            _state["progress"] = {"current": cur, "total": tot, "name": name or "..."}
        try:
            _log(f"[Arama] '{query}' @ '{location}'")
            results = find_businesses_without_website(query, location, max_n, cb)
            _log(f"[Arama] Tamamlandı — {len(results)} işletme")
            _state["businesses"] = results
            if results:
                _save(results)
            else:
                _state["error"] = (
                    f"'{query}' için '{location or 'belirsiz konum'}' "
                    f"yakınında web sitesiz işletme bulunamadı. "
                    f"Farklı kategori veya konum deneyin."
                )
        except Exception as e:
            _log(f"[HATA] {traceback.format_exc()}")
            _state["error"] = f"Hata: {str(e)}"
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


# ─── INSTAGRAM ─────────────────────────────────────────────────────

@app.route("/fetch-instagram/<slug>", methods=["POST"])
def fetch_instagram(slug):
    """Instagram hesabını arar + gerçek fotoğrafları çeker."""
    biz, b = _get_biz(slug)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404

    handle = request.form.get("handle", "").strip().lstrip("@")

    import instagram as ig

    # Handle verilmediyse otomatik ara
    if not handle:
        handle = ig.find_instagram_handle(b.name, b.address)
        if not handle:
            return jsonify({"error": "Instagram hesabı bulunamadı. Hesap adını elle gir."}), 404

    # Profili çek
    profile = ig.fetch_profile(handle)
    if not profile.posts and not profile.bio:
        return jsonify({"error": f"@{handle} profili çekilemedi (gizli veya yok)."}), 400

    # İşletme verisini güncelle
    b.instagram_handle   = profile.handle
    b.instagram_bio      = profile.bio
    b.instagram_followers = profile.followers
    b.instagram_posts    = profile.posts

    # Gerçek Instagram fotoğraflarını photos listesine al
    real_photos = [p["thumbnail"] for p in profile.posts if p.get("thumbnail")]
    if real_photos:
        b.photos       = real_photos
        b.cover_photo  = real_photos[0]

    _save(biz)

    return jsonify({
        "ok":         True,
        "handle":     profile.handle,
        "followers":  profile.followers,
        "bio":        profile.bio,
        "post_count": len(profile.posts),
        "photos":     real_photos[:9],
        "profile_pic": profile.profile_pic,
    })


@app.route("/set-instagram/<slug>", methods=["POST"])
def set_instagram(slug):
    """Elle Instagram handle set eder (fetch tetiklemez)."""
    biz, b = _get_biz(slug)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404
    b.instagram_handle = request.form.get("handle", "").strip().lstrip("@")
    _save(biz)
    return jsonify({"ok": True})


# ─── SITE ÜRET / DÜZENLE ──────────────────────────────────────────

@app.route("/generate/<slug>", methods=["POST"])
def generate(slug):
    biz, b = _get_biz(slug)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404
    try:
        tpl = os.path.join(os.path.dirname(__file__), "templates", "site")
        generate_business_site(b, config.OUTPUT_DIR, tpl)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": traceback.format_exc()}), 500


@app.route("/edit/<slug>", methods=["GET"])
def edit(slug):
    """Site editörü sayfası."""
    biz, b = _get_biz(slug)
    if not b:
        return "İşletme bulunamadı", 404

    # Mevcut içeriği yükle (varsa override JSON)
    override = _load_override(slug)
    site_exists = os.path.exists(os.path.join(config.OUTPUT_DIR, slug, "index.html"))
    return render_template("app/edit.html", business=b, override=override,
                           site_exists=site_exists)


@app.route("/edit/<slug>", methods=["POST"])
def edit_save(slug):
    """Düzenlenen içeriği kaydeder ve siteyi yeniler."""
    biz, b = _get_biz(slug)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404

    data = request.get_json(force=True) or {}

    # İletişim bilgilerini güncelle
    if "phone"    in data: b.phone    = data["phone"]
    if "address"  in data: b.address  = data["address"]
    if "name"     in data: b.name     = data["name"]
    if "category" in data: b.category = data["category"]
    if "about"    in data: b.about    = data["about"]
    if "instagram_handle" in data:
        b.instagram_handle = data["instagram_handle"].lstrip("@")

    # Fotoğraf sırası
    if "photos" in data and isinstance(data["photos"], list):
        b.photos      = data["photos"]
        b.cover_photo = b.photos[0] if b.photos else ""

    # Çalışma saatleri
    if "hours" in data and isinstance(data["hours"], dict):
        b.hours = data["hours"]

    # AI içerik override'ı kaydet
    override = {}
    for key in ("headline", "tagline", "about_text", "services", "cta_text"):
        if key in data and data[key]:
            override[key] = data[key]

    _save_override(slug, override)
    _save(biz)

    # Siteyi yeniden üret
    try:
        tpl = os.path.join(os.path.dirname(__file__), "templates", "site")
        generate_business_site(b, config.OUTPUT_DIR, tpl, override=override)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": traceback.format_exc()}), 500


def _override_path(slug):
    return os.path.join(config.OUTPUT_DIR, slug, "override.json")


def _load_override(slug):
    p = _override_path(slug)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_override(slug, data):
    p = _override_path(slug)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/preview/<slug>")
def preview(slug):
    path = os.path.join(config.OUTPUT_DIR, slug, "index.html")
    if not os.path.exists(path):
        return "Site henüz üretilmedi.", 404
    with open(path, encoding="utf-8") as f:
        return f.read()


# ─── DEPLOY ───────────────────────────────────────────────────────

@app.route("/deploy/<slug>", methods=["POST"])
def deploy(slug):
    if not config.GITHUB_TOKEN or not config.GITHUB_REPO:
        return jsonify({"error": "GITHUB_TOKEN ve GITHUB_REPO .env dosyasında eksik"}), 400
    biz, b = _get_biz(slug)
    if not b:
        return jsonify({"error": "İşletme bulunamadı"}), 404
    if not os.path.exists(os.path.join(config.OUTPUT_DIR, slug, "index.html")):
        return jsonify({"error": "Önce siteyi üretin"}), 400
    try:
        from deploy import push_to_github_pages
        url = push_to_github_pages(
            site_dir=os.path.join(config.OUTPUT_DIR, slug),
            repo=config.GITHUB_REPO, token=config.GITHUB_TOKEN,
            branch=f"site/{slug}", subdir=slug,
        )
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── EXPORT ───────────────────────────────────────────────────────

@app.route("/export/csv")
def export_csv():
    biz = _get_biz()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["İşletme", "Kategori", "Adres", "Telefon", "Instagram", "Google Maps"])
    for b in biz:
        w.writerow([b.name, b.category, b.address, b.phone,
                    f"@{b.instagram_handle}" if b.instagram_handle else "",
                    b.google_maps_url])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode("utf-8-sig")),
                     mimetype="text/csv", as_attachment=True,
                     download_name=f"isletmeler_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv")


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
    from scraper import OVERPASS_MIRRORS
    import requests as req
    results = {}

    try:
        r = req.get("https://nominatim.openstreetmap.org/search",
                    params={"q": "Istanbul", "format": "json", "limit": 1},
                    headers={"User-Agent": "maps-site-gen/1.0"}, timeout=8)
        d = r.json()
        results["nominatim"] = f"✓ {d[0]['lat'] if d else 'veri yok'}"
    except Exception as e:
        results["nominatim"] = f"✗ {e}"

    q = '[out:json][timeout:10];\nnode["amenity"="cafe"][!"website"](around:2000,41.0082,28.9784);\nout body;\n'
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "maps-site-gen/1.0"}
    mirror_results = {}
    for mirror in OVERPASS_MIRRORS:
        try:
            r = req.post(mirror, data={"data": q}, headers=hdrs, timeout=12)
            if r.status_code == 200:
                els = r.json().get("elements", [])
                mirror_results[mirror] = f"✓ {len(els)} sonuç"
            else:
                mirror_results[mirror] = f"✗ HTTP {r.status_code}"
        except Exception as e:
            mirror_results[mirror] = f"✗ {e}"
    results["overpass_mirrors"] = mirror_results
    results["log"] = _state["log"][-20:] or ["(boş)"]
    results["last_search"] = _state.get("last_search")
    results["businesses"] = len(_state["businesses"])

    html = "<h2 style='font-family:sans-serif'>Debug</h2><pre style='font-family:monospace;font-size:13px;background:#111;color:#eee;padding:1.5rem;border-radius:8px;'>"
    for k, v in results.items():
        if isinstance(v, dict):
            html += f"\n{k}:\n"
            for kk, vv in v.items():
                html += f"  {kk}: {vv}\n"
        elif isinstance(v, list):
            html += f"\n{k}:\n" + "".join(f"  {l}\n" for l in v)
        else:
            html += f"{k}: {v}\n"
    html += f"</pre><br><a href='/' style='color:#4f6ef7'>← Ana Sayfa</a>"
    return html


if __name__ == "__main__":
    print(f"\n✅ http://127.0.0.1:{config.FLASK_PORT}/  |  debug: /debug\n")
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)
