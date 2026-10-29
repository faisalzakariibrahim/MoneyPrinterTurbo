-- Long-form studio schema: plans, usage metering, niches, footage, scripts, renders,
-- YouTube channels and a pull-based job queue for the render worker.
--
-- Security model
--   * Every user table has RLS; users only ever see their own rows (+ public library rows).
--   * Users never write status/progress/output columns directly: jobs are created through
--     SECURITY DEFINER RPCs that check plan limits and reserve usage atomically.
--   * Worker-only RPCs are revoked from anon/authenticated and run with the service role.
--   * YouTube refresh tokens are AES-GCM encrypted by the app and the column is not
--     selectable by end users.

-- gen_random_uuid() is built in (PG13+); no extension needed.

-- ---------------------------------------------------------------------------
-- Plans & profiles
-- ---------------------------------------------------------------------------
create table public.plans (
  id text primary key,
  name text not null,
  script_minutes integer not null,       -- per billing period
  video_minutes integer not null,        -- per billing period
  trained_niches integer not null,
  max_resolution text not null default '1080p',
  concurrent_renders integer not null default 1,
  features jsonb not null default '{}'::jsonb,
  price_monthly_cents integer not null default 0,
  stripe_price_id text,
  sort integer not null default 0
);

insert into public.plans (id, name, script_minutes, video_minutes, trained_niches, max_resolution, concurrent_renders, features, price_monthly_cents, sort) values
  ('free',    'Trial',    60,     30,    1,  '1080p', 1, '{"borders":false,"particles":false,"elevenlabs":false,"youtube":false}', 0, 0),
  ('creator', 'Creator',  1200,   1200,  3,  '1440p', 1, '{"borders":true,"particles":false,"elevenlabs":true,"youtube":true}',  11900, 1),
  ('pro',     'Pro',      8400,   7200,  10, '2160p', 2, '{"borders":true,"particles":true,"elevenlabs":true,"youtube":true}',   23900, 2),
  ('scale',   'Scale',    18000,  15600, 25, '2160p', 3, '{"borders":true,"particles":true,"elevenlabs":true,"youtube":true}',   39900, 3),
  ('internal','Internal', 1000000,1000000,1000,'2160p',4, '{"borders":true,"particles":true,"elevenlabs":true,"youtube":true}',   0, 99);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  plan_id text not null default 'free' references public.plans(id),
  is_admin boolean not null default false,
  period_start timestamptz not null default date_trunc('month', now()),
  stripe_customer_id text unique,
  stripe_subscription_id text,
  created_at timestamptz not null default now()
);

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email) on conflict do nothing;
  return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Usage ledger (minutes). Positive = consumed/reserved, negative = refund.
-- ---------------------------------------------------------------------------
create table public.usage_ledger (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('script','video')),
  minutes numeric(10,2) not null,
  job_id uuid,
  note text,
  created_at timestamptz not null default now()
);
create index usage_ledger_user_idx on public.usage_ledger (user_id, kind, created_at);

-- ---------------------------------------------------------------------------
-- Library: footage packs, footage assets, music
-- ---------------------------------------------------------------------------
create table public.footage_packs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade, -- null = public library
  name text not null,
  description text,
  cover_path text,
  kind text not null default 'video' check (kind in ('video','image','combined')),
  created_at timestamptz not null default now()
);

create table public.footage_assets (
  id uuid primary key default gen_random_uuid(),
  pack_id uuid not null references public.footage_packs(id) on delete cascade,
  storage_path text not null,
  kind text not null check (kind in ('video','image')),
  duration_seconds numeric,
  size_bytes bigint,
  created_at timestamptz not null default now()
);
create index footage_assets_pack_idx on public.footage_assets (pack_id);

create table public.music_tracks (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade, -- null = public library
  name text not null,
  mood text,
  storage_path text not null,
  duration_seconds numeric,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Niches (script style profile + default footage pack)
-- ---------------------------------------------------------------------------
create table public.niches (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid references auth.users(id) on delete cascade, -- null = public niche
  name text not null,
  description text,
  source_url text,
  status text not null default 'ready' check (status in ('training','ready','failed')),
  style_profile jsonb not null default '{}'::jsonb,
  footage_pack_id uuid references public.footage_packs(id) on delete set null,
  thumbnail_url text,
  created_at timestamptz not null default now()
);
create index niches_owner_idx on public.niches (owner_id);

-- ---------------------------------------------------------------------------
-- Scripts & renders
-- ---------------------------------------------------------------------------
create table public.scripts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  niche_id uuid references public.niches(id) on delete set null,
  topic text not null check (char_length(topic) between 3 and 300),
  notes text check (char_length(notes) <= 4000),
  target_minutes integer not null check (target_minutes between 5 and 300),
  research boolean not null default false,
  status text not null default 'queued' check (status in ('queued','processing','completed','failed','cancelled')),
  title text,
  outline jsonb,
  content jsonb,          -- {hook, chapters:[{index,title,brief,text,summary,words}], metadata}
  words integer,
  est_minutes numeric,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index scripts_user_idx on public.scripts (user_id, created_at desc);

create table public.renders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  script_id uuid references public.scripts(id) on delete set null,
  niche_id uuid references public.niches(id) on delete set null,
  footage_pack_id uuid references public.footage_packs(id) on delete set null,
  title text not null check (char_length(title) between 1 and 200),
  voice_source text not null check (voice_source in ('upload','elevenlabs','edge')),
  voice_id text,
  audio_path text,        -- storage path for BYO narration
  music_track_ids uuid[] not null default '{}',
  spec jsonb not null default '{}'::jsonb,
  status text not null default 'queued' check (status in ('queued','processing','completed','failed','cancelled')),
  output_path text,
  output_bytes bigint,
  srt_path text,
  duration_seconds numeric,
  youtube_video_id text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index renders_user_idx on public.renders (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- YouTube channels (refresh token encrypted, never readable by users)
-- ---------------------------------------------------------------------------
create table public.youtube_channels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel_id text not null,
  title text,
  thumbnail_url text,
  refresh_token_enc text not null,
  created_at timestamptz not null default now(),
  unique (user_id, channel_id)
);

-- ---------------------------------------------------------------------------
-- Job queue
-- ---------------------------------------------------------------------------
create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type text not null check (type in ('train_niche','script','render','publish')),
  ref_id uuid not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'queued' check (status in ('queued','processing','completed','failed','cancelled')),
  progress numeric(5,4) not null default 0,
  stage text,
  error text,
  usage_kind text check (usage_kind in ('script','video')),
  reserved_minutes numeric(10,2) not null default 0,
  attempts integer not null default 0,
  cancel_requested boolean not null default false,
  worker_id text,
  heartbeat_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);
create index jobs_queue_idx on public.jobs (status, created_at) where status in ('queued','processing');
create index jobs_user_idx on public.jobs (user_id, created_at desc);
create index jobs_ref_idx on public.jobs (ref_id);

-- ---------------------------------------------------------------------------
-- updated_at
-- ---------------------------------------------------------------------------
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
create trigger scripts_touch before update on public.scripts for each row execute function public.touch_updated_at();
create trigger renders_touch before update on public.renders for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Row level security
-- ---------------------------------------------------------------------------
alter table public.plans enable row level security;
alter table public.profiles enable row level security;
alter table public.usage_ledger enable row level security;
alter table public.footage_packs enable row level security;
alter table public.footage_assets enable row level security;
alter table public.music_tracks enable row level security;
alter table public.niches enable row level security;
alter table public.scripts enable row level security;
alter table public.renders enable row level security;
alter table public.youtube_channels enable row level security;
alter table public.jobs enable row level security;

create policy plans_read on public.plans for select to authenticated, anon using (true);

create policy profiles_self on public.profiles for select to authenticated using (id = auth.uid());

create policy usage_self on public.usage_ledger for select to authenticated using (user_id = auth.uid());

create policy packs_read on public.footage_packs for select to authenticated
  using (owner_id is null or owner_id = auth.uid());
create policy packs_insert on public.footage_packs for insert to authenticated with check (owner_id = auth.uid());
create policy packs_update on public.footage_packs for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy packs_delete on public.footage_packs for delete to authenticated using (owner_id = auth.uid());

create policy assets_read on public.footage_assets for select to authenticated
  using (exists (select 1 from public.footage_packs p where p.id = pack_id and (p.owner_id is null or p.owner_id = auth.uid())));
create policy assets_write on public.footage_assets for insert to authenticated
  with check (
    exists (select 1 from public.footage_packs p where p.id = pack_id and p.owner_id = auth.uid())
    and storage_path like auth.uid()::text || '/%'
  );
create policy assets_delete on public.footage_assets for delete to authenticated
  using (exists (select 1 from public.footage_packs p where p.id = pack_id and p.owner_id = auth.uid()));

create policy music_read on public.music_tracks for select to authenticated using (owner_id is null or owner_id = auth.uid());
create policy music_insert on public.music_tracks for insert to authenticated
  with check (owner_id = auth.uid() and storage_path like auth.uid()::text || '/%');
create policy music_delete on public.music_tracks for delete to authenticated using (owner_id = auth.uid());

create policy niches_read on public.niches for select to authenticated using (owner_id is null or owner_id = auth.uid());
create policy niches_update on public.niches for update to authenticated
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy niches_delete on public.niches for delete to authenticated using (owner_id = auth.uid());

create policy scripts_read on public.scripts for select to authenticated using (user_id = auth.uid());
create policy scripts_delete on public.scripts for delete to authenticated using (user_id = auth.uid());

create policy renders_read on public.renders for select to authenticated using (user_id = auth.uid());
create policy renders_delete on public.renders for delete to authenticated using (user_id = auth.uid());

create policy jobs_read on public.jobs for select to authenticated using (user_id = auth.uid());

create policy yt_read on public.youtube_channels for select to authenticated using (user_id = auth.uid());
create policy yt_delete on public.youtube_channels for delete to authenticated using (user_id = auth.uid());
revoke select on public.youtube_channels from authenticated, anon;
grant select (id, user_id, channel_id, title, thumbnail_url, created_at) on public.youtube_channels to authenticated;

-- Users may only edit the narration text of their own finished scripts, nothing else.
revoke update on public.scripts from authenticated;
grant update (content, title) on public.scripts to authenticated;
create policy scripts_edit on public.scripts for update to authenticated
  using (user_id = auth.uid() and status = 'completed') with check (user_id = auth.uid());

-- Niche names/footage pack are user-editable, the style profile is too (power users tweak it).
revoke update on public.niches from authenticated;
grant update (name, description, style_profile, footage_pack_id) on public.niches to authenticated;

-- ---------------------------------------------------------------------------
-- Usage helpers
-- ---------------------------------------------------------------------------
create or replace function public.usage_summary(p_user uuid default auth.uid())
returns table (plan_id text, script_used numeric, script_limit integer, video_used numeric, video_limit integer, period_start timestamptz)
language sql stable security definer set search_path = public as $$
  select pr.plan_id,
         coalesce((select sum(minutes) from usage_ledger u where u.user_id = pr.id and u.kind = 'script' and u.created_at >= pr.period_start), 0),
         pl.script_minutes,
         coalesce((select sum(minutes) from usage_ledger u where u.user_id = pr.id and u.kind = 'video' and u.created_at >= pr.period_start), 0),
         pl.video_minutes,
         pr.period_start
  from profiles pr join plans pl on pl.id = pr.plan_id
  where pr.id = p_user and (p_user = auth.uid() or auth.role() = 'service_role');
$$;

-- Atomically check the plan allowance and reserve minutes for a job.
create or replace function public._reserve(p_user uuid, p_kind text, p_minutes numeric, p_job uuid)
returns void language plpgsql security definer set search_path = public as $$
declare
  v_limit integer;
  v_used numeric;
  v_period timestamptz;
begin
  -- Serialise reservations per user so two tabs can't double-spend.
  perform 1 from profiles where id = p_user for update;
  select case when p_kind = 'script' then pl.script_minutes else pl.video_minutes end, pr.period_start
    into v_limit, v_period
    from profiles pr join plans pl on pl.id = pr.plan_id where pr.id = p_user;
  if v_limit is null then raise exception 'profile not found'; end if;
  select coalesce(sum(minutes), 0) into v_used from usage_ledger
    where user_id = p_user and kind = p_kind and created_at >= v_period;
  if v_used + p_minutes > v_limit then
    raise exception 'plan_limit: not enough % minutes left (% of % used)', p_kind, round(v_used), v_limit
      using errcode = 'P0001';
  end if;
  insert into usage_ledger (user_id, kind, minutes, job_id, note) values (p_user, p_kind, p_minutes, p_job, 'reserve');
end $$;
revoke all on function public._reserve(uuid, text, numeric, uuid) from public, anon, authenticated;

create or replace function public._plan_feature(p_user uuid, p_feature text) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((pl.features ->> p_feature)::boolean, false)
  from profiles pr join plans pl on pl.id = pr.plan_id where pr.id = p_user;
$$;
revoke all on function public._plan_feature(uuid, text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- User-facing RPCs (create work)
-- ---------------------------------------------------------------------------
create or replace function public.create_niche_job(p_name text, p_source_url text, p_transcript text default null, p_footage_pack uuid default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_user uuid := auth.uid();
  v_niche uuid;
  v_job uuid;
  v_count integer;
  v_limit integer;
begin
  if v_user is null then raise exception 'not authenticated'; end if;
  if coalesce(trim(p_name), '') = '' or char_length(p_name) > 80 then raise exception 'invalid name'; end if;
  if p_source_url is null and coalesce(char_length(p_transcript), 0) < 1000 then
    raise exception 'provide a YouTube link or paste a transcript';
  end if;
  if char_length(coalesce(p_transcript, '')) > 400000 then raise exception 'transcript too long'; end if;
  if p_footage_pack is not null and not exists (
    select 1 from footage_packs where id = p_footage_pack and (owner_id is null or owner_id = v_user)) then
    raise exception 'footage pack not found';
  end if;
  select pl.trained_niches into v_limit from profiles pr join plans pl on pl.id = pr.plan_id where pr.id = v_user;
  select count(*) into v_count from niches where owner_id = v_user and status <> 'failed';
  if v_count >= v_limit then raise exception 'plan_limit: trained niche slots full (%)', v_limit using errcode = 'P0001'; end if;

  insert into niches (owner_id, name, source_url, status, footage_pack_id)
    values (v_user, trim(p_name), p_source_url, 'training', p_footage_pack) returning id into v_niche;
  insert into jobs (user_id, type, ref_id, payload)
    values (v_user, 'train_niche', v_niche, jsonb_build_object('url', p_source_url, 'transcript', p_transcript))
    returning id into v_job;
  return v_niche;
end $$;

create or replace function public.create_script_job(p_niche uuid, p_topic text, p_target_minutes integer, p_notes text default null, p_research boolean default false)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_user uuid := auth.uid();
  v_script uuid;
  v_job uuid := gen_random_uuid();
begin
  if v_user is null then raise exception 'not authenticated'; end if;
  if not exists (select 1 from niches where id = p_niche and status = 'ready' and (owner_id is null or owner_id = v_user)) then
    raise exception 'niche not found or not ready';
  end if;
  if p_target_minutes < 5 or p_target_minutes > 300 then raise exception 'target length must be 5-300 minutes'; end if;
  perform _reserve(v_user, 'script', p_target_minutes, v_job);
  insert into scripts (user_id, niche_id, topic, notes, target_minutes, research)
    values (v_user, p_niche, trim(p_topic), p_notes, p_target_minutes, coalesce(p_research, false)) returning id into v_script;
  insert into jobs (id, user_id, type, ref_id, usage_kind, reserved_minutes)
    values (v_job, v_user, 'script', v_script, 'script', p_target_minutes);
  return v_script;
end $$;

create or replace function public.create_render_job(
  p_title text, p_script uuid, p_niche uuid, p_footage_pack uuid, p_voice_source text, p_voice_id text,
  p_audio_path text, p_music uuid[], p_spec jsonb, p_est_minutes numeric
) returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_user uuid := auth.uid();
  v_render uuid;
  v_job uuid := gen_random_uuid();
  v_active integer;
  v_concurrent integer;
  v_maxres text;
  v_res text := coalesce(p_spec ->> 'resolution', '1080p');
  v_rank jsonb := '{"720p":1,"1080p":2,"1440p":3,"2160p":4}';
begin
  if v_user is null then raise exception 'not authenticated'; end if;
  if p_voice_source not in ('upload','elevenlabs','edge') then raise exception 'invalid voice source'; end if;
  if p_voice_source = 'upload' and (p_audio_path is null or p_audio_path not like v_user::text || '/%' or p_audio_path like '%..%') then
    raise exception 'invalid audio path';
  end if;
  if p_voice_source <> 'upload' and p_script is null then raise exception 'built-in voice needs a script'; end if;
  if p_voice_source = 'elevenlabs' and not _plan_feature(v_user, 'elevenlabs') then
    raise exception 'plan_limit: built-in ElevenLabs voice needs Creator or above' using errcode = 'P0001';
  end if;
  if p_script is not null and not exists (select 1 from scripts where id = p_script and user_id = v_user and status = 'completed') then
    raise exception 'script not found';
  end if;
  if p_footage_pack is null or not exists (select 1 from footage_packs where id = p_footage_pack and (owner_id is null or owner_id = v_user)) then
    raise exception 'footage pack not found';
  end if;
  if exists (select 1 from unnest(coalesce(p_music, '{}')) m
             where not exists (select 1 from music_tracks t where t.id = m and (t.owner_id is null or t.owner_id = v_user))) then
    raise exception 'music track not found';
  end if;
  if not (v_rank ? v_res) then raise exception 'invalid resolution'; end if;
  select pl.max_resolution, pl.concurrent_renders into v_maxres, v_concurrent
    from profiles pr join plans pl on pl.id = pr.plan_id where pr.id = v_user;
  if (v_rank ->> v_res)::int > (v_rank ->> v_maxres)::int then
    raise exception 'plan_limit: % rendering needs a higher plan', v_res using errcode = 'P0001';
  end if;
  if coalesce((p_spec #>> '{border,enabled}')::boolean, false) and not _plan_feature(v_user, 'borders') then
    raise exception 'plan_limit: borders need a higher plan' using errcode = 'P0001';
  end if;
  if coalesce((p_spec #>> '{particles,enabled}')::boolean, false) and not _plan_feature(v_user, 'particles') then
    raise exception 'plan_limit: particles need a higher plan' using errcode = 'P0001';
  end if;
  select count(*) into v_active from jobs where user_id = v_user and type = 'render' and status in ('queued','processing');
  if v_active >= v_concurrent then
    raise exception 'plan_limit: % render(s) already running', v_active using errcode = 'P0001';
  end if;
  if p_est_minutes is null or p_est_minutes < 1 or p_est_minutes > 300 then raise exception 'invalid length'; end if;

  perform _reserve(v_user, 'video', ceil(p_est_minutes), v_job);
  insert into renders (user_id, script_id, niche_id, footage_pack_id, title, voice_source, voice_id, audio_path, music_track_ids, spec)
    values (v_user, p_script, p_niche, p_footage_pack, left(trim(p_title), 200), p_voice_source, p_voice_id, p_audio_path, coalesce(p_music, '{}'), coalesce(p_spec, '{}'))
    returning id into v_render;
  insert into jobs (id, user_id, type, ref_id, usage_kind, reserved_minutes)
    values (v_job, v_user, 'render', v_render, 'video', ceil(p_est_minutes));
  return v_render;
end $$;

create or replace function public.create_publish_job(p_render uuid, p_channel uuid, p_title text, p_description text, p_tags text[], p_privacy text, p_publish_at timestamptz default null)
returns uuid language plpgsql security definer set search_path = public as $$
declare
  v_user uuid := auth.uid();
  v_job uuid;
begin
  if v_user is null then raise exception 'not authenticated'; end if;
  if not _plan_feature(v_user, 'youtube') then raise exception 'plan_limit: YouTube publishing needs Creator or above' using errcode = 'P0001'; end if;
  if not exists (select 1 from renders where id = p_render and user_id = v_user and status = 'completed') then raise exception 'render not found'; end if;
  if not exists (select 1 from youtube_channels where id = p_channel and user_id = v_user) then raise exception 'channel not found'; end if;
  if p_privacy not in ('private','unlisted','public') then raise exception 'invalid privacy'; end if;
  insert into jobs (user_id, type, ref_id, payload) values (v_user, 'publish', p_render, jsonb_build_object(
    'channel_id', p_channel, 'title', left(p_title, 100), 'description', left(p_description, 5000),
    'tags', to_jsonb(coalesce(p_tags, '{}')), 'privacy', p_privacy, 'publish_at', p_publish_at)) returning id into v_job;
  return v_job;
end $$;

create or replace function public.cancel_job(p_job uuid) returns void
language sql security definer set search_path = public as $$
  update jobs set cancel_requested = true,
    status = case when status = 'queued' then 'cancelled' else status end
  where id = p_job and user_id = auth.uid() and status in ('queued','processing');
$$;

-- Refund reservations when a queued job is cancelled before a worker picks it up.
create or replace function public._on_job_cancel() returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.status = 'cancelled' and old.status = 'queued' and new.reserved_minutes > 0 then
    insert into usage_ledger (user_id, kind, minutes, job_id, note)
      values (new.user_id, new.usage_kind, -new.reserved_minutes, new.id, 'refund: cancelled');
    update scripts set status = 'cancelled' where id = new.ref_id and new.type = 'script';
    update renders set status = 'cancelled' where id = new.ref_id and new.type = 'render';
  end if;
  return new;
end $$;
create trigger jobs_cancel_refund after update of status on public.jobs
  for each row execute function public._on_job_cancel();

grant execute on function public.usage_summary(uuid) to authenticated;
grant execute on function public.create_niche_job(text, text, text, uuid) to authenticated;
grant execute on function public.create_script_job(uuid, text, integer, text, boolean) to authenticated;
grant execute on function public.create_render_job(text, uuid, uuid, uuid, text, text, text, uuid[], jsonb, numeric) to authenticated;
grant execute on function public.create_publish_job(uuid, uuid, text, text, text[], text, timestamptz) to authenticated;
grant execute on function public.cancel_job(uuid) to authenticated;
revoke execute on function public.create_niche_job(text, text, text, uuid) from anon;
revoke execute on function public.create_script_job(uuid, text, integer, text, boolean) from anon;
revoke execute on function public.create_render_job(text, uuid, uuid, uuid, text, text, text, uuid[], jsonb, numeric) from anon;
revoke execute on function public.create_publish_job(uuid, uuid, text, text, text[], text, timestamptz) from anon;
revoke execute on function public.cancel_job(uuid) from anon;

-- ---------------------------------------------------------------------------
-- Worker-only RPCs (service role)
-- ---------------------------------------------------------------------------
create or replace function public.claim_job(p_worker text, p_types text[], p_stale_minutes integer default 10)
returns setof public.jobs language plpgsql security definer set search_path = public as $$
declare
  v_id uuid;
  r record;
begin
  -- Reap jobs whose worker died too often, or that were cancelled while their worker died.
  for r in select id, cancel_requested from jobs
            where status = 'processing' and heartbeat_at < now() - make_interval(mins => p_stale_minutes)
              and (attempts >= 3 or cancel_requested)
            for update skip locked loop
    perform finish_job(r.id, case when r.cancel_requested then 'cancelled' else 'failed' end,
                       case when r.cancel_requested then null else 'worker stopped responding; retries exhausted' end);
  end loop;

  select id into v_id from jobs
   where type = any(p_types)
     and cancel_requested = false
     and attempts < 3
     and (status = 'queued'
          or (status = 'processing' and heartbeat_at < now() - make_interval(mins => p_stale_minutes)))
   order by created_at
   for update skip locked
   limit 1;
  if v_id is null then return; end if;
  return query
    update jobs set status = 'processing', worker_id = p_worker, attempts = attempts + 1,
      heartbeat_at = now(), started_at = coalesce(started_at, now()), error = null
    where id = v_id returning *;
end $$;

create or replace function public.finish_job(p_job uuid, p_status text, p_error text default null, p_actual_minutes numeric default null)
returns void language plpgsql security definer set search_path = public as $$
declare
  j jobs%rowtype;
begin
  select * into j from jobs where id = p_job for update;
  if not found then return; end if;
  update jobs set status = p_status, error = p_error, finished_at = now(),
    progress = case when p_status = 'completed' then 1 else progress end
  where id = p_job;
  if j.reserved_minutes > 0 and j.usage_kind is not null then
    if p_status in ('failed','cancelled') then
      insert into usage_ledger (user_id, kind, minutes, job_id, note)
        values (j.user_id, j.usage_kind, -j.reserved_minutes, j.id, 'refund: ' || p_status);
    elsif p_status = 'completed' and p_actual_minutes is not null and abs(p_actual_minutes - j.reserved_minutes) >= 0.5 then
      insert into usage_ledger (user_id, kind, minutes, job_id, note)
        values (j.user_id, j.usage_kind, round(p_actual_minutes - j.reserved_minutes, 2), j.id, 'settle to actual');
    end if;
  end if;
end $$;

revoke all on function public.claim_job(text, text[], integer) from public, anon, authenticated;
revoke all on function public.finish_job(uuid, text, text, numeric) from public, anon, authenticated;
grant execute on function public.claim_job(text, text[], integer) to service_role;
grant execute on function public.finish_job(uuid, text, text, numeric) to service_role;

-- Realtime progress for the dashboard.
alter publication supabase_realtime add table public.jobs;

-- ---------------------------------------------------------------------------
-- Storage: one private bucket, per-user prefixes, shared read-only library/
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public) values ('longform', 'longform', false)
  on conflict (id) do nothing;

create policy lf_read_own on storage.objects for select to authenticated
  using (bucket_id = 'longform' and ((storage.foldername(name))[1] = auth.uid()::text or (storage.foldername(name))[1] = 'library'));
create policy lf_insert_own on storage.objects for insert to authenticated
  with check (bucket_id = 'longform' and (storage.foldername(name))[1] = auth.uid()::text
              and (storage.foldername(name))[2] in ('uploads','footage','music'));
create policy lf_delete_own on storage.objects for delete to authenticated
  using (bucket_id = 'longform' and (storage.foldername(name))[1] = auth.uid()::text);
