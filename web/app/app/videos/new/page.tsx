import { PageHead } from "@/components/ui";
import { NewVideoForm } from "./NewVideoForm";
import { requireUser } from "@/lib/supabase/server";
import type { Plan, Script, Usage } from "@/lib/types";

export default async function NewVideo({ searchParams }: { searchParams: { script?: string } }) {
  const { supabase } = await requireUser();
  const [{ data: scripts }, { data: packs }, { data: music }, { data: usage }, { data: plans }, { data: niches }] = await Promise.all([
    supabase.from("scripts").select("id,title,topic,niche_id,est_minutes,target_minutes,words,status").eq("status", "completed").order("created_at", { ascending: false }),
    supabase.from("footage_packs").select("id,name,owner_id,kind").order("name"),
    supabase.from("music_tracks").select("id,name,mood,owner_id").order("name"),
    supabase.rpc("usage_summary").single<Usage>(),
    supabase.from("plans").select("*"),
    supabase.from("niches").select("id,footage_pack_id"),
  ]);
  const plan = ((plans || []) as Plan[]).find((p) => p.id === usage?.plan_id) || null;
  return (
    <>
      <PageHead title="Make a video" sub="Choose a narration, footage and look. Rendering runs in the background — come back any time." />
      <NewVideoForm
        scripts={(scripts || []) as Script[]}
        defaultScript={searchParams.script}
        packs={(packs || []) as { id: string; name: string; owner_id: string | null }[]}
        music={(music || []) as { id: string; name: string; mood: string | null }[]}
        nichePacks={Object.fromEntries((niches || []).map((n: { id: string; footage_pack_id: string | null }) => [n.id, n.footage_pack_id]))}
        plan={plan}
        videoMinutesLeft={usage ? Math.max(0, usage.video_limit - Number(usage.video_used)) : 0}
      />
    </>
  );
}
