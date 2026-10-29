"""Thin, safe wrappers around ffmpeg/ffprobe.

Commands are always passed as argv lists (never through a shell), progress is read
from ``-progress pipe:1`` and stderr goes to a temp file so a chatty encoder can
never deadlock the pipe.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Callable, Sequence

ProgressFn = Callable[[float], None]


class FFmpegError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def run(
    args: Sequence[str],
    *,
    duration: float | None = None,
    on_progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
    cwd: str | None = None,
) -> None:
    """Run ffmpeg with ``args`` (excluding the binary). Raises FFmpegError on failure.

    ``on_progress`` receives a 0..1 fraction when ``duration`` is known.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
    if on_progress is not None:
        cmd += ["-progress", "pipe:1", "-nostats"]
    cmd += list(args)

    with tempfile.TemporaryFile(mode="w+b") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if on_progress is not None else subprocess.DEVNULL,
            stderr=err,
            cwd=cwd,
        )
        try:
            if on_progress is not None and proc.stdout is not None:
                for raw in proc.stdout:
                    if cancel is not None and cancel.is_set():
                        proc.kill()
                        raise Cancelled("render cancelled")
                    line = raw.decode("utf-8", "ignore").strip()
                    if line.startswith("out_time_us=") and duration:
                        try:
                            us = int(line.split("=", 1)[1])
                        except ValueError:
                            continue
                        on_progress(max(0.0, min(1.0, us / 1e6 / duration)))
            while True:
                try:
                    proc.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    if cancel is not None and cancel.is_set():
                        proc.kill()
                        raise Cancelled("render cancelled")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        if proc.returncode != 0:
            err.seek(0)
            tail = err.read()[-4000:].decode("utf-8", "ignore")
            raise FFmpegError(f"ffmpeg exited with {proc.returncode}: {tail.strip()}")
    if on_progress is not None:
        on_progress(1.0)


def probe(path: str) -> dict:
    out = subprocess.run(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        capture_output=True,
        check=False,
    )
    if out.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {out.stderr.decode()[-500:]}")
    return json.loads(out.stdout or b"{}")


def duration(path: str) -> float:
    info = probe(path)
    dur = info.get("format", {}).get("duration")
    if dur is None:
        for stream in info.get("streams", []):
            if stream.get("duration"):
                dur = stream["duration"]
                break
    if dur is None:
        raise FFmpegError(f"could not determine duration of {path}")
    return float(dur)


def has_stream(path: str, kind: str) -> bool:
    return any(s.get("codec_type") == kind for s in probe(path).get("streams", []))


_SAFE_FILTER_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


def safe_filter_path(path: str) -> str:
    """Return ``path`` if it can be embedded in a filtergraph without escaping.

    Filtergraph escaping is a classic injection foot-gun, so instead of escaping we
    only ever reference files we created ourselves (uuid names, relative to the
    ffmpeg ``cwd``) and refuse anything else.
    """
    if not _SAFE_FILTER_PATH.match(path) or ".." in path.split("/"):
        raise ValueError(f"unsafe path for filtergraph: {path!r}")
    return path


def concat_list_line(path: str) -> str:
    return "file '" + path.replace("'", "'\\''") + "'"


def video_encoder_args(codec: str, preset: str, crf: int, fps: int, threads: int) -> list[str]:
    gop = str(fps * 2)
    if codec == "h264_nvenc":
        return [
            "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", str(crf + 2),
            "-b:v", "0", "-g", gop, "-pix_fmt", "yuv420p",
        ]
    return [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-g", gop,
        "-pix_fmt", "yuv420p", "-threads", str(threads),
        "-x264-params", "scenecut=0",
    ]
