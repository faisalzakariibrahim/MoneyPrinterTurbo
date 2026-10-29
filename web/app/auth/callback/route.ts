import { NextResponse, type NextRequest } from "next/server";
import { supabaseServer } from "@/lib/supabase/server";

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const nextParam = url.searchParams.get("next") || "/app";
  // Only allow same-site relative redirects (no open redirect).
  const next = nextParam.startsWith("/app") && !nextParam.startsWith("//") ? nextParam : "/app";
  if (code) {
    await supabaseServer().auth.exchangeCodeForSession(code);
  }
  return NextResponse.redirect(new URL(next, url.origin));
}
