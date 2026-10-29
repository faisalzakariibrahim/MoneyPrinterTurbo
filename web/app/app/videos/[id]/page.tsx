import { notFound } from "next/navigation";
import { VideoView } from "./VideoView";
import { requireUser } from "@/lib/supabase/server";
import type { Render, Script } from "@/lib/types";

export default async function VideoPage({ params }: { params: { id: string } }) {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("renders").select("*").eq("id", params.id).maybeSingle();
  if (!data) notFound();
  const render = data as Render;
  const [{ data: channels }, { data: script }] = await Promise.all([
    supabase.from("youtube_channels").select("id,title,thumbnail_url"),
    render.script_id ? supabase.from("scripts").select("content,title").eq("id", render.script_id).maybeSingle() : Promise.resolve({ data: null }),
  ]);
  return (
    <VideoView
      initial={render}
      channels={(channels || []) as { id: string; title: string }[]}
      meta={(script as Pick<Script, "content"> | null)?.content?.metadata || null}
    />
  );
}
