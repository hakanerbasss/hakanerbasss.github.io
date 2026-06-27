"""FFmpeg ile slideshow video oluşturur.

Her sahne: Pexels fotoğrafı + TTS sesi + Ken Burns efekti + altyazı
Son: Tüm sahneler birleştirilir.
"""

import asyncio
import re
from pathlib import Path
from typing import List

from app.config import settings
from app.models import Scene, VideoFormat

_DIMS = {
    VideoFormat.SHORTS: (1080, 1920),
    VideoFormat.LANDSCAPE: (1920, 1080),
}

FPS = 30
FADE_DURATION = 0.4  # saniye


async def build_scene_clip(
    scene: Scene,
    fmt: VideoFormat,
    job_dir: Path,
) -> str:
    """Tek bir sahne için MP4 klip oluşturur. Klip yolunu döner."""
    w, h = _DIMS[fmt]
    output = str(job_dir / f"scene_{scene.index:03d}.mp4")
    duration = scene.duration + 0.3  # küçük buffer

    # Altyazı metni — ilk 80 karakter, FFmpeg drawtext için temizle
    subtitle = _clean_text(scene.text[:80] + ("..." if len(scene.text) > 80 else ""))

    # Ken Burns: yavaş zoom-in (1.0x → 1.5x)
    zoom_expr = "min(zoom+0.0015,1.5)"
    frames = int(duration * FPS) + 10  # biraz fazla ver, -shortest keser

    # Filtre zinciri
    vf = (
        # 1) Görüntüyü 2x büyüt → zoompan için yer açar
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
        f"crop={w * 2}:{h * 2},"
        # 2) Ken Burns zoom
        f"zoompan="
        f"z='{zoom_expr}':"
        f"d={frames}:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"s={w}x{h}:"
        f"fps={FPS},"
        # 3) Altyazı kutusu
        f"drawtext="
        f"fontfile={settings.font_path}:"
        f"text='{subtitle}':"
        f"fontcolor=white:"
        f"fontsize={_font_size(w)}:"
        f"x=(w-text_w)/2:"
        f"y=h-{_text_bottom(h)}:"
        f"borderw=2:"
        f"bordercolor=black@0.9:"
        f"box=1:"
        f"boxcolor=black@0.55:"
        f"boxborderw=12,"
        # 4) Fade in / out
        f"fade=t=in:st=0:d={FADE_DURATION},"
        f"fade=t=out:st={max(0, duration - FADE_DURATION):.2f}:d={FADE_DURATION}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", scene.image_path,
        "-i", scene.audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output,
    ]

    await _run(cmd, label=f"scene_{scene.index}")
    return output


async def concatenate_clips(clip_paths: List[str], output_path: str) -> None:
    """Tüm klipleri sırasıyla birleştirir (re-encode etmeden)."""
    list_file = Path(output_path).parent / "concat_list.txt"
    with open(list_file, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        output_path,
    ]
    await _run(cmd, label="concat")


async def create_solid_image(path: str, fmt: VideoFormat) -> None:
    """Pexels fotoğrafı bulunamazsa düz siyah placeholder oluşturur."""
    w, h = _DIMS[fmt]
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a1a2e:s={w}x{h}:d=1",
        "-frames:v", "1",
        path,
    ]
    await _run(cmd, label="placeholder")


# ── iç yardımcılar ──────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """FFmpeg drawtext için özel karakterleri temizle."""
    text = text.replace("\\", "")
    text = text.replace("'", "’")   # ' → ' (typographic)
    text = text.replace(":", " ")
    text = text.replace("[", "").replace("]", "")
    # Satır sonlarını boşluğa çevir
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _font_size(width: int) -> int:
    return 36 if width >= 1080 else 28


def _text_bottom(height: int) -> int:
    return 100 if height >= 1920 else 80


async def _run(cmd: list, label: str = "") -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg [{label}] hata (kod {proc.returncode}):\n"
            + stderr.decode()[-2000:]  # son 2000 karakter yeterli
        )
