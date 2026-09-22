import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ApiError } from "@/lib/api/errors";
import { readCorporateOrganization } from "@/lib/api/corporate";
import { apiRequest } from "@/lib/api/http";
import { sessionCookieValue } from "@/lib/auth/require-session";
import type { UsageReport } from "@/components/usage/usage-report-types";

export const dynamic = "force-dynamic";

const GROUP_BY = new Set([
  "component",
  "setup",
  "employee",
  "device",
  "project",
  "harness",
  "outcome",
]);
const OUTCOMES = new Set(["succeeded", "failed", "cancelled"]);
const KINDS = new Set([
  "instruction",
  "skill",
  "mcp",
  "hook",
  "command",
  "agent",
  "plugin",
  "setting",
  "cli",
]);
const PASS_THROUGH = [
  "employee_id",
  "team_id",
  "device_id",
  "project_id",
  "technology_id",
  "harness",
  "setup_stable_id",
  "component_stable_id",
  "invoked_from",
  "invoked_to",
] as const;

export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = await sessionCookieValue();
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const organization = await readCorporateOrganization(token);
  if (!organization) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const params = request.nextUrl.searchParams;
  const groupBy = params.get("group_by");
  const outcome = params.get("outcome");
  const kind = params.get("component_kind");
  const parseNumber = (value: string | null, fallback: number) => {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : fallback;
  };

  const query: Record<string, string | number | boolean | readonly string[]> = {
    group_by: groupBy && GROUP_BY.has(groupBy) ? groupBy : "component",
    offset: parseNumber(params.get("offset"), 0),
    limit: Math.min(512, Math.max(1, parseNumber(params.get("limit"), 128))),
  };
  for (const field of PASS_THROUGH) {
    const value = params.get(field);
    if (value) query[field] = value;
  }
  if (outcome && OUTCOMES.has(outcome)) query.outcome = outcome;
  if (kind && KINDS.has(kind)) query.component_kind = kind;

  try {
    const report = await apiRequest<UsageReport>(
      `/v1/corporate/organizations/${organization.organization_id}/telemetry/usage-reports`,
      { sessionToken: token, query },
    );
    return NextResponse.json(report, {
      headers: { "Cache-Control": "no-store, private" },
    });
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
