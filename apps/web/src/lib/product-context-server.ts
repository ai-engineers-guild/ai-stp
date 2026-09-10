import { cookies } from "next/headers";
import { cache } from "react";

import { ApiError } from "@/lib/api/errors";
import type { ActiveContext, OrganizationSummary } from "@/lib/api/generated/types.gen";
import { privateApiRequest } from "@/lib/api/http";
import { getEnv } from "@/lib/env";
import { LOCAL_SESSION_COOKIE } from "@/lib/context-cookies";
import {
  LOCAL_CONTEXT,
  ORGANIZATION_COOKIE,
  PRODUCT_MODE_COOKIE,
  type ProductContextSnapshot,
  type ProductContextStatus,
} from "@/lib/product-context";

export { contextStatus } from "@/lib/product-context";

export const loadProductContext = cache(async (): Promise<ProductContextSnapshot> => {
  const cookieStore = await cookies();
  const selected = cookieStore.get(ORGANIZATION_COOKIE)?.value;
  const local = cookieStore.get(PRODUCT_MODE_COOKIE)?.value === "local";
  const localAvailable =
    getEnv().AI_STP_USE_MOCKS || Boolean(cookieStore.get(LOCAL_SESSION_COOKIE)?.value);
  try {
    const options = local
      ? { headers: { "X-AI-STP-Product-Mode": "local" } }
      : selected
        ? { headers: { "X-AI-STP-Organization-Id": selected } }
        : {};
    const context = await privateApiRequest<ActiveContext>("/v1/context", options);
    if (Date.parse(context.capabilities.expires_at) <= Date.now()) {
      return { context, organizations: [], status: "stale", localAvailable };
    }
    if (selected && !local && context.organization_id !== selected) {
      return { context: LOCAL_CONTEXT, organizations: [], status: "forbidden", localAvailable };
    }
    if (
      context.mode === "local" &&
      !getEnv().AI_STP_USE_MOCKS &&
      !cookieStore.get(LOCAL_SESSION_COOKIE)
    ) {
      return { context, organizations: [], status: "unavailable", localAvailable };
    }
    if (context.mode === "local") {
      return { context, organizations: [], status: "ready", localAvailable };
    }
    let organizations: OrganizationSummary[];
    try {
      organizations = await privateApiRequest<{ items: OrganizationSummary[] }>(
        "/v1/organizations",
      ).then((value) => value.items);
    } catch (error) {
      const organizationStatus = statusFor(error);
      return {
        context,
        organizations: [],
        status: organizationStatus === "unauthenticated" ? organizationStatus : "partial",
        localAvailable,
      };
    }
    return { context, organizations, status: "ready", localAvailable };
  } catch (error) {
    return { context: LOCAL_CONTEXT, organizations: [], status: statusFor(error), localAvailable };
  }
});

function statusFor(error: unknown): ProductContextStatus {
  if (error instanceof ApiError && error.code === "AI_STP_UNAUTHORIZED") return "unauthenticated";
  if (error instanceof ApiError && error.code === "AI_STP_FORBIDDEN") return "forbidden";
  if (error instanceof ApiError && error.code === "AI_STP_PRECONDITION_FAILED") return "stale";
  if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") return "unavailable";
  return "failed";
}
