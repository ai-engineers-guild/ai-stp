/* eslint-disable @typescript-eslint/require-await -- Async transport doubles preserve the production contract. */
import { expect, it, vi } from "vitest";
import { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import { privateApiRequest } from "@/lib/api/http";
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next-intl/server", () => ({ getTranslations: async () => (key: string) => key }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => ({ value: "session-fixture" }) }),
}));
vi.mock("@/lib/auth/session", () => ({
  assertCsrf: vi.fn(),
  readCsrfToken: async () => "csrf",
  readSession: async () => ({}),
  SESSION_COOKIE: "session",
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: vi.fn() }));

it("uses current authorization while preserving the profile revision and rich content", async () => {
  const fields = {
    description: "| Tool | Features |\n| --- | --- |\n| 🚀 **Next.js** | SSR<br>App Router |",
    links: [{ label: "Website", url: "https://nextjs.org" }],
    media: [],
    avatar_asset_id: null,
  };
  vi.mocked(privateApiRequest)
    .mockResolvedValueOnce({ organization: { authorization_revision: 21 } })
    .mockResolvedValueOnce({
      schema_version: 1,
      name: "Employee",
      fields,
      revision: 3,
      authorization_revision: 21,
      can_edit: true,
      avatar_url: null,
      owner_account_id: null,
    });
  const data = {
    schema_version: 1,
    fields,
    expected_revision: 2,
    authorization_revision: 1,
    idempotency_key: "profile-save-fixture",
  };
  const result = await updateCorporatePresentationAction({
    csrfToken: "csrf",
    organizationId: "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    resource: "members",
    resourceId: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    data,
  });
  expect(result.ok).toBe(true);
  expect(privateApiRequest).toHaveBeenCalledTimes(2);
  expect(vi.mocked(privateApiRequest).mock.calls[1]?.[1]?.body).toEqual({
    ...data,
    authorization_revision: 21,
  });
});
