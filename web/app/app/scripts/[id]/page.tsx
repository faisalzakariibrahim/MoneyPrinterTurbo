import { notFound } from "next/navigation";
import { ScriptView } from "./ScriptView";
import { requireUser } from "@/lib/supabase/server";
import type { Script } from "@/lib/types";

export default async function ScriptPage({ params }: { params: { id: string } }) {
  const { supabase } = await requireUser();
  const { data } = await supabase.from("scripts").select("*").eq("id", params.id).maybeSingle();
  if (!data) notFound();
  return <ScriptView initial={data as Script} />;
}
