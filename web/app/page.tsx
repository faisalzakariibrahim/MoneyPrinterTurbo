import Link from "next/link";
import { RuntimeTrack } from "@/components/RuntimeTrack";
import { APP_NAME } from "@/lib/format";
import { supabaseServer } from "@/lib/supabase/server";

const demo = [
  ["Cold open", 3], ["The first king", 14], ["A crown of ash", 17], ["The northern pact", 15],
  ["Fire over the bay", 18], ["The long winter", 16], ["What the maesters hid", 19], ["Rebellion", 17],
  ["The last dragon", 18], ["Aftermath", 14], ["What if it never fell", 21], ["Epilogue", 8],
] as const;

const steps = [
  { title: "Train a niche", body: "Paste one video from a channel you admire. We learn its hooks, pacing, chapter rhythm and tone — never its words." },
  { title: "Write the script", body: "Pick a topic and a length up to five hours. You get an outline, a cold open and every chapter, ready to read aloud." },
  { title: "Build the video", body: "Upload your voiceover or pick a voice. We cut footage to it, add music, word-by-word captions and render up to 4K." },
  { title: "Publish", body: "Download the file or send it straight to YouTube with title, description, tags and captions filled in." },
];

export default async function Landing() {
  const { data } = await supabaseServer().auth.getUser();
  const signedIn = !!data.user;
  return (
    <main className="mx-auto max-w-6xl px-6 pb-24">
      <nav className="flex items-center justify-between py-6">
        <span className="font-display text-2xl font-semibold">{APP_NAME}</span>
        <div className="flex items-center gap-6 text-sm">
          <a href="#pricing" className="text-mute hover:text-paper">Pricing</a>
          <Link href={signedIn ? "/app" : "/login"} className="rounded-md bg-lamp px-4 py-2 font-medium text-night hover:bg-lampdeep">
            {signedIn ? "Open studio" : "Sign in"}
          </Link>
        </div>
      </nav>

      <section className="pt-16 md:pt-24">
        <p className="font-display text-[clamp(4.5rem,15vw,11rem)] font-bold leading-[0.85] tracking-tight text-lamp tabular">3:00:00</p>
        <h1 className="mt-6 max-w-3xl text-[clamp(2.2rem,5vw,3.6rem)] leading-[1.02]">
          Three-hour videos people fall asleep to. Written, voiced and edited in an afternoon.
        </h1>
        <p className="mt-5 max-w-xl text-lg text-mute">
          {APP_NAME} plans, writes and renders ultra-long narrated videos in the style of the channel you&apos;re building — lore deep-dives, what-ifs, history, sleep stories.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href={signedIn ? "/app" : "/login"} className="rounded-md bg-lamp px-5 py-3 font-medium text-night hover:bg-lampdeep">
            Start a video
          </Link>
          <a href="#how" className="rounded-md border border-line px-5 py-3 hover:border-dusk">See how it works</a>
        </div>
        <div className="mt-16 rounded-xl border border-line bg-panel/60 p-5 md:p-7">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <p className="font-display text-xl">What if the Iron Throne never fell</p>
            <p className="text-sm text-mute">12 chapters, written in the style of a lore channel</p>
          </div>
          <RuntimeTrack totalMinutes={180} segments={demo.map(([title, minutes], i) => ({ title, minutes, state: i < 9 ? "done" : i === 9 ? "active" : "pending" }))} />
        </div>
      </section>

      <section id="how" className="mt-28 grid gap-x-12 gap-y-10 md:grid-cols-2">
        <h2 className="text-4xl md:col-span-2">From one reference video to a finished upload</h2>
        {steps.map((s, i) => (
          <div key={s.title} className="flex gap-5">
            <span className="font-display text-5xl font-bold leading-none text-line tabular">{i + 1}</span>
            <div>
              <h3 className="text-2xl">{s.title}</h3>
              <p className="mt-1 text-mute">{s.body}</p>
            </div>
          </div>
        ))}
      </section>

      <section className="mt-28 grid gap-10 border-t border-line pt-14 md:grid-cols-3">
        <div>
          <h3 className="text-2xl">Built for hours, not minutes</h3>
          <p className="mt-1 text-mute">Scripts are planned chapter by chapter so hour three is as tight as minute one. Renders run in parallel parts and resume if anything stops.</p>
        </div>
        <div>
          <h3 className="text-2xl">Your style, original words</h3>
          <p className="mt-1 text-mute">We copy how a channel tells stories, never what it says. Every script is new writing, which is what YouTube&apos;s originality rules reward.</p>
        </div>
        <div>
          <h3 className="text-2xl">Your files stay yours</h3>
          <p className="mt-1 text-mute">Uploads and renders sit in private storage only your account can open. YouTube access is encrypted and can be removed any time.</p>
        </div>
      </section>

      <section id="pricing" className="mt-28">
        <h2 className="text-4xl">Pricing</h2>
        <p className="mt-1 text-mute">Script hours and video hours reset each month. Unused time from a failed or cancelled job is refunded automatically.</p>
        <div className="mt-8 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="text-mute">
              <tr className="border-b border-line">
                <th className="py-3 font-normal" />
                <th className="py-3 font-display text-2xl text-paper">Creator</th>
                <th className="py-3 font-display text-2xl text-paper">Pro</th>
                <th className="py-3 font-display text-2xl text-paper">Scale</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {[
                ["Per month", "$119", "$239", "$399"],
                ["Script hours", "20", "140", "300"],
                ["Video hours", "20", "120", "260"],
                ["Trained niches", "3", "10", "25"],
                ["Max resolution", "1440p", "4K", "4K"],
                ["Videos rendering at once", "1", "2", "3"],
                ["Borders and particles", "Borders", "Both", "Both"],
              ].map((row) => (
                <tr key={row[0]} className="border-b border-line/60">
                  {row.map((c, i) => (
                    <td key={i} className={`py-3 ${i === 0 ? "text-mute" : ""}`}>{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="mt-28 border-t border-line pt-6 text-sm text-mute">
        © {new Date().getFullYear()} {APP_NAME}. Made by Flicktek.
      </footer>
    </main>
  );
}
