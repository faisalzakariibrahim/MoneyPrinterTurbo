import { NextResponse, type NextRequest } from "next/server";
import Stripe from "stripe";
import { priceFor, siteUrl } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/admin";
import { requireUser } from "@/lib/supabase/server";

export async function POST(request: NextRequest) {
  const { user } = await requireUser();
  if (!user) return NextResponse.redirect(`${siteUrl()}/login`, { status: 303 });
  const plan = String((await request.formData()).get("plan") || "");
  const price = priceFor(plan);
  const key = process.env.STRIPE_SECRET_KEY;
  if (!price || !key) return NextResponse.redirect(`${siteUrl()}/app/settings?billing=unavailable`, { status: 303 });
  const stripe = new Stripe(key);
  const admin = supabaseAdmin();
  const { data: profile } = await admin.from("profiles").select("stripe_customer_id").eq("id", user.id).single();
  let customer = profile?.stripe_customer_id as string | null;
  if (!customer) {
    customer = (await stripe.customers.create({ email: user.email, metadata: { user_id: user.id } })).id;
    await admin.from("profiles").update({ stripe_customer_id: customer }).eq("id", user.id);
  }
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    customer,
    client_reference_id: user.id,
    line_items: [{ price, quantity: 1 }],
    subscription_data: { metadata: { user_id: user.id } },
    allow_promotion_codes: true,
    success_url: `${siteUrl()}/app/settings?billing=success`,
    cancel_url: `${siteUrl()}/app/settings`,
  });
  return NextResponse.redirect(session.url!, { status: 303 });
}
