"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { JobBar } from "@/components/JobBar";
import { RuntimeTrack, type TrackSegment } from "@/components/RuntimeTrack";
import { Button, LinkButton, Notice, PageHead, StatusPill, Textarea } from "@/components/ui";
import { useJob, usePoll } from "@/components/useJob";
import { supabaseBrowser } from "@/lib/supabase/client";
import { runtime } from "@/lib/format";
import type { Chapter, Script } from "@/lib/types";

function words(t: string) {
  return t.trim() ? t.trim().split(/\s+/).length : 0;
}

export function ScriptView({ initial }: { initial: Script }) {
  const [script, setScript] = useState(initial);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);
  const job = useJob(script.id);
  const active = script.status === "queued" || script.status === "processing";

  const load = useCallback(async () => {
    const { data } = await supabaseBrowser().from("scripts").select("*").eq("id", initial.id).single();
    if (data) setScript(data as Script);
  }, [initial.id]);
  usePoll(active, load, 8000);
  useEffect(() => {
    if (job && ["completed", "failed", "cancelled"].includes(job.status)) load();
  }, [job?.status, job, load]);

  const wpm = useMemo(() => (script.words && script.est_minutes ? script.words / Number(script.est_minutes) : 150), [script.words, script.est_minutes]);
  const outline = script.outline?.chapters || [];
  const written = new Map((script.content?.chapters || []).filter((c) => c.text).map((c) => [c.index, c]));
  const segs: TrackSegment[] = [];
  const hook = script.content?.hook || "";
  segs.push({ title: "Cold open", minutes: hook ? words(hook) / wpm : 2, state: hook ? "done" : active ? "active" : "pending" });
  const per = (script.target_minutes - 2) / Math.max(outline.length, 1);
  outline.forEach((c, i) => {
    const w = written.get(i);
    segs.push({ title: c.title, minutes: w ? words(w.text) / wpm : per, state: w ? "done" : active ? "active" : "pending" });
  });
  const fullText = [hook, ...(script.content?.chapters || []).map((c) => c.text)].filter(Boolean).join("\n\n");
  const meta = script.content?.metadata;

  async function saveChapter(ch: Chapter) {
    if (!script.content) return;
    setSaving(true);
    const chapters = (script.content.chapters || []).map((c) => (c.index === ch.index ? { ...c, text: draft, words: words(draft) } : c));
    const content = { ...script.content, chapters };
    const { error } = await supabaseBrowser().from("scripts").update({ content }).eq("id", script.id);
    setSaving(false);
    if (!error) {
      setScript({ ...script, content, words: words([hook, ...chapters.map((c) => c.text)].join(" ")) });
      setEditing(null);
    }
  }

  return (
    <>
      <PageHead
        title={script.title || script.topic}
        sub={<span className="flex flex-wrap items-center gap-3"><StatusPill status={script.status} /><span className="tabular">{script.words ? `${script.words.toLocaleString()} words · ${runtime(script.est_minutes || script.target_minutes)}` : `Target ${runtime(script.target_minutes)}`}</span></span>}
        action={script.status === "completed" ? (
          <div className="flex gap-2">
            <Button variant="quiet" onClick={async () => { await navigator.clipboard.writeText(fullText); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>{copied ? "Copied" : "Copy narration"}</Button>
            <LinkButton href={`/app/videos/new?script=${script.id}`}>Make the video</LinkButton>
          </div>
        ) : null}
      />
      <div className="space-y-8">
        <JobBar job={job} />
        {script.status === "failed" ? <Notice tone="error">{script.error || "Writing failed."} Your script time was refunded.</Notice> : null}
        {outline.length ? <RuntimeTrack totalMinutes={Math.max(script.target_minutes, segs.reduce((a, s) => a + s.minutes, 0))} segments={segs} /> : null}

        {meta?.titles?.length ? (
          <section className="rounded-lg border border-line p-5">
            <h2 className="text-2xl">Packaging</h2>
            <div className="mt-3 grid gap-6 md:grid-cols-2">
              <div><p className="text-sm text-mute">Title options</p><ul className="mt-1 space-y-1">{meta.titles.map((t) => <li key={t}>{t}</li>)}</ul></div>
              <div><p className="text-sm text-mute">Thumbnail text</p><ul className="mt-1 space-y-1 font-display text-xl">{(meta.thumbnail_text || []).map((t) => <li key={t}>{t}</li>)}</ul></div>
            </div>
          </section>
        ) : null}

        <article className="max-w-[72ch] space-y-10">
          {hook ? (
            <section>
              <h2 className="text-2xl text-lamp">Cold open</h2>
              <p className="mt-3 whitespace-pre-line leading-relaxed">{hook}</p>
            </section>
          ) : null}
          {outline.map((o, i) => {
            const ch = written.get(i);
            return (
              <section key={i} id={`ch-${i + 1}`}>
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="text-2xl">{i + 1}. {o.title}</h2>
                  {ch && script.status === "completed" && editing !== i ? (
                    <button className="text-sm text-dusk hover:text-lamp" onClick={() => { setEditing(i); setDraft(ch.text); }}>Edit</button>
                  ) : null}
                </div>
                {!ch ? (
                  <p className="mt-2 text-mute">{o.brief}</p>
                ) : editing === i ? (
                  <div className="mt-3 space-y-3">
                    <Textarea rows={18} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label={`Edit chapter ${i + 1}`} />
                    <div className="flex items-center gap-3">
                      <Button disabled={saving} onClick={() => saveChapter(ch)}>Save chapter</Button>
                      <Button variant="quiet" onClick={() => setEditing(null)}>Discard changes</Button>
                      <span className="text-sm text-mute tabular">{words(draft).toLocaleString()} words</span>
                    </div>
                  </div>
                ) : (
                  <p className="mt-3 whitespace-pre-line leading-relaxed">{ch.text}</p>
                )}
              </section>
            );
          })}
        </article>
      </div>
    </>
  );
}
