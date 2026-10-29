import { NextResponse, type NextRequest } from "next/server";
import { supabaseServer } from "@/lib/supabase/server";

export async function POST(request: NextRequest) {
  await supabaseServer().auth.signOut();
  return NextResponse.redirect(new URL("/", request.url), { status: 303 });
}
