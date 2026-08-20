export const SITE_NAME = "ai_stp";
export const CONTACT_EMAIL_PLACEHOLDER = "contact@example.invalid";
export const PUBLIC_LOCALES = ["ru", "en"] as const;

export function publicOrigin(): URL {
  return new URL(process.env["NEXT_PUBLIC_APP_URL"] ?? "http://localhost:3000");
}
