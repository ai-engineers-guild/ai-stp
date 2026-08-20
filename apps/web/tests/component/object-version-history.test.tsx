import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import { ObjectVersionHistory } from "@/components/molecules/object-version-history";

describe("ObjectVersionHistory", () => {
  it("lists versions with a current marker", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ObjectVersionHistory
        title="Version history"
        note="Gaps are intentional."
        currentLabel="Current"
        emptyLabel="No offered versions."
        hrefFor={(version) => `/versions/${version}`}
        versions={[
          {
            version: "1.0",
            published_at: "2026-08-01",
            lifecycle: "active",
            support: { state: "verified", tier: "beta" },
          },
        ]}
        current="1.0"
      />,
    );

    expect(container.querySelector("svg.lucide-chevron-down")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /Version history/ }));
    expect(screen.getByRole("link", { name: "v1.0" })).toHaveAttribute("href", "/versions/1.0");
    expect(screen.getByText("Current")).toBeVisible();
    expect(container.querySelector("svg.lucide-chevron-up")).not.toBeNull();
  });

  it("shows an empty state when no versions are offered", async () => {
    const user = userEvent.setup();
    render(
      <ObjectVersionHistory
        title="Version history"
        note="Gaps are intentional."
        currentLabel="Current"
        emptyLabel="No offered versions."
        hrefFor={(version) => `/versions/${version}`}
        versions={[]}
        current="1.0"
      />,
    );
    await user.click(screen.getByRole("button", { name: /Version history/ }));
    expect(screen.getByText("No offered versions.")).toBeVisible();
  });
});
