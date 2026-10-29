import Link from "next/link";
import { PageHead, LinkButton, StatusPill, Empty } from "@/components/ui";
import { UsageMeters } from "@/components/UsageMeters";
import { ago, runtime } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import type { Render, Script, Usage } from "@/lib/types";

export default async function Overview() {
  const { supabase } = await requireUser();
  const [{ data: usage }, { data: scripts }, { data: renders }] = await Promise.all([
    supabase.rpc("usage_summary").single<Usage>(),
    supabase.from("scripts").select("id,title,topic,status,target_minutes,est_minutes,created_at").order("created_at", { ascending: false }).limit(6),
    supabase.from("renders").select("id,title,status,duration_seconds,created_at").order("created_at", { ascending: false }).limit(6),
  ]);
  const s = (scripts || []) as Script[];
  const r = (renders || []) as Render[];
  return (
    <>
      <PageHead
        title="Overview"
        sub={usage ? `You're on the ${usage.plan_id[0].toUpperCase() + usage.plan_id.slice(1)} plan.` : undefined}
        action={<LinkButton href="/app/scripts/new">Write a script</LinkButton>}
      />
      <UsageMeters usage={usage} />
      {s.length === 0 && r.length === 0 ? (
        <div className="mt-12">
          <Empty
            title="Your first long-form video starts with a niche"
            body="Pick one of the ready-made niches or train your own from a single YouTube video, then write a script in that style."
            action={<LinkButton href="/app/niches">Choose a niche</LinkButton>}
          />
        </div>
      ) : (
        <div className="mt-12 grid gap-12 lg:grid-cols-2">
          <section>
            <h2 className="mb-3 text-2xl">Recent scripts</h2>
            <ul className="divide-y divide-line border-y border-line">
              {s.map((x) => (
                <li key={x.id}>
                  <Link href={`/app/scripts/${x.id}`} className="flex items-center justify-between gap-4 py-3 hover:text-lamp">
                    <span className="min-w-0">
                      <span className="block truncate">{x.title || x.topic}</span>
                      <span className="text-xs text-mute">{runtime(x.est_minutes || x.target_minutes)} · {ago(x.created_at)}</span>
                    </span>
                    <StatusPill status={x.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="mb-3 text-2xl">Recent videos</h2>
            <ul className="divide-y divide-line border-y border-line">
              {r.map((x) => (
                <li key={x.id}>
                  <Link href={`/app/videos/${x.id}`} className="flex items-center justify-between gap-4 py-3 hover:text-lamp">
                    <span className="min-w-0">
                      <span className="block truncate">{x.title}</span>
                      <span className="text-xs text-mute">{x.duration_seconds ? runtime(x.duration_seconds / 60) : "Not rendered yet"} · {ago(x.created_at)}</span>
                    </span>
                    <StatusPill status={x.status} />
                  </Link>
                </li>
              ))}
              {r.length === 0 ? <li className="py-3 text-sm text-mute">No videos yet. Finish a script, then choose Make the video.</li> : null}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
