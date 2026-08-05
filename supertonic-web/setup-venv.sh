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

# --ignore-installed: --system-site-packages yüzünden pip, paketi sistemde
# görünce venv'e HİÇ kurmuyor. Bu iki soruna yol açıyor:
#   1) Konsol script'i (.venv/bin/uvicorn) oluşmuyor -> systemd 203/EXEC
#   2) İzolasyon kağıt üzerinde kalıyor; başka bir proje sistemdeki httpx'i
#      düşürdüğünde supertonic yine kırılıyor
# --no-deps: doğrudan bağımlılıkları venv'e sabitler ama torch/onnxruntime
# gibi ağır TRANSİTİF paketleri yeniden indirmez (sistemden okunmaya devam).
#
# Paketler TEK TEK kurulur: bazıları (örn. openai-whisper) hazır wheel'i
# olmadığı için kaynaktan derlenmeye çalışıyor ve yeni setuptools'ta
# pkg_resources kalktığı için patlıyor. Tek bir paketin başarısızlığı tüm
# kurulumu durdurmasın — o paket sistemdeki sürümünden okunmaya devam eder.
SKIPPED=""
while IFS= read -r _line; do
  pkg="$(printf '%s' "$_line" | sed 's/#.*//' | xargs || true)"
  [ -z "$pkg" ] && continue
  if "$VENV_DIR/bin/pip" install --ignore-installed --no-deps -q "$pkg" 2>/dev/null; then
    echo "    venv   : $pkg"
  else
    echo "    ATLANDI: $pkg  (sistemdeki sürüm kullanılacak)"
    SKIPPED="$SKIPPED $pkg"
  fi
done < "$APP_DIR/requirements.txt"

if [ -n "$SKIPPED" ]; then
  echo ""
  echo "    NOT: Şu paketler venv'e kurulamadı, sistemden okunacak:$SKIPPED"
  echo "    Bu sorun değil — bunlar sürüm çakışması yaratan paketler değil."
fi

echo "==> Kurulum doğrulanıyor..."
# Modülün NEREDEN geldiği de yazdırılır: yol venv içindeyse gerçekten izole,
# /usr/... ise sistemden okunuyor demektir.
"$VENV_DIR/bin/python" - "$VENV_DIR" <<'PY'
import sys
venv = sys.argv[1]
print(f"    python : {sys.executable}")
mods = ["fastapi", "uvicorn", "httpx", "openai", "edge_tts", "whisper", "supertonic"]
for m in mods:
    try:
        mod = __import__(m)
        v = getattr(mod, "__version__", "?")
        loc = getattr(mod, "__file__", "") or ""
        where = "venv" if loc.startswith(venv) else "SİSTEM"
        print(f"    ok     : {m:12} {v:12} [{where}]")
    except Exception as e:
        print(f"    EKSİK  : {m} -> {type(e).__name__}: {e}")
PY

# app.py gerçekten yüklenebiliyor mu? Servisi yeniden başlatmadan ÖNCE dene —
# yoksa systemd sonsuz auto-restart döngüsüne giriyor.
echo "==> Uygulama import testi..."
if ! (cd "$APP_DIR" && "$VENV_DIR/bin/python" -c "import uvicorn, app" 2>&1 | tail -20); then
  echo "HATA: app.py venv içinde import edilemedi — servis güncellenmedi." >&2
  exit 1
fi
echo "    ok"

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

stripped_any = False

def fix(m):
    global stripped_any
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
            parts.pop(0); stripped_any = True
        elif p == "-m" and len(parts) > 1 and parts[1] == "uvicorn":
            parts.pop(0); parts.pop(0); stripped_any = True
        else:
            break
    if not stripped_any:
        # Baştaki hiçbir belirteç python/uvicorn değil — bu birim beklediğimiz
        # biçimde değil. Bozmak yerine olduğu gibi bırak, çağıran hata versin.
        return line
    # "python -m uvicorn": konsol script'i (.venv/bin/uvicorn) bir sebeple
    # oluşmasa bile çalışır. Doğrudan .venv/bin/uvicorn yazmak 203/EXEC
    # hatasına yol açmıştı.
    return f"ExecStart={venv}/bin/python -m uvicorn " + " ".join(parts)

new = re.sub(r"^ExecStart=.*$", fix, s, count=1, flags=re.M)
if new == s:
    # İki ihtimal: (a) satır zaten doğru — script daha önce çalışmış veya elle
    # düzeltilmiş, (b) satır hiç tanınamamış. İkisini ayırt et; (a) hata değil.
    cur = next((l for l in s.splitlines() if l.startswith("ExecStart=")), "")
    if f"{venv}/bin/python" in cur and "uvicorn" in cur:
        print("    zaten güncel — değişiklik gerekmedi")
        sys.exit(0)
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
