"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Field, Input, Notice } from "@/components/ui";
import { supabaseBrowser } from "@/lib/supabase/client";
import { mediaDuration, uploadFile } from "@/lib/upload";

type Pack = { id: string; name: string; owner_id: string | null };
type Track = { id: string; name: string; mood: string | null; owner_id: string | null };

const MAX_FILE = 4 * 1024 ** 3;

export function LibraryManager({ userId, packs, counts, music }: { userId: string; packs: Pack[]; counts: Record<string, number>; music: Track[] }) {
  const router = useRouter();
  const [packName, setPackName] = useState("");
  const [target, setTarget] = useState<string | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const db = supabaseBrowser();

  async function createPack(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const { data, error } = await db.from("footage_packs").insert({ name: packName.trim(), owner_id: userId }).select("id").single();
    if (error) return setError(error.message);
    setPackName("");
    setTarget(data.id);
    router.refresh();
  }

  async function addFootage(packId: string, files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    const list = Array.from(files);
    for (const [i, f] of list.entries()) {
      const kind = f.type.startsWith("image/") ? "image" : f.type.startsWith("video/") ? "video" : null;
      if (!kind) { setError(`${f.name} isn't a video or image.`); continue; }
      if (f.size > MAX_FILE) { setError(`${f.name} is over 4 GB.`); continue; }
      try {
        const duration = kind === "video" ? await mediaDuration(f).catch(() => null) : null;
        const key = await uploadFile(f, "footage", (p) => setProgress(`Uploading ${i + 1} of ${list.length} · ${Math.round(p * 100)}%`));
        const { error } = await db.from("footage_assets").insert({ pack_id: packId, storage_path: key, kind, duration_seconds: duration, size_bytes: f.size });
        if (error) throw error;
      } catch (err) {
        setError(`${f.name}: ${(err as Error).message}`);
      }
    }
    setProgress(null);
    router.refresh();
  }

  async function addMusic(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    for (const [i, f] of Array.from(files).entries()) {
      if (!f.type.startsWith("audio/")) { setError(`${f.name} isn't an audio file.`); continue; }
      try {
        const key = await uploadFile(f, "music", (p) => setProgress(`Uploading track ${i + 1} · ${Math.round(p * 100)}%`));
        const duration = await mediaDuration(f).catch(() => null);
        const { error } = await db.from("music_tracks").insert({ name: f.name.replace(/\.[^.]+$/, "").slice(0, 80), storage_path: key, owner_id: userId, duration_seconds: duration });
        if (error) throw error;
      } catch (err) {
        setError(`${f.name}: ${(err as Error).message}`);
      }
    }
    setProgress(null);
    router.refresh();
  }

  async function deletePack(id: string) {
    if (!confirm("Delete this footage pack? Videos already rendered are not affected.")) return;
    await db.from("footage_packs").delete().eq("id", id);
    router.refresh();
  }

  const mine = packs.filter((p) => p.owner_id);
  const shared = packs.filter((p) => !p.owner_id);

  return (
    <div className="grid gap-12 lg:grid-cols-2">
      <section>
        <h2 className="text-2xl">Footage packs</h2>
        <p className="mt-1 text-sm text-mute">Use several clips per pack — at least 10 minutes of footage looks varied even in a 3-hour video. Licence-free or your own footage only.</p>
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {mine.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <span><span className="block">{p.name}</span><span className="text-xs text-mute tabular">{counts[p.id] || 0} files</span></span>
              <span className="flex items-center gap-3">
                <label className="cursor-pointer rounded-md border border-line px-3 py-1.5 text-sm hover:border-dusk">
                  Add files
                  <input type="file" multiple accept="video/*,image/*" className="sr-only" onChange={(e) => addFootage(p.id, e.target.files)} />
                </label>
                <button onClick={() => deletePack(p.id)} className="text-sm text-mute hover:text-ember">Delete</button>
              </span>
            </li>
          ))}
          {shared.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-3">
              <span><span className="block">{p.name}</span><span className="text-xs text-mute tabular">Ready-made · {counts[p.id] || 0} files</span></span>
            </li>
          ))}
        </ul>
        <form onSubmit={createPack} className="mt-6 flex items-end gap-3">
          <div className="flex-1"><Field label="New footage pack" htmlFor="pname"><Input id="pname" required maxLength={80} value={packName} onChange={(e) => setPackName(e.target.value)} placeholder="Medieval castles" /></Field></div>
          <Button type="submit">Create pack</Button>
        </form>
        {target ? <p className="mt-2 text-sm text-mute">Pack created. Use Add files to upload clips or images.</p> : null}
      </section>
      <section>
        <h2 className="text-2xl">Music</h2>
        <p className="mt-1 text-sm text-mute">Only upload music you have the rights to use on YouTube.</p>
        <ul className="mt-4 divide-y divide-line border-y border-line">
          {music.map((m) => (
            <li key={m.id} className="flex items-center justify-between py-3">
              <span>{m.name}</span>
              <span className="text-xs text-mute">{m.owner_id ? "Yours" : "Ready-made"}{m.mood ? ` · ${m.mood}` : ""}</span>
            </li>
          ))}
          {!music.length ? <li className="py-3 text-sm text-mute">No tracks yet.</li> : null}
        </ul>
        <label className="mt-6 inline-flex cursor-pointer rounded-md bg-lamp px-4 py-2 text-sm font-medium text-night hover:bg-lampdeep">
          Upload tracks
          <input type="file" multiple accept="audio/*" className="sr-only" onChange={(e) => addMusic(e.target.files)} />
        </label>
      </section>
      <div className="lg:col-span-2" aria-live="polite">
        {progress ? <Notice>{progress}</Notice> : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
      </div>
    </div>
  );
}
