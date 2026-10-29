import { createServerClient, type CookieOptions } from "@supabase/ssr";

type CookieItem = { name: string; value: string; options: CookieOptions };
import { cookies } from "next/headers";

export function supabaseServer() {
  const store = cookies();
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => store.getAll(),
        setAll: (items: CookieItem[]) => {
          try {
            items.forEach(({ name, value, options }) => store.set(name, value, options));
          } catch {
            // Called from a Server Component: middleware refreshes the session instead.
          }
        },
      },
    },
  );
}

export async function requireUser() {
  const supabase = supabaseServer();
  const { data } = await supabase.auth.getUser();
  return { supabase, user: data.user };
}
