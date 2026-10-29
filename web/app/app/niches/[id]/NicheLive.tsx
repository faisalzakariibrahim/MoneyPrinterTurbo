"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { JobBar } from "@/components/JobBar";
import { Notice } from "@/components/ui";
import { useJob } from "@/components/useJob";

export function NicheLive({ id, status }: { id: string; status: string }) {
  const job = useJob(status === "training" || status === "failed" ? id : null);
  const router = useRouter();
  useEffect(() => {
    if (job && ["completed", "failed"].includes(job.status) && status === "training") router.refresh();
  }, [job, status, router]);
  if (status === "failed") return <div className="mb-8"><Notice tone="error">{job?.error || "Training failed."} Delete this niche or train it again with a pasted transcript.</Notice></div>;
  return <div className="mb-8"><JobBar job={job} /></div>;
}
