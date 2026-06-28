"""FFmpeg video üretici — görsel + ses + altyazı → MP4."""

import asyncio
import os
import subprocess
from pathlib import Path

_DEFAULT_BG = Path(__file__).parent.parent.parent / "static" / "default_bg.jpg"


def _make_default_bg():
    if _DEFAULT_BG.exists():
        return
    _DEFAULT_BG.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "color=c=0x1a1a2e:size=1920x1080:rate=1",
        "-frames:v", "1", str(_DEFAULT_BG),
    ], capture_output=True)


def build_video_sync(
    image_paths: list[str | None],
    wav_paths: list[str],
    durations: list[float],
    srt_path: str,
    output_mp4: str,
) -> None:
    _make_default_bg()
    fallback = str(_DEFAULT_BG)
    job_dir = Path(output_mp4).parent
    seg_dir = job_dir / "segments"
    seg_dir.mkdir(exist_ok=True)

    seg_files: list[str] = []

    for i, (img, wav, dur) in enumerate(zip(image_paths, wav_paths, durations)):
        seg = str(seg_dir / f"{i:05d}.mp4")
        seg_files.append(seg)
        if Path(seg).exists():
            continue
        img = img or fallback
        r = subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(round(dur, 3)), "-i", img,
            "-i", wav,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-pix_fmt", "yuv420p",
            seg,
        ], capture_output=True, timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"Segment {i} hatası: {r.stderr.decode()[-500:]}")

    # Concat
    list_path = str(job_dir / "seg_list.txt")
    with open(list_path, "w") as f:
        for s in seg_files:
            f.write(f"file '{os.path.abspath(s)}'\n")

    no_sub = output_mp4 + ".nosub.mp4"
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
        "-c", "copy", no_sub,
    ], capture_output=True, timeout=7200)
    if r.returncode != 0:
        raise RuntimeError(f"Concat hatası: {r.stderr.decode()[-500:]}")

    # Altyazı burn-in — path'i escape et
    safe_srt = srt_path.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([
        "ffmpeg", "-y", "-i", no_sub,
        "-vf", f"subtitles='{safe_srt}':force_style='FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", output_mp4,
    ], capture_output=True, timeout=7200)
    if r.returncode != 0:
        # Altyazı başarısız olursa altyazısız kaydet
        os.rename(no_sub, output_mp4)
        return

    for f in (no_sub, list_path):
        try:
            os.remove(f)
        except OSError:
            pass


async def build_video(
    image_paths: list[str | None],
    wav_paths: list[str],
    durations: list[float],
    srt_path: str,
    output_mp4: str,
) -> None:
    import functools
    loop = asyncio.get_event_loop()
    fn = functools.partial(build_video_sync, image_paths, wav_paths, durations, srt_path, output_mp4)
    await loop.run_in_executor(None, fn)
