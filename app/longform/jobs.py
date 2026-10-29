"""Job handlers: train_niche, script, render, publish.

The database RPCs already checked plan limits and ownership when the job was
created, but the worker re-validates everything it touches (owner of every row,
every storage key) because the job payload is user-influenced input.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass
from typing import Callable

from loguru import logger

from app.longform import align, captions, ffmpeg, niche, render, script, storage, voice, youtube
from app.longform.secrets_box import decrypt
from app.longform.settings import get_settings
from app.longform.supa import Supa


class JobFailed(RuntimeError):
    """An error whose message is safe to show the user."""


@dataclass
class Ctx:
    db: Supa
    job: dict
    progress: Callable[[float, str], None]
    cancel: threading.Event

    @property
    def user(self) -> str:
        return self.job["user_id"]

    @property
    def work_dir(self) -> str:
        d = os.path.join(get_settings().work_dir, "jobs", self.job["id"])
        os.makedirs(d, exist_ok=True)
        return d

    def check(self) -> None:
        if self.cancel.is_set():
            raise ffmpeg.Cancelled("cancelled")


def _owned_or_public(row: dict, user: str, owner_key: str = "owner_id") -> bool:
    return row.get(owner_key) in (None, user)


# --------------------------------------------------------------------------- niche
def handle_train_niche(ctx: Ctx) -> float | None:
    db, job = ctx.db, ctx.job
    row = db.one("niches", {"id": job["ref_id"]})
    if row["owner_id"] != ctx.user:
        raise JobFailed("niche not found")
    payload = job.get("payload") or {}
    ctx.progress(0.1, "Reading reference video")
    try:
        if payload.get("transcript"):
            t = niche.transcript_from_text(payload["transcript"], title=row["name"])
        else:
            t = niche.fetch_transcript(payload.get("url") or "")
    except niche.NicheError as e:
        raise JobFailed(str(e)) from e
    ctx.check()
    ctx.progress(0.35, "Learning the style")
    profile = niche.analyze_style(t)
    db.update("niches", {"id": row["id"]}, {
        "status": "ready",
        "style_profile": profile,
        "description": profile.get("summary", "")[:500],
    })
    return None


def _fail_niche(db: Supa, job: dict, _msg: str) -> None:
    db.update("niches", {"id": job["ref_id"], "owner_id": job["user_id"]}, {"status": "failed"})


# --------------------------------------------------------------------------- script
def _load_profile(db: Supa, niche_id: str | None, user: str) -> dict:
    if not niche_id:
        raise JobFailed("script has no niche")
    n = db.one("niches", {"id": niche_id})
    if not _owned_or_public(n, user) or n["status"] != "ready":
        raise JobFailed("niche not available")
    return n.get("style_profile") or {}


def handle_script(ctx: Ctx) -> float | None:
    db = ctx.db
    row = db.one("scripts", {"id": ctx.job["ref_id"]})
    if row["user_id"] != ctx.user:
        raise JobFailed("script not found")
    profile = _load_profile(db, row["niche_id"], ctx.user)
    db.update("scripts", {"id": row["id"]}, {"status": "processing", "error": None})
    last_push = [0.0]

    def push_partial(s: script.Script) -> None:
        if time.time() - last_push[0] < 8:
            return
        last_push[0] = time.time()
        d = s.to_dict()
        db.update("scripts", {"id": row["id"]}, {
            "title": s.title, "outline": s.outline,
            "content": {"hook": d["hook"], "chapters": d["chapters"], "metadata": {}},
            "words": d["words"],
        })

    result = script.generate_script(
        profile=profile,
        topic=row["topic"],
        target_minutes=int(row["target_minutes"]),
        notes=row.get("notes") or "",
        with_research=bool(row.get("research")),
        on_progress=ctx.progress,
        cancel=ctx.cancel,
        on_chapter=push_partial,
    )
    d = result.to_dict()
    db.update("scripts", {"id": row["id"]}, {
        "status": "completed",
        "title": result.title,
        "outline": result.outline,
        "content": {"hook": d["hook"], "chapters": d["chapters"], "metadata": result.metadata},
        "words": d["words"],
        "est_minutes": d["est_minutes"],
    })
    return None  # script usage is billed at the requested length


def _fail_script(db: Supa, job: dict, msg: str) -> None:
    db.update("scripts", {"id": job["ref_id"], "user_id": job["user_id"]}, {"status": "failed", "error": msg})


def script_text(content: dict | None) -> str:
    content = content or {}
    parts = [content.get("hook") or ""] + [c.get("text") or "" for c in content.get("chapters") or []]
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


# --------------------------------------------------------------------------- render
def handle_render(ctx: Ctx) -> float | None:
    db, s = ctx.db, get_settings()
    row = db.one("renders", {"id": ctx.job["ref_id"]})
    user = ctx.user
    if row["user_id"] != user:
        raise JobFailed("render not found")
    db.update("renders", {"id": row["id"]}, {"status": "processing", "error": None})
    lib_cache = os.path.join(s.work_dir, "library-cache")
    allowed = (f"{user}/", "library/")

    # Footage pack (own or public) and its assets.
    pack = db.one("footage_packs", {"id": row["footage_pack_id"]})
    if not _owned_or_public(pack, user):
        raise JobFailed("footage pack not available")
    assets = db.select("footage_assets", {"pack_id": pack["id"]})
    if not assets:
        raise JobFailed("footage pack is empty")
    ctx.progress(0.01, "Fetching footage")
    footage_files = [
        storage.download_cached(storage.validate_key(a["storage_path"], allowed_prefixes=allowed), lib_cache)
        for a in assets
    ]
    music_files: list[str] = []
    if row.get("music_track_ids"):
        for t in db.select_in("music_tracks", "id", row["music_track_ids"]):
            if _owned_or_public(t, user):
                music_files.append(storage.download_cached(
                    storage.validate_key(t["storage_path"], allowed_prefixes=allowed), lib_cache))
    ctx.check()

    text = ""
    if row.get("script_id"):
        sc = db.one("scripts", {"id": row["script_id"]})
        if sc["user_id"] != user:
            raise JobFailed("script not available")
        text = script_text(sc.get("content"))

    # Narration + word timings.
    work = ctx.work_dir
    words: list[captions.Word] | None
    if row["voice_source"] == "upload":
        key = storage.validate_key(row["audio_path"] or "", allowed_prefixes=(f"{user}/uploads/",))
        ctx.progress(0.03, "Fetching narration")
        src = storage.download(key, os.path.join(work, "upload" + os.path.splitext(key)[1].lower()))
        if not ffmpeg.has_stream(src, "audio"):
            raise JobFailed("the uploaded file has no audio track")
        narration = os.path.join(work, "narration.wav")
        ffmpeg.run(["-i", src, "-vn", "-ac", "1", "-ar", "48000", narration])
        words = None
    else:
        if not text:
            raise JobFailed("script is empty")
        ctx.progress(0.03, "Recording voiceover")
        try:
            narration, words = voice.synthesize(
                text, f"{row['voice_source']}:{row.get('voice_id') or ''}", os.path.join(work, "tts"),
                on_progress=lambda f: ctx.progress(0.03 + 0.10 * f, "Recording voiceover"), cancel=ctx.cancel,
            )
        except voice.VoiceError as e:
            raise JobFailed(str(e)) from e
    total = ffmpeg.duration(narration)
    if total > s.max_video_minutes * 60:
        raise JobFailed(f"narration is longer than {s.max_video_minutes} minutes")
    spec = render.RenderSpec.from_dict({**(row.get("spec") or {}), "seed": row["id"]})
    if words is None and spec.captions.enabled:
        ctx.progress(0.13, "Syncing captions to the voice")
        words = align.words_for_audio(
            narration, text or None, duration=total,
            on_progress=lambda f: ctx.progress(0.13 + 0.07 * f, "Syncing captions to the voice"), cancel=ctx.cancel,
        )
    words = words or []
    ctx.check()

    out = os.path.join(work, "final.mp4")
    result = render.render_longform(
        narration_path=narration, words=words, footage_sources=footage_files, music_sources=music_files,
        spec=spec, work_dir=os.path.join(work, "render"), out_path=out,
        on_progress=lambda f, st: ctx.progress(0.20 + 0.70 * f, st), cancel=ctx.cancel,
    )

    ctx.progress(0.92, "Uploading video")
    out_key = f"{user}/renders/{row['id']}.mp4"
    storage.upload(out, out_key, "video/mp4")
    srt_key = None
    if words:
        srt_local = os.path.join(work, "captions.srt")
        with open(srt_local, "w", encoding="utf-8") as fh:
            fh.write(captions.words_to_srt(words))
        srt_key = f"{user}/renders/{row['id']}.srt"
        storage.upload(srt_local, srt_key, "application/x-subrip")
    db.update("renders", {"id": row["id"]}, {
        "status": "completed",
        "output_path": out_key,
        "output_bytes": os.path.getsize(out),
        "srt_path": srt_key,
        "duration_seconds": round(result.duration, 2),
    })
    # Keep the final file briefly for a fast YouTube publish; drop everything else.
    keep = _render_cache_path(row["id"])
    os.replace(out, keep)
    shutil.rmtree(work, ignore_errors=True)
    _prune_render_cache()
    return result.duration / 60


def _render_cache_path(render_id: str) -> str:
    d = os.path.join(get_settings().work_dir, "renders-cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{render_id}.mp4")


def _prune_render_cache(max_age_hours: float = 48) -> None:
    d = os.path.join(get_settings().work_dir, "renders-cache")
    cutoff = time.time() - max_age_hours * 3600
    for name in os.listdir(d):
        path = os.path.join(d, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def _fail_render(db: Supa, job: dict, msg: str) -> None:
    db.update("renders", {"id": job["ref_id"], "user_id": job["user_id"]}, {"status": "failed", "error": msg})


# --------------------------------------------------------------------------- publish
def handle_publish(ctx: Ctx) -> float | None:
    db, user = ctx.db, ctx.user
    p = ctx.job.get("payload") or {}
    row = db.one("renders", {"id": ctx.job["ref_id"]})
    if row["user_id"] != user or row["status"] != "completed" or not row.get("output_path"):
        raise JobFailed("render not ready")
    ch = db.one("youtube_channels", {"id": p.get("channel_id")})
    if ch["user_id"] != user:
        raise JobFailed("channel not found")
    token = decrypt(ch["refresh_token_enc"])
    key = storage.validate_key(row["output_path"], allowed_prefixes=(f"{user}/renders/",))
    local = _render_cache_path(row["id"])
    if not (os.path.isfile(local) and os.path.getsize(local) == row.get("output_bytes")):
        ctx.progress(0.02, "Fetching video")
        storage.download(key, local)
    ctx.progress(0.05, "Uploading to YouTube")
    try:
        vid = youtube.upload_video(
            local, refresh_token=token, title=p.get("title") or row["title"],
            description=p.get("description") or "", tags=list(p.get("tags") or []),
            privacy=p.get("privacy") or "private", publish_at=p.get("publish_at"),
            synthetic_media=row["voice_source"] != "upload",
            on_progress=lambda f: ctx.progress(0.05 + 0.9 * f, "Uploading to YouTube"), cancel=ctx.cancel,
        )
    except youtube.YouTubeError as e:
        raise JobFailed(str(e)) from e
    if row.get("srt_path"):
        try:
            srt_local = storage.download(row["srt_path"], local + ".srt")
            with open(srt_local, encoding="utf-8") as fh:
                youtube.upload_captions(vid, fh.read(), token)
        except Exception as e:  # captions are a bonus; never fail the publish
            logger.warning(f"caption upload skipped: {e}")
    db.update("renders", {"id": row["id"]}, {"youtube_video_id": vid})
    return None


HANDLERS: dict[str, Callable[[Ctx], float | None]] = {
    "train_niche": handle_train_niche,
    "script": handle_script,
    "render": handle_render,
    "publish": handle_publish,
}

ON_FAIL: dict[str, Callable[[Supa, dict, str], None]] = {
    "train_niche": _fail_niche,
    "script": _fail_script,
    "render": _fail_render,
}
