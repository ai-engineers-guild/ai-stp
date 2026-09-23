import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { readCorporateOrganization } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";

import type { InstallationHeartbeatList } from "@/components/installations/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = await sessionCookieValue();
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const organization = await readCorporateOrganization(token);
  if (!organization) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const health = request.nextUrl.searchParams.get("health_state");
  try {
    const page = await apiRequest<InstallationHeartbeatList>(
      `/v1/corporate/organizations/${organization.organization_id}/telemetry/heartbeats`,
      {
        sessionToken: token,
        ...(health ? { query: { health_state: health } } : {}),
      },
    );
    return NextResponse.json(page, { headers: { "Cache-Control": "no-store, private" } });
  } catch (error) {
    if (error instanceof ApiError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.status > 0 ? error.status : 503 },
      );
    }
    throw error;
  }
}
