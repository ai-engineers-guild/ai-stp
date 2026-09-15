import { NextResponse } from "next/server";
import { readCorporateContext } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { readSession } from "@/lib/auth/session";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { canViewCorporateAdministration } from "@/lib/corporate-hub";
import { COMPILED_FEATURE_PROFILE } from "@/lib/features/compiled";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const headers = { "Cache-Control": "no-store, private" };
  if (COMPILED_FEATURE_PROFILE !== "corporate_hub" || !(await readSession())) {
    return NextResponse.json({ administration: false }, { headers });
  }
  try {
    const token = await sessionCookieValue();
    const context = token ? await readCorporateContext(token) : null;
    return NextResponse.json(
      { administration: canViewCorporateAdministration(context?.capabilities ?? []) },
      { headers },
    );
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return NextResponse.json({ administration: false }, { headers, status: 503 });
  }
}
