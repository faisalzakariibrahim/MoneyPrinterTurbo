"""Chunked, parallel FFmpeg renderer for 1–4 hour videos.

Pipeline:
  1. normalise the footage pack to the target resolution (cached)
  2. build one soundtrack for the whole video (narration + ducked music, -14 LUFS)
  3. plan a random cut timeline and split it into fixed-length chunks
  4. render chunks in parallel (cuts + border + vignette + particles + captions)
  5. stream-copy concat the chunks and mux the soundtrack (+faststart)

Chunks are resumable: a finished chunk is kept with a marker, so a crashed or
cancelled render picks up where it stopped.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from typing import Callable, Sequence

from loguru import logger

from app.longform import audio as audio_mod
from app.longform import captions as cap
from app.longform import ffmpeg, footage, particles
from app.longform.settings import FONTS_DIR, get_settings

RESOLUTIONS = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
}

StageProgress = Callable[[float, str], None]


@dataclass
class BorderStyle:
    enabled: bool = False
    width_ratio: float = 0.022
    color: str = "#0B0B0F"


@dataclass
class ParticleStyle:
    enabled: bool = False
    style: str = "dust"  # dust | embers | snow | magic
    opacity: float = 0.55


@dataclass
class RenderSpec:
    resolution: str = "1080p"
    fps: int = 30
    min_segment: float = 6.0
    max_segment: float = 14.0
    image_seconds: float = 10.0
    vignette: bool = True
    music_db: float = -20.0
    duck_music: bool = True
    seed: str = "0"
    captions: cap.CaptionStyle = field(default_factory=cap.CaptionStyle)
    border: BorderStyle = field(default_factory=BorderStyle)
    particles: ParticleStyle = field(default_factory=ParticleStyle)

    @property
    def size(self) -> tuple[int, int]:
        return RESOLUTIONS.get(self.resolution, RESOLUTIONS["1080p"])

    @classmethod
    def from_dict(cls, data: dict | None) -> "RenderSpec":
        data = dict(data or {})
        spec = cls()
        for key in ("resolution", "fps", "min_segment", "max_segment", "image_seconds",
                    "vignette", "music_db", "duck_music", "seed"):
            if key in data and data[key] is not None:
                setattr(spec, key, type(getattr(spec, key))(data[key]))
        if spec.resolution not in RESOLUTIONS:
            raise ValueError(f"unsupported resolution {spec.resolution}")
        spec.fps = max(24, min(60, spec.fps))
        spec.captions = cap.CaptionStyle.from_dict(data.get("captions"))
        b = data.get("border") or {}
        spec.border = BorderStyle(**{k: v for k, v in b.items() if k in BorderStyle.__dataclass_fields__})
        p = data.get("particles") or {}
        spec.particles = ParticleStyle(**{k: v for k, v in p.items() if k in ParticleStyle.__dataclass_fields__})
        return spec

    def fingerprint(self) -> str:
        return hashlib.sha1(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()[:12]


@dataclass
class RenderResult:
    path: str
    duration: float
    chunks: int
    width: int
    height: int


def _hex(color: str) -> str:
    c = color.lstrip("#")
    return "0x" + (c if len(c) == 6 else "000000")


def _chunk_filtergraph(
    n_inputs: int,
    spec: RenderSpec,
    duration: float,
    particles_input: int | None,
    ass_name: str | None,
) -> str:
    w, h = spec.size
    parts = [f"[{i}:v]setpts=PTS-STARTPTS,setsar=1[s{i}]" for i in range(n_inputs)]
    chain = "".join(f"[s{i}]" for i in range(n_inputs))
    parts.append(f"{chain}concat=n={n_inputs}:v=1:a=0[cat]")
    base = (
        f"[cat]fps={spec.fps},tpad=stop_mode=clone:stop_duration=2,"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS"
    )
    if spec.border.enabled:
        bw = max(2, int(round(min(w, h) * spec.border.width_ratio / 2)) * 2)
        base += f",scale={w - 2 * bw}:{h - 2 * bw},pad={w}:{h}:{bw}:{bw}:color={_hex(spec.border.color)}"
    if spec.vignette:
        base += ",vignette=angle=PI/5"
    parts.append(base + "[base]")
    current = "base"
    if particles_input is not None:
        op = max(0.05, min(1.0, spec.particles.opacity))
        parts.append(
            f"[{particles_input}:v]scale={w}:{h},fps={spec.fps},trim=duration={duration:.3f},"
            "setpts=PTS-STARTPTS,format=gbrp[pp]"
        )
        parts.append("[base]format=gbrp[bb]")
        parts.append(f"[bb][pp]blend=all_mode=screen:all_opacity={op:.2f},format=yuv420p[fx]")
        current = "fx"
    if ass_name:
        parts.append(
            f"[{current}]ass=filename={ffmpeg.safe_filter_path(ass_name)}:fontsdir=fonts,format=yuv420p[v]"
        )
    else:
        parts.append(f"[{current}]format=yuv420p[v]")
    return ";".join(parts)


def render_chunk(
    chunk: footage.Chunk,
    clips: Sequence[footage.Clip],
    spec: RenderSpec,
    chunk_dir: str,
    ass_text: str | None,
    particles_path: str | None,
    *,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    settings = get_settings()
    os.makedirs(chunk_dir, exist_ok=True)
    out = os.path.join(chunk_dir, "out.mp4")
    marker = os.path.join(chunk_dir, "done.json")
    signature = hashlib.sha1(
        json.dumps(
            {
                "spec": spec.fingerprint(),
                "segs": [asdict(s) for s in chunk.segments],
                "ass": hashlib.sha1((ass_text or "").encode()).hexdigest(),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if os.path.isfile(marker) and os.path.isfile(out):
        try:
            with open(marker, encoding="utf-8") as fh:
                if json.load(fh).get("signature") == signature:
                    if on_progress:
                        on_progress(1.0)
                    return out
        except (OSError, ValueError):
            pass

    fonts_link = os.path.join(chunk_dir, "fonts")
    if not os.path.exists(fonts_link):
        os.symlink(FONTS_DIR, fonts_link)
    ass_name = None
    if ass_text:
        ass_name = "captions.ass"
        with open(os.path.join(chunk_dir, ass_name), "w", encoding="utf-8") as fh:
            fh.write(ass_text)

    args: list[str] = []
    for seg in chunk.segments:
        args += ["-ss", f"{seg.inpoint:.3f}", "-t", f"{seg.duration + 0.1:.3f}", "-i", clips[seg.clip].path]
    particles_input = None
    if particles_path:
        particles_input = len(chunk.segments)
        args += ["-stream_loop", "-1", "-i", particles_path]
    graph = _chunk_filtergraph(len(chunk.segments), spec, chunk.duration, particles_input, ass_name)
    with open(os.path.join(chunk_dir, "graph.txt"), "w", encoding="utf-8") as fh:
        fh.write(graph)
    frames = int(round(chunk.duration * spec.fps))
    tmp = "out.part.mp4"
    args += [
        "-filter_complex_script", "graph.txt", "-map", "[v]", "-an",
        "-frames:v", str(frames), "-r", str(spec.fps),
        *ffmpeg.video_encoder_args(settings.video_codec, settings.x264_preset, settings.crf,
                                   spec.fps, settings.threads_per_render),
        "-video_track_timescale", "90000", tmp,
    ]
    ffmpeg.run(args, duration=chunk.duration, on_progress=on_progress, cancel=cancel, cwd=chunk_dir)
    os.replace(os.path.join(chunk_dir, tmp), out)
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"signature": signature, "frames": frames}, fh)
    return out


def render_longform(
    *,
    narration_path: str,
    words: Sequence[cap.Word],
    footage_sources: Sequence[str],
    music_sources: Sequence[str] = (),
    spec: RenderSpec,
    work_dir: str,
    out_path: str,
    on_progress: StageProgress | None = None,
    cancel: threading.Event | None = None,
) -> RenderResult:
    settings = get_settings()
    cancel = cancel or threading.Event()
    os.makedirs(work_dir, exist_ok=True)
    w, h = spec.size

    def report(frac: float, stage: str) -> None:
        if on_progress:
            on_progress(max(0.0, min(1.0, frac)), stage)

    total = ffmpeg.duration(narration_path)
    if total < 5:
        raise ValueError("narration is too short to render")
    if total > settings.max_video_minutes * 60:
        raise ValueError(f"narration exceeds the {settings.max_video_minutes} minute limit")
    # Snap to the frame grid so chunk frame counts add up exactly.
    total = math.floor(total * spec.fps) / spec.fps
    logger.info(f"longform render: {total / 60:.1f} min at {spec.resolution}")

    # 1. footage
    report(0.0, "Preparing footage")
    cache_dir = os.path.join(settings.work_dir, "footage-cache", f"{w}x{h}@{spec.fps}")
    clips = footage.prepare_pack(
        footage_sources, cache_dir, w, h, spec.fps,
        image_seconds=spec.image_seconds, threads=settings.threads_per_render,
        on_progress=lambda f: report(0.10 * f, "Preparing footage"),
    )
    if cancel.is_set():
        raise ffmpeg.Cancelled("render cancelled")

    # 2. soundtrack
    soundtrack = os.path.join(work_dir, "soundtrack.m4a")
    audio_mod.build_soundtrack(
        narration_path, soundtrack, duration=total, music=music_sources,
        music_db=spec.music_db, duck=spec.duck_music, seed=spec.seed, work_dir=work_dir,
        on_progress=lambda f: report(0.10 + 0.05 * f, "Mixing audio"), cancel=cancel,
    )

    # 3. plan
    segments = footage.plan_timeline(
        clips, total, seed=spec.seed, min_seg=spec.min_segment, max_seg=spec.max_segment
    )
    chunks = footage.split_chunks(segments, total, settings.chunk_seconds)
    events = []
    if spec.captions.enabled and words:
        events = cap.events(cap.build_phrases(words, spec.captions), spec.captions)
    particles_path = None
    if spec.particles.enabled:
        particles_path = particles.generate(
            os.path.join(settings.work_dir, "fx", f"particles-{spec.particles.style}.mp4"),
            style=spec.particles.style,
        )

    # 4. chunks in parallel
    fractions = [0.0] * len(chunks)
    lock = threading.Lock()

    def chunk_progress(i: int):
        def _cb(f: float) -> None:
            with lock:
                fractions[i] = f
                done = sum(fr * c.duration for fr, c in zip(fractions, chunks)) / total
            report(0.15 + 0.80 * done, f"Rendering video ({len(chunks)} parts)")
        return _cb

    def job(chunk: footage.Chunk) -> str:
        if cancel.is_set():
            raise ffmpeg.Cancelled("render cancelled")
        ass_text = None
        if events:
            ass_text = cap.render_ass(events, spec.captions, w, h, window=(chunk.start, chunk.start + chunk.duration))
        return render_chunk(
            chunk, clips, spec, os.path.join(work_dir, "chunks", f"{chunk.index:04d}"),
            ass_text, particles_path, on_progress=chunk_progress(chunk.index), cancel=cancel,
        )

    outputs: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=settings.render_workers) as pool:
        futures = {pool.submit(job, c): c.index for c in chunks}
        done, pending = wait(futures, return_when=FIRST_EXCEPTION)
        failed = [f for f in done if f.exception() is not None]
        if failed:
            cancel.set()
            for f in pending:
                f.cancel()
            wait(pending)
            raise failed[0].exception()  # type: ignore[misc]
        for f, idx in futures.items():
            outputs[idx] = f.result()

    # 5. concat + mux
    report(0.96, "Finalising")
    list_path = os.path.join(work_dir, "chunks.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for idx in sorted(outputs):
            fh.write(ffmpeg.concat_list_line(os.path.abspath(outputs[idx])) + "\n")
    tmp_out = out_path + ".part.mp4"
    ffmpeg.run(
        [
            "-f", "concat", "-safe", "0", "-i", list_path, "-i", soundtrack,
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-shortest",
            "-movflags", "+faststart", tmp_out,
        ]
    )
    os.replace(tmp_out, out_path)
    final = ffmpeg.duration(out_path)
    report(1.0, "Done")
    return RenderResult(out_path, final, len(chunks), w, h)
