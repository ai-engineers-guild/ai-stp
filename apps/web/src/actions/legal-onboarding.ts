"use server";

import { redirect } from "next/navigation";

import { completeLegalOnboarding } from "@/lib/api/legal";

export async function completeLegalOnboardingAction(
  locale: string,
  returnTo: string,
  serviceRulesRevisionId: string,
  personalDataConsentRevisionId: string,
  formData: FormData,
): Promise<void> {
  if (
    formData.get("service-rules") !== "accepted" ||
    formData.get("personal-data") !== "accepted"
  ) {
    redirect(
      `/${locale}/onboarding?${new URLSearchParams({ returnTo, reason: "required" }).toString()}`,
    );
  }
  await completeLegalOnboarding(locale, {
    service_rules_revision_id: serviceRulesRevisionId,
    personal_data_consent_revision_id: personalDataConsentRevisionId,
  });
  redirect(returnTo);
}
