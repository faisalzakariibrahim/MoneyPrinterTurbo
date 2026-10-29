"""End-to-end worker test against a real Postgres running the real migration.

Requires: ``pip install pgserver "psycopg[binary]"`` and ffmpeg. Claude, Whisper and
ElevenLabs are mocked; FFmpeg rendering and all SQL (RLS, RPCs, metering) are real.

    python -m pytest test/longform/test_worker_e2e.py -s
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")
from psycopg.types.json import Jsonb  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = next((ROOT / "supabase" / "migrations").glob("*_longform_studio.sql"))

STUB = """
create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
create schema auth; create table auth.users (id uuid primary key, email text);
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
create function auth.role() returns text language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claim.role', true),''), current_user::text) $$;
create schema storage; create table storage.buckets (id text primary key, name text, public bool);
create table storage.objects (id uuid default gen_random_uuid(), bucket_id text, name text); alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language sql as $$ select (string_to_array(name,'/'))[1:array_length(string_to_array(name,'/'),1)-1] $$;
create publication supabase_realtime;
grant usage on schema public, auth, storage to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
"""


class FakeSupa:
    """Implements the worker's Supa interface with SQL as the service role."""

    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.lock = threading.Lock()

    def _conn(self):
        c = psycopg.connect(self.uri, autocommit=True)
        c.execute("set request.jwt.claim.role = 'service_role'")
        c.execute("set role service_role")
        return c

    def _rows(self, cur):
        if cur.description is None:
            return []
        cols = [d.name for d in cur.description]
        out = []
        for r in cur.fetchall():
            row = {}
            for k, v in zip(cols, r):
                if isinstance(v, uuid.UUID):
                    v = str(v)
                elif isinstance(v, list):
                    v = [str(x) if isinstance(x, uuid.UUID) else x for x in v]
                elif hasattr(v, "is_finite"):
                    v = float(v)
                row[k] = v
            out.append(row)
        return out

    def rpc(self, fn, params=None):
        from decimal import Decimal
        params = {k: (Decimal(str(v)) if isinstance(v, float) else v) for k, v in (params or {}).items()}
        args = ", ".join(f"{k} => %({k})s" for k in params)
        with self._conn() as c:
            cur = c.execute(f"select * from public.{fn}({args})", params)
            rows = self._rows(cur)
        if fn == "claim_job":
            return [r for r in rows if r.get("id")]
        return rows

    def select(self, table, match, columns="*"):
        where = " and ".join(f"{k} = %({k})s" for k in match) or "true"
        with self._conn() as c:
            return self._rows(c.execute(f"select {columns} from public.{table} where {where}", match))

    def select_in(self, table, column, values, columns="*"):
        with self._conn() as c:
            return self._rows(c.execute(f"select {columns} from public.{table} where {column} = any(%s)", (list(values),)))

    def one(self, table, match, columns="*"):
        rows = self.select(table, match, columns)
        if not rows:
            from app.longform.supa import SupaError
            raise SupaError(f"{table} row not found")
        return rows[0]

    def update(self, table, match, values):
        sets = ", ".join(f"{k} = %(v_{k})s" for k in values)
        where = " and ".join(f"{k} = %(m_{k})s" for k in match)
        params = {f"v_{k}": (Jsonb(v) if isinstance(v, dict) else v) for k, v in values.items()}
        params.update({f"m_{k}": v for k, v in match.items()})
        with self._conn() as c:
            c.execute(f"update public.{table} set {sets} where {where}", params)


def ff(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base = tmp_path_factory.mktemp("lf")
    store = base / "store"
    os.environ["LF_LOCAL_STORAGE_DIR"] = str(store)
    os.environ["LF_WORK_DIR"] = str(base / "work")
    os.environ["LF_CHUNK_SECONDS"] = "30"
    os.environ["ANTHROPIC_API_KEY"] = "test"
    from app.longform.settings import get_settings
    get_settings.cache_clear()

    # media
    lib = store / "library"
    (lib / "footage").mkdir(parents=True)
    (lib / "music").mkdir(parents=True)
    ff("-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "20", str(lib / "footage" / "a.mp4"))
    ff("-f", "lavfi", "-i", "mandelbrot=size=640x360:rate=30", "-t", "15", str(lib / "footage" / "b.mp4"))
    ff("-f", "lavfi", "-i", "sine=frequency=330:duration=30", str(lib / "music" / "m.mp3"))

    srv = pgserver.get_server(str(base / "pg"), cleanup_mode="stop")
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute("drop schema if exists public cascade; create schema public; grant all on schema public to public;")
        for s in ("auth", "storage"):
            c.execute(f"drop schema if exists {s} cascade")
        for r in ("anon", "authenticated", "service_role"):
            c.execute(f"do $$ begin if exists (select 1 from pg_roles where rolname='{r}') then "
                      f"execute 'drop owned by {r}'; execute 'drop role {r}'; end if; end $$")
        c.execute("drop publication if exists supabase_realtime")
        c.execute(STUB)
        c.execute(MIGRATION.read_text())
        user = uuid.uuid4()
        c.execute("insert into auth.users values (%s, 'faisal@example.com')", (user,))
        c.execute("update profiles set plan_id = 'internal' where id = %s", (user,))
        pack = c.execute("insert into footage_packs (name) values ('Test pack') returning id").fetchone()[0]
        for name in ("a.mp4", "b.mp4"):
            c.execute("insert into footage_assets (pack_id, storage_path, kind) values (%s, %s, 'video')",
                      (pack, f"library/footage/{name}"))
        music = c.execute("insert into music_tracks (name, storage_path) values ('Calm', 'library/music/m.mp3') returning id").fetchone()[0]
        niche = c.execute("insert into niches (name, status, style_profile, footage_pack_id) values "
                          "('Lore', 'ready', %s, %s) returning id",
                          (Jsonb({"name": "Lore", "words_per_minute": 150, "structure": {"minutes_per_chapter": 5}}), pack)).fetchone()[0]
    # user narration upload (75 s)
    up = store / str(user) / "uploads"
    up.mkdir(parents=True)
    ff("-f", "lavfi", "-i", "anoisesrc=d=75:c=pink:a=0.2", str(up / "voice.wav"))
    yield {"uri": uri, "user": str(user), "pack": str(pack), "music": str(music), "niche": str(niche), "store": store}
    srv.cleanup()


def as_user(uri, user):
    c = psycopg.connect(uri, autocommit=True)
    c.execute(f"set request.jwt.claim.sub = '{user}'")
    c.execute("set request.jwt.claim.role = 'authenticated'")
    c.execute("set role authenticated")
    return c


def usage(env):
    with as_user(env["uri"], env["user"]) as c:
        return c.execute("select script_used, video_used from usage_summary()").fetchone()


def fake_words(total, n=120):
    from app.longform.captions import Word
    step = total / n
    return [Word(f"word{i}", i * step, i * step + step * 0.8) for i in range(n)]


def test_render_job_end_to_end(env, monkeypatch):
    from app.longform import align, worker
    monkeypatch.setattr(align, "words_for_audio", lambda path, text, **kw: fake_words(kw.get("duration") or 60))
    spec = {"resolution": "720p", "border": {"enabled": True}, "particles": {"enabled": True, "style": "dust"}}
    with as_user(env["uri"], env["user"]) as c:
        render_id = c.execute(
            "select create_render_job('My first ULF', null, %s, %s, 'upload', null, %s, %s, %s, 2)",
            (env["niche"], env["pack"], f"{env['user']}/uploads/voice.wav", [env["music"]], Jsonb(spec)),
        ).fetchone()[0]
    assert float(usage(env)[1]) == 2
    db = FakeSupa(env["uri"])
    job = db.rpc("claim_job", {"p_worker": "t", "p_types": ["render"]})[0]
    worker.run_one(db, job)

    r = db.one("renders", {"id": str(render_id)})
    assert r["status"] == "completed", r
    out = env["store"] / r["output_path"]
    assert out.is_file() and abs(r["duration_seconds"] - 75) < 0.5
    assert (env["store"] / r["srt_path"]).is_file()
    j = db.one("jobs", {"id": job["id"]})
    assert j["status"] == "completed" and float(j["progress"]) == 1
    # Reserved 2 minutes, actual 1.25 -> settled
    assert abs(float(usage(env)[1]) - 1.25) < 0.01


def test_render_cancel_refunds(env, monkeypatch):
    from app.longform import align, worker
    monkeypatch.setattr(align, "words_for_audio", lambda path, text, **kw: fake_words(kw.get("duration") or 60))
    before = float(usage(env)[1])
    with as_user(env["uri"], env["user"]) as c:
        render_id = c.execute(
            "select create_render_job('Cancel me', null, null, %s, 'upload', null, %s, null, %s, 2)",
            (env["pack"], f"{env['user']}/uploads/voice.wav", Jsonb({"resolution": "1080p"})),
        ).fetchone()[0]
    db = FakeSupa(env["uri"])
    job = db.rpc("claim_job", {"p_worker": "t", "p_types": ["render"]})[0]

    def cancel_soon():
        time.sleep(3)
        with as_user(env["uri"], env["user"]) as c:
            c.execute("select cancel_job(%s)", (job["id"],))

    threading.Thread(target=cancel_soon, daemon=True).start()
    worker.run_one(db, job)
    assert db.one("jobs", {"id": job["id"]})["status"] == "cancelled"
    assert db.one("renders", {"id": str(render_id)})["status"] == "failed"
    assert abs(float(usage(env)[1]) - before) < 0.01, "cancelled render must be refunded"


def test_script_job_with_mocked_claude(env, monkeypatch):
    from app.longform import llm, worker

    def structured(**kw):
        if kw["tool_name"] == "save_outline":
            return {"title": "The Fall of the Iron Throne", "logline": "x", "hook_plan": "x", "outro_plan": "x",
                    "chapters": [{"title": f"Part {i}", "brief": "b", "beats": ["a"], "handoff": "h"} for i in range(4)]}
        return {"titles": ["T"], "description": "D", "tags": ["t"], "thumbnail_text": ["X"]}

    calls = {"n": 0}

    def text(**kw):
        calls["n"] += 1
        content = kw["messages"][-1]["content"]
        if "Summarise" in str(kw.get("system")):
            return "summary.", "end_turn"
        if "Continue this chapter" in content:
            return " ".join(["more"] * 200), "end_turn"
        if "cold-open" in content:
            return "## HOOK\nWhat if everything you knew was wrong? " + " ".join(["hook"] * 200), "end_turn"
        # first pass deliberately short to exercise the top-up path
        return "**Chapter**\n" + " ".join(["story"] * 300), "end_turn"

    monkeypatch.setattr(llm, "structured", structured)
    monkeypatch.setattr(llm, "text", text)
    with as_user(env["uri"], env["user"]) as c:
        sid = c.execute("select create_script_job(%s, 'What if the dragons never died', 20)", (env["niche"],)).fetchone()[0]
    db = FakeSupa(env["uri"])
    job = db.rpc("claim_job", {"p_worker": "t", "p_types": ["script"]})[0]
    worker.run_one(db, job)
    s = db.one("scripts", {"id": str(sid)})
    assert s["status"] == "completed", s
    content = s["content"]
    assert len(content["chapters"]) == 4
    assert all("##" not in ch["text"] and "**" not in ch["text"] for ch in content["chapters"])
    assert "## HOOK" not in content["hook"]
    assert s["words"] > 1800  # 300 + top-up per chapter + hook
    assert content["metadata"]["titles"] == ["T"]
    assert float(usage(env)[0]) == 20


def test_niche_training_from_transcript(env, monkeypatch):
    from app.longform import llm, worker
    monkeypatch.setattr(llm, "structured", lambda **kw: {"name": "Dark Lore", "summary": "Slow, eerie lore.",
                                                         "tone": ["eerie"], "pov": "you", "hook": {"pattern": "q", "techniques": []},
                                                         "structure": {"intro": "", "chapter_pattern": "", "minutes_per_chapter": 8, "outro": ""},
                                                         "retention_devices": [], "do": [], "dont": [], "topic_ideas": []})
    transcript = " ".join(["Long ago in a forgotten kingdom the old gods slept beneath the ice."] * 120)
    with as_user(env["uri"], env["user"]) as c:
        nid = c.execute("select create_niche_job('Dark Lore', null, %s)", (transcript,)).fetchone()[0]
    db = FakeSupa(env["uri"])
    job = db.rpc("claim_job", {"p_worker": "t", "p_types": ["train_niche"]})[0]
    worker.run_one(db, job)
    n = db.one("niches", {"id": str(nid)})
    assert n["status"] == "ready"
    assert n["style_profile"]["name"] == "Dark Lore" and n["style_profile"]["words_per_minute"] > 0


def test_worker_rejects_foreign_storage_paths(env):
    from app.longform import storage
    with pytest.raises(storage.StorageError):
        storage.validate_key(f"{uuid.uuid4()}/uploads/x.wav", allowed_prefixes=(f"{env['user']}/uploads/",))
    with pytest.raises(storage.StorageError):
        storage.validate_key(f"{env['user']}/uploads/../../etc/passwd", allowed_prefixes=(f"{env['user']}/uploads/",))
