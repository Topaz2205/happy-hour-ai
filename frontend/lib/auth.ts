/**
 * Client-side session storage.
 *
 * This is convenience, not security: the API decides what every request may
 * see from the token alone, and rejects anything outside the caller's
 * workspace. Losing or tampering with what is stored here can only log the
 * person out.
 *
 * The token is kept in localStorage because the app and the API live on
 * different sites (Vercel and Render), where third-party cookies are
 * unreliable. All rendered text in this app goes through React escaping, and
 * nothing uses dangerouslySetInnerHTML.
 */

const TOKEN_KEY = "hh.access_token";

export const PUBLIC_PATHS = ["/login", "/signup"];

export function isPublicPath(pathname: string | null | undefined): boolean {
  if (!pathname) return false;
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage blocked — the session simply won't survive a reload */
  }
  window.dispatchEvent(new Event("hh-auth-changed"));
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event("hh-auth-changed"));
}

/** Send the person to sign in, remembering where they were. */
export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  if (isPublicPath(window.location.pathname)) return;
  const next = window.location.pathname + window.location.search;
  window.location.replace(`/login?next=${encodeURIComponent(next)}`);
}

/** Only same-site relative paths are allowed as a post-login destination. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || isPublicPath(next)) return "/";
  return next;
}
