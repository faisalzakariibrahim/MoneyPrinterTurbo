"""Object storage for inputs/outputs.

Production: Supabase Storage's S3-compatible endpoint (or Cloudflare R2) through
boto3, which does multipart transfers for multi-GB renders. Dev fallback: the
Supabase Storage REST API (fine for files up to a few hundred MB).
"""

from __future__ import annotations

import os
import re
import shutil
from functools import lru_cache

import requests

from app.longform.settings import get_settings

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


class StorageError(RuntimeError):
    pass


def validate_key(key: str, *, allowed_prefixes: tuple[str, ...]) -> str:
    """Reject anything that isn't a plain relative key under an allowed prefix."""
    if not _KEY.match(key) or ".." in key.split("/") or "//" in key:
        raise StorageError("invalid storage path")
    if not any(key.startswith(p) for p in allowed_prefixes):
        raise StorageError("storage path not permitted for this user")
    return key


@lru_cache(maxsize=1)
def _s3():
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 8, "mode": "adaptive"}),
    )


def _local_root() -> str | None:
    """LF_LOCAL_STORAGE_DIR: plain-disk backend for self-hosted/internal use and tests."""
    root = os.environ.get("LF_LOCAL_STORAGE_DIR", "").strip()
    return os.path.realpath(root) if root else None


def _local_path(root: str, key: str) -> str:
    path = os.path.realpath(os.path.join(root, key))
    if os.path.commonpath([root, path]) != root:
        raise StorageError("invalid storage path")
    return path


def _rest_base() -> tuple[str, dict]:
    s = get_settings()
    if not s.supabase_enabled:
        raise StorageError("no storage backend configured")
    headers = {"apikey": s.supabase_service_role_key, "Authorization": f"Bearer {s.supabase_service_role_key}"}
    return f"{s.supabase_url}/storage/v1/object", headers


def download(key: str, dest: str) -> str:
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    s = get_settings()
    local_root = _local_root()
    if local_root:
        src = _local_path(local_root, key)
        if not os.path.isfile(src):
            raise StorageError(f"object not found: {key}")
        shutil.copyfile(src, tmp)
    elif s.s3_enabled:
        _s3().download_file(s.s3_bucket, key, tmp)
    else:
        base, headers = _rest_base()
        with requests.get(f"{base}/{s.supabase_bucket}/{key}", headers=headers, stream=True, timeout=600) as r:
            if not r.ok:
                raise StorageError(f"download failed ({r.status_code}) for {key}")
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(r.raw, fh, length=8 * 1024 * 1024)
    os.replace(tmp, dest)
    return dest


def download_cached(key: str, cache_dir: str) -> str:
    """Library assets are immutable; keep them on local disk across jobs."""
    dest = os.path.join(cache_dir, key)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return dest
    return download(key, dest)


def upload(local: str, key: str, content_type: str) -> None:
    s = get_settings()
    local_root = _local_root()
    if local_root:
        dest = _local_path(local_root, key)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(local, dest)
        return
    if s.s3_enabled:
        _s3().upload_file(local, s.s3_bucket, key, ExtraArgs={"ContentType": content_type})
        return
    base, headers = _rest_base()
    with open(local, "rb") as fh:
        r = requests.post(
            f"{base}/{s.supabase_bucket}/{key}",
            headers={**headers, "Content-Type": content_type, "x-upsert": "true"},
            data=fh, timeout=3600,
        )
    if not r.ok:
        raise StorageError(f"upload failed ({r.status_code}) for {key}")
