import { NextRequest, NextResponse } from "next/server";
import { AUTH_ENDPOINTS } from "@/utils/api-endpoints";
import { getServerApiUrl } from "@/lib/server-api-url";

const PUBLIC_PATHS = [
  "/_next",
  "/api/auth",
  "/api/health",
  "/fonts",
  "/favicon",
];

// request.nextUrl is basePath-aware: its `pathname` is the logical route with
// any configured basePath already stripped, and cloning it preserves that
// basePath so the redirect Location is correctly prefixed (e.g. /mem0/login
// instead of /login when basePath is "/mem0"). Plain `new URL(path, request.url)`
// would bypass this and always produce a root-relative Location.
function redirectTo(request: NextRequest, pathname: string, search?: Record<string, string>) {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  url.search = "";
  if (search) {
    for (const [key, value] of Object.entries(search)) {
      url.searchParams.set(key, value);
    }
  }
  return NextResponse.redirect(url);
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const hasRefreshToken = request.cookies.has("mem0_refresh_token");

  if (pathname === "/" || pathname === "/login" || pathname === "/setup") {
    try {
      const res = await fetch(
        `${getServerApiUrl()}${AUTH_ENDPOINTS.SETUP_STATUS}`,
      );
      if (res.ok) {
        const { needsSetup } = await res.json();

        if (needsSetup && pathname !== "/setup") {
          return redirectTo(request, "/setup");
        }
        if (!needsSetup && pathname === "/setup") {
          return redirectTo(request, "/login");
        }
      }
    } catch {
      // API unreachable — fall through to default behavior
    }
  }

  if (pathname === "/login" || pathname === "/setup") {
    return NextResponse.next();
  }

  if (pathname === "/") {
    return redirectTo(request, hasRefreshToken ? "/dashboard/requests" : "/login");
  }

  if (pathname === "/dashboard" || pathname === "/dashboard/") {
    return redirectTo(request, "/dashboard/requests");
  }

  if (!hasRefreshToken) {
    return redirectTo(request, "/login", { next: pathname });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|fonts|images|icons).*)"],
};
