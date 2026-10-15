import { describe, expect, it, vi } from "vitest";
import type * as NextNavigation from "next/navigation";

const { component, version, redirect } = vi.hoisted(() => ({
  component: vi.fn(),
  version: vi.fn(),
  redirect: vi.fn(() => {
    throw new Error("redirected");
  }),
}));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  notFound: () => {
    throw new Error("not found");
  },
  redirect,
}));
vi.mock("next-intl/server", () => ({ setRequestLocale: vi.fn(), getTranslations: vi.fn() }));
vi.mock("@/lib/auth/require-session", () => ({ sessionCookieValue: () => Promise.resolve(null) }));
vi.mock("@/lib/api/catalog", () => ({
  readComponent: component,
  readComponentVersion: version,
  readComponentContextBudget: vi.fn(),
  readComponentGithubMetadata: vi.fn(),
  isAuthorizedPrivateComponentVersion: vi.fn(),
}));

import ComponentVersionPage from "@/app/[locale]/(site)/catalog/components/[stableId]/versions/[version]/page";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
describe("latest component version alias", () => {
  it("redirects to the canonical exact version before requesting a passport", async () => {
    component.mockResolvedValue({ summary: { latest_version: "1.2" } });
    version.mockRejectedValue(new Error("invalid version"));
    await expect(
      ComponentVersionPage({
        params: Promise.resolve({ locale: "en", stableId, version: "latest" }),
      }),
    ).rejects.toThrow("redirected");
    expect(redirect).toHaveBeenCalledWith(`/en/catalog/components/${stableId}/versions/1.2`);
    expect(version).not.toHaveBeenCalled();
  });
});
