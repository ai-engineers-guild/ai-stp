import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
    "aria-current"?: "page";
  }) => (
    <a href={href} className={props.className} aria-current={props["aria-current"]}>
      {children}
    </a>
  ),
}));

import { DocsNav } from "@/components/organisms/docs-nav";

describe("DocsNav", () => {
  it("renders nested sections and marks the current page", () => {
    render(
      <DocsNav
        ariaLabel="Documentation sections"
        currentHref="/docs/quickstart/agent"
        tree={[
          { title: "Overview", href: "/docs" },
          {
            title: "Quickstart",
            href: "/docs/quickstart",
            children: [
              { title: "For people", href: "/docs/quickstart/human" },
              { title: "For agents", href: "/docs/quickstart/agent" },
            ],
          },
          {
            title: "CLI",
            href: "/docs/cli",
            children: [
              { title: "Command map", href: "/docs/cli/commands" },
              {
                title: "Component",
                children: [{ title: "Overview", href: "/docs/cli/component" }],
              },
            ],
          },
        ]}
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Documentation sections" });
    expect(nav).toHaveAttribute("data-ui", "docs-nav");
    expect(screen.getByRole("link", { name: "For people" })).toHaveAttribute(
      "href",
      "/docs/quickstart/human",
    );
    expect(screen.getByRole("link", { name: "For agents" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Component")).toBeVisible();
    expect(nav.querySelector('a[href="/docs"]')).toHaveTextContent("Overview");
    expect(nav.querySelector('a[href="/docs/cli/component"]')).toHaveTextContent("Overview");
  });
});
