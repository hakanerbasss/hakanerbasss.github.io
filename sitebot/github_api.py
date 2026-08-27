"""
GitHub API istemcisi.

Önemli tasarım kararı: dosyalar Contents API ile tek tek değil, Git Data
API ile **tek commit** halinde gönderiliyor. GitHub Pages repo başına
saatte 10 build sınırı koyuyor; 20 ürün görselini 20 ayrı commit'le
göndermek bu sınırı ilk müşteride patlatırdı.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

import config

API = "https://api.github.com"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class GitHubError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    token = config.load()["github_token"]
    if not token:
        raise GitHubError("GitHub token tanımlı değil (settings.json → github_token).")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SiteBot/1.0",
    }


async def _req(client: httpx.AsyncClient, method: str, path: str,
               ok: tuple[int, ...] = (200, 201, 204), **kw: Any) -> Any:
    r = await client.request(method, f"{API}{path}", headers=_headers(), **kw)
    if r.status_code not in ok:
        detail = ""
        try:
            body = r.json()
            detail = body.get("message", "")
            if body.get("errors"):
                detail += f" — {body['errors']}"
        except ValueError:
            detail = r.text[:300]
        raise GitHubError(f"GitHub {method} {path} → {r.status_code}: {detail}")
    if r.status_code == 204 or not r.content:
        return {}
    return r.json()


async def owner_type() -> str:
    """Repoların açılacağı hesap organizasyon mu, normal kullanıcı mı?

    İkisi de destekleniyor ve repo açma adresleri farklı olduğu için bunu
    bilmek zorundayız. Sonuç önbelleğe alınıyor; ayarlar değişince sıfırlanır.
    """
    cfg = config.load()
    owner = cfg["github_org"]
    cached = _owner_type_cache.get(owner)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        data = await _req(c, "GET", f"/users/{owner}")
    kind = "Organization" if data.get("type") == "Organization" else "User"
    _owner_type_cache[owner] = kind
    return kind


_owner_type_cache: dict[str, str] = {}


async def check_token() -> dict[str, Any]:
    """Kurulum ekranı için: token geçerli mi, doğru hesaba mı bağlı?"""
    cfg = config.load()
    owner = cfg["github_org"]
    _owner_type_cache.pop(owner, None)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        me = await _req(c, "GET", "/user")
    kind = await owner_type()

    if kind == "User" and me.get("login", "").lower() != owner.lower():
        raise GitHubError(
            f"Token '{me.get('login')}' hesabına ait ama siteler '{owner}' "
            f"hesabında açılacak. Ya ayarlardaki hesap adını '{me.get('login')}' "
            f"yapın ya da '{owner}' hesabına girip oradan token üretin."
        )
    # Token gerçekten depo açabiliyor mu? Sahte bir istekle önden dene —
    # yetkisi yoksa müşteri bilgilerini girdikten sonra değil, burada öğrenelim.
    yetki = "bilinmiyor"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        path = f"/orgs/{owner}/repos" if kind == "Organization" else "/user/repos"
        probe = await c.post(f"{API}{path}", headers=_headers(), json={"name": ""})
        if probe.status_code == 403:
            raise GitHubError(
                "Token bağlandı ama yeni depo açma yetkisi yok. GitHub'da token "
                "ayarlarında Repository access = 'All repositories' ve Permissions → "
                "Administration / Contents / Pages = 'Read and write' olmalı. "
                "Olmazsa 'Tokens (classic)' ile 'repo' + 'delete_repo' kapsamlı "
                "token üretin — o kesin çalışır."
            )
        # 422 = "isim boş olamaz" → yetki var, sadece veri geçersiz. Beklenen sonuç.
        yetki = "depo açabilir" if probe.status_code == 422 else f"HTTP {probe.status_code}"

    return {
        "login": me.get("login"),
        "org": owner,
        "tur": "organizasyon" if kind == "Organization" else "kullanıcı hesabı",
        "yetki": yetki,
    }


async def repo_exists(repo: str) -> bool:
    cfg = config.load()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{API}/repos/{cfg['github_org']}/{repo}", headers=_headers())
        return r.status_code == 200


async def create_repo(repo: str, description: str) -> dict[str, Any]:
    """Org altında public repo aç.

    GitHub Pages ücretsiz planda yalnızca public repolarda çalışıyor.
    Repo'da hiçbir gizli bilgi tutmuyoruz — admin paneli de sadece
    API'ye konuşan statik bir arayüz.
    """
    cfg = config.load()
    payload = {
        "name": repo,
        "description": description[:300],
        "private": False,
        "auto_init": True,                    # ilk commit'i GitHub atsın, ref hazır olsun
        "has_issues": False,
        "has_projects": False,
        "has_wiki": False,
    }
    # Organizasyon ve kullanıcı hesabının repo açma adresleri farklı.
    kind = await owner_type()
    path = f"/orgs/{cfg['github_org']}/repos" if kind == "Organization" else "/user/repos"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        try:
            return await _req(c, "POST", path, json=payload)
        except GitHubError as exc:
            # GitHub bu durumda sadece "Resource not accessible" diyor; sebebi
            # neredeyse her zaman token'ın repo açma yetkisinin olmaması.
            if "403" in str(exc):
                raise GitHubError(
                    "Token yeni depo açamıyor. GitHub'da token ayarlarını kontrol edin: "
                    "Repository access = 'All repositories' olmalı ve Permissions altında "
                    "Administration, Contents, Pages = 'Read and write' seçili olmalı. "
                    "Fine-grained token çalışmazsa 'Tokens (classic)' ile 'repo' + "
                    "'delete_repo' kapsamlı bir token üretin — o kesin çalışır."
                ) from exc
            raise


async def push_files(repo: str, files: dict[str, bytes | str], message: str,
                     branch: str = "main") -> str:
    """Birden çok dosyayı TEK commit ile gönder. Dönen değer: commit sha."""
    cfg = config.load()
    owner = cfg["github_org"]
    base = f"/repos/{owner}/{repo}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        ref = await _req(c, "GET", f"{base}/git/ref/heads/{branch}")
        head_sha = ref["object"]["sha"]
        head_commit = await _req(c, "GET", f"{base}/git/commits/{head_sha}")
        base_tree = head_commit["tree"]["sha"]

        tree_items = []
        for path, content in files.items():
            if isinstance(content, str):
                blob = await _req(c, "POST", f"{base}/git/blobs",
                                  json={"content": content, "encoding": "utf-8"})
            else:
                blob = await _req(
                    c, "POST", f"{base}/git/blobs",
                    json={"content": base64.b64encode(content).decode(),
                          "encoding": "base64"},
                )
            tree_items.append({"path": path, "mode": "100644",
                               "type": "blob", "sha": blob["sha"]})

        tree = await _req(c, "POST", f"{base}/git/trees",
                          json={"base_tree": base_tree, "tree": tree_items})
        commit = await _req(c, "POST", f"{base}/git/commits",
                            json={"message": message[:500],
                                  "tree": tree["sha"], "parents": [head_sha]})
        await _req(c, "PATCH", f"{base}/git/refs/heads/{branch}",
                   json={"sha": commit["sha"], "force": False})
        return commit["sha"]


async def delete_paths(repo: str, paths: list[str], message: str,
                       branch: str = "main") -> str | None:
    """Silinen görselleri repodan tek commit'le kaldır."""
    if not paths:
        return None
    cfg = config.load()
    owner = cfg["github_org"]
    base = f"/repos/{owner}/{repo}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        ref = await _req(c, "GET", f"{base}/git/ref/heads/{branch}")
        head_sha = ref["object"]["sha"]
        head_commit = await _req(c, "GET", f"{base}/git/commits/{head_sha}")

        tree_items = [{"path": p, "mode": "100644", "type": "blob", "sha": None}
                      for p in paths]
        tree = await _req(c, "POST", f"{base}/git/trees",
                          json={"base_tree": head_commit["tree"]["sha"], "tree": tree_items})
        commit = await _req(c, "POST", f"{base}/git/commits",
                            json={"message": message[:500],
                                  "tree": tree["sha"], "parents": [head_sha]})
        await _req(c, "PATCH", f"{base}/git/refs/heads/{branch}",
                   json={"sha": commit["sha"], "force": False})
        return commit["sha"]


async def enable_pages(repo: str, branch: str = "main") -> dict[str, Any]:
    cfg = config.load()
    base = f"/repos/{cfg['github_org']}/{repo}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{API}{base}/pages", headers=_headers(),
                         json={"source": {"branch": branch, "path": "/"}})
        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 409:                  # zaten açık
            return await _req(c, "GET", f"{base}/pages")
        raise GitHubError(f"Pages açılamadı ({r.status_code}): {r.text[:300]}")


async def set_custom_domain(repo: str, domain: str, https: bool = True) -> None:
    """Repo'nun Pages alan adını ayarla ve HTTPS'i zorla.

    HTTPS zorlaması sertifika üretilmeden önce reddedilebiliyor; bu
    normal, sertifika hazır olunca provisioner tekrar deniyor.
    """
    cfg = config.load()
    base = f"/repos/{cfg['github_org']}/{repo}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        await _req(c, "PUT", f"{base}/pages", ok=(200, 204),
                   json={"cname": domain})
        if https:
            r = await c.put(f"{API}{base}/pages", headers=_headers(),
                            json={"https_enforced": True})
            if r.status_code not in (200, 204, 400, 422):
                raise GitHubError(f"HTTPS zorlanamadı ({r.status_code}): {r.text[:200]}")


async def pages_status(repo: str) -> dict[str, Any]:
    cfg = config.load()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.get(f"{API}/repos/{cfg['github_org']}/{repo}/pages",
                        headers=_headers())
        if r.status_code == 404:
            return {"status": "yok"}
        if r.status_code != 200:
            return {"status": "bilinmiyor", "detail": r.text[:200]}
        data = r.json()
        cert = (data.get("https_certificate") or {}).get("state", "")
        return {
            "status": data.get("status"),
            "url": data.get("html_url"),
            "cname": data.get("cname"),
            "https_enforced": data.get("https_enforced"),
            "certificate": cert,
        }


async def delete_repo(repo: str) -> None:
    cfg = config.load()
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        await _req(c, "DELETE", f"/repos/{cfg['github_org']}/{repo}", ok=(204, 404))
