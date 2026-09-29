/** Storybook no-op for account server actions. */
import type { OAuthProvider } from "@/lib/api/generated/types.gen";

export async function unlinkIdentityAction(_input: {
  provider: OAuthProvider;
  csrfToken: string;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  return { ok: true };
}

export async function updatePublicProfileAction(_input: unknown): Promise<never> {
  throw new Error("profile write unavailable in Storybook");
}
