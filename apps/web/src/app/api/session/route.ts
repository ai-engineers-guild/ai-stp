import { NextResponse } from "next/server";

import { readSession } from "@/lib/auth/session";

/**
 * Whether this browser has a session, asked at request time.
 *
 * The shell used to answer this by calling `readSession()` while rendering, and
 * the routes it renders on — the landing, the catalogue, services — are built as
 * SSG. A statically rendered tree cannot honestly depend on a cookie: either the
 * header is baked as signed-out for everybody, or one visitor's signed-in shell
 * is cached and served to the next.
 *
 * So the personalised part moved here, where a request actually exists. The
 * public HTML stays static and identical for everyone, and the header asks this
 * once after hydration.
 *
 * It reports presence and nothing else. There is no account id, no device, no
 * expiry — the header only needs to know which controls to show, and a body
 * that carried more would be an identity endpoint reachable without CSRF.
 */
export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const session = await readSession();
  return NextResponse.json(
    { signedIn: session !== null },
    // Never store this. A shared cache holding it is the exact leak the move
    // away from the static shell was made to prevent.
    { headers: { "Cache-Control": "no-store, private" } },
  );
}
