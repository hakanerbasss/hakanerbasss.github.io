"""
Fotoğraf + ses → konuşan kafa videosu (Wav2Lip sarmalayıcı).

Önce setup_wav2lip.sh çalıştırılmış olmalı (Wav2Lip/ klasörü ve
model ağırlıkları hazır olmalı).

Kullanım:
    python3 make_talking_photo.py --foto ben.jpg --ses haber.wav --cikti video.mp4

Fotoğraf ipuçları:
- Yüz kameraya dönük, iyi aydınlatılmış, ağız kapalı ya da hafif gülümseme
- Yüz karede büyük olsun ama kenarlara yapışmasın
- Dikey video için 1080x1920 kırpılmış fotoğraf kullan (Reels formatı)
"""

import argparse
import subprocess
import sys
from pathlib import Path

WAV2LIP_DIR = Path(__file__).parent / "Wav2Lip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--foto", required=True, help="Yüz fotoğrafı (jpg/png)")
    ap.add_argument("--ses", required=True, help="Ses dosyası (wav/mp3)")
    ap.add_argument("--cikti", default="konusan_foto.mp4", help="Çıktı videosu")
    ap.add_argument("--pad-alt", type=int, default=10,
                    help="Çene altı dolgu (çene kesiliyorsa artır, örn. 20)")
    args = ap.parse_args()

    if not WAV2LIP_DIR.exists():
        sys.exit("Wav2Lip bulunamadı — önce ./setup_wav2lip.sh çalıştır")

    foto = Path(args.foto).resolve()
    ses = Path(args.ses).resolve()
    cikti = Path(args.cikti).resolve()

    cmd = [
        sys.executable, "inference.py",
        "--checkpoint_path", "checkpoints/wav2lip_gan.pth",
        "--face", str(foto),
        "--audio", str(ses),
        "--outfile", str(cikti),
        "--static", "True",          # tek fotoğraf → sabit kare + hareketli ağız
        "--pads", "0", str(args.pad_alt), "0", "0",
        "--nosmooth",
    ]
    print("Çalıştırılıyor:", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(WAV2LIP_DIR))
    if r.returncode != 0:
        sys.exit("Wav2Lip hata verdi — yukarıdaki çıktıya bak")
    print(f"✓ Video hazır: {cikti}")


if __name__ == "__main__":
    main()
