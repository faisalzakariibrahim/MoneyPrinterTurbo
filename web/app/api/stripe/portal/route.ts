import { NextResponse } from "next/server";
import Stripe from "stripe";
import { siteUrl } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/admin";
import { requireUser } from "@/lib/supabase/server";

export async function POST() {
  const { user } = await requireUser();
  if (!user || !process.env.STRIPE_SECRET_KEY) return NextResponse.redirect(`${siteUrl()}/app/settings`, { status: 303 });
  const { data } = await supabaseAdmin().from("profiles").select("stripe_customer_id").eq("id", user.id).single();
  if (!data?.stripe_customer_id) return NextResponse.redirect(`${siteUrl()}/app/settings`, { status: 303 });
  const session = await new Stripe(process.env.STRIPE_SECRET_KEY).billingPortal.sessions.create({
    customer: data.stripe_customer_id,
    return_url: `${siteUrl()}/app/settings`,
  });
  return NextResponse.redirect(session.url, { status: 303 });
}
