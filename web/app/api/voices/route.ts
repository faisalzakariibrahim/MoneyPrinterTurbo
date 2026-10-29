import { NextResponse } from "next/server";
import { requireUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

let cache: { at: number; voices: unknown[] } | null = null;

/** ElevenLabs voice list, proxied so the API key never reaches the browser. */
export async function GET() {
  const { user } = await requireUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) return NextResponse.json({ voices: [] });
  if (!cache || Date.now() - cache.at > 10 * 60_000) {
    const r = await fetch("https://api.elevenlabs.io/v1/voices", { headers: { "xi-api-key": key }, cache: "no-store" });
    if (!r.ok) return NextResponse.json({ voices: [] });
    const body = (await r.json()) as { voices?: { voice_id: string; name: string; preview_url?: string; labels?: Record<string, string> }[] };
    cache = {
      at: Date.now(),
      voices: (body.voices || []).map((v) => ({ id: v.voice_id, name: v.name, preview: v.preview_url || null, labels: v.labels || {} })),
    };
  }
  return NextResponse.json({ voices: cache.voices });
}
