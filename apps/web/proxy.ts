import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth/login", "/api/auth/logout"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/elixir-logo.png") ||
    pathname.startsWith("/favicon.png")
  ) {
    return NextResponse.next();
  }

  const session = request.cookies.get("sandbox_session")?.value;
  const validToken = process.env.ACCESS_TOKEN;

  if (!session || session !== validToken) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.png|elixir-logo.png).*)"],
};
