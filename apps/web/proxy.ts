import { type NextRequest, NextResponse } from "next/server";

/**
 * Optimistic redirect for signed-out visitors: if there's no session cookie at
 * all, go straight to /login instead of rendering the app shell first.
 *
 * This is a UX shortcut, NOT the security boundary. The cookie is httpOnly and
 * opaque; whether it's valid is decided by the API on every request
 * (SessionProvider redirects on 401, and all data endpoints enforce access).
 */
const SESSION_COOKIE = "via_session";

export function proxy(request: NextRequest) {
  // Only redirect full page loads. Client-side navigations and prefetches are
  // fetches (Sec-Fetch-Dest: empty) and are left to SessionProvider; Next.js
  // strips its own RSC headers before the proxy runs, so the browser's
  // Sec-Fetch-Dest is the reliable signal. Clients without it (curl) count as
  // page loads.
  const isPageLoad = (request.headers.get("sec-fetch-dest") ?? "document") === "document";
  if (isPageLoad && !request.cookies.has(SESSION_COOKIE)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/projects/:path*", "/activity/:path*", "/settings/:path*"],
};
