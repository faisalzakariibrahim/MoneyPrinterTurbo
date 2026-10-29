"use client";
import { supabaseBrowser } from "@/lib/supabase/client";
import type { Job } from "@/lib/types";
import { Button } from "./ui";

export function JobBar({ job }: { job: Job | null }) {
  if (!job || !["queued", "processing"].includes(job.status)) return null;
  const pct = Math.round((job.progress || 0) * 100);
  return (
    <div className="rounded-lg border border-lamp/40 bg-panel px-5 py-4" role="status" aria-live="polite">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-display text-xl text-lamp">{job.status === "queued" ? "In the queue" : job.stage || "Working"}</p>
          <p className="text-xs text-mute">You can leave this page. It keeps going and updates here.</p>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-display text-3xl tabular">{pct}%</span>
          <Button variant="quiet" onClick={() => supabaseBrowser().rpc("cancel_job", { p_job: job.id })}>
            Cancel
          </Button>
        </div>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line">
        <div className="h-full bg-lamp transition-[width] duration-700" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
