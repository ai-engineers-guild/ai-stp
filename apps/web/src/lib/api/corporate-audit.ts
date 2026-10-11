import { apiRequest } from "@/lib/api/http";
import { readCorporateContext } from "@/lib/api/corporate";
import { AUDIT_PAGE_SIZES } from "@/lib/page-window";

import type { CorporateAuditList, CorporateMemberList } from "./generated/types.gen";

export async function readCorporateAudit(
  sessionToken: string,
  params: Record<string, string | string[] | undefined> = {},
) {
  const context = await readCorporateContext(sessionToken);
  if (!context || !context.capabilities.includes("audit.list")) return null;
  const { page, size } = corporateAuditPage(params);
  const path = `/v1/corporate/organizations/${context.organization.organization_id}`;
  const [audit, members] = await Promise.all([
    apiRequest<CorporateAuditList>(`${path}/audit`, {
      sessionToken,
      query: {
        ...corporateAuditFilters(params),
        limit: size,
        offset: (page - 1) * size,
      },
    }),
    context.capabilities.includes("member.list")
      ? apiRequest<CorporateMemberList>(`${path}/members`, { sessionToken })
      : null,
  ]);
  return { context, audit, members, page, size };
}

export type CorporateAuditFilterValues = {
  actor_account_id?: string;
  action?: string;
  target_table?: string;
  target_id?: string;
  outcome?: string;
  q?: string;
  created_from?: string;
  created_to?: string;
};

const AUDIT_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const AUDIT_TEXT_PATTERN = /^[ -~]{1,128}$/;
// Control characters are deliberately excluded from free-text journal search.
// eslint-disable-next-line no-control-regex
const AUDIT_QUERY_PATTERN = /^[^\u0000-\u001f]{1,200}$/u;
const AUDIT_TARGET_TABLE_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
const AUDIT_OUTCOMES = new Set(["succeeded", "denied", "failed"]);

function scalarParam(
  params: Record<string, string | string[] | undefined>,
  key: string,
): string | undefined {
  const value = params[key];
  return typeof value === "string" ? value : undefined;
}

function validDateInput(value: string | undefined): value is string {
  if (!value || !AUDIT_DATE_PATTERN.test(value)) return false;
  const date = new Date(`${value}T00:00:00.000Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

function validAuditText(value: string | undefined): value is string {
  return value !== undefined && AUDIT_TEXT_PATTERN.test(value);
}

export function corporateAuditFilterValues(
  params: Record<string, string | string[] | undefined>,
): CorporateAuditFilterValues {
  const actor = scalarParam(params, "actor_account_id");
  const action = scalarParam(params, "action");
  const targetTable = scalarParam(params, "target_table");
  const targetId = scalarParam(params, "target_id");
  const outcome = scalarParam(params, "outcome");
  const query = scalarParam(params, "q");
  const createdFrom = scalarParam(params, "created_from");
  const createdTo = scalarParam(params, "created_to");
  return {
    ...(actor && /^account_[0-9A-HJKMNP-TV-Z]{26}$/.test(actor) ? { actor_account_id: actor } : {}),
    ...(validAuditText(action) ? { action } : {}),
    ...(targetTable && AUDIT_TARGET_TABLE_PATTERN.test(targetTable)
      ? { target_table: targetTable }
      : {}),
    ...(validAuditText(targetId) ? { target_id: targetId } : {}),
    ...(outcome && AUDIT_OUTCOMES.has(outcome) ? { outcome } : {}),
    ...(query && AUDIT_QUERY_PATTERN.test(query) ? { q: query } : {}),
    ...(validDateInput(createdFrom) ? { created_from: createdFrom } : {}),
    ...(validDateInput(createdTo) ? { created_to: createdTo } : {}),
  };
}

/** API query shape; also used by the export server action. */
export function corporateAuditFilters(params: Record<string, string | string[] | undefined>) {
  const filters = corporateAuditFilterValues(params);
  return {
    ...(filters.actor_account_id ? { actor_account_id: filters.actor_account_id } : {}),
    ...(filters.action ? { action: filters.action } : {}),
    ...(filters.target_table ? { target_table: filters.target_table } : {}),
    ...(filters.target_id ? { target_id: filters.target_id } : {}),
    ...(filters.outcome ? { outcome: filters.outcome } : {}),
    ...(filters.q ? { q: filters.q } : {}),
    ...(filters.created_from ? { created_from: `${filters.created_from}T00:00:00.000Z` } : {}),
    ...(filters.created_to ? { created_to: `${filters.created_to}T23:59:59.999Z` } : {}),
  };
}

/** Cursor parameters remain part of the list contract; the UI paginates by offset. */
export function corporateAuditCursor(cursor: Record<string, string | string[] | undefined>) {
  const id = cursor.before_id;
  const date = cursor.before_created_at;
  return typeof id === "string" &&
    /^[1-9]\d*$/.test(id) &&
    Number.isSafeInteger(Number(id)) &&
    typeof date === "string" &&
    date.length <= 64 &&
    Number.isFinite(Date.parse(date))
    ? { before_id: id, before_created_at: date }
    : {};
}

export function corporateAuditPage(params: Record<string, string | string[] | undefined>): {
  page: number;
  size: number;
} {
  const rawPage = Number(scalarParam(params, "page") ?? "1");
  const rawSize = Number(scalarParam(params, "size") ?? String(AUDIT_PAGE_SIZES[0]));
  return {
    page: Number.isSafeInteger(rawPage) && rawPage >= 1 ? rawPage : 1,
    size: (AUDIT_PAGE_SIZES as readonly number[]).includes(rawSize) ? rawSize : AUDIT_PAGE_SIZES[0],
  };
}
