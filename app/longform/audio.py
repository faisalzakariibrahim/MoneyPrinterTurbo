"""Soundtrack assembly: narration + looped music with sidechain ducking + loudness."""

from __future__ import annotations

import os
import random
import threading
from typing import Callable, Sequence

from app.longform import ffmpeg


def concat_audio(files: Sequence[str], out: str, work_dir: str) -> str:
    """Concatenate TTS chunks into one narration WAV (re-encoded, gapless)."""
    if not files:
        raise ValueError("no audio files to concatenate")
    list_path = os.path.join(work_dir, "narration_concat.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for f in files:
            fh.write(ffmpeg.concat_list_line(os.path.abspath(f)) + "\n")
    ffmpeg.run(["-f", "concat", "-safe", "0", "-i", list_path, "-ac", "1", "-ar", "48000", out])
    return out


def build_soundtrack(
    narration: str,
    out: str,
    *,
    duration: float,
    music: Sequence[str] = (),
    music_db: float = -20.0,
    duck: bool = True,
    seed: int | str = 0,
    work_dir: str,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> str:
    """Write a single AAC track (48 kHz, -14 LUFS) for the whole video.

    Doing audio in one pass (instead of per video chunk) means no clicks or level
    jumps at chunk boundaries; video chunks are muxed against this track at the end.
    """
    loud = "loudnorm=I=-14:TP=-1.5:LRA=11"
    args: list[str] = ["-i", narration]
    music = [m for m in music if os.path.isfile(m)]
    if music:
        rng = random.Random(str(seed))
        playlist = list(music)
        total = 0.0
        entries: list[str] = []
        durations = {m: max(1.0, ffmpeg.duration(m)) for m in playlist}
        while total < duration + 5:
            rng.shuffle(playlist)
            for m in playlist:
                entries.append(m)
                total += durations[m]
                if total >= duration + 5:
                    break
        list_path = os.path.join(work_dir, "music_concat.txt")
        with open(list_path, "w", encoding="utf-8") as fh:
            for m in entries:
                fh.write(ffmpeg.concat_list_line(os.path.abspath(m)) + "\n")
        args += ["-f", "concat", "-safe", "0", "-i", list_path]
        voice = "[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v1][v2]"
        mus = f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={music_db}dB[m]"
        if duck:
            mix = (
                "[m][v2]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=600[md];"
                f"[v1][md]amix=inputs=2:duration=first:normalize=0,{loud}[a]"
            )
        else:
            mix = f"[v1][m]amix=inputs=2:duration=first:normalize=0,{loud}[a]"
        graph = f"{voice};{mus};{mix}"
    else:
        graph = f"[0:a]aresample=48000,aformat=channel_layouts=stereo,{loud}[a]"
    args += [
        "-filter_complex", graph, "-map", "[a]", "-t", f"{duration:.3f}",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out,
    ]
    ffmpeg.run(args, duration=duration, on_progress=on_progress, cancel=cancel)
    return out
