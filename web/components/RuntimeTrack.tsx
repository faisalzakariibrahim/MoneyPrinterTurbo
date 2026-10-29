import { runtime } from "@/lib/format";

export type TrackSegment = { title: string; minutes: number; state: "done" | "active" | "pending" };

/**
 * The product's signature: the whole video laid out to scale, chapter by chapter,
 * with an hour ruler. Filled segments are written/rendered, the active one glows.
 */
export function RuntimeTrack({ segments, totalMinutes, label, compact = false }: { segments: TrackSegment[]; totalMinutes: number; label?: string; compact?: boolean }) {
  const total = Math.max(totalMinutes, segments.reduce((a, s) => a + s.minutes, 0), 1);
  const hourMarks = Math.floor(total / 60);
  return (
    <figure className="w-full" aria-label={label || `Runtime ${runtime(total)}`}>
      <div className={`relative flex w-full gap-[3px] ${compact ? "h-3" : "h-10"}`}>
        {segments.map((s, i) => (
          <div
            key={i}
            title={`${s.title} · ${runtime(s.minutes)}`}
            style={{ width: `${(s.minutes / total) * 100}%`, animationDelay: `${i * 35}ms` }}
            className={`track-seg relative rounded-[3px] ${
              s.state === "done" ? "bg-lamp" : s.state === "active" ? "bg-lamp/45 ring-1 ring-lamp" : "bg-line"
            }`}
          >
            {!compact && s.minutes / total > 0.07 ? (
              <span className={`absolute inset-x-2 top-1/2 hidden -translate-y-1/2 truncate text-[11px] font-medium lg:block ${s.state === "done" ? "text-night" : "text-paper/70"}`}>
                {s.title}
              </span>
            ) : null}
          </div>
        ))}
      </div>
      {!compact ? (
        <div className="relative mt-1.5 h-4 font-display text-xs text-mute tabular">
          <span className="absolute left-0">0:00</span>
          {Array.from({ length: hourMarks }, (_, i) => i + 1)
            .filter((h) => h * 60 < total - 8)
            .map((h) => (
              <span key={h} className="absolute -translate-x-1/2" style={{ left: `${((h * 60) / total) * 100}%` }}>
                {h}:00:00
              </span>
            ))}
          <span className="absolute right-0">{runtime(total)}</span>
        </div>
      ) : null}
    </figure>
  );
}
