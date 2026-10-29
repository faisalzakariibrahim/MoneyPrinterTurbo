"use client";
import { useCallback, useEffect, useState } from "react";
import { JobBar } from "@/components/JobBar";
import { Button, Field, Input, LinkButton, Notice, PageHead, Select, StatusPill, Textarea } from "@/components/ui";
import { useJob, usePoll } from "@/components/useJob";
import { supabaseBrowser } from "@/lib/supabase/client";
import { signedUrl } from "@/lib/upload";
import { bytes, rpcError, timecode } from "@/lib/format";
import type { Job, Render } from "@/lib/types";

type Meta = { titles?: string[]; description?: string; tags?: string[] } | null;

export function VideoView({ initial, channels, meta }: { initial: Render; channels: { id: string; title: string }[]; meta: Meta }) {
  const [render, setRender] = useState(initial);
  const [src, setSrc] = useState<string | null>(null);
  const job = useJob(render.id);
  const active = render.status === "queued" || render.status === "processing";
  const load = useCallback(async () => {
    const { data } = await supabaseBrowser().from("renders").select("*").eq("id", initial.id).single();
    if (data) setRender(data as Render);
  }, [initial.id]);
  usePoll(active, load, 10000);
  useEffect(() => {
    if (job && ["completed", "failed", "cancelled"].includes(job.status) && job.type === "render") load();
  }, [job, load]);
  useEffect(() => {
    if (render.output_path) signedUrl(render.output_path, 6 * 3600).then(setSrc);
  }, [render.output_path]);

  async function download(path: string, name: string) {
    const url = await signedUrl(path, 600, name);
    if (url) window.location.href = url;
  }
  const safeName = render.title.replace(/[^\w\- ]+/g, "").trim().slice(0, 80) || "video";

  return (
    <>
      <PageHead
        title={render.title}
        sub={<span className="flex flex-wrap items-center gap-3"><StatusPill status={render.status} />{render.duration_seconds ? <span className="font-display text-lg tabular">{timecode(render.duration_seconds)}</span> : null}<span>{String((render.spec as { resolution?: string }).resolution || "1080p")}</span></span>}
      />
      <div className="space-y-8">
        {job?.type === "render" ? <JobBar job={job} /> : null}
        {render.status === "failed" ? <Notice tone="error">{render.error || "Rendering failed."} Your video time was refunded.</Notice> : null}
        {render.status === "completed" && render.output_path ? (
          <div className="grid gap-10 lg:grid-cols-[1fr_360px]">
            <div className="space-y-4">
              {src ? <video src={src} controls preload="metadata" className="aspect-video w-full rounded-lg bg-black" /> : <div className="aspect-video w-full rounded-lg bg-panel" />}
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => download(render.output_path!, `${safeName}.mp4`)}>Download MP4 ({bytes(render.output_bytes)})</Button>
                {render.srt_path ? <Button variant="quiet" onClick={() => download(render.srt_path!, `${safeName}.srt`)}>Download captions (SRT)</Button> : null}
              </div>
            </div>
            <Publish render={render} channels={channels} meta={meta} onPublished={load} />
          </div>
        ) : null}
      </div>
    </>
  );
}

function Publish({ render, channels, meta, onPublished }: { render: Render; channels: { id: string; title: string }[]; meta: Meta; onPublished: () => void }) {
  const [channel, setChannel] = useState(channels[0]?.id || "");
  const [title, setTitle] = useState(meta?.titles?.[0] || render.title);
  const [description, setDescription] = useState(meta?.description || "");
  const [tags, setTags] = useState((meta?.tags || []).join(", "));
  const [privacy, setPrivacy] = useState("private");
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const t = setInterval(async () => {
      const { data } = await supabaseBrowser().from("jobs").select("*").eq("id", jobId).single();
      if (data) {
        setJob(data as Job);
        if (["completed", "failed", "cancelled"].includes(data.status)) {
          clearInterval(t);
          onPublished();
        }
      }
    }, 4000);
    return () => clearInterval(t);
  }, [jobId, onPublished]);

  if (render.youtube_video_id) {
    return (
      <aside className="space-y-3 rounded-lg border border-line p-5">
        <h2 className="text-2xl">On YouTube</h2>
        <p className="text-sm text-mute">Uploaded. YouTube may take a while to finish processing high resolutions.</p>
        <a className="text-lamp underline-offset-2 hover:underline" href={`https://studio.youtube.com/video/${render.youtube_video_id}/edit`} target="_blank" rel="noopener noreferrer">Open in YouTube Studio</a>
      </aside>
    );
  }
  if (!channels.length) {
    return (
      <aside className="space-y-3 rounded-lg border border-line p-5">
        <h2 className="text-2xl">Publish to YouTube</h2>
        <p className="text-sm text-mute">Connect a channel to upload with the title, description, tags and captions filled in.</p>
        <LinkButton href="/app/settings" variant="quiet">Connect a channel</LinkButton>
      </aside>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { data, error } = await supabaseBrowser().rpc("create_publish_job", {
      p_render: render.id, p_channel: channel, p_title: title, p_description: description,
      p_tags: tags.split(",").map((t) => t.trim()).filter(Boolean), p_privacy: privacy, p_publish_at: null,
    });
    if (error) return setError(rpcError(error));
    setJobId(data as string);
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-line p-5">
      <h2 className="text-2xl">Publish to YouTube</h2>
      {job && ["queued", "processing"].includes(job.status) ? (
        <div role="status">
          <p className="text-sm">{job.stage || "Waiting to upload"} · {Math.round(job.progress * 100)}%</p>
          <div className="mt-1 h-1.5 rounded-full bg-line"><div className="h-full rounded-full bg-lamp" style={{ width: `${job.progress * 100}%` }} /></div>
        </div>
      ) : (
        <>
          <Field label="Channel" htmlFor="ch"><Select id="ch" value={channel} onChange={(e) => setChannel(e.target.value)}>{channels.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</Select></Field>
          <Field label="Title" htmlFor="yt">
            <Input id="yt" required maxLength={100} value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          {meta?.titles && meta.titles.length > 1 ? (
            <div className="flex flex-wrap gap-1.5">{meta.titles.map((t) => <button type="button" key={t} onClick={() => setTitle(t)} className="rounded-full border border-line px-2 py-0.5 text-xs text-mute hover:text-paper">{t}</button>)}</div>
          ) : null}
          <Field label="Description" htmlFor="yd"><Textarea id="yd" rows={6} maxLength={5000} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <Field label="Tags" htmlFor="ytags" hint="Separate with commas."><Input id="ytags" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
          <Field label="Visibility" htmlFor="yp">
            <Select id="yp" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
              <option value="private">Private</option><option value="unlisted">Unlisted</option><option value="public">Public</option>
            </Select>
          </Field>
          {render.voice_source !== "upload" ? <p className="text-xs text-mute">AI voice videos are marked as altered or synthetic content, as YouTube requires.</p> : null}
          {job?.status === "failed" ? <Notice tone="error">{job.error}</Notice> : null}
          {error ? <Notice tone="error">{error}</Notice> : null}
          <Button type="submit" className="w-full">Publish to YouTube</Button>
        </>
      )}
    </form>
  );
}
