"""Word timing for user-supplied narration (BYO TTS).

faster-whisper gives word timestamps; when we also have the script, we snap the
recognised words onto the script's words so captions show the exact spelling and
punctuation the creator wrote, keeping Whisper's timing.
"""

from __future__ import annotations

import difflib
import os
import re
import threading
from typing import Callable, Sequence

from loguru import logger

from app.longform.captions import Word

_model = None
_model_lock = threading.Lock()


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", token.lower())


def _load_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            size = os.environ.get("LF_WHISPER_MODEL", "small.en")
            device = os.environ.get("LF_WHISPER_DEVICE", "auto")
            compute = os.environ.get("LF_WHISPER_COMPUTE", "int8")
            logger.info(f"loading whisper {size} on {device}/{compute}")
            _model = WhisperModel(size, device=device, compute_type=compute)
    return _model


def transcribe_words(
    audio_path: str,
    *,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[Word]:
    model = _load_model()
    segments, _info = model.transcribe(
        audio_path, beam_size=1, word_timestamps=True, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False,
    )
    words: list[Word] = []
    for seg in segments:  # generator: transcription happens while iterating
        if cancel is not None and cancel.is_set():
            raise RuntimeError("cancelled")
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(t, float(w.start), float(w.end)))
        if on_progress and duration:
            on_progress(min(1.0, seg.end / duration))
    return words


def snap_to_script(recognised: Sequence[Word], script_text: str) -> list[Word]:
    """Re-label recognised words with the script's tokens (timings preserved).

    Unmatched script words get timings interpolated between their matched
    neighbours; script words the narrator skipped never appear on screen
    without a time slot because interpolation keeps order.
    """
    script_tokens = script_text.split()
    if not recognised or not script_tokens:
        return list(recognised)
    a = [_norm(w.text) for w in recognised]
    b = [_norm(t) for t in script_tokens]
    times: list[tuple[float, float] | None] = [None] * len(b)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            r = recognised[block.a + k]
            times[block.b + k] = (r.start, r.end)
    matched = sum(1 for t in times if t)
    if matched < 0.5 * len(b):
        # Narration doesn't follow the script closely; trust Whisper's own words.
        return list(recognised)
    # Interpolate gaps.
    out: list[Word] = []
    i = 0
    n = len(b)
    while i < n:
        if times[i] is not None:
            s, e = times[i]  # type: ignore[misc]
            out.append(Word(script_tokens[i], s, e))
            i += 1
            continue
        j = i
        while j < n and times[j] is None:
            j += 1
        left = out[-1].end if out else (times[j][0] if j < n else 0.0)  # type: ignore[index]
        right = times[j][0] if j < n else left + 0.3 * (j - i)  # type: ignore[index]
        span = max(0.05 * (j - i), right - left)
        step = span / (j - i)
        for k in range(i, j):
            st = left + step * (k - i)
            out.append(Word(script_tokens[k], st, st + step * 0.9))
        i = j
    return out


def words_for_audio(
    audio_path: str,
    script_text: str | None,
    *,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[Word]:
    rec = transcribe_words(audio_path, duration=duration, on_progress=on_progress, cancel=cancel)
    return snap_to_script(rec, script_text) if script_text else rec
