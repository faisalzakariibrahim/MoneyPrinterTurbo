import { hours } from "@/lib/format";
import type { Usage } from "@/lib/types";

function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const unlimited = limit >= 100000;
  const pct = unlimited ? 0 : Math.min(100, (used / Math.max(limit, 1)) * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-mute">{label}</span>
        <span className="font-display text-xl tabular">
          {hours(used)} <span className="text-mute">/ {unlimited ? "unlimited" : hours(limit)}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line" role="meter" aria-valuenow={used} aria-valuemax={limit} aria-label={label}>
        <div className={`h-full ${pct > 90 ? "bg-ember" : "bg-lamp"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function UsageMeters({ usage }: { usage: Usage | null }) {
  if (!usage) return null;
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Meter label="Script time this month" used={Number(usage.script_used)} limit={usage.script_limit} />
      <Meter label="Video time this month" used={Number(usage.video_used)} limit={usage.video_limit} />
    </div>
  );
}
