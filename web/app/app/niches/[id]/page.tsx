import { notFound } from "next/navigation";
import { LinkButton, PageHead, StatusPill } from "@/components/ui";
import { NicheLive } from "./NicheLive";
import { requireUser } from "@/lib/supabase/server";
import type { Niche } from "@/lib/types";

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <section>
      <h3 className="text-xl">{title}</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-mute">{items.map((x) => <li key={x}>{x}</li>)}</ul>
    </section>
  );
}

export default async function NichePage({ params }: { params: { id: string } }) {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("niches").select("*").eq("id", params.id).maybeSingle();
  if (!data) notFound();
  const n = data as Niche;
  const p = n.style_profile || {};
  return (
    <>
      <PageHead
        title={n.name}
        sub={<span className="flex items-center gap-3"><StatusPill status={n.status} />{n.owner_id ? "Trained by you" : "Ready-made niche"}</span>}
        action={n.status === "ready" ? <LinkButton href={`/app/scripts/new?niche=${n.id}`}>Write in this style</LinkButton> : null}
      />
      <NicheLive id={n.id} status={n.status} />
      {n.status === "ready" ? (
        <div className="grid gap-10 lg:grid-cols-[1fr_320px]">
          <div className="space-y-8">
            {p.summary ? <p className="max-w-2xl text-lg">{p.summary}</p> : null}
            <section>
              <h3 className="text-xl">How it hooks</h3>
              <p className="mt-1 max-w-2xl text-mute">{p.hook?.pattern}</p>
            </section>
            <section>
              <h3 className="text-xl">How it&apos;s structured</h3>
              <p className="mt-1 max-w-2xl text-mute">{p.structure?.chapter_pattern}</p>
            </section>
            <List title="What keeps people watching" items={p.retention_devices} />
            <div className="grid gap-8 sm:grid-cols-2">
              <List title="Do" items={p.do} />
              <List title="Avoid" items={p.dont} />
            </div>
          </div>
          <aside className="space-y-6 text-sm">
            <dl className="grid grid-cols-2 gap-y-3 border-y border-line py-4">
              <dt className="text-mute">Pace</dt><dd className="font-display text-lg tabular">{Math.round(p.words_per_minute || 150)} wpm</dd>
              <dt className="text-mute">Chapter length</dt><dd className="font-display text-lg tabular">{p.structure?.minutes_per_chapter ? `${Math.round(p.structure.minutes_per_chapter)} min` : "—"}</dd>
              <dt className="text-mute">Point of view</dt><dd>{p.pov || "—"}</dd>
              <dt className="text-mute">Tone</dt><dd>{(p.tone || []).join(", ") || "—"}</dd>
            </dl>
            {p.topic_ideas?.length ? (
              <section>
                <h3 className="text-xl">Video ideas</h3>
                <ul className="mt-2 space-y-2">
                  {p.topic_ideas.slice(0, 10).map((t) => (
                    <li key={t}>
                      <a className="text-dusk hover:text-lamp" href={`/app/scripts/new?niche=${n.id}&topic=${encodeURIComponent(t)}`}>{t}</a>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </aside>
        </div>
      ) : null}
    </>
  );
}
