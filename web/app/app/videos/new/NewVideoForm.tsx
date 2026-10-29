"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Button, Field, Input, Notice, Select } from "@/components/ui";
import { supabaseBrowser } from "@/lib/supabase/client";
import { mediaDuration, uploadFile } from "@/lib/upload";
import { hours, rpcError, runtime } from "@/lib/format";
import type { Plan, Script } from "@/lib/types";

type Voice = { id: string; name: string; preview: string | null; labels: Record<string, string> };

const EDGE_VOICES = [
  { id: "en-US-AndrewMultilingualNeural-Male", name: "Andrew (calm, US)" },
  { id: "en-US-GuyNeural-Male", name: "Guy (deep, US)" },
  { id: "en-GB-RyanNeural-Male", name: "Ryan (British)" },
  { id: "en-US-AriaNeural-Female", name: "Aria (warm, US)" },
  { id: "en-GB-SoniaNeural-Female", name: "Sonia (British)" },
];
const RES = ["720p", "1080p", "1440p", "2160p"] as const;
const RES_LABEL: Record<string, string> = { "720p": "720p", "1080p": "1080p HD", "1440p": "1440p", "2160p": "4K" };
const CAPTION_POS = [["bottom", "Bottom"], ["center", "Middle"], ["top", "Top"]] as const;
const PARTICLES = [["dust", "Dust"], ["embers", "Embers"], ["snow", "Snow"], ["magic", "Magic"]] as const;

export function NewVideoForm(props: {
  scripts: Script[];
  defaultScript?: string;
  packs: { id: string; name: string; owner_id: string | null }[];
  music: { id: string; name: string; mood: string | null }[];
  nichePacks: Record<string, string | null>;
  plan: Plan | null;
  videoMinutesLeft: number;
}) {
  const { scripts, packs, music, plan, videoMinutesLeft, nichePacks } = props;
  const router = useRouter();
  const features = plan?.features || {};
  const maxRes = RES.indexOf((plan?.max_resolution || "1080p") as (typeof RES)[number]);

  const [scriptId, setScriptId] = useState(props.defaultScript && scripts.some((s) => s.id === props.defaultScript) ? props.defaultScript : scripts[0]?.id || "");
  const script = scripts.find((s) => s.id === scriptId);
  const [title, setTitle] = useState(script?.title || "");
  const [source, setSource] = useState<"upload" | "elevenlabs" | "edge">(scripts.length ? (features.elevenlabs ? "elevenlabs" : "edge") : "upload");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState("");
  const [edgeVoice, setEdgeVoice] = useState(EDGE_VOICES[0].id);
  const [file, setFile] = useState<File | null>(null);
  const [fileMinutes, setFileMinutes] = useState<number | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [packId, setPackId] = useState("");
  const [musicIds, setMusicIds] = useState<string[]>(music[0] ? [music[0].id] : []);
  const [resolution, setResolution] = useState<(typeof RES)[number]>("1080p");
  const [captions, setCaptions] = useState({ enabled: true, mode: "karaoke", position: "bottom", highlight: "#F2B544", uppercase: false });
  const [border, setBorder] = useState(false);
  const [particles, setParticles] = useState<string | null>(null);
  const [vignette, setVignette] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (script) {
      setTitle(script.title || script.topic);
      const p = script.niche_id ? nichePacks[script.niche_id] : null;
      if (p) setPackId(p);
    }
  }, [scriptId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!packId && packs[0]) setPackId(packs[0].id);
  }, [packId, packs]);
  useEffect(() => {
    if (source !== "elevenlabs" || voices.length) return;
    fetch("/api/voices").then((r) => r.json()).then((b) => {
      setVoices(b.voices || []);
      if (b.voices?.[0]) setVoiceId(b.voices[0].id);
    });
  }, [source, voices.length]);

  const estMinutes = useMemo(() => {
    if (source === "upload") return fileMinutes;
    return script ? Number(script.est_minutes || script.target_minutes) : null;
  }, [source, fileMinutes, script]);

  async function pickFile(f: File | null) {
    setFile(f);
    setFileMinutes(null);
    if (!f) return;
    try {
      setFileMinutes((await mediaDuration(f)) / 60);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!estMinutes) return setError("Choose a narration first.");
    setBusy(true);
    try {
      let audioPath: string | null = null;
      if (source === "upload") {
        if (!file) throw new Error("Choose your voiceover file.");
        setUploadPct(0);
        audioPath = await uploadFile(file, "uploads", setUploadPct);
      }
      const spec = {
        resolution,
        vignette,
        captions: { ...captions, primary: "#FFFFFF" },
        border: { enabled: border },
        particles: { enabled: !!particles, style: particles || "dust" },
      };
      const { data, error } = await supabaseBrowser().rpc("create_render_job", {
        p_title: title,
        p_script: source === "upload" ? scriptId || null : scriptId,
        p_niche: script?.niche_id || null,
        p_footage_pack: packId,
        p_voice_source: source,
        p_voice_id: source === "elevenlabs" ? voiceId : source === "edge" ? edgeVoice : null,
        p_audio_path: audioPath,
        p_music: musicIds,
        p_spec: spec,
        p_est_minutes: Math.ceil(estMinutes),
      });
      if (error) throw new Error(rpcError(error));
      router.push(`/app/videos/${data}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
      setUploadPct(null);
    }
  }

  const radio = (active: boolean) => `rounded-md border px-3 py-2 text-left text-sm ${active ? "border-lamp text-paper" : "border-line text-mute hover:text-paper"}`;

  return (
    <form onSubmit={submit} className="grid gap-10 lg:grid-cols-[1fr_340px]">
      <div className="space-y-10">
        <section className="space-y-4">
          <h2 className="text-2xl">Narration</h2>
          <Field label="Script" htmlFor="script" hint={source === "upload" ? "Optional when you upload audio — it makes captions spell names exactly as written." : undefined}>
            <Select id="script" value={scriptId} onChange={(e) => setScriptId(e.target.value)}>
              {source === "upload" ? <option value="">No script (captions from the audio)</option> : null}
              {scripts.map((s) => <option key={s.id} value={s.id}>{s.title || s.topic} · {runtime(Number(s.est_minutes || s.target_minutes))}</option>)}
            </Select>
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Voice</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              <button type="button" className={radio(source === "upload")} onClick={() => setSource("upload")}>Upload my voiceover<span className="block text-xs text-mute">Your own TTS or recording</span></button>
              <button type="button" disabled={!scripts.length || !features.elevenlabs} className={radio(source === "elevenlabs")} onClick={() => setSource("elevenlabs")}>ElevenLabs voice<span className="block text-xs text-mute">{features.elevenlabs ? "Natural, made from the script" : "Creator plan and up"}</span></button>
              <button type="button" disabled={!scripts.length} className={radio(source === "edge")} onClick={() => setSource("edge")}>Standard voice<span className="block text-xs text-mute">Free, made from the script</span></button>
            </div>
          </fieldset>
          {source === "upload" ? (
            <Field label="Voiceover file" htmlFor="audio" hint={file ? `${file.name} · ${fileMinutes ? runtime(fileMinutes) : "reading length…"}` : "MP3, WAV or M4A up to 5 hours. Uploads resume if your connection drops."}>
              <Input id="audio" type="file" accept="audio/*,video/mp4" onChange={(e) => pickFile(e.target.files?.[0] || null)} />
            </Field>
          ) : source === "elevenlabs" ? (
            <Field label="ElevenLabs voice" htmlFor="voice">
              <Select id="voice" value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
                {voices.length ? voices.map((v) => <option key={v.id} value={v.id}>{v.name}{v.labels?.accent ? ` (${v.labels.accent})` : ""}</option>) : <option>Loading voices…</option>}
              </Select>
            </Field>
          ) : (
            <Field label="Standard voice" htmlFor="edge">
              <Select id="edge" value={edgeVoice} onChange={(e) => setEdgeVoice(e.target.value)}>
                {EDGE_VOICES.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </Select>
            </Field>
          )}
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl">Footage and music</h2>
          <Field label="Footage" htmlFor="pack" hint="Clips are cut to random lengths and never repeat back to back.">
            <Select id="pack" required value={packId} onChange={(e) => setPackId(e.target.value)}>
              {packs.map((p) => <option key={p.id} value={p.id}>{p.name}{p.owner_id ? " (yours)" : ""}</option>)}
            </Select>
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Background music</legend>
            <div className="flex flex-wrap gap-2">
              {music.map((m) => {
                const on = musicIds.includes(m.id);
                return (
                  <button type="button" key={m.id} aria-pressed={on} onClick={() => setMusicIds(on ? musicIds.filter((x) => x !== m.id) : [...musicIds, m.id])} className={`rounded-full border px-3 py-1 text-sm ${on ? "border-lamp text-paper" : "border-line text-mute"}`}>
                    {m.name}
                  </button>
                );
              })}
              {!music.length ? <p className="text-sm text-mute">No music yet. Add tracks under Footage & music.</p> : null}
            </div>
            <p className="mt-2 text-xs text-mute">Music ducks automatically under the voice. Pick several to rotate through long videos.</p>
          </fieldset>
        </section>

        <section className="space-y-5">
          <h2 className="text-2xl">Look</h2>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Resolution</legend>
            <div className="flex flex-wrap gap-2">
              {RES.map((r, i) => (
                <button type="button" key={r} disabled={i > maxRes} onClick={() => setResolution(r)} className={`${radio(resolution === r)} disabled:opacity-40`} title={i > maxRes ? "Needs a higher plan" : undefined}>{RES_LABEL[r]}</button>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-3">
            <legend className="mb-1 text-sm font-medium">Captions</legend>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-lamp" checked={captions.enabled} onChange={(e) => setCaptions({ ...captions, enabled: e.target.checked })} /> Burn in word-by-word captions</label>
            {captions.enabled ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Style" htmlFor="cmode">
                  <Select id="cmode" value={captions.mode} onChange={(e) => setCaptions({ ...captions, mode: e.target.value })}>
                    <option value="karaoke">Highlight each word</option>
                    <option value="phrase">Short phrases</option>
                    <option value="word">One word at a time</option>
                  </Select>
                </Field>
                <Field label="Position" htmlFor="cpos">
                  <Select id="cpos" value={captions.position} onChange={(e) => setCaptions({ ...captions, position: e.target.value })}>
                    {CAPTION_POS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                </Field>
                <Field label="Highlight colour" htmlFor="chl">
                  <Input id="chl" type="color" value={captions.highlight} onChange={(e) => setCaptions({ ...captions, highlight: e.target.value })} className="h-10 p-1" />
                </Field>
              </div>
            ) : null}
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-lamp" checked={vignette} onChange={(e) => setVignette(e.target.checked)} /> Soft vignette</label>
            <label className={`flex items-center gap-2 text-sm ${features.borders ? "" : "text-mute"}`}><input type="checkbox" className="accent-lamp" disabled={!features.borders} checked={border} onChange={(e) => setBorder(e.target.checked)} /> Frame border {features.borders ? "" : "(Creator and up)"}</label>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Particles {features.particles ? "" : <span className="text-mute">(Pro and up)</span>}</legend>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={radio(particles === null)} onClick={() => setParticles(null)}>None</button>
              {PARTICLES.map(([v, l]) => (
                <button type="button" key={v} disabled={!features.particles} className={`${radio(particles === v)} disabled:opacity-40`} onClick={() => setParticles(v)}>{l}</button>
              ))}
            </div>
          </fieldset>
        </section>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-10 lg:self-start">
        <Field label="Video title" htmlFor="vtitle">
          <Input id="vtitle" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <div className="rounded-lg border border-line bg-panel p-5">
          <p className="text-sm text-mute">Estimated length</p>
          <p className="font-display text-4xl tabular">{estMinutes ? runtime(estMinutes) : "—"}</p>
          <p className="mt-1 text-sm text-mute tabular">{hours(videoMinutesLeft)} of video time left. You&apos;re charged for the final length.</p>
        </div>
        {uploadPct !== null ? (
          <div role="status">
            <p className="text-sm text-mute">Uploading voiceover · {Math.round(uploadPct * 100)}%</p>
            <div className="mt-1 h-1.5 rounded-full bg-line"><div className="h-full rounded-full bg-lamp" style={{ width: `${uploadPct * 100}%` }} /></div>
          </div>
        ) : null}
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Button type="submit" disabled={busy || !packId || (!!estMinutes && estMinutes > videoMinutesLeft)} className="w-full py-3">{busy ? "Starting…" : "Render video"}</Button>
        {!packs.length ? <p className="text-sm text-ember">Add a footage pack first under Footage & music.</p> : null}
      </aside>
    </form>
  );
}
