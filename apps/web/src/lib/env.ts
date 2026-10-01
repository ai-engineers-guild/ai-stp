import { z } from "zod";

/** Corporate OIDC providers that may render an SSO button on the login page. */
const SSO_PROVIDERS = ["authentik", "keycloak"] as const;
export type SsoProvider = (typeof SSO_PROVIDERS)[number];

const ssoProvidersSchema = z
  .string()
  .default("")
  .transform((value) =>
    value
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean),
  )
  .pipe(z.array(z.enum(SSO_PROVIDERS)));

/**
 * Environment boundary (REQ-2201). Missing or invalid vars fail loud at load.
 * Never put secrets into NEXT_PUBLIC_* fields.
 */
const envSchema = z.object({
  NEXT_PUBLIC_APP_URL: z.url(),
  AI_STP_USER_DOCS_URL: z.url().default("http://localhost:8011"),
  AI_STP_API_BASE_URL: z.url(),
  AI_STP_USE_MOCKS: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  // When true, mock only the auth surface (OAuth/account/devices) while the
  // catalog uses the real API. Default false: real OAuth via the API.
  AI_STP_MOCK_AUTH: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  AI_STP_SESSION_SECRET: z.string().min(32),
  // How long a parked invitation claim cookie may live; matches the default
  // invitation TTL on the API side. Secret stays httpOnly the whole time.
  AI_STP_INVITATION_CLAIM_TTL_SECONDS: z.coerce.number().int().min(60).default(86400),
  // Corporate OIDC providers enabled on the API (ADR-0218), comma-separated.
  // Each name renders one SSO button on /login; empty hides them.
  AI_STP_AUTH_SSO_PROVIDERS: ssoProvidersSchema,
  // Contextual corporate rail (ADR-0219). "false" reverts to the secondary tabs.
  AI_STP_CORPORATE_CONTEXT_NAV: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
});

export type AppEnv = z.infer<typeof envSchema>;

function readRawEnv(): Record<string, string | undefined> {
  return {
    NEXT_PUBLIC_APP_URL: process.env["NEXT_PUBLIC_APP_URL"],
    AI_STP_USER_DOCS_URL: process.env["AI_STP_USER_DOCS_URL"],
    AI_STP_API_BASE_URL: process.env["AI_STP_API_BASE_URL"],
    AI_STP_USE_MOCKS: process.env["AI_STP_USE_MOCKS"] ?? "false",
    AI_STP_MOCK_AUTH: process.env["AI_STP_MOCK_AUTH"] ?? "false",
    AI_STP_SESSION_SECRET: process.env["AI_STP_SESSION_SECRET"],
    AI_STP_INVITATION_CLAIM_TTL_SECONDS: process.env["AI_STP_INVITATION_CLAIM_TTL_SECONDS"],
    AI_STP_AUTH_SSO_PROVIDERS: process.env["AI_STP_AUTH_SSO_PROVIDERS"] ?? "",
    AI_STP_CORPORATE_CONTEXT_NAV: process.env["AI_STP_CORPORATE_CONTEXT_NAV"],
  };
}

let cached: AppEnv | null = null;

export function resetEnvCache(): void {
  cached = null;
}

export function getEnv(): AppEnv {
  if (cached) {
    return cached;
  }
  const parsed = envSchema.safeParse(readRawEnv());
  if (!parsed.success) {
    const details = parsed.error.issues
      .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
      .join("; ");
    throw new Error(`Invalid apps/web environment: ${details}`);
  }
  cached = parsed.data;
  return cached;
}

/** Client-safe public subset only. */
export function getPublicEnv(): Pick<AppEnv, "NEXT_PUBLIC_APP_URL" | "AI_STP_USER_DOCS_URL"> {
  const env = getEnv();
  return {
    NEXT_PUBLIC_APP_URL: env.NEXT_PUBLIC_APP_URL,
    AI_STP_USER_DOCS_URL: env.AI_STP_USER_DOCS_URL,
  };
}
