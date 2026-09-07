import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { SetupProvenance } from "@/components/molecules/setup-provenance";

describe("SetupProvenance", () => {
  it("renders exact source and related setup navigation without write actions", () => {
    render(
      <SetupProvenance
        portedFrom={{
          stable_id: "setup_source",
          version: "1.2",
          passport_digest: "sha256:source",
        }}
        relatedSetupIds={["setup_related"]}
        labels={{
          heading: "Setup provenance",
          portedFrom: "Ported from",
          relatedSetups: "Related setups",
        }}
      />,
    );

    expect(screen.getByRole("link", { name: "setup_source@1.2" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_source/versions/1.2",
    );
    expect(screen.getByRole("link", { name: "setup_related" })).toHaveAttribute(
      "href",
      "/catalog/setups/setup_related",
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
