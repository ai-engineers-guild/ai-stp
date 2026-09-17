import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ApiError } from "@/lib/api/errors";
import { apiRequest } from "@/lib/api/http";
import { readCorporateOrganization } from "@/lib/api/corporate";
import type {
  CorporateDirectoryQuery,
  CorporateDirectoryView,
} from "@/lib/api/generated/types.gen";
import { sessionCookieValue } from "@/lib/auth/require-session";

export const dynamic = "force-dynamic";

const arrayFields = [
  "lead_ids",
  "team_ids",
  "technology_ids",
  "project_ids",
  "category_ids",
] as const;

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = await sessionCookieValue();
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const params = request.nextUrl.searchParams;
  const resource = params.get("resource");
  if (
    resource !== "projects" &&
    resource !== "teams" &&
    resource !== "members" &&
    resource !== "technologies"
  ) {
    return NextResponse.json({ error: "Invalid resource" }, { status: 400 });
  }

  const organization = await readCorporateOrganization(token);
  if (!organization) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const parseNumber = (value: string | null, fallback: number) => {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : fallback;
  };
  const textQuery = params.get("query");
  const query: CorporateDirectoryQuery = {
    resource,
    ...(textQuery ? { query: textQuery } : {}),
    include_archived: params.get("include_archived") === "true",
    offset: parseNumber(params.get("offset"), 0),
    limit: Math.min(256, Math.max(1, parseNumber(params.get("limit"), 10))),
    ...(params.get("is_lead") === "true" || params.get("is_lead") === "false"
      ? { is_lead: params.get("is_lead") === "true" }
      : {}),
  };
  for (const field of arrayFields) {
    const values = params.getAll(field).filter(Boolean);
    if (values.length) query[field] = values;
  }

  try {
    const outboundQuery = Object.fromEntries(
      Object.entries(query).filter(([, value]) => value !== null),
    ) as Record<string, string | number | boolean | readonly string[]>;
    const page = await apiRequest<CorporateDirectoryView>(
      `/v1/corporate/organizations/${organization.organization_id}/directory`,
      { sessionToken: token, query: outboundQuery },
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
