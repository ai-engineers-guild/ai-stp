import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { cache } from "react";

import { cookies } from "next/headers";

import { CSRF_COOKIE, SESSION_COOKIE } from "@/lib/auth/cookies";
import { asAccountId, asDeviceId, type AccountId, type DeviceId } from "@/lib/brands";
import { getEnv } from "@/lib/env";

export { CSRF_COOKIE, SESSION_COOKIE };

export type WebSession = {
  accountId: AccountId;
  /** Optional current device id for revoke-current distinction. */
  deviceId: DeviceId | null;
  expiresAt: number;
};

type SessionPayload = {
  accountId: string;
  deviceId: string | null;
  expiresAt: number;
};

const SESSION_TTL_MS = 12 * 60 * 60 * 1000;

function sign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

function encodeSession(session: WebSession, secret: string): string {
  const body: SessionPayload = {
    accountId: session.accountId,
    deviceId: session.deviceId,
    expiresAt: session.expiresAt,
  };
  const payload = Buffer.from(JSON.stringify(body), "utf8").toString("base64url");
  const signature = sign(payload, secret);
  return `${payload}.${signature}`;
}

function decodeSession(token: string, secret: string): WebSession | null {
  const parts = token.split(".");
  if (parts.length !== 2) {
    return null;
  }
  const [payload, signature] = parts;
  if (!payload || !signature) {
    return null;
  }
  const expected = sign(payload, secret);
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    return null;
  }
  try {
    const raw = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as SessionPayload;
    if (typeof raw.expiresAt !== "number" || raw.expiresAt <= Date.now()) {
      return null;
    }
    return {
      accountId: asAccountId(raw.accountId),
      deviceId: raw.deviceId ? asDeviceId(raw.deviceId) : null,
      expiresAt: raw.expiresAt,
    };
  } catch {
    return null;
  }
}

export function createSessionToken(
  accountId: AccountId,
  deviceId: DeviceId | null = null,
): { token: string; session: WebSession } {
  const secret = getEnv().AI_STP_SESSION_SECRET;
  const session: WebSession = {
    accountId,
    deviceId,
    expiresAt: Date.now() + SESSION_TTL_MS,
  };
  return { token: encodeSession(session, secret), session };
}

export function parseSessionToken(token: string): WebSession | null {
  return decodeSession(token, getEnv().AI_STP_SESSION_SECRET);
}

export function createCsrfToken(): string {
  return randomBytes(24).toString("base64url");
}

/**
 * Read the current web session.
 *
 * Mock/offline mode uses an HMAC-signed cookie owned by apps/web. Real mode
 * uses the opaque server session cookie issued by the API (ADR-0041); identity
 * is confirmed via GET /v1/auth/me rather than local claims.
 *
 * Request-scoped via React.cache so layout + page + actions share one resolution
 * (and at most one /v1/auth/me) per render pass.
 */
export const readSession = cache(async (): Promise<WebSession | null> => {
  const jar = await cookies();
  const raw = jar.get(SESSION_COOKIE)?.value;
  if (!raw) {
    return null;
  }
  const parsed = parseSessionToken(raw);
  if (parsed) {
    return parsed;
  }

  const env = getEnv();
  if (env.AI_STP_USE_MOCKS || env.AI_STP_MOCK_AUTH) {
    // Unparseable cookie under mock auth is stale mock material.
    return null;
  }

  try {
    // Dynamic import avoids a static cycle with lib/api/http (cookies/session).
    const { readAuthMe } = await import("@/lib/api/auth-me");
    const me = await readAuthMe();
    return {
      accountId: asAccountId(me.account_id),
      deviceId: me.device_id ? asDeviceId(me.device_id) : null,
      expiresAt: Date.now() + SESSION_TTL_MS,
    };
  } catch {
    return null;
  }
});

export async function readCsrfToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(CSRF_COOKIE)?.value ?? null;
}

export async function setSessionCookies(sessionToken: string, csrfToken: string): Promise<void> {
  const jar = await cookies();
  const secure = process.env.NODE_ENV === "production";
  jar.set(SESSION_COOKIE, sessionToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
  jar.set(CSRF_COOKIE, csrfToken, {
    httpOnly: false,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
}

export async function clearSessionCookies(): Promise<void> {
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  jar.delete(CSRF_COOKIE);
}

export function assertCsrf(headerToken: string | null, cookieToken: string | null): void {
  if (!headerToken || !cookieToken) {
    throw new Error("CSRF token missing");
  }
  const a = Buffer.from(headerToken);
  const b = Buffer.from(cookieToken);
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    throw new Error("CSRF token mismatch");
  }
}
