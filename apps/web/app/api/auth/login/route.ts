import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const { token } = await request.json();
  const validToken = process.env.ACCESS_TOKEN;

  if (!token || token !== validToken) {
    return NextResponse.json({ error: "Invalid token" }, { status: 401 });
  }

  const cookieStore = await cookies();
  cookieStore.set("sandbox_session", token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 86400,
  });

  return NextResponse.json({ ok: true });
}
