"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import AppSidebar from "@/components/AppSidebar";
import { api, type SessionInfo } from "@/lib/api";
import { clearToken, getToken, isPublicPath } from "@/lib/auth";

type SessionState = {
  session: SessionInfo | null;
  /** Re-read /me — e.g. after an AI call changed the remaining quota. */
  refresh: () => Promise<void>;
  signOut: () => void;
};

const SessionContext = createContext<SessionState>({
  session: null,
  refresh: async () => {},
  signOut: () => {},
});

export const useSession = () => useContext(SessionContext);

/**
 * Keeps signed-out visitors on the sign-in pages and gives the rest of the app
 * the current user and workspace.
 *
 * This is a user-experience layer only. Every API route enforces sign-in and
 * workspace ownership on the server; nothing here is relied on for security.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = isPublicPath(pathname);

  const [session, setSession] = useState<SessionInfo | null>(null);
  const [checked, setChecked] = useState(false);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setSession(null);
      setChecked(true);
      return;
    }
    try {
      setSession(await api.me());
    } catch {
      setSession(null);
    } finally {
      setChecked(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const onChange = () => refresh();
    window.addEventListener("hh-auth-changed", onChange);
    // Signing out in another tab signs this one out too.
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("hh-auth-changed", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, [refresh]);

  useEffect(() => {
    if (!checked) return;
    if (!session && !isPublic) {
      const next = typeof window !== "undefined" ? window.location.pathname + window.location.search : "/";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
    if (session && isPublic) router.replace("/");
  }, [checked, session, isPublic, router]);

  const signOut = useCallback(() => {
    clearToken();
    setSession(null);
    router.replace("/login");
  }, [router]);

  const value = { session, refresh, signOut };

  if (isPublic) {
    return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
  }

  if (!checked || !session) {
    return (
      <div className="min-h-screen grid place-items-center text-[13px] text-ink-3">
        Loading…
      </div>
    );
  }

  return (
    <SessionContext.Provider value={value}>
      {/* On desktop the rail is a column beside the content. On mobile the
          same component renders a top bar, which must stack ABOVE the content
          rather than sit beside it — hence flex-col until md. */}
      <div className="flex flex-col md:flex-row min-h-screen">
        <AppSidebar />
        <div className="flex-1 min-w-0">{children}</div>
      </div>
    </SessionContext.Provider>
  );
}
