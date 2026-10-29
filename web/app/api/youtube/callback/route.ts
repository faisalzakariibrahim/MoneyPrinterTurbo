import { timingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import { encrypt } from "@/lib/crypto";
import { siteUrl } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/admin";
import { requireUser } from "@/lib/supabase/server";

function back(status: string) {
  const res = NextResponse.redirect(`${siteUrl()}/app/settings?yt=${status}`);
  res.cookies.delete({ name: "yt_oauth_state", path: "/api/youtube" });
  return res;
}

export async function GET(request: NextRequest) {
  const { user } = await requireUser();
  if (!user) return NextResponse.redirect(`${siteUrl()}/login`);
  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  const expected = request.cookies.get("yt_oauth_state")?.value || "";
  if (!state || state.length !== expected.length || !timingSafeEqual(Buffer.from(state), Buffer.from(expected))) return back("state_mismatch");
  const code = url.searchParams.get("code");
  if (!code) return back("denied");

  const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: process.env.YOUTUBE_CLIENT_ID!,
      client_secret: process.env.YOUTUBE_CLIENT_SECRET!,
      redirect_uri: `${siteUrl()}/api/youtube/callback`,
      grant_type: "authorization_code",
    }),
  });
  if (!tokenRes.ok) return back("token_failed");
  const tokens = (await tokenRes.json()) as { access_token: string; refresh_token?: string };
  if (!tokens.refresh_token) return back("no_refresh_token");

  const chRes = await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  const ch = (await chRes.json()) as { items?: { id: string; snippet: { title: string; thumbnails?: { default?: { url: string } } } }[] };
  const item = ch.items?.[0];
  if (!item) return back("no_channel");

  const { error } = await supabaseAdmin().from("youtube_channels").upsert(
    {
      user_id: user.id,
      channel_id: item.id,
      title: item.snippet.title.slice(0, 120),
      thumbnail_url: item.snippet.thumbnails?.default?.url || null,
      refresh_token_enc: encrypt(tokens.refresh_token),
    },
    { onConflict: "user_id,channel_id" },
  );
  return back(error ? "save_failed" : "connected");
}
