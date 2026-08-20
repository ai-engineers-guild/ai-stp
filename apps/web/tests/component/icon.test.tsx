import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Icon } from "@/theme";

describe("Icon kit", () => {
  it("renders a registry icon with aria-hidden by default", () => {
    const { container } = render(<Icon name="search" data-testid="icon-search" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("accepts an accessible label", () => {
    render(<Icon name="alert" aria-label="Warning" />);
    expect(screen.getByLabelText("Warning")).toBeInTheDocument();
  });
});
