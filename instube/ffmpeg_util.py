"""ffmpeg sarmalayıcı — gerçek hata sebebini görünür kılar."""
import subprocess
import time


def run_ffmpeg(cmd, timeout, retries=0, step=""):
    """ffmpeg çalıştırır; hata olursa stderr'in son satırlarını mesaja ekler.

    subprocess'in varsayılan hatası sadece komutu yazıp ffmpeg'in asıl
    çıktısını gizliyordu — eski sistemin en büyük derdi buydu. Geçici
    (OOM/yük) hatalar için opsiyonel retry da yapar.
    """
    last_err = None
    for attempt in range(retries + 1):
        try:
            return subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        except subprocess.CalledProcessError as e:
            err = e.stderr or b""
            if isinstance(err, bytes):
                err = err.decode("utf-8", "ignore")
            err_tail = "\n".join(err.strip().splitlines()[-8:]) or "stderr boş"
            last_err = RuntimeError(f"ffmpeg {step} başarısız (exit {e.returncode}): {err_tail}")
        except subprocess.TimeoutExpired:
            last_err = RuntimeError(f"ffmpeg {step} {timeout}sn içinde tamamlanamadı (timeout)")
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    raise last_err
