"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { supabaseBrowser } from "@/lib/supabase/client";
import { Button, Field, Input, Notice } from "@/components/ui";
import { APP_NAME } from "@/lib/format";

function LoginForm() {
  const params = useSearchParams();
  const next = params.get("next")?.startsWith("/app") ? params.get("next")! : "/app";
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const redirectTo = () => `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;

  async function magic(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabaseBrowser().auth.signInWithOtp({ email, options: { emailRedirectTo: redirectTo() } });
    setBusy(false);
    if (error) setError(error.message);
    else setSent(true);
  }

  async function google() {
    await supabaseBrowser().auth.signInWithOAuth({ provider: "google", options: { redirectTo: redirectTo() } });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <p className="font-display text-2xl font-semibold">{APP_NAME}</p>
      <h1 className="mt-8 text-4xl">Sign in</h1>
      {sent ? (
        <p className="mt-4 text-mute">Check {email} for a sign-in link. It expires in an hour.</p>
      ) : (
        <form onSubmit={magic} className="mt-6 space-y-4">
          <Field label="Email" htmlFor="email">
            <Input id="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          {error ? <Notice tone="error">{error}</Notice> : null}
          <Button type="submit" disabled={busy} className="w-full">Email me a sign-in link</Button>
          <Button type="button" variant="quiet" onClick={google} className="w-full">Continue with Google</Button>
        </form>
      )}
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
