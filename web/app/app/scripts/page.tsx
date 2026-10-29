import Link from "next/link";
import { Empty, LinkButton, PageHead, StatusPill } from "@/components/ui";
import { ago, runtime } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import type { Script } from "@/lib/types";

export default async function ScriptsPage() {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("scripts").select("id,title,topic,status,target_minutes,est_minutes,words,created_at").order("created_at", { ascending: false });
  const scripts = (data || []) as Script[];
  return (
    <>
      <PageHead title="Scripts" action={<LinkButton href="/app/scripts/new">Write a script</LinkButton>} />
      {scripts.length === 0 ? (
        <Empty title="No scripts yet" body="Choose a niche, give it a topic and a length, and the full narration is written chapter by chapter." action={<LinkButton href="/app/scripts/new">Write a script</LinkButton>} />
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-mute"><tr className="border-b border-line"><th className="py-2 font-normal">Title</th><th className="py-2 font-normal">Length</th><th className="hidden py-2 font-normal sm:table-cell">Words</th><th className="py-2 font-normal">Status</th></tr></thead>
          <tbody>
            {scripts.map((s) => (
              <tr key={s.id} className="border-b border-line/60">
                <td className="py-3 pr-4"><Link href={`/app/scripts/${s.id}`} className="hover:text-lamp">{s.title || s.topic}</Link><div className="text-xs text-mute">{ago(s.created_at)}</div></td>
                <td className="py-3 font-display text-lg tabular">{runtime(s.est_minutes || s.target_minutes)}</td>
                <td className="hidden py-3 tabular text-mute sm:table-cell">{s.words ? s.words.toLocaleString() : "—"}</td>
                <td className="py-3"><StatusPill status={s.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
