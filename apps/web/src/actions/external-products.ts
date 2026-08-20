"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { createOwnerExternalProduct, replaceOwnerExternalProducts } from "@/lib/api/owner";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { assertCsrf, readCsrfToken } from "@/lib/auth/session";

const base = z.object({
  csrfToken: z.string().min(1),
  locale: z.string().min(2).max(5),
  objectKind: z.enum(["component", "setup"]),
  stableId: z.string().min(8).max(64),
});

async function authorize(csrfToken: string) {
  assertCsrf(csrfToken, await readCsrfToken());
  const token = await sessionCookieValue();
  if (!token) throw new Error("Not signed in.");
  return token;
}

export async function replaceExternalProductsAction(input: unknown) {
  const parsed = base
    .extend({ canonicalDomains: z.array(z.string().min(3).max(253)).max(32) })
    .safeParse(input);
  if (!parsed.success) return { ok: false as const, message: "Invalid service selection." };
  try {
    const token = await authorize(parsed.data.csrfToken);
    await replaceOwnerExternalProducts(
      token,
      parsed.data.objectKind,
      parsed.data.stableId,
      parsed.data.canonicalDomains,
    );
    revalidatePath(
      `/${parsed.data.locale}/objects/${parsed.data.objectKind}/${parsed.data.stableId}`,
    );
    revalidatePath(`/${parsed.data.locale}/catalog`);
    return { ok: true as const };
  } catch (error) {
    return {
      ok: false as const,
      message: error instanceof ApiError ? error.message : "Could not save services.",
    };
  }
}

export async function createExternalProductAction(input: unknown) {
  const parsed = base
    .extend({
      name: z.string().min(1).max(160),
      primaryUrl: z.string().url().max(512),
      countryCodes: z.array(z.string().regex(/^[A-Z]{2}$/)).max(249),
    })
    .safeParse(input);
  if (!parsed.success) return { ok: false as const, message: "Invalid service data." };
  try {
    const token = await authorize(parsed.data.csrfToken);
    const product = await createOwnerExternalProduct(token, {
      name: parsed.data.name,
      primary_url: parsed.data.primaryUrl,
      country_codes: parsed.data.countryCodes,
    });
    return { ok: true as const, product };
  } catch (error) {
    return {
      ok: false as const,
      message: error instanceof ApiError ? error.message : "Could not create service.",
    };
  }
}
