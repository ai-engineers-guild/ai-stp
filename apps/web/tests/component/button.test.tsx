import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "@/components/atoms/button";

describe("Button atom", () => {
  it("renders accessible button text", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });

  it("keeps smooth color transition classes for interactive feedback", () => {
    render(<Button>Go</Button>);
    const el = screen.getByRole("button", { name: "Go" });
    expect(el.className).toMatch(/transition-colors/);
    // Motion duration comes from the design-token CSS variable.
    expect(el.className).toMatch(/duration-\[var\(--duration-fast\)\]/);
  });

  it("exposes token-backed variant utilities", () => {
    render(
      <>
        <Button variant="secondary">Sec</Button>
        <Button variant="destructive">Del</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Sec" }).className).toMatch(/bg-secondary/);
    expect(screen.getByRole("button", { name: "Del" }).className).toMatch(/bg-destructive/);
  });
});
