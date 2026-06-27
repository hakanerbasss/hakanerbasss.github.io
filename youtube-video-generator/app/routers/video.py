"""Video üretim endpoint'leri."""

import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.models import JobStatus, Scene, VideoFormat, VideoGenerateRequest, VideoJob
from app.services import llm, pexels, tts, video_builder

router = APIRouter(prefix="/api/video", tags=["video"])

# Basit in-memory job store (production'da Redis/DB kullanın)
jobs: dict[str, VideoJob] = {}


@router.post("/generate")
async def generate(req: VideoGenerateRequest, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex[:10]
    job = VideoJob(job_id=job_id, request=req, message="Sıraya alındı...")
    jobs[job_id] = job
    background_tasks.add_task(_run_job, job_id)
    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def status(job_id: str):
    job = _get_job(job_id)
    return job.model_dump(exclude={"request"})


@router.get("/download/{job_id}")
async def download(job_id: str):
    job = _get_job(job_id)
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(400, f"Video henüz hazır değil: {job.status}")
    if not job.output_path or not Path(job.output_path).exists():
        raise HTTPException(500, "Video dosyası bulunamadı.")
    filename = f"{job.request.title[:40].replace(' ', '_')}.mp4"
    return FileResponse(job.output_path, media_type="video/mp4", filename=filename)


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    job = _get_job(job_id)
    jobs.pop(job_id, None)
    # Temp dosyaları temizle
    import shutil
    job_dir = settings.temp_dir / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    out_dir = settings.outputs_dir / job_id
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    return {"deleted": job_id}


# ── iş yükleyici ────────────────────────────────────────────────────────────

def _get_job(job_id: str) -> VideoJob:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job bulunamadı.")
    return job


def _set(job: VideoJob, **kwargs):
    for k, v in kwargs.items():
        setattr(job, k, v)


async def _run_job(job_id: str):
    job = jobs[job_id]
    _set(job, status=JobStatus.PROCESSING)

    try:
        req = job.request
        job_dir = settings.temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        orientation = "portrait" if req.format == VideoFormat.SHORTS else "landscape"

        # ── 1. Metin → Sahneler (LLM) ───────────────────────────────────────
        _set(job, progress=5, message="Metin sahnelere ayrılıyor (DeepSeek)...")
        scene_data = await llm.split_into_scenes(req.text)

        job.scenes = [
            Scene(
                index=i,
                text=s["text"],
                keywords=s.get("keywords", ["nature"]),
                atmosphere=s.get("atmosphere", "neutral"),
            )
            for i, s in enumerate(scene_data)
        ]

        total = len(job.scenes)
        clip_paths = []

        # ── 2. Her sahne için TTS + Pexels + FFmpeg ─────────────────────────
        for i, scene in enumerate(job.scenes):
            base = 10 + int(i / total * 70)
            _set(job, progress=base, message=f"Sahne {i+1}/{total} — ses üretiliyor...")

            # TTS
            audio_path = str(job_dir / f"audio_{i:03d}.mp3")
            scene.duration = await tts.synthesize(scene.text, audio_path)
            scene.audio_path = audio_path

            # Pexels
            _set(job, progress=base + 1, message=f"Sahne {i+1}/{total} — fotoğraf aranıyor...")
            image_path = str(job_dir / f"image_{i:03d}.jpg")
            ok = await pexels.search_and_download(scene.keywords, image_path, orientation)
            if not ok:
                await video_builder.create_solid_image(image_path, req.format)
            scene.image_path = image_path

            # Video klip
            _set(job, progress=base + 2, message=f"Sahne {i+1}/{total} — video oluşturuluyor...")
            clip_path = await video_builder.build_scene_clip(scene, req.format, job_dir)
            scene.clip_path = clip_path
            clip_paths.append(clip_path)

        # ── 3. Birleştirme ───────────────────────────────────────────────────
        _set(job, progress=85, message="Sahneler birleştiriliyor...")
        out_dir = settings.outputs_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        final_path = str(out_dir / "video.mp4")
        await video_builder.concatenate_clips(clip_paths, final_path)

        _set(
            job,
            status=JobStatus.COMPLETED,
            progress=100,
            message="Video hazır! İndirmeye başlayabilirsiniz.",
            output_path=final_path,
        )

    except Exception as exc:
        traceback.print_exc()
        _set(
            job,
            status=JobStatus.FAILED,
            error=str(exc),
            message=f"Hata: {exc}",
        )
