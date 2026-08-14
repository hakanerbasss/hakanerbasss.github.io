"""
SiteBot uçtan uca duman testi.

GitHub ve Cloudflare çağrıları taklit edilir — gerçek repo açılmaz, gerçek
DNS kaydı oluşturulmaz, hiçbir anahtara ihtiyaç yoktur. Sunucuya deploy
etmeden önce çalıştır:

    cd sitebot && .venv/bin/python test_smoke.py
"""
import asyncio, json, os, sys, tempfile, pathlib
tmp = pathlib.Path(tempfile.mkdtemp())
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import config
config.SETTINGS_PATH = tmp/"settings.json"
config.DB_PATH = tmp/"sitebot.db"
config.UPLOAD_DIR = tmp/"uploads"
config._cache = None
config.save({"github_token":"gh_test","cloudflare_token":"cf_test",
             "cloudflare_zone_id":"zone1","github_org":"wizaicorp",
             "root_domain":"wizaicorp.com","panel_domain":"kur.wizaicorp.com"})

import db; db.DB_PATH = config.DB_PATH
import images; images.UPLOAD_DIR = config.UPLOAD_DIR
import github_api, cloudflare_api
PUSHED = {}
async def fake_repo_exists(repo): return False
async def fake_create_repo(repo, desc): return {"name":repo}
async def fake_push(repo, files, msg, branch="main"):
    PUSHED[repo] = files; return "abc1234def"
async def fake_pages(repo, branch="main"): return {"status":"building"}
async def fake_domain(repo, domain, https=True): return None
async def fake_cname(sub, target, proxied=None): return {"id":"r1"}
github_api.repo_exists=fake_repo_exists; github_api.create_repo=fake_create_repo
github_api.push_files=fake_push; github_api.enable_pages=fake_pages
github_api.set_custom_domain=fake_domain; cloudflare_api.upsert_cname=fake_cname

import app as appmod
from fastapi.testclient import TestClient
db.init()
config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
_tc = TestClient(appmod.app)
_tc.__enter__()
c = _tc

# 1) ilk kurulum
r = c.post("/api/super/setup", json={"username":"hakan","password":"cokgizli123"})
assert r.status_code==200, r.text
SUP = {"Authorization":"Bearer "+r.json()["token"]}
print("1) süper yönetici kuruldu")

# 2) slug kontrolü — Türkçe karakter ASCII'ye inmeli
r = c.post("/api/super/slug-check", json={"value":"Hurdacı Ali Ticaret"}, headers=SUP)
assert r.json()["slug"]=="hurdaci-ali-ticaret", r.json()
r2 = c.post("/api/super/slug-check", json={"value":"panel"}, headers=SUP)
assert r2.json()["uygun"] is False
print("2) slug:", r.json()["domain"], "| ayrılmış ad reddedildi:", r2.json()["sebep"][:40])

# 3) site aç
r = c.post("/api/super/sites", json={"title":"Hurdacı Ali","slug":"hurdaci",
    "template":"hizmet","email":"ali@ornek.com","phone":"0532 111 22 33"}, headers=SUP)
assert r.status_code==200, r.text
site = r.json(); PW = site["password"]
print("3) site açıldı:", site["domain"], "| şifre:", PW)
import time
for _ in range(40):
    time.sleep(0.5)
    if db.get_site(site["id"])["status"] != "kuruluyor": break
print("   kurulum durumu:", db.get_site(site["id"])["status"])

# 4) müşteri girişi
r = c.post("/api/admin/login", json={"slug":"hurdaci","email":"ali@ornek.com","password":PW})
assert r.status_code==200, r.text
AD = {"Authorization":"Bearer "+r.json()["token"]}
print("4) müşteri girişi tamam")

# 4b) yanlış şifre + başka sitenin oturumu reddedilmeli
assert c.post("/api/admin/login", json={"slug":"hurdaci","email":"ali@ornek.com","password":"yanlis"}).status_code==401
assert c.get("/api/admin/me").status_code==401
print("4b) yetkisiz erişim engellendi")

# 5) içerik kaydet
me = c.get("/api/admin/me", headers=AD).json()
content = me["content"]
content["site"]["title"]="Hurdacı Ali Geri Dönüşüm"
content["theme"]["preset"]="okyanus"
content["products"]=[{"id":"","name":"Hurda Bakır","desc":"kilo","price":"285","currency":"₺/kg",
                      "category":"Metal","badge":"Yeni","link":"","images":[]}]
r = c.put("/api/admin/content", json=content, headers=AD)
assert r.status_code==200, r.text
print("5) içerik kaydedildi | ürün sayısı:", len(r.json()["content"]["products"]))

# 6) görsel yükleme
from PIL import Image
import io
buf=io.BytesIO(); Image.new("RGB",(3000,2000),(200,80,40)).save(buf,"JPEG")
r = c.post("/api/admin/upload", files={"file":("foto.jpg",buf.getvalue(),"image/jpeg")},
           data={"kind":"photo"}, headers=AD)
assert r.status_code==200, r.text
asset = r.json()
print(f"6) görsel: {len(buf.getvalue())//1024} KB → {asset['bytes']//1024} KB ({asset['width']}x{asset['height']})")

# 7) önizleme
content["banner"]["image"]=asset["path"]
r = c.post("/api/admin/preview", json=content, headers=AD)
assert r.status_code==200 and "Hurda Bakır" in r.text
assert "/api/admin/asset/" in r.text, "önizlemede görsel yolu çevrilmemiş"
print("7) önizleme üretildi:", len(r.text), "bayt")

# 8) her üç şablon da aynı içerikle render olmalı
for t in ("hizmet","katalog","kurumsal"):
    content["theme"]["template"]=t
    rr = c.post("/api/admin/preview", json=content, headers=AD)
    assert rr.status_code==200 and "Hurda Bakır" in rr.text, t
print("8) üç şablon da aynı veriyle çalıştı (içerik kaybı yok)")

# 9) yayınla
c.put("/api/admin/content", json=content, headers=AD)
r = c.post("/api/admin/publish", headers=AD)
assert r.status_code==200, r.text
pub = r.json()
files = PUSHED["hurdaci"]
assert "index.html" in files and "admin/index.html" in files and "CNAME" in files
assert asset["path"] in files, "görsel aynı commit'e binmedi"
assert files["CNAME"].strip()=="hurdaci.wizaicorp.com"
assert "__API_BASE__" not in files["admin/index.html"], "admin paneli adresi yerleşmemiş"
assert "gh_test" not in json.dumps({k:v for k,v in files.items() if isinstance(v,str)}), "SIZINTI: token repoda!"
print(f"9) yayın: {pub['files']} dosya, {pub['assets']} görsel, tek commit {pub['commit'][:7]}")

# 10) kilit
sid = site["id"]
c.post(f"/api/super/sites/{sid}/lock", json={"locked":True}, headers=SUP)
assert c.post("/api/admin/login", json={"slug":"hurdaci","email":"ali@ornek.com","password":PW}).status_code==403
print("10) abonelik kilidi çalışıyor (site yayında kalır, panel kapanır)")

print("\n✅ hepsi geçti")
