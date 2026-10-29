const supabase = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseWs = supabase.replace(/^https/, "wss");

// Strict security headers. The CSP only allows our own origin plus Supabase.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'" + (process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""),
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://i.ytimg.com https://yt3.ggpht.com " + supabase,
  "media-src 'self' blob: " + supabase,
  "font-src 'self' data:",
  "connect-src 'self' " + supabase + " " + supabaseWs,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self' https://checkout.stripe.com https://billing.stripe.com https://accounts.google.com",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        ],
      },
    ];
  },
};

export default nextConfig;
