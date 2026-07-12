#!/bin/bash
# Wav2Lip kurulumu — fotoğrafı sesle konuşturma (dudak senkronu)
# GPU'da hızlı, CPU'da yavaş ama çalışır (60 sn video ≈ CPU'da 15-40 dk)
set -e

echo "== Wav2Lip klonlanıyor =="
if [ ! -d Wav2Lip ]; then
    git clone https://github.com/Rudrabha/Wav2Lip.git
fi
cd Wav2Lip

echo "== Bağımlılıklar =="
pip install -r requirements.txt
pip install opencv-python-headless

echo "== Model ağırlıkları indiriliyor =="
mkdir -p checkpoints face_detection/detection/sfd

# Dudak senkron modeli (GAN sürümü — daha keskin ağız görüntüsü)
if [ ! -f checkpoints/wav2lip_gan.pth ]; then
    wget -O checkpoints/wav2lip_gan.pth \
        "https://huggingface.co/numz/wav2lip_studio/resolve/main/wav2lip/wav2lip_gan.pth"
fi

# Yüz algılama modeli (s3fd)
if [ ! -f face_detection/detection/sfd/s3fd.pth ]; then
    wget -O face_detection/detection/sfd/s3fd.pth \
        "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"
fi

echo "== Kurulum tamam =="
echo "Kullanım: python3 ../make_talking_photo.py --foto ben.jpg --ses haber.wav --cikti video.mp4"
