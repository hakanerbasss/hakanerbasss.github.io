"""
Ses Klonu Stüdyosu — XTTS-v2 ile kendi sesinle Türkçe TTS.

HuggingFace Spaces'te (ücretsiz CPU) çalışacak şekilde tasarlandı.
Gradio arayüzü + API: bot, gradio_client ile /speak endpoint'ini çağırır.

Referans ses: ya arayüzden yüklenir ya da bu klasöre konan
`referans_sesim.wav` dosyası otomatik kullanılır (20-30 sn temiz kayıt).
"""

import os
import tempfile
from pathlib import Path

os.environ["COQUI_TOS_AGREED"] = "1"  # XTTS model lisansı onayı (CPML — ticari olmayan kullanım)

import torch
import gradio as gr
from TTS.api import TTS

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DEFAULT_REF = Path(__file__).parent / "referans_sesim.wav"

print(f"XTTS-v2 yükleniyor (cihaz: {DEVICE})... ilk açılışta model iner, birkaç dakika sürebilir")
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(DEVICE)
print("Model hazır.")


def speak(text: str, ref_audio, language: str = "tr", speed: float = 1.0):
    """Metni, referans sesteki kişinin sesiyle seslendirir."""
    text = (text or "").strip()
    if not text:
        raise gr.Error("Metin boş olamaz")
    if len(text) > 3000:
        raise gr.Error("Metin çok uzun (en fazla 3000 karakter)")

    ref = ref_audio or (str(DEFAULT_REF) if DEFAULT_REF.exists() else None)
    if not ref:
        raise gr.Error(
            "Referans ses yok — arayüzden bir ses kaydı yükle "
            "ya da Space'e 'referans_sesim.wav' dosyası ekle"
        )

    out_path = tempfile.mktemp(suffix=".wav")
    tts.tts_to_file(
        text=text,
        speaker_wav=ref,
        language=language,
        file_path=out_path,
        speed=float(speed),
        split_sentences=True,  # uzun haber metinleri cümle cümle işlenir
    )
    return out_path


with gr.Blocks(title="Ses Klonu Stüdyosu") as demo:
    gr.Markdown(
        "# 🎙 Ses Klonu Stüdyosu\n"
        "Kendi sesinle Türkçe seslendirme — XTTS-v2.\n\n"
        "**Referans kayıt ipuçları:** 20-30 saniye, sessiz ortam, doğal haber sunumu "
        "tonunda konuş, ağız şapırtısı ve uzun duraklamalardan kaçın."
    )
    with gr.Row():
        with gr.Column():
            text_in = gr.Textbox(
                label="Seslendirilecek metin",
                lines=6,
                placeholder="Haber metnini buraya yapıştır...",
            )
            ref_in = gr.Audio(
                label="Referans ses (boş bırakılırsa Space'teki referans_sesim.wav kullanılır)",
                type="filepath",
                sources=["upload", "microphone"],
            )
            lang_in = gr.Dropdown(
                choices=["tr", "en", "de", "fr", "es", "ar", "ru"],
                value="tr",
                label="Dil",
            )
            speed_in = gr.Slider(0.7, 1.4, value=1.0, step=0.05, label="Hız")
            btn = gr.Button("🔊 Seslendir", variant="primary")
        with gr.Column():
            audio_out = gr.Audio(label="Sonuç", type="filepath")

    btn.click(speak, [text_in, ref_in, lang_in, speed_in], audio_out, api_name="speak")

demo.queue(max_size=10).launch()
