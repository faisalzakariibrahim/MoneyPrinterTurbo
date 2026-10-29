import Link from "next/link";
import { PageHead, StatusPill } from "@/components/ui";
import { TrainNiche } from "./TrainNiche";
import { requireUser } from "@/lib/supabase/server";
import type { Niche } from "@/lib/types";

export default async function NichesPage({ searchParams }: { searchParams: { q?: string } }) {
  const { supabase, user } = await requireUser();
  const [{ data: niches }, { data: packs }] = await Promise.all([
    supabase.from("niches").select("*").order("created_at", { ascending: false }),
    supabase.from("footage_packs").select("id,name,owner_id").order("name"),
  ]);
  const q = (searchParams.q || "").toLowerCase();
  const all = ((niches || []) as Niche[]).filter((n) => !q || n.name.toLowerCase().includes(q) || (n.description || "").toLowerCase().includes(q));
  const mine = all.filter((n) => n.owner_id === user!.id);
  const library = all.filter((n) => n.owner_id === null);

  const row = (n: Niche) => (
    <li key={n.id}>
      <Link href={`/app/niches/${n.id}`} className="grid grid-cols-[1fr_auto] items-center gap-4 py-4 hover:text-lamp">
        <span className="min-w-0">
          <span className="block font-display text-xl">{n.name}</span>
          <span className="line-clamp-2 text-sm text-mute">{n.description || n.style_profile?.summary || "Learning this style…"}</span>
        </span>
        <span className="flex items-center gap-3 text-sm text-mute tabular">
          {n.style_profile?.words_per_minute ? `${Math.round(n.style_profile.words_per_minute)} wpm` : null}
          <StatusPill status={n.status} />
        </span>
      </Link>
    </li>
  );

  return (
    <>
      <PageHead title="Niches" sub="A niche is a storytelling style plus the footage that goes with it. Scripts are written in the niche's voice." />
      <div className="grid gap-12 lg:grid-cols-[1fr_380px]">
        <div>
          <form className="mb-6">
            <label htmlFor="q" className="sr-only">Search niches</label>
            <input id="q" name="q" defaultValue={searchParams.q} placeholder="Search niches" className="w-full rounded-md border border-line bg-night px-3 py-2 text-sm focus:border-lamp focus:outline-none" />
          </form>
          <h2 className="text-2xl">Your trained niches</h2>
          {mine.length ? <ul className="mt-2 divide-y divide-line border-y border-line">{mine.map(row)}</ul> : <p className="mt-2 text-sm text-mute">None yet. Train one from a YouTube video on the right.</p>}
          <h2 className="mt-10 text-2xl">Ready-made niches</h2>
          {library.length ? <ul className="mt-2 divide-y divide-line border-y border-line">{library.map(row)}</ul> : <p className="mt-2 text-sm text-mute">The shared library is empty. An admin can seed it from the worker README.</p>}
        </div>
        <aside className="lg:sticky lg:top-10 lg:self-start">
          <TrainNiche packs={(packs || []) as { id: string; name: string }[]} />
        </aside>
      </div>
    </>
  );
}
