import { NextResponse, type NextRequest } from "next/server";
import Stripe from "stripe";
import { planForPrice } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/admin";

export const dynamic = "force-dynamic";

/** Keeps profiles.plan_id in sync with the Stripe subscription. Signature-verified. */
export async function POST(request: NextRequest) {
  const key = process.env.STRIPE_SECRET_KEY;
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!key || !secret) return NextResponse.json({ error: "not configured" }, { status: 503 });
  const stripe = new Stripe(key);
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(await request.text(), request.headers.get("stripe-signature") || "", secret);
  } catch {
    return NextResponse.json({ error: "bad signature" }, { status: 400 });
  }
  const admin = supabaseAdmin();

  async function apply(sub: Stripe.Subscription) {
    const customer = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
    const active = ["active", "trialing", "past_due"].includes(sub.status);
    const plan = active ? planForPrice(sub.items.data[0]?.price.id) : null;
    const item = sub.items.data[0] as Stripe.SubscriptionItem & { current_period_start?: number };
    const periodStart = item?.current_period_start ?? (sub as unknown as { current_period_start?: number }).current_period_start;
    const update: Record<string, unknown> = { plan_id: plan || "free", stripe_subscription_id: active ? sub.id : null };
    if (periodStart) update.period_start = new Date(periodStart * 1000).toISOString();
    await admin.from("profiles").update(update).eq("stripe_customer_id", customer).neq("plan_id", "internal");
  }

  switch (event.type) {
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
      await apply(event.data.object as Stripe.Subscription);
      break;
    case "invoice.paid": {
      const inv = event.data.object as Stripe.Invoice & { subscription?: string | null };
      const subId = typeof inv.subscription === "string" ? inv.subscription : null;
      if (subId) await apply(await stripe.subscriptions.retrieve(subId));
      break;
    }
  }
  return NextResponse.json({ received: true });
}
