import Link from "next/link";
import { Empty, LinkButton, PageHead, StatusPill } from "@/components/ui";
import { ago, bytes, runtime } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import type { Render } from "@/lib/types";

export default async function VideosPage() {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("renders").select("id,title,status,duration_seconds,output_bytes,youtube_video_id,spec,created_at").order("created_at", { ascending: false });
  const rows = (data || []) as Render[];
  return (
    <>
      <PageHead title="Videos" action={<LinkButton href="/app/videos/new">Make a video</LinkButton>} />
      {!rows.length ? (
        <Empty title="No videos yet" body="Render a finished script with a voice, or upload your own voiceover and we'll edit the video around it." action={<LinkButton href="/app/videos/new">Make a video</LinkButton>} />
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-mute"><tr className="border-b border-line"><th className="py-2 font-normal">Title</th><th className="py-2 font-normal">Length</th><th className="hidden py-2 font-normal sm:table-cell">Size</th><th className="py-2 font-normal">Status</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-line/60">
                <td className="py-3 pr-4">
                  <Link href={`/app/videos/${r.id}`} className="hover:text-lamp">{r.title}</Link>
                  <div className="text-xs text-mute">{String((r.spec as { resolution?: string }).resolution || "1080p")} · {ago(r.created_at)}{r.youtube_video_id ? " · on YouTube" : ""}</div>
                </td>
                <td className="py-3 font-display text-lg tabular">{r.duration_seconds ? runtime(r.duration_seconds / 60) : "—"}</td>
                <td className="hidden py-3 tabular text-mute sm:table-cell">{bytes(r.output_bytes)}</td>
                <td className="py-3"><StatusPill status={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
