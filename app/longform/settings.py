"""Environment-driven settings for the long-form worker.

Every secret comes from the environment. Nothing here is ever logged or returned
from an API response.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
FONTS_DIR = ROOT_DIR / "resource" / "fonts" / "longform"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    render_workers: int
    chunk_seconds: int
    video_codec: str
    x264_preset: str
    crf: int
    threads_per_render: int

    anthropic_api_key: str
    script_model: str
    analysis_model: str
    fast_model: str

    worker_secret: str
    allowed_origins: list[str] = field(default_factory=list)

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "longform"

    elevenlabs_api_key: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    youtube_client_id: str = ""
    youtube_client_secret: str = ""

    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""

    max_upload_bytes: int = 2 * 1024**3
    max_video_minutes: int = 300

    @property
    def s3_enabled(self) -> bool:
        return bool(
            self.s3_endpoint
            and self.s3_bucket
            and self.s3_access_key_id
            and self.s3_secret_access_key
        )

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    cpu = os.cpu_count() or 2
    work_dir = Path(_env("LF_WORK_DIR") or ROOT_DIR / "storage" / "longform")
    work_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, _env_int("LF_RENDER_WORKERS", max(1, cpu // 4)))
    return Settings(
        work_dir=work_dir,
        render_workers=workers,
        chunk_seconds=max(30, _env_int("LF_CHUNK_SECONDS", 300)),
        video_codec=_env("LF_VIDEO_CODEC", "libx264"),
        x264_preset=_env("LF_X264_PRESET", "veryfast"),
        crf=_env_int("LF_CRF", 21),
        threads_per_render=max(1, _env_int("LF_THREADS_PER_RENDER", max(1, cpu // workers))),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        script_model=_env("LF_SCRIPT_MODEL", "claude-sonnet-5-5"),
        analysis_model=_env("LF_ANALYSIS_MODEL", "claude-sonnet-5-5"),
        fast_model=_env("LF_FAST_MODEL", "claude-haiku-5-5"),
        worker_secret=_env("LF_WORKER_SECRET"),
        allowed_origins=[o for o in _env("LF_ALLOWED_ORIGINS").split(",") if o],
        supabase_url=_env("SUPABASE_URL").rstrip("/"),
        supabase_service_role_key=_env("SUPABASE_SERVICE_ROLE_KEY"),
        supabase_bucket=_env("LF_SUPABASE_BUCKET", "longform"),
        elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
        elevenlabs_model=_env("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        youtube_client_id=_env("YOUTUBE_CLIENT_ID"),
        youtube_client_secret=_env("YOUTUBE_CLIENT_SECRET"),
        s3_endpoint=_env("S3_ENDPOINT"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION", "auto"),
        s3_access_key_id=_env("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=_env("S3_SECRET_ACCESS_KEY"),
        max_upload_bytes=_env_int("LF_MAX_UPLOAD_BYTES", 2 * 1024**3),
        max_video_minutes=_env_int("LF_MAX_VIDEO_MINUTES", 300),
    )
