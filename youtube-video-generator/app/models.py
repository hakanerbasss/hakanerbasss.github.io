from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class VideoFormat(str, Enum):
    SHORTS = "shorts"        # 1080x1920
    LANDSCAPE = "landscape"  # 1920x1080


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Scene(BaseModel):
    index: int
    text: str
    keywords: List[str] = []
    atmosphere: str = "neutral"
    audio_path: Optional[str] = None
    image_path: Optional[str] = None
    clip_path: Optional[str] = None
    duration: float = 0.0


class VideoGenerateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=50)
    format: VideoFormat = VideoFormat.SHORTS
    youtube_description: str = ""
    youtube_tags: List[str] = []


class VideoJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    message: str = "Bekleniyor..."
    scenes: List[Scene] = []
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    request: Optional[VideoGenerateRequest] = None


class YouTubeUploadRequest(BaseModel):
    job_id: str
    title: str
    description: str = ""
    tags: List[str] = []
    privacy: str = "private"
    category_id: str = "22"
