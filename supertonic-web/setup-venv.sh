#!/bin/bash
# Supertonic'i kendi sanal ortamına (venv) taşır.
#
# NEDEN: Sunucuda tek bir sistem Python'u var ve birden fazla proje onu
# paylaşıyor. "pip install -r requirements.txt" çalıştırıldığında buradaki
# sabit sürümler diğer projelerin paketlerini geri düşürüyor — 05.08.2026'da
# httpx 0.28.1 -> 0.27.0 düşünce firebase-admin kırıldı.
#
# ÇÖZÜM: --system-site-packages ile venv. Kendi kurduğumuz paketler venv
# içinde kalır ve sistemdekileri GÖLGELER (sistemi değiştirmez); torch,
# whisper, TTS gibi ağır paketler sistemden okunmaya devam eder, yeniden
# indirilmez (~2 GB tasarruf).
#
# Kullanım (sunucuda, bir kez):
#   bash /root/hakanerbasss.github.io/supertonic-web/setup-venv.sh
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/tts.service"

echo "==> Uygulama dizini: $APP_DIR"

if [ ! -f "$APP_DIR/app.py" ]; then
  echo "HATA: $APP_DIR içinde app.py yok. Yanlış dizin." >&2
  exit 1
fi

echo "==> python3-venv kontrol ediliyor..."
if ! python3 -c "import venv" 2>/dev/null; then
  apt-get update -qq && apt-get install -y -qq python3-venv
fi

echo "==> Sanal ortam hazırlanıyor: $VENV_DIR"
if [ ! -d "$VENV_DIR" ]; then
  # --system-site-packages: torch/whisper/TTS sistemden okunur, tekrar inmez
  python3 -m venv --system-site-packages "$VENV_DIR"
else
  echo "    (zaten var, yeniden kullanılıyor)"
fi

echo "==> Bağımlılıklar venv içine kuruluyor (sistem Python'u değişmez)..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "==> Kurulum doğrulanıyor..."
"$VENV_DIR/bin/python" - <<'PY'
import sys
print(f"    python : {sys.executable}")
mods = ["fastapi", "uvicorn", "httpx", "openai", "edge_tts", "whisper", "supertonic"]
for m in mods:
    try:
        mod = __import__(m)
        v = getattr(mod, "__version__", "?")
        print(f"    ok     : {m} {v}")
    except Exception as e:
        print(f"    EKSİK  : {m} -> {type(e).__name__}: {e}")
PY

if [ ! -f "$SERVICE_FILE" ]; then
  echo ""
  echo "UYARI: $SERVICE_FILE bulunamadı — systemd birimi elle güncellenmeli."
  echo "ExecStart'taki yorumlayıcıyı şununla değiştir:"
  echo "  $VENV_DIR/bin/uvicorn"
  exit 0
fi

echo "==> systemd birimi güncelleniyor..."
cp "$SERVICE_FILE" "${SERVICE_FILE}.bak-$(date +%Y%m%d-%H%M%S)"
echo "    yedek: ${SERVICE_FILE}.bak-*"

CURRENT_EXEC="$(grep -m1 '^ExecStart=' "$SERVICE_FILE" || true)"
echo "    eski : $CURRENT_EXEC"

# ExecStart'taki uvicorn yolunu venv'inkiyle değiştir; argümanlar (host/port
# vb.) olduğu gibi korunur. "python3 /usr/local/bin/uvicorn ..." biçimi de,
# doğrudan "/usr/local/bin/uvicorn ..." biçimi de desteklenir.
python3 - "$SERVICE_FILE" "$VENV_DIR" <<'PY'
import re, sys
path, venv = sys.argv[1], sys.argv[2]
s = open(path).read()

def fix(m):
    line = m.group(0)
    # "ExecStart=" sonrasındaki komutu parçala
    cmd = line.split("=", 1)[1].strip()
    parts = cmd.split()
    # Baştaki çalıştırıcı biçimlerinin hepsini soy:
    #   /usr/bin/python3 /usr/local/bin/uvicorn ...
    #   /usr/bin/python3 -m uvicorn ...
    #   /usr/local/bin/uvicorn ...
    # Geriye sadece uygulama argümanları (app:app --host ... --port ...) kalsın.
    while parts:
        p = parts[0]
        if "python" in p or p.endswith("uvicorn"):
            parts.pop(0)
        elif p == "-m" and len(parts) > 1 and parts[1] == "uvicorn":
            parts.pop(0); parts.pop(0)
        else:
            break
    return f"ExecStart={venv}/bin/uvicorn " + " ".join(parts)

new = re.sub(r"^ExecStart=.*$", fix, s, count=1, flags=re.M)
if new == s:
    print("    DEĞİŞMEDİ — ExecStart satırı tanınamadı, elle düzelt", file=sys.stderr)
    sys.exit(1)
open(path, "w").write(new)
PY

echo "    yeni : $(grep -m1 '^ExecStart=' "$SERVICE_FILE")"

echo "==> Servis yeniden başlatılıyor..."
systemctl daemon-reload
systemctl restart tts
sleep 3
systemctl --no-pager --lines=0 status tts || true

echo ""
echo "==> BİTTİ."
echo "    Bundan sonra deploy:  cd /root/hakanerbasss.github.io && git pull && systemctl restart tts"
echo "    Yeni paket gerekirse: $VENV_DIR/bin/pip install <paket>"
echo "    Sistem Python'una bir daha pip install YAPMA."
