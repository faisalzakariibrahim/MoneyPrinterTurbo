"""Procedural, seamlessly looping dust/ember particle overlay.

Rendered once with numpy + Pillow at 720p, encoded on black and screen-blended over
the footage at render time. Every particle's motion is periodic over the loop
length, so the overlay loops without a visible seam.
"""

from __future__ import annotations

import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.longform import ffmpeg

LOOP_SECONDS = 8
FPS = 30
W, H = 1280, 720


def _palette(style: str) -> list[tuple[int, int, int]]:
    if style == "embers":
        return [(255, 170, 60), (255, 120, 40), (255, 210, 120)]
    if style == "snow":
        return [(255, 255, 255), (220, 235, 255)]
    if style == "magic":
        return [(170, 140, 255), (120, 210, 255), (255, 200, 255)]
    return [(255, 245, 225), (230, 220, 200)]  # dust


def generate(path: str, style: str = "dust", count: int = 90, seed: int = 7) -> str:
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rng = np.random.default_rng(seed)
    frames = LOOP_SECONDS * FPS
    colors = _palette(style)
    x0 = rng.uniform(0, W, count)
    y0 = rng.uniform(0, H, count)
    # Integer wrap counts keep motion periodic over the loop.
    vy_wraps = rng.integers(-1, 2, count) if style != "snow" else rng.integers(1, 3, count)
    if style == "embers":
        vy_wraps = -rng.integers(1, 3, count)
    vx_wraps = rng.integers(-1, 2, count) * (1 if style != "snow" else 0)
    wobble = rng.uniform(4, 18, count)
    wob_freq = rng.integers(1, 4, count)
    phase = rng.uniform(0, 2 * math.pi, count)
    radius = rng.uniform(1.2, 3.6, count)
    tw_freq = rng.integers(1, 4, count)
    col = [colors[i % len(colors)] for i in range(count)]

    tmp = path + ".part.mp4"
    proc = subprocess.Popen(
        [
            ffmpeg.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
            "-g", str(FPS), tmp,
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        for f in range(frames):
            t = f / frames
            img = Image.new("RGB", (W, H), (0, 0, 0))
            draw = ImageDraw.Draw(img)
            xs = (x0 + vx_wraps * W * t + wobble * np.sin(2 * math.pi * wob_freq * t + phase)) % W
            ys = (y0 + vy_wraps * H * t) % H
            alpha = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * math.pi * tw_freq * t + phase))
            for i in range(count):
                c = tuple(int(v * alpha[i]) for v in col[i])
                r = radius[i]
                draw.ellipse((xs[i] - r, ys[i] - r, xs[i] + r, ys[i] + r), fill=c)
            img = img.filter(ImageFilter.GaussianBlur(1.1))
            proc.stdin.write(img.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise ffmpeg.FFmpegError("particle overlay encode failed")
    finally:
        if proc.poll() is None:
            proc.kill()
    os.replace(tmp, path)
    return path
