# Longform Studio

Ultra-long-form (1–5 hour) narrated YouTube video studio, built on this MoneyPrinterTurbo fork.

```
web/ (Next.js 14, Vercel) ──RPC──▶ Supabase (Postgres + RLS + Storage + Realtime)
                                          ▲
                                          │ claim_job / heartbeat / finish_job
                                          │
                           app/longform/worker.py (Railway / Fly / GPU box)
                           niche training · scripts · TTS · FFmpeg render · YouTube
```

The worker has **no inbound port**. It pulls jobs from Postgres (`FOR UPDATE SKIP LOCKED`),
heartbeats progress, honours cancellation, and re-claims jobs whose worker died. Renders
resume from finished chunks.

## Pipeline

| Step | Module | Notes |
|---|---|---|
| Train niche | `niche.py` | YouTube captions (or pasted transcript) → Claude style profile (forced tool output). Transcript is fenced as untrusted data. Only YouTube URLs accepted; the server never fetches user URLs. |
| Script | `script.py` | Optional web research → outline → cold open → chapters written in parallel with a prompt-cached system prompt → short chapters topped up → YouTube packaging. |
| Voice | `voice.py`, `align.py` | ElevenLabs `/with-timestamps` (exact word timings) or free Edge voices; BYO audio aligned with faster-whisper and snapped to script spelling. |
| Render | `render.py` | Footage normalised once and cached → one soundtrack (ducked music, −14 LUFS) → random non-repeating cut plan → fixed-length chunks rendered in parallel (border, vignette, particles, word-by-word ASS captions) → stream-copy concat. |
| Publish | `youtube.py` | Resumable upload, synthetic-media disclosure for AI voices, SRT captions. |

## Setup

1. **Supabase**: run `supabase/migrations/20261028000000_longform_studio.sql`. Enable email and Google auth.
   Make yourself unlimited: `update profiles set plan_id = 'internal', is_admin = true where email = 'you@…';`
2. **Storage**: the migration creates the private `longform` bucket. Raise its file size limit
   (Storage → Settings) to fit multi-GB renders, and create S3 access keys for the worker.
3. **Worker**: copy `.env.worker.example` → `.env.worker`, then
   `docker build -f Dockerfile.longform -t ulf-worker . && docker run --env-file .env.worker -v ulf:/data ulf-worker`.
   Production layout: one light worker (`LF_WORKER_TYPES=train_niche,script,publish`, `LF_WORKER_CONCURRENCY=6`)
   and render workers on big CPU boxes or NVENC GPUs (`LF_VIDEO_CODEC=h264_nvenc`).
4. **Web**: `cd web && cp .env.example .env.local && npm i && npm run dev`. Deploy to Vercel.
   `LF_TOKEN_ENC_KEY` must be identical on web and worker (`openssl rand -base64 32`).
5. **YouTube**: Google Cloud OAuth client (web), redirect `https://<site>/api/youtube/callback`,
   YouTube Data API v3 enabled. Unverified projects can only upload private videos until Google's audit passes.
6. **Stripe** (optional): three monthly prices → `STRIPE_PRICE_*`; webhook at `/api/stripe/webhook`
   for `customer.subscription.*` and `invoice.paid`.

### Seeding the shared library

Ready-made niches, footage packs and music are rows with `owner_id = null` and files under
`library/` in the bucket (users can read, never write there). Upload licence-free footage, then:

```sql
insert into footage_packs (name, kind) values ('Medieval', 'video') returning id;
insert into footage_assets (pack_id, storage_path, kind) values ('<pack>', 'library/footage/medieval/01.mp4', 'video');
insert into music_tracks (name, mood, storage_path) values ('Night ambience', 'calm', 'library/music/night.mp3');
```

Public niches: train one with your own account, then `update niches set owner_id = null where id = '<id>';`

## Render throughput (measure on your hardware)

On the 2-core dev box: 150 s of 1080p with every effect rendered in ~200 s (≈0.75× real time).
Chunks parallelise across `LF_RENDER_WORKERS`, so throughput scales roughly with cores. For
3-hour 4K videos use NVENC GPUs or several large CPU workers per render.

## Security notes

- RLS on every table; users can't write status, usage, or other users' rows. Work is created only
  through `SECURITY DEFINER` RPCs that check plan limits and reserve minutes atomically.
- Worker RPCs are revoked from `anon`/`authenticated`. The service-role key lives only on the worker and web server.
- The worker re-validates every row's owner and every storage key (prefix allow-list, no traversal).
- ASS caption text is escaped (no override-tag injection); filtergraphs reference only files the worker created.
- YouTube refresh tokens are AES-256-GCM encrypted, and the column is not selectable by users. OAuth uses a state cookie.
- Stripe webhooks are signature-verified. CSP, HSTS and frame-deny headers are set on the web app.

## Tests

```bash
uv run pytest test/longform -q                 # 18 unit + 5 end-to-end (real Postgres + FFmpeg)
python supabase/tests/test_schema.py supabase/migrations/*_longform_studio.sql /tmp/pg   # 34 RLS/limit checks
cd web && npx tsc --noEmit && npm run build
```

The end-to-end tests need `pip install pgserver "psycopg[binary]"`.
