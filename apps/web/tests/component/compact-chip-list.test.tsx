import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { CompactChipList } from "@/components/molecules/compact-chip-list";

describe("CompactChipList", () => {
  it("shows three chips and exposes the rest through an accessible disclosure", async () => {
    const user = userEvent.setup();
    render(
      <CompactChipList
        values={["codex", "claude-code", "pi", "cursor", "codex"]}
        label="Harness"
      />,
    );

    expect(screen.getAllByText("codex")[0]).toBeVisible();
    expect(screen.getAllByText("claude-code")[0]).toBeVisible();
    expect(screen.getAllByText("pi")[0]).toBeVisible();
    const more = screen.getByText("+1");
    expect(more).toHaveTextContent("+1");
    await user.click(more);
    expect(more.closest("details")).toHaveAttribute("open");
    expect(screen.getAllByText("cursor").length).toBeGreaterThan(0);
  });
});
