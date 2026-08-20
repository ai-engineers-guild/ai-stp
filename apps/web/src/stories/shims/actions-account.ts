/** Storybook no-op for account server actions. */
export async function unlinkIdentityAction(_input: {
  provider: "google" | "github";
  csrfToken: string;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  return { ok: true };
}

export async function updatePublicProfileAction(_input: unknown): Promise<never> {
  throw new Error("profile write unavailable in Storybook");
}
