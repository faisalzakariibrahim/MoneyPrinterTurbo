"""Pull-based job worker.

    python -m app.longform.worker                  # all job types
    LF_WORKER_TYPES=render python -m app.longform.worker
    LF_WORKER_TYPES=train_niche,script,publish LF_WORKER_CONCURRENCY=6 python -m app.longform.worker

The worker never listens on a port: it claims jobs from Postgres with
``FOR UPDATE SKIP LOCKED`` (see ``claim_job``), heartbeats progress, and stops a job
as soon as the user cancels it. Crashed jobs are re-claimed after their heartbeat
goes stale, and renders resume from their finished chunks.
"""

from __future__ import annotations

import os
import signal
import socket
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

from loguru import logger

from app.longform import ffmpeg, llm
from app.longform.jobs import HANDLERS, ON_FAIL, Ctx, JobFailed
from app.longform.supa import Supa, SupaError

STOP = threading.Event()


class Heartbeat:
    """Batches progress updates and polls for cancellation every few seconds."""

    def __init__(self, db: Supa, job_id: str, cancel: threading.Event, every: float = 5.0) -> None:
        self.db, self.job_id, self.cancel, self.every = db, job_id, cancel, every
        self._latest: tuple[float, str] = (0.0, "Starting")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def progress(self, frac: float, stage: str) -> None:
        with self._lock:
            self._latest = (round(max(0.0, min(0.999, frac)), 4), stage[:120])

    def _push(self) -> None:
        with self._lock:
            frac, stage = self._latest
        try:
            self.db.update("jobs", {"id": self.job_id, "status": "processing"}, {
                "progress": frac, "stage": stage,
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            })
            row = self.db.one("jobs", {"id": self.job_id}, "cancel_requested")
            if row.get("cancel_requested"):
                self.cancel.set()
        except SupaError as e:
            logger.warning(f"heartbeat failed: {e}")

    def _run(self) -> None:
        while not self._stop.wait(self.every):
            self._push()

    def __enter__(self) -> "Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        self._push()


def _user_message(exc: BaseException) -> str:
    if isinstance(exc, JobFailed):
        return str(exc)
    if isinstance(exc, llm.LLMError):
        return "The AI model is unavailable right now. Your minutes were refunded — please retry."
    if isinstance(exc, ffmpeg.FFmpegError):
        return "Video processing failed. Your minutes were refunded — please retry or contact support."
    return "Something went wrong. Your minutes were refunded — please retry."


def run_one(db: Supa, job: dict) -> None:
    jid, jtype = job["id"], job["type"]
    cancel = threading.Event()
    logger.info(f"job {jid} ({jtype}) attempt {job.get('attempts')}")
    status, msg, actual = "failed", None, None
    fatal: BaseException | None = None
    with Heartbeat(db, jid, cancel) as hb:
        ctx = Ctx(db=db, job=job, progress=hb.progress, cancel=cancel)
        try:
            actual = HANDLERS[jtype](ctx)
            status = "completed"
        except ffmpeg.Cancelled as e:
            status = "cancelled"
            logger.info(f"job {jid} cancelled: {e}")
        except BaseException as e:  # noqa: BLE001 — every failure must be recorded
            if cancel.is_set():
                status = "cancelled"
            else:
                msg = _user_message(e)
                logger.error(f"job {jid} failed: {e}\n{traceback.format_exc()}")
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                fatal = e
    # Record the outcome only after the heartbeat has stopped, so a late progress
    # flush can never overwrite the final state.
    try:
        if status != "completed" and jtype in ON_FAIL:
            ON_FAIL[jtype](db, job, msg or "Cancelled")
        db.rpc("finish_job", {"p_job": jid, "p_status": status, "p_error": msg,
                              "p_actual_minutes": actual if status == "completed" else None})
        logger.info(f"job {jid} {status}")
    except SupaError as e:
        logger.error(f"could not record job {jid} outcome: {e}")
    if fatal is not None:
        raise fatal


def loop(types: list[str], worker_id: str) -> None:
    db = Supa()
    idle = 2.0
    while not STOP.is_set():
        try:
            rows = db.rpc("claim_job", {"p_worker": worker_id, "p_types": types}) or []
        except SupaError as e:
            logger.warning(f"claim failed: {e}")
            rows = []
        if not rows:
            STOP.wait(idle)
            idle = min(10.0, idle * 1.3)
            continue
        idle = 2.0
        run_one(db, rows[0])


def main() -> None:
    types = [t.strip() for t in os.environ.get("LF_WORKER_TYPES", ",".join(HANDLERS)).split(",") if t.strip()]
    unknown = set(types) - set(HANDLERS)
    if unknown:
        raise SystemExit(f"unknown job types: {unknown}")
    n = max(1, int(os.environ.get("LF_WORKER_CONCURRENCY", "1")))
    base = f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    def _stop(*_):
        logger.info("stopping after current jobs…")
        STOP.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info(f"worker {base}: types={types} concurrency={n}")
    threads = [threading.Thread(target=loop, args=(types, f"{base}-{i}"), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(1)


if __name__ == "__main__":
    main()
