"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";
import { Button, Field, Input, Notice, Select, Textarea } from "@/components/ui";
import { rpcError } from "@/lib/format";

export function TrainNiche({ packs }: { packs: { id: string; name: string }[] }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [usePaste, setUsePaste] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [pack, setPack] = useState(packs[0]?.id || "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error } = await supabaseBrowser().rpc("create_niche_job", {
      p_name: name,
      p_source_url: usePaste ? null : url,
      p_transcript: usePaste ? transcript : null,
      p_footage_pack: pack || null,
    });
    setBusy(false);
    if (error) return setError(rpcError(error));
    router.push(`/app/niches/${data}`);
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-line bg-panel p-5">
      <h2 className="text-2xl">Train a niche</h2>
      <p className="text-sm text-mute">One reference video is enough. Learning takes about a minute.</p>
      <Field label="Name" htmlFor="nname">
        <Input id="nname" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Dark fantasy what-ifs" />
      </Field>
      {usePaste ? (
        <Field label="Transcript" htmlFor="ntx" hint="Paste at least a few minutes of the narration.">
          <Textarea id="ntx" rows={7} required minLength={1000} value={transcript} onChange={(e) => setTranscript(e.target.value)} />
        </Field>
      ) : (
        <Field label="YouTube link" htmlFor="nurl" hint="A long video from a channel whose style you want.">
          <Input id="nurl" required type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
        </Field>
      )}
      <button type="button" className="text-sm text-dusk underline-offset-2 hover:underline" onClick={() => setUsePaste(!usePaste)}>
        {usePaste ? "Use a YouTube link instead" : "Paste a transcript instead"}
      </button>
      <Field label="Default footage" htmlFor="npack" hint="You can change footage per video.">
        <Select id="npack" value={pack} onChange={(e) => setPack(e.target.value)}>
          <option value="">Choose later</option>
          {packs.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
      </Field>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Button type="submit" disabled={busy} className="w-full">{busy ? "Starting…" : "Train niche"}</Button>
    </form>
  );
}
