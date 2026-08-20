import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { IdentityList } from "@/components/organisms/identity-list";
import en from "../../messages/en.json";
import { FIXTURE_TIMESTAMP } from "@/mocks/fixtures/identity";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("@/actions/account", () => ({
  unlinkIdentityAction: vi.fn(() => Promise.resolve({ ok: true as const })),
}));

function renderList(identities: React.ComponentProps<typeof IdentityList>["identities"]) {
  return render(
    <NextIntlClientProvider locale="en" messages={en}>
      <IdentityList identities={identities} csrfToken="csrf" returnTo="/en/account" />
    </NextIntlClientProvider>,
  );
}

describe("IdentityList (GitHub / Google bundle)", () => {
  it("renders a linked GitHub identity and blocks unlink when it is the only one", () => {
    renderList([
      {
        provider: "github",
        linked_at: FIXTURE_TIMESTAMP,
        avatar_url: "https://avatars.githubusercontent.com/u/1?v=4",
        display_name: "fixture-github",
      },
    ]);
    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("fixture-github")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Unlink/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: /Google/i })).toBeInTheDocument();
  });

  it("allows unlink when both providers are linked", () => {
    renderList([
      {
        provider: "github",
        linked_at: FIXTURE_TIMESTAMP,
        avatar_url: null,
        display_name: "gh",
      },
      {
        provider: "google",
        linked_at: FIXTURE_TIMESTAMP,
        avatar_url: null,
        display_name: "gg",
      },
    ]);
    const unlinks = screen.getAllByRole("button", { name: /Unlink/i });
    expect(unlinks).toHaveLength(2);
    for (const btn of unlinks) {
      expect(btn).not.toBeDisabled();
    }
  });
});
