export type JobStatus = "queued" | "processing" | "completed" | "failed" | "cancelled";

export type Job = {
  id: string;
  type: "train_niche" | "script" | "render" | "publish";
  ref_id: string;
  status: JobStatus;
  progress: number;
  stage: string | null;
  error: string | null;
  created_at: string;
};

export type StyleProfile = {
  name?: string;
  summary?: string;
  tone?: string[];
  pov?: string;
  words_per_minute?: number;
  hook?: { pattern?: string; techniques?: string[] };
  structure?: { chapter_pattern?: string; minutes_per_chapter?: number; intro?: string; outro?: string };
  retention_devices?: string[];
  do?: string[];
  dont?: string[];
  topic_ideas?: string[];
  title_patterns?: string[];
  reference?: { video_id?: string | null; title?: string; minutes?: number };
};

export type Niche = {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  status: "training" | "ready" | "failed";
  style_profile: StyleProfile;
  footage_pack_id: string | null;
  source_url: string | null;
  created_at: string;
};

export type Chapter = { index: number; title: string; brief: string; text: string; summary: string; words: number; target_words: number };

export type Script = {
  id: string;
  niche_id: string | null;
  topic: string;
  target_minutes: number;
  status: JobStatus;
  title: string | null;
  outline: { chapters?: { title: string; brief: string }[] } | null;
  content: { hook?: string; chapters?: Chapter[]; metadata?: { titles?: string[]; description?: string; tags?: string[]; thumbnail_text?: string[] } } | null;
  words: number | null;
  est_minutes: number | null;
  error: string | null;
  created_at: string;
};

export type Render = {
  id: string;
  script_id: string | null;
  title: string;
  voice_source: "upload" | "elevenlabs" | "edge";
  status: JobStatus;
  output_path: string | null;
  output_bytes: number | null;
  srt_path: string | null;
  duration_seconds: number | null;
  youtube_video_id: string | null;
  spec: Record<string, unknown>;
  error: string | null;
  created_at: string;
};

export type Usage = {
  plan_id: string;
  script_used: number;
  script_limit: number;
  video_used: number;
  video_limit: number;
  period_start: string;
};

export type Plan = {
  id: string;
  name: string;
  script_minutes: number;
  video_minutes: number;
  trained_niches: number;
  max_resolution: string;
  concurrent_renders: number;
  features: Record<string, boolean>;
  price_monthly_cents: number;
  sort: number;
};
