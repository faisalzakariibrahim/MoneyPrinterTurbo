"""Footage packs: normalisation, image Ken Burns clips and timeline planning."""

from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from app.longform import ffmpeg

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@dataclass(frozen=True)
class Clip:
    path: str
    duration: float


@dataclass(frozen=True)
class Segment:
    clip: int  # index into the clip list
    inpoint: float
    duration: float


@dataclass
class Chunk:
    index: int
    start: float
    duration: float
    segments: list[Segment]


def _cache_key(src: str, *parts: object) -> str:
    st = os.stat(src)
    raw = "|".join([os.path.realpath(src), str(st.st_size), str(int(st.st_mtime))] + [str(p) for p in parts])
    return hashlib.sha1(raw.encode()).hexdigest()[:20]


def kind_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    return "unknown"


def normalize_video(src: str, dst: str, width: int, height: int, fps: int, threads: int) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},setsar=1,format=yuv420p"
    )
    ffmpeg.run(
        [
            "-i", src, "-an", "-sn", "-dn", "-vf", vf,
            *ffmpeg.video_encoder_args("libx264", "veryfast", 18, fps, threads),
            "-g", str(fps), "-movflags", "+faststart", dst,
        ]
    )


def image_to_clip(
    src: str, dst: str, width: int, height: int, fps: int, seconds: float, variant: int, threads: int
) -> None:
    """Render a still into a slow Ken Burns move (alternating zoom in/out and pan)."""
    frames = max(1, int(round(seconds * fps)))
    up_w, up_h = width * 2, height * 2
    zoom_in = variant % 2 == 0
    z = "min(1+0.12*on/{f},1.12)".format(f=frames) if zoom_in else "max(1.12-0.12*on/{f},1)".format(f=frames)
    pans = [
        ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        ("(iw-iw/zoom)*on/{f}", "ih/2-(ih/zoom/2)"),
        ("(iw-iw/zoom)*(1-on/{f})", "ih/2-(ih/zoom/2)"),
        ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{f}"),
    ]
    x, y = (p.format(f=frames) for p in pans[variant % len(pans)])
    vf = (
        f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,crop={up_w}:{up_h},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        "setsar=1,format=yuv420p"
    )
    ffmpeg.run(
        [
            "-loop", "1", "-i", src, "-vf", vf, "-frames:v", str(frames),
            *ffmpeg.video_encoder_args("libx264", "veryfast", 18, fps, threads),
            "-g", str(fps), dst,
        ]
    )


def prepare_pack(
    sources: Sequence[str],
    cache_dir: str,
    width: int,
    height: int,
    fps: int,
    *,
    image_seconds: float = 10.0,
    threads: int = 2,
    on_progress: Callable[[float], None] | None = None,
) -> list[Clip]:
    """Normalise every source to the target resolution/fps. Results are cached by
    content key so a niche pack is only transcoded once per resolution."""
    os.makedirs(cache_dir, exist_ok=True)
    clips: list[Clip] = []
    usable = [s for s in sources if kind_of(s) in ("video", "image") and os.path.isfile(s)]
    if not usable:
        raise ValueError("footage pack has no usable video or image files")
    for i, src in enumerate(usable):
        kind = kind_of(src)
        key = _cache_key(src, kind, width, height, fps, image_seconds, i % 4 if kind == "image" else "")
        dst = os.path.join(cache_dir, f"{key}.mp4")
        if not (os.path.isfile(dst) and os.path.getsize(dst) > 0):
            tmp = dst + ".part.mp4"
            if kind == "video":
                normalize_video(src, tmp, width, height, fps, threads)
            else:
                image_to_clip(src, tmp, width, height, fps, image_seconds, i, threads)
            os.replace(tmp, dst)
        try:
            dur = ffmpeg.duration(dst)
        except ffmpeg.FFmpegError:
            continue
        if dur >= 1.0:
            clips.append(Clip(dst, dur))
        if on_progress:
            on_progress((i + 1) / len(usable))
    if not clips:
        raise ValueError("no footage clip survived normalisation")
    return clips


def plan_timeline(
    clips: Sequence[Clip],
    total: float,
    *,
    seed: int | str = 0,
    min_seg: float = 6.0,
    max_seg: float = 14.0,
) -> list[Segment]:
    """Fill ``total`` seconds with random cuts from ``clips``.

    Avoids repeating any of the last few clips so a small pack still looks varied,
    and never reads past the end of a clip.
    """
    if not clips:
        raise ValueError("no clips to plan with")
    rng = random.Random(str(seed))
    min_seg = max(1.0, min(min_seg, max_seg))
    recent: list[int] = []
    avoid = min(len(clips) - 1, 3)
    segments: list[Segment] = []
    t = 0.0
    while t < total - 1e-6:
        choices = [i for i in range(len(clips)) if i not in recent] or list(range(len(clips)))
        idx = rng.choice(choices)
        clip = clips[idx]
        seg = rng.uniform(min_seg, max_seg)
        seg = min(seg, clip.duration - 0.05, total - t)
        if seg <= 0.2:
            # Tail shorter than a usable cut: extend the previous segment if possible.
            if segments:
                last = segments[-1]
                room = clips[last.clip].duration - 0.05 - (last.inpoint + last.duration)
                if room >= total - t:
                    segments[-1] = Segment(last.clip, last.inpoint, last.duration + (total - t))
                    break
            seg = total - t
            seg = min(seg, clip.duration - 0.05)
        inpoint = rng.uniform(0, max(0.0, clip.duration - seg - 0.05))
        segments.append(Segment(idx, round(inpoint, 3), seg))
        t += seg
        recent.append(idx)
        if len(recent) > avoid:
            recent.pop(0)
    return segments


def split_chunks(segments: Sequence[Segment], total: float, chunk_seconds: float) -> list[Chunk]:
    """Cut the global timeline into fixed-length chunks (splitting segments at the
    boundaries) so each chunk can render independently and in parallel."""
    chunks: list[Chunk] = []
    bounds = []
    s = 0.0
    while s < total - 1e-6:
        e = min(total, s + chunk_seconds)
        bounds.append((s, e))
        s = e
    seg_iter = list(segments)
    pos = 0.0
    si = 0
    offset_in_seg = 0.0
    for ci, (cs, ce) in enumerate(bounds):
        need = ce - cs
        parts: list[Segment] = []
        while need > 1e-6 and si < len(seg_iter):
            seg = seg_iter[si]
            remaining = seg.duration - offset_in_seg
            take = min(remaining, need)
            parts.append(Segment(seg.clip, round(seg.inpoint + offset_in_seg, 3), take))
            need -= take
            pos += take
            if take >= remaining - 1e-6:
                si += 1
                offset_in_seg = 0.0
            else:
                offset_in_seg += take
        chunks.append(Chunk(ci, cs, ce - cs, parts))
    return chunks
