"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { z } from "zod";

import { ApiError, type ApiErrorCode } from "@/lib/api/errors";
import {
  fieldErrorsFromDetails,
  fieldErrorsFromIssues,
  type FieldErrors,
} from "@/lib/api/field-errors";
import { privateApiRequest } from "@/lib/api/http";
import {
  corporatePresentationPath,
  entityProfileViewSchema,
  entityProfileWriteRequestSchema,
  type CorporateDetailResource,
} from "@/lib/corporate-detail";
import { assertCsrf, readCsrfToken, readSession, SESSION_COOKIE } from "@/lib/auth/session";

type CorporateDetailMutationResult =
  | { ok: true; data: unknown }
  | { ok: false; message: string; code?: ApiErrorCode; fieldErrors?: FieldErrors };

/** Profile writes own their target and payload validation at the server boundary. */
export async function updateCorporatePresentationAction(input: {
  csrfToken: string;
  organizationId: string;
  resource: CorporateDetailResource;
  resourceId: string;
  data: unknown;
}): Promise<CorporateDetailMutationResult> {
  const resource = z
    .enum(["teams", "projects", "members", "technologies"])
    .safeParse(input.resource);
  if (!resource.success) return { ok: false, message: "invalid corporate target", fieldErrors: {} };
  let path: string;
  try {
    path = corporatePresentationPath(input.organizationId, resource.data, input.resourceId);
  } catch {
    return { ok: false, message: "invalid corporate target", fieldErrors: {} };
  }
  const parsed = entityProfileWriteRequestSchema.safeParse(input.data);
  if (!parsed.success) {
    return {
      ok: false,
      message: "invalid corporate profile",
      fieldErrors: fieldErrorsFromIssues(parsed.error.issues),
    };
  }
  try {
    assertCsrf(input.csrfToken, await readCsrfToken());
  } catch {
    return { ok: false, message: "csrf failed", fieldErrors: {} };
  }
  if (!(await readSession())) return { ok: false, message: "not signed in", fieldErrors: {} };
  const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!sessionToken) return { ok: false, message: "not signed in", fieldErrors: {} };
  try {
    const data = entityProfileViewSchema.parse(
      await privateApiRequest<unknown>(path, {
        method: "PUT",
        body: parsed.data,
        sessionToken,
      }),
    );
    revalidatePath("/[locale]/corporate", "layout");
    return { ok: true, data };
  } catch (error) {
    return error instanceof ApiError
      ? {
          ok: false,
          message: error.message,
          code: error.code,
          fieldErrors: fieldErrorsFromDetails(error.details, error.message),
        }
      : { ok: false, message: "request failed", fieldErrors: {} };
  }
}
