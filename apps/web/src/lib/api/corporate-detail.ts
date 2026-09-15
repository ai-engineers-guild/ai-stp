import { ApiError } from "./errors";
import { apiRequest } from "./http";
import { searchComponents } from "./catalog";
import { asCursorToken, type CursorToken } from "@/lib/brands";
import {
  corporatePresentationPath,
  presentationFromProfile,
  type CorporateDetailResource,
} from "@/lib/corporate-detail";

export async function readCorporatePresentation(
  sessionToken: string,
  organizationId: string,
  resource: CorporateDetailResource,
  id: string,
  authorizationRevision: number,
) {
  try {
    return presentationFromProfile(
      await apiRequest<unknown>(corporatePresentationPath(organizationId, resource, id), {
        sessionToken,
      }),
      authorizationRevision,
    );
  } catch (error) {
    // A missing optional profile falls back to the incumbent entity description.
    // Availability failures must remain visible instead of looking like an empty profile.
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function readCorporateAuthoredComponents(accountId: string) {
  const items: { kind: "component"; id: string; name: string }[] = [];
  let cursor: CursorToken | undefined;
  const seen = new Set<string>();
  do {
    const page = await searchComponents({
      authors: [accountId],
      page_size: 100,
      include_experimental: true,
      ...(cursor ? { cursor } : {}),
    });
    items.push(
      ...[...page.items, ...page.experimental].map((item) => ({
        kind: "component" as const,
        id: item.stable_id,
        name: item.latest_name,
      })),
    );
    const next = page.page.next_cursor;
    if (!next) break;
    if (seen.has(next)) throw new Error("catalog pagination did not advance");
    seen.add(next);
    cursor = asCursorToken(next);
  } while (cursor);
  return [...new Map(items.map((item) => [item.id, item])).values()];
}
