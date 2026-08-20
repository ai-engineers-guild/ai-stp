import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DetailAccordion } from "@/components/molecules/detail-accordion";

describe("DetailAccordion", () => {
  it("points the chevron down when collapsed and up when expanded", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DetailAccordion
        title="Technical details"
        summary="1.0"
        headerAction={<a href="/docs">How checks work</a>}
      >
        <p>Body</p>
      </DetailAccordion>,
    );

    const trigger = screen.getByRole("button", { name: /Technical details/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Body")).not.toBeInTheDocument();
    expect(container.querySelector("svg.lucide-chevron-down")).not.toBeNull();
    expect(screen.getByRole("link", { name: "How checks work" })).toBeVisible();

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Body")).toBeVisible();
    expect(container.querySelector("svg.lucide-chevron-up")).not.toBeNull();
  });
});
