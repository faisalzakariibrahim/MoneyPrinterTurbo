import { PageHead } from "@/components/ui";
import { NewScriptForm } from "./NewScriptForm";
import { requireUser } from "@/lib/supabase/server";
import type { Niche, Usage } from "@/lib/types";

export default async function NewScript({ searchParams }: { searchParams: { niche?: string; topic?: string } }) {
  const { supabase } = await requireUser();
  const [{ data: niches }, { data: usage }] = await Promise.all([
    supabase.from("niches").select("id,name,owner_id,style_profile,status").eq("status", "ready").order("name"),
    supabase.rpc("usage_summary").single<Usage>(),
  ]);
  const left = usage ? Math.max(0, usage.script_limit - Number(usage.script_used)) : 0;
  return (
    <>
      <PageHead title="Write a script" sub="Pick a style and a topic. Length is billed against your script time, and refunded if anything fails." />
      <NewScriptForm niches={(niches || []) as Niche[]} defaultNiche={searchParams.niche} defaultTopic={searchParams.topic} minutesLeft={left} />
    </>
  );
}
