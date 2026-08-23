import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn() } }));
vi.mock("@/lib/actions/catalog-reactions", () => ({
  updateCatalogReaction: vi.fn((_kind: string, _id: string, liked: boolean) =>
    Promise.resolve({ schema_version: 1, liked, likes_count: liked ? 1 : 0 }),
  ),
}));
vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: ({
    label,
    hideTrigger,
    open,
  }: {
    label: string;
    hideTrigger?: boolean;
    open?: boolean;
  }) =>
    hideTrigger && !open ? null : (
      <div role="dialog" aria-label={label}>
        {label}
      </div>
    ),
}));

const { CatalogItemMenu } = await import("@/components/organisms/catalog-item-menu");

const { updateCatalogReaction } = await import("@/lib/actions/catalog-reactions");

const labels = {
  more: "More actions",
  copyUrl: "Copy URL",
  copyCli: "Copy CLI command",
  copyId: "Copy ID",
  copied: "Copied",
  report: "Report setup",
  like: "Like",
  unlike: "Unlike",
};

describe("CatalogItemMenu", () => {
  it("offers copy commands then report, with clipboard feedback", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });

    render(
      <CatalogItemMenu
        kind="setup"
        stableId="setup_example"
        version="1.0"
        href="/catalog/setups/setup_example"
        labels={labels}
      />,
    );

    expect(screen.getByRole("button", { name: "More actions" })).toHaveClass("h-11", "w-11");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    const items = screen.getAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Copy URL",
      "Copy ID",
      "Copy CLI command",
      "Like",
      "Report setup",
    ]);
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(getComputedStyle(document.body).overflow).not.toBe("hidden");
    await user.click(screen.getByRole("menuitem", { name: "Copy ID" }));
    expect(writeText).toHaveBeenCalledWith("setup_example");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Copy CLI command" }));
    expect(writeText).toHaveBeenCalledWith("ai-stp registry show --kind setup --id setup_example");
  });

  it("names the report action for a component and restores focus on Escape", async () => {
    const user = userEvent.setup();
    render(
      <CatalogItemMenu
        kind="component"
        stableId="cmp_example"
        version="1.0"
        href="/catalog/components/cmp_example"
        labels={{ ...labels, report: "Report component" }}
      />,
    );
    const trigger = screen.getByRole("button", { name: "More actions" });
    await user.click(trigger);
    expect(screen.getByRole("menuitem", { name: "Report component" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("moves between menu items with the arrow keys", async () => {
    const user = userEvent.setup();
    render(
      <CatalogItemMenu
        kind="component"
        stableId="cmp_example"
        version="1.0"
        href="/catalog/components/cmp_example"
        labels={{ ...labels, report: "Report component" }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Copy ID" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitem", { name: "Report component" })).toHaveFocus();
  });

  it("toggles like through the catalog reaction action without locking page scroll", async () => {
    const user = userEvent.setup();
    render(
      <CatalogItemMenu
        kind="component"
        stableId="cmp_example"
        version="1.0"
        href="/catalog/components/cmp_example"
        labels={{ ...labels, report: "Report component" }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    expect(getComputedStyle(document.body).overflow).not.toBe("hidden");
    await user.click(screen.getByRole("menuitem", { name: "Like" }));
    await waitFor(() => {
      expect(updateCatalogReaction).toHaveBeenCalledWith("component", "cmp_example", true);
    });
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Unlike" }));
    await waitFor(() => {
      expect(updateCatalogReaction).toHaveBeenCalledWith("component", "cmp_example", false);
    });
  });
});
