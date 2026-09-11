import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { ContextSurfaceNav } from "@/components/molecules/context-surface-nav";
import { LOCAL_CONTEXT } from "@/lib/product-context";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const labels = {
  navigation: "Context",
  projects: "Projects",
  technology: "Technology",
  landscape: "Landscape",
  catalog: "Catalog",
};

describe("ContextSurfaceNav", () => {
  it("renders only routes allowed by the server projection", () => {
    const context = {
      ...LOCAL_CONTEXT,
      capabilities: {
        ...LOCAL_CONTEXT.capabilities,
        capabilities: ["project.list"],
      },
    };
    render(<ContextSurfaceNav context={context} status="ready" labels={labels} />);

    expect(screen.getByRole("link", { name: "Projects" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Technology" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Landscape" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Catalog" })).toBeNull();
  });

  it("renders no navigation while the projection is stale", () => {
    render(<ContextSurfaceNav context={LOCAL_CONTEXT} status="stale" labels={labels} />);
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});
