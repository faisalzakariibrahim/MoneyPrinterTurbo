export function runtime(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h ? `${h}h ${String(r).padStart(2, "0")}m` : `${r}m`;
}

export function timecode(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function hours(minutes: number): string {
  const h = minutes / 60;
  return h >= 10 ? `${Math.round(h)}h` : `${h.toFixed(1).replace(/\.0$/, "")}h`;
}

export function bytes(n: number | null | undefined): string {
  if (!n) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i >= 2 ? 1 : 0)} ${units[i]}`;
}

export function ago(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

/** Turn a Postgres "plan_limit: ..." exception into a sentence for the UI. */
export function rpcError(e: { message?: string } | null | undefined): string {
  const msg = e?.message || "Something went wrong.";
  return msg.replace(/^plan_limit:\s*/, "").replace(/^./, (c) => c.toUpperCase());
}

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "Longform Studio";
