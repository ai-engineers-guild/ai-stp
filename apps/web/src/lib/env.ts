import { z } from "zod";

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
