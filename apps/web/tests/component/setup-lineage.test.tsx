import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SetupLineage } from "@/components/molecules/setup-lineage";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a {...props}>{children}</a>
  ),
}));
const labels = { title: "Setup origin", portedFrom: "Ported from", related: "Related setups" };

describe("setup lineage", () => {
  it("links the exact source version separately from related setups", () => {
    render(
      <SetupLineage
        labels={labels}
        passport={{
          ported_from: {
            stable_id: "setup_source",
            version: "2.4",
            passport_digest: "sha256:" + "a".repeat(64),
          },
          related_setup_ids: ["setup_related"],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "setup_source@2.4" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_source/versions/2.4",
    );
    expect(screen.getByRole("link", { name: "setup_related" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_related",
    );
  });
  it("omits an empty lineage", () => {
    const { container } = render(
      <SetupLineage labels={labels} passport={{ ported_from: null, related_setup_ids: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
