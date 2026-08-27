#!/usr/bin/env bash
# SiteBot kendi sanal ortamini kurar. Sistem Python'una asla dokunma —
# sunucudaki diger projeleri (firebase-admin vb.) kirar.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "Tamam. Servis: systemctl restart sitebot"
