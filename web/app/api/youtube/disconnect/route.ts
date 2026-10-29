import { NextResponse, type NextRequest } from "next/server";
import { decrypt } from "@/lib/crypto";
import { siteUrl } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/admin";
import { requireUser } from "@/lib/supabase/server";

/** Revoke Google access and delete the stored token. */
export async function POST(request: NextRequest) {
  const { user } = await requireUser();
  if (!user) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const form = await request.formData();
  const id = String(form.get("id") || "");
  const admin = supabaseAdmin();
  const { data } = await admin.from("youtube_channels").select("id,refresh_token_enc").eq("id", id).eq("user_id", user.id).maybeSingle();
  if (data) {
    try {
      await fetch(`https://oauth2.googleapis.com/revoke?token=${encodeURIComponent(decrypt(data.refresh_token_enc))}`, { method: "POST" });
    } catch {
      // Revocation is best effort; the token is deleted either way.
    }
    await admin.from("youtube_channels").delete().eq("id", data.id).eq("user_id", user.id);
  }
  return NextResponse.redirect(`${siteUrl()}/app/settings?yt=disconnected`, { status: 303 });
}
