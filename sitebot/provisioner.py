"""
Site kurma ve yayınlama akışı.

Kurulum (~60 sn):
  repo aç → dosyaları bas → Pages'i aç → alan adını bağla → DNS kaydı

Yayınlama:
  taslaktan HTML üret → bekleyen görsellerle birlikte TEK commit → Pages derler

Her adım veritabanına yazılıyor; panel bu günlüğü canlı gösteriyor, böylece
bir şey ters gittiğinde nerede durduğu belli oluyor.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import cloudflare_api as cf
import config
import db
import github_api as gh
import images
import renderer

PANEL_DIR = Path(__file__).resolve().parent / "panel"

# Arka plan kurulum görevlerine referans tutuyoruz: asyncio yalnızca zayıf
# referans tuttuğu için, tutmazsak görev iş bitmeden çöp toplayıcıya gidebilir.
_tasks: set[asyncio.Task] = set()


def start_provision(site_id: int) -> asyncio.Task:
    task = asyncio.create_task(provision(site_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


# ------------------------------------------------------------------ günlük

def _log(site_id: int, step: str, ok: bool = True, detail: str = "") -> None:
    site = db.get_site(site_id)
    if not site:
        return
    entries = json.loads(site["provision_log"] or "[]")
    entries.append({"t": int(time.time()), "step": step, "ok": ok, "detail": detail[:400]})
    db.update_site(site_id, provision_log=json.dumps(entries[-40:], ensure_ascii=False))
    db.log(site_id, "kurulum" if ok else "hata", f"{step} — {detail}"[:400])


# ----------------------------------------------------------- admin arayüzü

def admin_bundle(slug: str) -> dict[str, str]:
    """Müşterinin reposuna gidecek admin sayfası.

    Panelin kendisi BURAYA gömülmüyor — bir bakım yaptığımızda her
    müşterinin tekrar "Yayınla" demesini beklemek yerine, bu ince kabuk
    en güncel paneli sunucudan (kur.wizaicorp.com) her açılışta canlı
    çekiyor. Adres çubuğunda müşterinin kendi alan adı görünmeye devam
    ediyor — "kendi paneli" hissi bozulmuyor — ama içerik hep taze:
    panel düzeltmeleri artık HİÇBİR siteyi yeniden yayınlamadan anında
    herkese ulaşıyor.

    Sunucuya erişilemezse (bakım, ağ sorunu) doğrudan bağlantı veren bir
    yedek mesaj gösteriliyor; site adminsiz de yayında kalmaya devam
    eder, sadece o an düzenlenemez.
    """
    cfg = config.load()
    panel_url = f"https://{cfg['panel_domain']}/panel/{slug}"
    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Site Yönetimi</title>
<style>
*,*::before,*::after{{box-sizing:border-box}}
html,body{{margin:0;height:100%;background:#0c1018}}
iframe{{position:fixed;inset:0;width:100%;height:100%;border:0;background:#0c1018}}
.fb{{position:fixed;inset:0;display:none;place-items:center;padding:24px;text-align:center;
  background:#0c1018;color:#e9edf6;font:15px/1.6 -apple-system,'Segoe UI',sans-serif}}
.fb a{{color:#5b8cff;font-weight:700}}
</style></head>
<body>
<iframe id="pf" src="{panel_url}" title="Site Yönetimi"></iframe>
<div class="fb" id="fb"><div>Panel şu an yüklenemedi.<br><br>
  <a href="{panel_url}" target="_top">Buraya tıklayıp doğrudan açın →</a></div></div>
<script>
  var t=setTimeout(function(){{document.getElementById('fb').style.display='grid'}},8000);
  document.getElementById('pf').addEventListener('load',function(){{clearTimeout(t)}});
</script>
</body></html>"""
    return {
        "admin/index.html": html,
        "admin/.nojekyll": "",
    }


# --------------------------------------------------------------- yayınlama

async def publish(site_id: int, message: str = "") -> dict[str, Any]:
    """Taslağı canlıya al. Değişmemiş dosyayı göndermeyerek boş commit'i önler."""
    site = db.get_site(site_id)
    if not site:
        raise RuntimeError("Site bulunamadı.")

    data = db.draft_of(site)
    domain = site["custom_domain"] or site["domain"]

    files: dict[str, bytes | str] = dict(
        renderer.render_site(data, domain, admin_bundle(site["slug"]))
    )

    # Yeni yüklenen görseller aynı commit'e binsin.
    used = images.used_paths(data)
    pushed_paths: list[str] = []
    for asset in db.pending_assets(site_id):
        if asset["path"] not in used:
            continue                       # yüklenmiş ama kullanılmayan görseli gönderme
        blob = images.read(site_id, asset["path"])
        if blob:
            files[asset["path"]] = blob
            pushed_paths.append(asset["path"])

    sha = await gh.push_files(
        site["repo"],
        files,
        message or f"Site güncellendi — {time.strftime('%d.%m.%Y %H:%M')}",
    )
    db.mark_assets_pushed(site_id, pushed_paths)

    # Silinen ürünlerin sayfaları depoda kalmamalı; kalırsa ürün panelden
    # kaldırılsa bile Google'da ve doğrudan adresten açılmaya devam eder.
    if site["live_json"]:
        try:
            eski = renderer.product_page_paths(json.loads(site["live_json"]))
            artik = sorted(eski - renderer.product_page_paths(data))
            if artik:
                await gh.delete_paths(site["repo"], artik, "Kaldırılan ürün sayfaları")
                db.log(site_id, "yayin", f"{len(artik)} ürün sayfası silindi")
        except (ValueError, gh.GitHubError) as exc:
            db.log(site_id, "hata", f"eski ürün sayfaları silinemedi: {exc}")
    db.update_site(
        site_id,
        live_json=site["draft_json"],
        published_at=db.now(),
        status="yayinda",
    )
    db.log(site_id, "yayin", f"commit {sha[:7]} — {len(files)} dosya")
    return {"commit": sha, "files": len(files), "assets": len(pushed_paths)}


# ------------------------------------------------------------------ kurulum

async def provision(site_id: int) -> None:
    """Sıfırdan site kur. Hata olursa site 'hata' durumunda kalır, tekrar denenebilir."""
    site = db.get_site(site_id)
    if not site:
        return
    cfg = config.load()
    slug, repo, domain = site["slug"], site["repo"], site["domain"]

    try:
        db.update_site(site_id, status="kuruluyor")

        # 1) Repo
        if await gh.repo_exists(repo):
            _log(site_id, "GitHub deposu zaten vardı, üzerine yazılıyor")
        else:
            await gh.create_repo(repo, f"{site['title']} — {domain}")
            _log(site_id, "GitHub deposu açıldı", detail=f"{cfg['github_org']}/{repo}")
            await asyncio.sleep(2)          # auto_init commit'inin oturması için

        # 2) Dosyalar
        data = db.draft_of(site)
        files = dict(renderer.render_site(data, domain, admin_bundle(slug)))
        await gh.push_files(repo, files, "İlk yayın — SiteBot")
        _log(site_id, "Site dosyaları yüklendi", detail=f"{len(files)} dosya")

        # 3) Pages
        await gh.enable_pages(repo)
        _log(site_id, "GitHub Pages açıldı")

        # 4) DNS — alan adını bağlamadan önce kaydın var olması gerekiyor
        await cf.upsert_cname(slug, cfg["github_pages_host"])
        proxy = "Cloudflare korumalı" if cfg["cloudflare_proxied"] else "doğrudan"
        _log(site_id, "DNS kaydı oluşturuldu", detail=f"{domain} → {cfg['github_pages_host']} ({proxy})")

        # 5) Özel alan adı + HTTPS
        await asyncio.sleep(3)
        try:
            await gh.set_custom_domain(repo, domain)
            _log(site_id, "Alan adı ve HTTPS ayarlandı", detail=domain)
        except gh.GitHubError as exc:
            # Sertifika henüz üretilmemiş olabilir; site yine de açılır.
            _log(site_id, "Alan adı bağlandı, HTTPS beklemede", detail=str(exc))

        db.update_site(site_id, status="yayinda", live_json=site["draft_json"],
                       published_at=db.now())
        _log(site_id, "Site yayında", detail=f"https://{domain}")
        await notify(f"✅ Yeni site yayında: https://{domain}")

    except Exception as exc:                       # noqa: BLE001 — panelde göstereceğiz
        db.update_site(site_id, status="hata")
        _log(site_id, "Kurulum durdu", ok=False, detail=f"{type(exc).__name__}: {exc}")
        await notify(f"⚠️ Site kurulamadı ({site['domain']}): {exc}")


async def teardown(site_id: int, delete_repo: bool = True) -> dict[str, Any]:
    """Siteyi tamamen kaldır: DNS kaydı + repo + veritabanı kaydı."""
    site = db.get_site(site_id)
    if not site:
        return {"ok": False}
    result: dict[str, Any] = {}
    try:
        result["dns"] = await cf.delete_cname(site["slug"])
    except cf.CloudflareError as exc:
        result["dns_error"] = str(exc)
    if delete_repo:
        try:
            await gh.delete_repo(site["repo"])
            result["repo"] = True
        except gh.GitHubError as exc:
            result["repo_error"] = str(exc)
    db.delete_site(site_id)
    return result


async def health(site_id: int) -> dict[str, Any]:
    """Panelin 'sitem gerçekten ayakta mı' rozeti için."""
    site = db.get_site(site_id)
    if not site:
        return {}
    out: dict[str, Any] = {"domain": site["domain"], "status": site["status"]}
    # Durum sorgusu hiçbir koşulda hata döndürmemeli: GitHub ya da Cloudflare
    # ulaşılamıyorsa bile panel açılmaya devam etsin, sadece "bilinmiyor" yazsın.
    try:
        out["pages"] = await gh.pages_status(site["repo"])
    except Exception as exc:                          # noqa: BLE001
        out["pages"] = {"status": "bilinmiyor", "detail": str(exc)[:200]}
    try:
        rec = await cf.find_record(site["custom_domain"] or site["domain"])
        out["dns"] = {"var": bool(rec), "proxied": rec.get("proxied") if rec else None}
    except Exception as exc:                          # noqa: BLE001
        out["dns"] = {"var": None, "detail": str(exc)[:200]}
    return out


# --------------------------------------------------------------- bildirim

async def notify(text: str) -> None:
    """Telegram bildirimi — ayarlanmamışsa sessizce atlanır."""
    cfg = config.load()
    token, chat = cfg.get("telegram_token"), cfg.get("telegram_chat_id")
    if not (token and chat):
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat, "text": text})
    except httpx.HTTPError:
        pass
