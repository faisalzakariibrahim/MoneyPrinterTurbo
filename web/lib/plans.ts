import "server-only";

export const PAID_PLANS = ["creator", "pro", "scale"] as const;
export type PaidPlan = (typeof PAID_PLANS)[number];

export function priceFor(plan: string): string | undefined {
  return {
    creator: process.env.STRIPE_PRICE_CREATOR,
    pro: process.env.STRIPE_PRICE_PRO,
    scale: process.env.STRIPE_PRICE_SCALE,
  }[plan];
}

export function planForPrice(price: string | undefined | null): PaidPlan | null {
  if (!price) return null;
  return PAID_PLANS.find((p) => priceFor(p) === price) || null;
}

export function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(/\/$/, "");
}
