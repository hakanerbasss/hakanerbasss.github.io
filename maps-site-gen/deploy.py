"""
Üretilen siteleri GitHub Pages veya başka bir hedefe deploy eder.

GitHub Pages için iki mod:
  - gh-pages branch: Klasördeki tüm içeriği gh-pages branch'ine push eder
  - Subdirectory: Mevcut repoya bir klasör olarak ekler

Kullanım:
  python deploy.py --output output/ --repo kullanici/repo --branch gh-pages
"""

import os
import subprocess
import shutil
import tempfile
import click
import config


def _run(cmd: str, cwd: str = None):
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Komut başarısız: {cmd}\n{result.stderr}")
    return result.stdout.strip()


@click.command()
@click.option("--output", "-o", default=config.OUTPUT_DIR, help="Kaynak klasör (generate çıktısı)")
@click.option("--repo", "-r", default=config.GITHUB_REPO, help="GitHub repo (kullanici/repo)")
@click.option("--branch", "-b", default="gh-pages", help="Hedef branch")
@click.option("--token", "-t", default=None, help="GitHub token (opsiyonel, env:GITHUB_TOKEN)")
@click.option("--message", "-m", default="Deploy: maps-site-gen siteler güncellendi", help="Commit mesajı")
def deploy_gh_pages(output, repo, branch, token, message):
    """Çıktı klasörünü GitHub Pages branch'ine push eder."""

    if not repo:
        click.echo("[!] --repo gerekli. Örn: --repo kullanici/repo")
        raise SystemExit(1)

    if not os.path.isdir(output):
        click.echo(f"[!] Klasör bulunamadı: {output}")
        raise SystemExit(1)

    token = token or config.GITHUB_TOKEN
    if token:
        remote_url = f"https://{token}@github.com/{repo}.git"
    else:
        remote_url = f"https://github.com/{repo}.git"

    click.echo(f"[Deploy] {repo} → {branch} branch'ine deploy ediliyor...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Geçici git repo kur
        _run("git init", tmpdir)
        _run(f"git remote add origin {remote_url}", tmpdir)
        _run('git config user.email "deploy@maps-site-gen.local"', tmpdir)
        _run('git config user.name "maps-site-gen"', tmpdir)

        # Çıktı dosyalarını kopyala
        for item in os.listdir(output):
            src = os.path.join(output, item)
            dst = os.path.join(tmpdir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # .nojekyll ekle (GitHub Pages Jekyll'i atla)
        open(os.path.join(tmpdir, ".nojekyll"), "w").close()

        # Commit ve push
        _run("git add -A", tmpdir)
        _run(f'git commit -m "{message}"', tmpdir)
        _run(f"git push --force origin HEAD:{branch}", tmpdir)

    site_url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}"
    click.echo(f"\n✅ Deploy tamamlandı!")
    click.echo(f"   URL: {site_url}")


@click.command()
@click.option("--output", "-o", default=config.OUTPUT_DIR)
@click.option("--port", "-p", default=8080, type=int)
def serve(output, port):
    """Üretilen siteleri yerel sunucuda önizler."""
    import http.server
    import socketserver

    os.chdir(output)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        click.echo(f"[Önizleme] http://localhost:{port}/")
        click.echo("  Durdurmak için: Ctrl+C")
        httpd.serve_forever()


@click.group()
def cli():
    """Deploy ve önizleme araçları."""
    pass


cli.add_command(deploy_gh_pages, name="gh-pages")
cli.add_command(serve, name="serve")

if __name__ == "__main__":
    cli()
