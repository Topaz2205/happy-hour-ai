"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { safeNext, setToken } from "@/lib/auth";
import { Button, Note } from "@/components/ui";

const inputClass =
  "w-full h-10 px-3 rounded-lg border border-line-2 bg-surface text-[14px] " +
  "placeholder:text-ink-4 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft";

export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isSignup = mode === "signup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = isSignup
        ? await api.signup({ email, password, display_name: name || undefined })
        : await api.login({ email, password });
      setToken(res.access_token);
      // A full navigation so every page starts with the new session.
      window.location.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen grid place-items-center px-5 py-10 bg-canvas">
      <div className="w-full max-w-[380px]">
        <div className="flex items-center gap-2 mb-6">
          <span className="shrink-0 w-[30px] h-[30px] rounded-lg bg-accent grid place-items-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2.5 3h11l-4.6 5.2v3.9h2.4a.6.6 0 010 1.2H4.7a.6.6 0 010-1.2h2.4V8.2L2.5 3z" fill="#fff" />
            </svg>
          </span>
          <span className="text-[16px] font-semibold tracking-[-.01em]">Happy Hour Cocktails AI</span>
        </div>

        <h1 className="text-[22px] font-semibold tracking-[-.015em] text-ink">
          {isSignup ? "Create your workspace" : "Sign in"}
        </h1>
        <p className="mt-1 text-[13.5px] text-ink-3 leading-relaxed">
          {isSignup
            ? "Your events stay private to your own workspace. The cocktail and supplier catalogue is shared."
            : "Welcome back. Sign in to see your events."}
        </p>

        <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
          {isSignup && (
            <label className="flex flex-col gap-1.5 text-[13px] text-ink-2">
              Your name
              <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)}
                     autoComplete="name" maxLength={120} placeholder="Optional" />
            </label>
          )}
          <label className="flex flex-col gap-1.5 text-[13px] text-ink-2">
            Email
            <input className={inputClass} type="email" required value={email}
                   onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </label>
          <label className="flex flex-col gap-1.5 text-[13px] text-ink-2">
            Password
            <input className={inputClass} type="password" required minLength={isSignup ? 8 : 1}
                   maxLength={128} value={password} onChange={(e) => setPassword(e.target.value)}
                   autoComplete={isSignup ? "new-password" : "current-password"}
                   placeholder={isSignup ? "At least 8 characters" : undefined} />
          </label>

          {error && <Note tone="warn" icon={AlertCircle}>{error}</Note>}

          <Button type="submit" variant="primary" disabled={busy} className="h-10 mt-1">
            {busy ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="mt-5 text-[13px] text-ink-3">
          {isSignup ? "Already have an account? " : "New to Happy Hour Cocktails AI? "}
          <Link
            href={`${isSignup ? "/login" : "/signup"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`}
            className="text-accent hover:text-accent-hi font-medium"
          >
            {isSignup ? "Sign in" : "Create an account"}
          </Link>
        </p>
        <p className="mt-6 text-[11.5px] text-ink-4 leading-relaxed">
          Public beta: AI suggestions are limited per day. Quantities, costs and shopping lists are
          always calculated without AI.
        </p>
      </div>
    </main>
  );
}
