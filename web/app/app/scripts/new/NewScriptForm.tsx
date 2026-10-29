"use client";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { RuntimeTrack } from "@/components/RuntimeTrack";
import { Button, Field, Input, Notice, Select, Textarea } from "@/components/ui";
import { supabaseBrowser } from "@/lib/supabase/client";
import { hours, rpcError, runtime } from "@/lib/format";
import type { Niche } from "@/lib/types";

const presets = [30, 60, 120, 180, 240];

export function NewScriptForm({ niches, defaultNiche, defaultTopic, minutesLeft }: { niches: Niche[]; defaultNiche?: string; defaultTopic?: string; minutesLeft: number }) {
  const router = useRouter();
  const [nicheId, setNicheId] = useState(defaultNiche && niches.some((n) => n.id === defaultNiche) ? defaultNiche : niches[0]?.id || "");
  const [topic, setTopic] = useState(defaultTopic || "");
  const [minutes, setMinutes] = useState(120);
  const [notes, setNotes] = useState("");
  const [research, setResearch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const niche = niches.find((n) => n.id === nicheId);
  const wpm = niche?.style_profile?.words_per_minute || 150;
  const perChapter = Math.min(15, Math.max(5, niche?.style_profile?.structure?.minutes_per_chapter || 9));
  const chapters = Math.max(3, Math.min(40, Math.round(minutes / perChapter)));
  const preview = useMemo(
    () => [{ title: "Cold open", minutes: 2, state: "pending" as const }].concat(
      Array.from({ length: chapters }, (_, i) => ({ title: `Chapter ${i + 1}`, minutes: (minutes - 2) / chapters, state: "pending" as const })),
    ),
    [chapters, minutes],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error } = await supabaseBrowser().rpc("create_script_job", {
      p_niche: nicheId, p_topic: topic, p_target_minutes: minutes, p_notes: notes || null, p_research: research,
    });
    setBusy(false);
    if (error) return setError(rpcError(error));
    router.push(`/app/scripts/${data}`);
  }

  if (!niches.length) return <Notice>No niches are ready yet. Train one or ask an admin to add ready-made niches first.</Notice>;

  return (
    <form onSubmit={submit} className="grid gap-10 lg:grid-cols-[1fr_340px]">
      <div className="space-y-6">
        <Field label="Style" htmlFor="niche">
          <Select id="niche" value={nicheId} onChange={(e) => setNicheId(e.target.value)}>
            {niches.map((n) => <option key={n.id} value={n.id}>{n.name}{n.owner_id ? "" : " (ready-made)"}</option>)}
          </Select>
        </Field>
        <Field label="Topic" htmlFor="topic" hint="Phrase it like a title. You'll get title options at the end.">
          <Input id="topic" required minLength={3} maxLength={300} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="What if the Night King had won" />
        </Field>
        {niche?.style_profile?.topic_ideas?.length ? (
          <div className="flex flex-wrap gap-2">
            {niche.style_profile.topic_ideas.slice(0, 6).map((t) => (
              <button type="button" key={t} onClick={() => setTopic(t)} className="rounded-full border border-line px-3 py-1 text-xs text-mute hover:border-dusk hover:text-paper">{t}</button>
            ))}
          </div>
        ) : null}
        <div>
          <div className="flex items-baseline justify-between">
            <label htmlFor="len" className="text-sm font-medium">Length</label>
            <span className="font-display text-3xl text-lamp tabular">{runtime(minutes)}</span>
          </div>
          <input id="len" type="range" min={15} max={300} step={5} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} className="mt-2 w-full accent-lamp" />
          <div className="mt-2 flex flex-wrap gap-2">
            {presets.map((p) => (
              <button type="button" key={p} onClick={() => setMinutes(p)} className={`rounded-md border px-3 py-1 text-sm tabular ${p === minutes ? "border-lamp text-lamp" : "border-line text-mute hover:text-paper"}`}>{runtime(p)}</button>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-line p-4">
          <RuntimeTrack totalMinutes={minutes} segments={preview} />
          <p className="mt-3 text-sm text-mute tabular">
            About {Math.round(minutes * wpm).toLocaleString()} words in {chapters} chapters at {Math.round(wpm)} words a minute.
          </p>
        </div>
        <Field label="Notes for the writer" htmlFor="notes" hint="Angles to cover, things to avoid, a twist for the ending. Optional.">
          <Textarea id="notes" rows={4} maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" checked={research} onChange={(e) => setResearch(e.target.checked)} className="mt-1 accent-lamp" />
          <span>Research the topic on the web first<span className="block text-mute">Best for history and real events. Adds a few minutes.</span></span>
        </label>
      </div>
      <aside className="space-y-4 lg:sticky lg:top-10 lg:self-start">
        <div className="rounded-lg border border-line bg-panel p-5">
          <p className="text-sm text-mute">This script uses</p>
          <p className="font-display text-4xl tabular">{hours(minutes)}</p>
          <p className="mt-1 text-sm text-mute tabular">{hours(minutesLeft)} of script time left this month</p>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Button type="submit" disabled={busy || minutes > minutesLeft} className="w-full py-3">{busy ? "Starting…" : "Write script"}</Button>
        {minutes > minutesLeft ? <p className="text-sm text-ember">Not enough script time left. Shorten it or upgrade your plan.</p> : null}
      </aside>
    </form>
  );
}
