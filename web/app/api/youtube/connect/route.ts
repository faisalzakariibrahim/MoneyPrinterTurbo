import { randomBytes } from "crypto";
import { NextResponse } from "next/server";
import { requireUser } from "@/lib/supabase/server";
import { siteUrl } from "@/lib/plans";

export async function GET() {
  const { user } = await requireUser();
  if (!user) return NextResponse.redirect(`${siteUrl()}/login`);
  const clientId = process.env.YOUTUBE_CLIENT_ID;
  if (!clientId) return NextResponse.redirect(`${siteUrl()}/app/settings?yt=not_configured`);
  const state = randomBytes(24).toString("base64url");
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: `${siteUrl()}/api/youtube/callback`,
    response_type: "code",
    access_type: "offline",
    prompt: "consent",
    include_granted_scopes: "true",
    scope: "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.force-ssl",
    state,
  });
  const res = NextResponse.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`);
  // CSRF protection: the callback must present the same state value.
  res.cookies.set("yt_oauth_state", state, { httpOnly: true, secure: true, sameSite: "lax", path: "/api/youtube", maxAge: 600 });
  return res;
}
