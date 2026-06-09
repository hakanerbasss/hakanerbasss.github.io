"""
Üretilen siteleri GitHub Pages'e deploy eder.
"""

import os
import shutil
import subprocess
import tempfile
import config


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd}\n{r.stderr}")
    return r.stdout.strip()


def push_to_github_pages(
    site_dir: str,
    repo: str,
    token: str,
    branch: str = "gh-pages",
    subdir: str = "",
) -> str:
    """
    site_dir içeriğini GitHub repo'nun branch'ine push eder.
    subdir: repo içinde hangi alt klasöre koyulacak (boşsa root)
    Döner: site URL
    """
    remote = f"https://{token}@github.com/{repo}.git"

    with tempfile.TemporaryDirectory() as tmp:
        _run("git init", tmp)
        _run(f"git remote add origin {remote}", tmp)
        _run('git config user.email "bot@maps-site-gen"', tmp)
        _run('git config user.name "MapsSiteGen"', tmp)

        # Mevcut branch'i çekmeye çalış (var olmayabilir)
        try:
            _run(f"git fetch origin {branch} --depth=1", tmp)
            _run(f"git checkout {branch}", tmp)
        except RuntimeError:
            _run(f"git checkout --orphan {branch}", tmp)

        # Dosyaları kopyala
        dest = os.path.join(tmp, subdir) if subdir else tmp
        os.makedirs(dest, exist_ok=True)
        for item in os.listdir(site_dir):
            s = os.path.join(site_dir, item)
            d = os.path.join(dest, item)
            if os.path.isdir(s):
                if os.path.exists(d):
                    shutil.rmtree(d)
                shutil.copytree(s, d)
            else:
                shutil.copy2(s, d)

        # .nojekyll
        open(os.path.join(tmp, ".nojekyll"), "w").close()

        _run("git add -A", tmp)
        _run(f'git commit -m "Deploy: {subdir or repo}"', tmp)
        _run(f"git push --force origin HEAD:{branch}", tmp)

    owner = repo.split("/")[0]
    repo_name = repo.split("/")[1]
    page = f"https://{owner}.github.io/{repo_name}"
    if subdir:
        page += f"/{subdir}"
    return page
