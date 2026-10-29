"use client";
import { useEffect, useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";
import type { Job } from "@/lib/types";

/** Latest job for a script/render/niche, kept live through Supabase Realtime. */
export function useJob(refId: string | null | undefined) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!refId) return;
    const supabase = supabaseBrowser();
    let alive = true;
    supabase
      .from("jobs")
      .select("*")
      .eq("ref_id", refId)
      .order("created_at", { ascending: false })
      .limit(1)
      .then(({ data }) => alive && data?.[0] && setJob(data[0] as Job));
    const channel = supabase
      .channel(`job-${refId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "jobs", filter: `ref_id=eq.${refId}` }, (p) => {
        if (p.new && "id" in p.new) setJob(p.new as Job);
      })
      .subscribe();
    return () => {
      alive = false;
      supabase.removeChannel(channel);
    };
  }, [refId]);
  return job;
}

/** Re-run `load` every few seconds while `active` (safety net if Realtime is off). */
export function usePoll(active: boolean, load: () => void, ms = 6000) {
  useEffect(() => {
    if (!active) return;
    const t = setInterval(load, ms);
    return () => clearInterval(t);
  }, [active, load, ms]);
}
