import { entityMenuResult, catalogActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { render } from "../render-with-intl";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MenuItem } from "@/components/atoms/menu";
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

    expect(screen.getByRole("button", { name: "More actions" })).toHaveClass("size-11");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await screen.findByRole("menuitem", { name: "Copy ID" });
    const items = screen.getAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Open details",
      "Copy ID",
      "Copy URL",
      "Copy CLI command",
      "Share",
      "Like",
      "Report setup",
    ]);
    expect(document.body.style.overflow).not.toBe("hidden");
    expect(getComputedStyle(document.body).overflow).not.toBe("hidden");
    await user.click(await screen.findByRole("menuitem", { name: "Copy ID" }));
    expect(writeText).toHaveBeenCalledWith("setup_example");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Copy CLI command" }));
    expect(writeText).toHaveBeenCalledWith("ai-stp registry show --kind setup --id setup_example");
  });

  it("ignores locally injected owner actions without server authorization", async () => {
    const user = userEvent.setup();
    render(
      <CatalogItemMenu
        kind="component"
        stableId="cmp_example"
        version="1.0"
        href="/objects/component/cmp_example"
        leadingItems={[
          <MenuItem key="visibility">Make public</MenuItem>,
          <MenuItem key="edit">Edit public presentation</MenuItem>,
          <MenuItem key="access">Manage access</MenuItem>,
        ]}
        labels={{ ...labels, report: "Report component" }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "More actions" }));
    await screen.findByRole("menuitem", { name: "Copy ID" });
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Open details",
      "Copy ID",
      "Copy URL",
      "Copy CLI command",
      "Share",
      "Like",
      "Report component",
    ]);
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
    expect(await screen.findByRole("menuitem", { name: "Report component" })).toBeInTheDocument();
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
    await screen.findByRole("menuitem", { name: "Copy ID" });
    await user.keyboard("{Home}{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Copy ID" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(await screen.findByRole("menuitem", { name: "Report component" })).toHaveFocus();
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
    await user.click(await screen.findByRole("menuitem", { name: "Like" }));
    await waitFor(() => {
      expect(updateCatalogReaction).toHaveBeenCalledWith("component", "cmp_example", true);
    });
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Unlike" }));
    await waitFor(() => {
      expect(updateCatalogReaction).toHaveBeenCalledWith("component", "cmp_example", false);
    });
  });
});

vi.mock("@/lib/entity-action-query", () => ({
  queryEntityActionMenu: vi.fn((subject: EntityActionSubject) =>
    Promise.resolve(
      entityMenuResult(
        subject,
        catalogActions,
        `/catalog/${subject.kind === "component" ? "components" : "setups"}/${subject.id}`,
      ),
    ),
  ),
}));
