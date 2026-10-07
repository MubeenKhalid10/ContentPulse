import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "cp_session";
// Supabase mode: @supabase/ssr stores the session as sb-<ref>-auth-token (chunked as .0, .1, ...).
const SUPABASE_COOKIE = /^sb-[^-]+-auth-token(\.\d+)?$/;
const PUBLIC_PATHS = ["/login", "/register", "/invite", "/forgot-password", "/reset-password", "/auth"];

/**
 * Optimistic redirect only: checks that a session cookie exists. The backend
 * verifies the token on every API call and the app shell handles 401s.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession =
    request.cookies.has(SESSION_COOKIE) ||
    request.cookies.getAll().some((c) => SUPABASE_COOKIE.test(c.name));
  const isPublic =
    pathname === "/" || PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (!hasSession && !isPublic) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if (hasSession && (pathname === "/login" || pathname === "/register" || pathname === "/forgot-password")) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|svg|ico|webp)$).*)"],
};
