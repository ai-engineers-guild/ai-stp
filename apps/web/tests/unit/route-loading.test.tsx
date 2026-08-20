import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RouteLoading } from "@/components/molecules/route-loading";

describe("RouteLoading", () => {
  it("renders an accessible skeleton status region", () => {
    render(<RouteLoading label="Loading" />);
    const status = screen.getByRole("status", { name: "Loading" });
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-live", "polite");
    // Screen-reader text + visible skeletons keep soft-nav from a blank page.
    expect(screen.getByText("Loading", { selector: ".sr-only" })).toBeInTheDocument();
  });
});
