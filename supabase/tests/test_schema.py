# Runs the migration against an embedded Postgres with Supabase auth/storage stubs.
# Usage: pip install pgserver "psycopg[binary]" && python supabase/tests/test_schema.py supabase/migrations/<file>.sql /tmp/pgdata
import sys, uuid, pgserver, psycopg
MIG = sys.argv[1]
srv = pgserver.get_server(sys.argv[2], cleanup_mode="stop")
uri = srv.get_uri()
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
grant all on storage.objects to authenticated;
"""
with psycopg.connect(uri, autocommit=True) as c:
    c.execute("drop schema if exists public cascade; create schema public; grant all on schema public to public;")
    for s in ("auth","storage"): c.execute(f"drop schema if exists {s} cascade")
    for r in ("anon","authenticated","service_role"):
        c.execute(f"do $$ begin if exists (select 1 from pg_roles where rolname='{r}') then execute 'drop owned by {r}'; execute 'drop role {r}'; end if; end $$")
    c.execute("drop publication if exists supabase_realtime")
    c.execute(STUB)
    c.execute(open(MIG).read())
    print("migration applied")

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print("  PASS", name)
    else: fail += 1; print("  FAIL", name)

def as_user(c, uid):
    c.execute("reset role"); c.execute(f"set request.jwt.claim.sub = '{uid}'"); c.execute("set request.jwt.claim.role = 'authenticated'"); c.execute("set role authenticated")
def as_service(c):
    c.execute("reset role"); c.execute("set request.jwt.claim.sub = ''"); c.execute("set request.jwt.claim.role = 'service_role'"); c.execute("set role service_role")
def expect_error(c, sql, args=(), contains=""):
    try:
        with c.transaction(): c.execute(sql, args)
        return False
    except psycopg.Error as e:
        return contains.lower() in str(e).lower()

A, B = uuid.uuid4(), uuid.uuid4()
with psycopg.connect(uri, autocommit=True) as c:
    c.execute("insert into auth.users values (%s,'a@x.com'),(%s,'b@x.com')", (A, B))
    check("profiles auto-created", c.execute("select count(*) from public.profiles").fetchone()[0] == 2)
    pack = c.execute("insert into footage_packs (name) values ('Medieval') returning id").fetchone()[0]
    pub_niche = c.execute("insert into niches (name, status, style_profile, footage_pack_id) values ('Medieval Lore','ready','{\"name\":\"x\"}',%s) returning id", (pack,)).fetchone()[0]

    as_user(c, A)
    niche = c.execute("select create_niche_job('My niche','https://youtu.be/dQw4w9WgXcQ')").fetchone()[0]
    check("niche job created", c.execute("select count(*) from jobs where ref_id=%s and type='train_niche'", (niche,)).fetchone()[0] == 1)
    check("free plan: 1 trained niche slot", expect_error(c, "select create_niche_job('Second','https://youtu.be/dQw4w9WgXcQ')", contains="plan_limit"))
    check("can't script on a training niche", expect_error(c, "select create_script_job(%s,'Topic here',30)", (niche,), "not ready"))
    s1 = c.execute("select create_script_job(%s,'The fall of an empire',40)", (pub_niche,)).fetchone()[0]
    used = c.execute("select script_used, script_limit from usage_summary()").fetchone()
    check("script minutes reserved (40/60)", float(used[0]) == 40 and used[1] == 60)
    check("over-limit script blocked", expect_error(c, "select create_script_job(%s,'Another long one',30)", (pub_niche,), "plan_limit"))
    check("user can't set script status", expect_error(c, "update scripts set status='completed' where id=%s", (s1,), "permission denied"))
    check("user can't edit unfinished script", c.execute("update scripts set title='x' where id=%s returning id", (s1,)).fetchone() is None)
    check("user can't run worker RPC", expect_error(c, "select * from claim_job('w',array['script'])", contains="permission denied"))
    check("user can't insert ledger rows", expect_error(c, "insert into usage_ledger (user_id,kind,minutes) values (%s,'script',-500)", (A,), "row-level security"))
    check("user can't reserve directly", expect_error(c, "select _reserve(%s,'script',-100,null)", (A,), "permission denied"))

    as_user(c, B)
    check("user B can't see A's scripts", c.execute("select count(*) from scripts").fetchone()[0] == 0)
    check("user B can't see A's jobs", c.execute("select count(*) from jobs").fetchone()[0] == 0)
    check("user B sees public niche only", c.execute("select count(*) from niches").fetchone()[0] == 1)
    check("user B can't cancel A's job", c.execute("select cancel_job(id) from (select %s::uuid id) t", (uuid.uuid4(),)) is not None)

    as_service(c)
    job = c.execute("select * from claim_job('worker-1', array['script'])").fetchone()
    check("worker claims script job", job is not None)
    jid = job[0]
    check("second claim gets nothing", c.execute("select * from claim_job('worker-2', array['script'])").fetchone() is None)
    c.execute("select finish_job(%s,'failed','boom')", (jid,))
    as_user(c, A)
    check("failed job refunded", float(c.execute("select script_used from usage_summary()").fetchone()[0]) == 0)

    # render job checks
    check("borders blocked on free", expect_error(c, "select create_render_job('T',null,null,%s,'upload',null,%s,null,'{\"border\":{\"enabled\":true}}',20)",
          (pack, f"{A}/uploads/a.mp3"), "plan_limit"))
    check("4K blocked on free", expect_error(c, "select create_render_job('T',null,null,%s,'upload',null,%s,null,'{\"resolution\":\"2160p\"}',20)",
          (pack, f"{A}/uploads/a.mp3"), "plan_limit"))
    check("foreign audio path blocked", expect_error(c, "select create_render_job('T',null,null,%s,'upload',null,%s,null,'{}',20)",
          (pack, f"{B}/uploads/a.mp3"), "invalid audio path"))
    check("path traversal blocked", expect_error(c, "select create_render_job('T',null,null,%s,'upload',null,%s,null,'{}',20)",
          (pack, f"{A}/uploads/../../{B}/x.mp3"), "invalid audio path"))
    r1 = c.execute("select create_render_job('T',null,null,%s,'upload',null,%s,null,'{}',20)", (pack, f"{A}/uploads/a.mp3")).fetchone()[0]
    check("render created + 20 video min reserved", float(c.execute("select video_used from usage_summary()").fetchone()[0]) == 20)
    check("concurrency limit enforced", expect_error(c, "select create_render_job('T2',null,null,%s,'upload',null,%s,null,'{}',5)", (pack, f"{A}/uploads/b.mp3"), "plan_limit"))
    rjob = c.execute("select id from jobs where ref_id=%s", (r1,)).fetchone()[0]
    c.execute("select cancel_job(%s)", (rjob,))
    check("cancel queued render refunds", float(c.execute("select video_used from usage_summary()").fetchone()[0]) == 0)
    check("render marked cancelled", c.execute("select status from renders where id=%s", (r1,)).fetchone()[0] == "cancelled")

    # settle to actual
    r2 = c.execute("select create_render_job('T3',null,null,%s,'upload',null,%s,null,'{}',20)", (pack, f"{A}/uploads/c.mp3")).fetchone()[0]
    as_service(c)
    j2 = c.execute("select * from claim_job('w', array['render'])").fetchone()[0]
    c.execute("select finish_job(%s,'completed',null,23.4)", (j2,))
    as_user(c, A)
    check("usage settled to actual 23.4 min", abs(float(c.execute("select video_used from usage_summary()").fetchone()[0]) - 23.4) < 0.01)

    # youtube token column not readable
    as_service(c)
    c.execute("insert into youtube_channels (user_id, channel_id, title, refresh_token_enc) values (%s,'UC1','Chan','secret')", (A,))
    as_user(c, A)
    check("user reads own channel metadata", c.execute("select title from youtube_channels").fetchone()[0] == "Chan")
    check("user can't read refresh token", expect_error(c, "select refresh_token_enc from youtube_channels", contains="permission denied"))

    # stale job reaping
    as_service(c)
    c.execute("reset role")
    c.execute("insert into jobs (user_id,type,ref_id,status,attempts,heartbeat_at,usage_kind,reserved_minutes) values (%s,'render',gen_random_uuid(),'processing',3, now()-interval '1 hour','video',10)", (A,))
    c.execute("insert into usage_ledger (user_id,kind,minutes,note) values (%s,'video',10,'reserve')", (A,))
    as_service(c)
    c.execute("select * from claim_job('w', array['render'])")
    c.execute("reset role")
    check("dead job reaped as failed", c.execute("select count(*) from jobs where status='failed' and error like 'worker stopped%%'").fetchone()[0] == 1)

    # storage policies
    as_user(c, A)
    check("upload into own folder ok", c.execute("insert into storage.objects (bucket_id,name) values ('longform',%s) returning id", (f"{A}/uploads/x.mp3",)).fetchone() is not None)
    check("upload into other user's folder blocked", expect_error(c, "insert into storage.objects (bucket_id,name) values ('longform',%s)", (f"{B}/uploads/x.mp3",), "row-level security"))
    check("upload into library blocked", expect_error(c, "insert into storage.objects (bucket_id,name) values ('longform','library/footage/x.mp4')", (), "row-level security"))
    check("upload into renders/ blocked", expect_error(c, "insert into storage.objects (bucket_id,name) values ('longform',%s)", (f"{A}/renders/x.mp4",), "row-level security"))

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
