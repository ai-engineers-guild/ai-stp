import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ request: vi.fn(), csrf: vi.fn(), session: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ get: () => ({ value: "session" }) }),
}));
vi.mock("next-intl/server", () => ({
  getTranslations: () => Promise.resolve((key: string) => key),
}));
vi.mock("@/lib/api/http", () => ({ privateApiRequest: mocks.request }));
vi.mock("@/lib/auth/session", () => ({
  assertCsrf: () => {},
  readCsrfToken: mocks.csrf,
  readSession: mocks.session,
  SESSION_COOKIE: "session",
}));

import { corporateCatalogSearchAction } from "@/actions/corporate";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.csrf.mockResolvedValue("csrf");
  mocks.session.mockResolvedValue({ accountId: "account" });
  mocks.request.mockResolvedValue({ items: [], experimental: [] });
});

it("omits q for the initial empty catalog search accepted by the API", async () => {
  const result = await corporateCatalogSearchAction({
    kind: "component",
    query: "",
    csrfToken: "csrf",
  });
  expect(result).toEqual({ ok: true, items: [] });
  expect(mocks.request).toHaveBeenCalledWith("/v1/catalog/components", {
    sessionToken: "session",
    query: { page_size: 32, include_experimental: true },
  });
});

it("trims a nonempty search query and keeps its kind", async () => {
  await corporateCatalogSearchAction({ kind: "setup", query: "  Mobile  ", csrfToken: "csrf" });
  expect(mocks.request).toHaveBeenCalledWith("/v1/catalog/setups", {
    sessionToken: "session",
    query: { q: "Mobile", page_size: 32, include_experimental: true },
  });
});
