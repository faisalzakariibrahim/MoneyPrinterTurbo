"""Long-form text-to-speech.

* ``elevenlabs:<voice_id>`` — uses the ``/with-timestamps`` endpoint so we get exact
  per-character timings for captions with no transcription pass.
* ``edge:<voice>`` — free Microsoft Edge voices through MPT's existing TTS code
  (captions then come from Whisper alignment).

Long scripts are split at paragraph/sentence boundaries and synthesised in parallel,
passing neighbouring text to ElevenLabs so prosody stays continuous across chunks.
"""

from __future__ import annotations

import base64
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import requests
from loguru import logger

from app.longform import audio as audio_mod
from app.longform import ffmpeg
from app.longform.captions import Word
from app.longform.settings import get_settings

ELEVEN = "https://api.elevenlabs.io/v1"
MAX_CHARS = 2400


class VoiceError(RuntimeError):
    pass


def split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""

    def push(piece: str) -> None:
        nonlocal cur
        if not cur:
            cur = piece
        elif len(cur) + 2 + len(piece) <= max_chars:
            cur += "\n\n" + piece
        else:
            chunks.append(cur)
            cur = piece

    for p in paras:
        if len(p) <= max_chars:
            push(p)
            continue
        sentences = re.split(r"(?<=[.!?…])\s+", p)
        buf = ""
        for s in sentences:
            while len(s) > max_chars:  # pathological run-on sentence
                cut = s.rfind(" ", 0, max_chars)
                cut = cut if cut > 0 else max_chars
                if buf:
                    push(buf)
                    buf = ""
                push(s[:cut])
                s = s[cut:].strip()
            if len(buf) + 1 + len(s) <= max_chars:
                buf = (buf + " " + s).strip()
            else:
                push(buf)
                buf = s
        if buf:
            push(buf)
    if cur:
        chunks.append(cur)
    return chunks


def list_elevenlabs_voices() -> list[dict]:
    key = get_settings().elevenlabs_api_key
    if not key:
        return []
    r = requests.get(f"{ELEVEN}/voices", headers={"xi-api-key": key}, timeout=20)
    if not r.ok:
        raise VoiceError(f"ElevenLabs voices request failed ({r.status_code})")
    return [
        {"id": v["voice_id"], "name": v.get("name", ""), "preview_url": v.get("preview_url"),
         "labels": v.get("labels", {})}
        for v in r.json().get("voices", [])
    ]


def _chars_to_words(alignment: dict, offset: float) -> list[Word]:
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[Word] = []
    buf, ws, we = "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append(Word(buf, offset + ws, offset + we))
            buf, ws, we = "", None, None
            continue
        if ws is None:
            ws = s
        buf += ch
        we = e
    if buf and ws is not None:
        words.append(Word(buf, offset + ws, offset + we))
    return words


def _eleven_chunk(text: str, voice_id: str, prev: str, nxt: str, out_path: str) -> dict:
    s = get_settings()
    url = f"{ELEVEN}/text-to-speech/{voice_id}/with-timestamps"
    body = {
        "text": text,
        "model_id": s.elevenlabs_model,
        "previous_text": prev[-600:] or None,
        "next_text": nxt[:600] or None,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    for attempt in range(5):
        r = requests.post(
            url, params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": s.elevenlabs_api_key, "Content-Type": "application/json"},
            json=body, timeout=300,
        )
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(4 * (attempt + 1))
            continue
        if not r.ok:
            raise VoiceError(f"ElevenLabs TTS failed ({r.status_code})")
        data = r.json()
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(data["audio_base64"]))
        return data.get("alignment") or data.get("normalized_alignment") or {}
    raise VoiceError("ElevenLabs TTS kept failing (rate limited)")


def synthesize(
    text: str,
    voice: str,
    out_dir: str,
    *,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> tuple[str, list[Word] | None]:
    """Return (narration_wav, words). ``words`` is None when alignment must come from Whisper."""
    os.makedirs(out_dir, exist_ok=True)
    provider, _, voice_id = voice.partition(":")
    chunks = split_text(text)
    if not chunks:
        raise VoiceError("script is empty")
    files = [os.path.join(out_dir, f"tts_{i:04d}.mp3") for i in range(len(chunks))]
    done = [0]
    lock = threading.Lock()

    def tick() -> None:
        with lock:
            done[0] += 1
            if on_progress:
                on_progress(done[0] / len(chunks))

    if provider == "elevenlabs":
        if not get_settings().elevenlabs_api_key:
            raise VoiceError("ElevenLabs is not configured on the worker")
        if not re.fullmatch(r"[A-Za-z0-9]{8,40}", voice_id):
            raise VoiceError("invalid ElevenLabs voice id")
        alignments: list[dict] = [{}] * len(chunks)

        def job(i: int) -> None:
            if cancel is not None and cancel.is_set():
                raise ffmpeg.Cancelled("cancelled")
            prev = chunks[i - 1] if i > 0 else ""
            nxt = chunks[i + 1] if i + 1 < len(chunks) else ""
            alignments[i] = _eleven_chunk(chunks[i], voice_id, prev, nxt, files[i])
            tick()

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(job, range(len(chunks))))
        words: list[Word] = []
        offset = 0.0
        for f, al in zip(files, alignments):
            words += _chars_to_words(al, offset)
            offset += ffmpeg.duration(f)
        narration = audio_mod.concat_audio(files, os.path.join(out_dir, "narration.wav"), out_dir)
        return narration, words

    if provider == "edge":
        from app.services import voice as mpt_voice

        for i, chunk in enumerate(chunks):
            if cancel is not None and cancel.is_set():
                raise ffmpeg.Cancelled("cancelled")
            ok = None
            for attempt in range(3):
                ok = mpt_voice.tts(chunk, voice_id, 1.0, files[i])
                if ok is not None and os.path.isfile(files[i]):
                    break
                logger.warning(f"edge tts chunk {i} failed, retry {attempt + 1}")
                time.sleep(2)
            if ok is None:
                raise VoiceError("Edge TTS failed")
            tick()
        narration = audio_mod.concat_audio(files, os.path.join(out_dir, "narration.wav"), out_dir)
        return narration, None

    raise VoiceError(f"unknown voice provider '{provider}'")
