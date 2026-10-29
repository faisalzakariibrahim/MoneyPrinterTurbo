"""YouTube publishing via the Data API v3 resumable upload protocol."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable

import requests

from app.longform.settings import get_settings

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CAPTION_URL = "https://www.googleapis.com/upload/youtube/v3/captions"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CHUNK = 64 * 1024 * 1024  # must be a multiple of 256 KiB


class YouTubeError(RuntimeError):
    pass


def access_token(refresh_token: str) -> str:
    s = get_settings()
    if not (s.youtube_client_id and s.youtube_client_secret):
        raise YouTubeError("YouTube OAuth client is not configured on the worker")
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": s.youtube_client_id,
            "client_secret": s.youtube_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if not r.ok:
        raise YouTubeError("YouTube authorisation expired — reconnect the channel")
    return r.json()["access_token"]


def upload_video(
    path: str,
    *,
    refresh_token: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy: str = "private",
    category_id: str = "24",
    synthetic_media: bool = True,
    publish_at: str | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """Upload and return the YouTube video id.

    ``synthetic_media`` sets YouTube's altered/synthetic content disclosure, which is
    required when realistic AI voice or visuals are used.
    """
    if privacy not in ("private", "unlisted", "public"):
        raise YouTubeError("invalid privacy setting")
    token = access_token(refresh_token)
    size = os.path.getsize(path)
    status: dict = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": bool(synthetic_media),
    }
    if publish_at:
        status["publishAt"] = publish_at
    meta = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": [t[:60] for t in (tags or [])][:30],
            "categoryId": category_id,
        },
        "status": status,
    }
    init = requests.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        data=json.dumps(meta),
        timeout=60,
    )
    if not init.ok or "Location" not in init.headers:
        raise YouTubeError(f"YouTube rejected the upload ({init.status_code}): {init.text[:300]}")
    session = init.headers["Location"]

    sent = 0
    with open(path, "rb") as fh:
        while sent < size:
            if cancel is not None and cancel.is_set():
                raise YouTubeError("upload cancelled")
            fh.seek(sent)
            data = fh.read(CHUNK)
            end = sent + len(data) - 1
            for attempt in range(6):
                try:
                    r = requests.put(
                        session,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Length": str(len(data)),
                            "Content-Range": f"bytes {sent}-{end}/{size}",
                        },
                        data=data,
                        timeout=600,
                    )
                except requests.RequestException:
                    r = None
                if r is not None and r.status_code in (200, 201):
                    if on_progress:
                        on_progress(1.0)
                    return r.json()["id"]
                if r is not None and r.status_code == 308:
                    rng = r.headers.get("Range")
                    sent = int(rng.split("-")[1]) + 1 if rng else 0
                    break
                if r is not None and r.status_code == 401:
                    token = access_token(refresh_token)
                    continue
                if r is not None and r.status_code < 500:
                    raise YouTubeError(f"YouTube upload failed ({r.status_code}): {r.text[:300]}")
                time.sleep(min(60, 2 ** attempt))
                # Ask the server how much it has before retrying.
                q = requests.put(session, headers={"Authorization": f"Bearer {token}",
                                                   "Content-Range": f"bytes */{size}"}, timeout=60)
                if q.status_code in (200, 201):
                    return q.json()["id"]
                if q.status_code == 308:
                    rng = q.headers.get("Range")
                    sent = int(rng.split("-")[1]) + 1 if rng else 0
                    break
            else:
                raise YouTubeError("YouTube upload kept failing")
            if on_progress:
                on_progress(sent / size)
    raise YouTubeError("upload ended without a video id")


def upload_captions(video_id: str, srt_text: str, refresh_token: str, language: str = "en") -> None:
    token = access_token(refresh_token)
    boundary = "lfcaptionboundary"
    meta = json.dumps({"snippet": {"videoId": video_id, "language": language, "name": "", "isDraft": False}})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n{srt_text}\r\n--{boundary}--"
    ).encode()
    r = requests.post(
        CAPTION_URL,
        params={"part": "snippet", "uploadType": "multipart"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=120,
    )
    if not r.ok:
        raise YouTubeError(f"caption upload failed ({r.status_code})")
