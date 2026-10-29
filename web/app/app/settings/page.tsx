import { PageHead, Notice } from "@/components/ui";
import { UsageMeters } from "@/components/UsageMeters";
import { hours } from "@/lib/format";
import { requireUser } from "@/lib/supabase/server";
import type { Plan, Usage } from "@/lib/types";

const YT_MESSAGES: Record<string, [string, "info" | "error"]> = {
  connected: ["Channel connected. You can publish from any finished video.", "info"],
  disconnected: ["Channel disconnected and access revoked.", "info"],
  denied: ["Google sign-in was cancelled.", "error"],
  state_mismatch: ["That sign-in link expired. Try connecting again.", "error"],
  no_refresh_token: ["Google didn't grant offline access. Remove the app in your Google account permissions and connect again.", "error"],
  no_channel: ["That Google account has no YouTube channel.", "error"],
  not_configured: ["YouTube publishing isn't set up on this server yet.", "error"],
  token_failed: ["Google rejected the sign-in. Try again.", "error"],
  save_failed: ["Couldn't save the channel. Try again.", "error"],
};

export default async function SettingsPage({ searchParams }: { searchParams: { yt?: string; billing?: string } }) {
  const { supabase } = await requireUser();
  const [{ data: usage }, { data: plans }, { data: channels }] = await Promise.all([
    supabase.rpc("usage_summary").single<Usage>(),
    supabase.from("plans").select("*").order("sort"),
    supabase.from("youtube_channels").select("id,title,thumbnail_url,channel_id"),
  ]);
  const current = usage?.plan_id;
  const paid = ((plans || []) as Plan[]).filter((p) => ["creator", "pro", "scale"].includes(p.id));
  const yt = searchParams.yt ? YT_MESSAGES[searchParams.yt] : null;
  return (
    <>
      <PageHead title="Plan & channels" />
      <div className="space-y-14">
        <section className="space-y-6">
          <h2 className="text-2xl">This month</h2>
          {searchParams.billing === "success" ? <Notice>Payment received. Your new limits apply now.</Notice> : null}
          {searchParams.billing === "unavailable" ? <Notice tone="error">Billing isn&apos;t set up on this server yet.</Notice> : null}
          <UsageMeters usage={usage} />
          <div className="grid gap-4 md:grid-cols-3">
            {paid.map((p) => (
              <form key={p.id} action="/api/stripe/checkout" method="post" className={`rounded-lg border p-5 ${current === p.id ? "border-lamp" : "border-line"}`}>
                <input type="hidden" name="plan" value={p.id} />
                <h3 className="text-2xl">{p.name}</h3>
                <p className="font-display text-4xl tabular">${Math.round(p.price_monthly_cents / 100)}<span className="text-base text-mute"> / month</span></p>
                <p className="mt-2 text-sm text-mute tabular">{hours(p.script_minutes)} scripts · {hours(p.video_minutes)} video · up to {p.max_resolution === "2160p" ? "4K" : p.max_resolution}</p>
                {current === p.id ? (
                  <p className="mt-4 text-sm text-lamp">Your current plan</p>
                ) : (
                  <button className="mt-4 w-full rounded-md bg-lamp px-4 py-2 text-sm font-medium text-night hover:bg-lampdeep">Switch to {p.name}</button>
                )}
              </form>
            ))}
          </div>
          {current && current !== "free" && current !== "internal" ? (
            <form action="/api/stripe/portal" method="post"><button className="text-sm text-dusk hover:text-lamp">Manage billing and invoices</button></form>
          ) : null}
        </section>

        <section className="space-y-4">
          <h2 className="text-2xl">YouTube channels</h2>
          {yt ? <Notice tone={yt[1]}>{yt[0]}</Notice> : null}
          <ul className="divide-y divide-line border-y border-line">
            {(channels || []).map((c: { id: string; title: string; channel_id: string }) => (
              <li key={c.id} className="flex items-center justify-between py-3">
                <a href={`https://youtube.com/channel/${c.channel_id}`} target="_blank" rel="noopener noreferrer" className="hover:text-lamp">{c.title}</a>
                <form action="/api/youtube/disconnect" method="post">
                  <input type="hidden" name="id" value={c.id} />
                  <button className="text-sm text-mute hover:text-ember">Disconnect</button>
                </form>
              </li>
            ))}
            {!channels?.length ? <li className="py-3 text-sm text-mute">No channels connected.</li> : null}
          </ul>
          <a href="/api/youtube/connect" className="inline-flex rounded-md border border-line px-4 py-2 text-sm hover:border-dusk">Connect a YouTube channel</a>
          <p className="max-w-xl text-xs text-mute">We ask only for permission to upload videos and captions. The access token is encrypted, and you can disconnect at any time.</p>
        </section>
      </div>
    </>
  );
}
