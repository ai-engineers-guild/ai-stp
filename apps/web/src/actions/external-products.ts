"use server";

import { revalidatePath } from "next/cache";
import { getTranslations } from "next-intl/server";
import { z } from "zod";

import { ApiError } from "@/lib/api/errors";
import { replaceOwnerExternalProducts } from "@/lib/api/owner";
import { createCatalogRequest } from "@/lib/api/reports";
import { sessionCookieValue } from "@/lib/auth/require-session";
import { requireCsrf } from "@/lib/auth/session";

const base = z.object({
  csrfToken: z.string().min(1),
  locale: z.string().min(2).max(5),
  objectKind: z.enum(["component", "setup"]),
  stableId: z.string().min(8).max(64),
});

class AuthorizeError extends Error {
  constructor(readonly key: "notSignedIn") {
    super(key);
  }
}

async function authorize(csrfToken: string) {
  await requireCsrf(csrfToken);
  const token = await sessionCookieValue();
  if (!token) throw new AuthorizeError("notSignedIn");
  return token;
}

async function failureMessage(error: unknown, fallback: string): Promise<string> {
  if (error instanceof ApiError) return error.message;
  const common = await getTranslations("common");
  if (error instanceof AuthorizeError) return common(error.key);
  return fallback;
}

export async function replaceExternalProductsAction(input: unknown) {
  const t = await getTranslations("objects");
  const parsed = base
    .extend({ canonicalDomains: z.array(z.string().min(3).max(253)).max(32) })
    .safeParse(input);
  if (!parsed.success) return { ok: false as const, message: t("serviceSelectionInvalid") };
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
      message: await failureMessage(error, t("servicesSaveFailed")),
    };
  }
}

export async function requestExternalProductAction(input: unknown) {
  const t = await getTranslations("objects");
  const parsed = base
    .extend({
      name: z.string().min(1).max(160),
      primaryUrl: z.string().url().max(512),
      descriptionRu: z.string().min(1).max(2000),
      descriptionEn: z.string().min(1).max(2000),
      sourceUrl: z.string().url().max(512),
      countryCodes: z.array(z.string().regex(/^[A-Z]{2}$/)).max(249),
    })
    .safeParse(input);
  if (!parsed.success) return { ok: false as const, message: t("serviceDataInvalid") };
  try {
    const token = await authorize(parsed.data.csrfToken);
    const request = await createCatalogRequest(token, {
      topic: "service_request",
      service: {
        name: parsed.data.name,
        primary_url: parsed.data.primaryUrl,
        description_ru: parsed.data.descriptionRu,
        description_en: parsed.data.descriptionEn,
        source_url: parsed.data.sourceUrl,
        country_codes: parsed.data.countryCodes,
      },
    });
    return { ok: true as const, caseId: request.case_id };
  } catch (error) {
    return {
      ok: false as const,
      message: await failureMessage(error, t("serviceRequestFailed")),
    };
  }
}

export async function requestCountryAction(input: unknown) {
  const t = await getTranslations("objects");
  const parsed = base
    .extend({
      code: z.string().regex(/^[A-Z]{2}$/),
      nameRu: z.string().min(1).max(160),
      nameEn: z.string().min(1).max(160),
    })
    .safeParse(input);
  if (!parsed.success) return { ok: false as const, message: t("countryDataInvalid") };
  try {
    const token = await authorize(parsed.data.csrfToken);
    const request = await createCatalogRequest(token, {
      topic: "country_request",
      country: { code: parsed.data.code, name_ru: parsed.data.nameRu, name_en: parsed.data.nameEn },
    });
    return { ok: true as const, caseId: request.case_id };
  } catch (error) {
    return {
      ok: false as const,
      message: await failureMessage(error, t("countryRequestFailed")),
    };
  }
}
