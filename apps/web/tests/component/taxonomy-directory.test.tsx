import { entityMenuResult, publicActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { NextIntlClientProvider } from "next-intl";
import userEvent from "@testing-library/user-event";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps, ReactNode } from "react";
import messages from "../../messages/en.json";
import { TaxonomyDirectory } from "@/components/organisms/taxonomy-directory";
import { authority, areas, categories } from "@/mocks/technology-workspace-fixture";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, ...props }: ComponentProps<"a">) => <a {...props}>{children}</a>,
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));

afterEach(cleanup);

function wrap(children: ReactNode) {
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      {children}
    </NextIntlClientProvider>
  );
}

function manyCategories(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    ...categories[0],
    category_id: `category_01JQZK7B8N4M6P2R9T5V0X3Y${String(index).padStart(2, "0")}`,
    name: `Category ${String(index).padStart(2, "0")}`,
  }));
}

it("searches cards, filters by area and pages results", () => {
  const items = manyCategories(26);
  render(
    wrap(
      <TaxonomyDirectory
        kind="category"
        items={items}
        areas={areas}
        authority={authority}
        canCreate
        canUpdate
        canRemove
        detailBase="/corporate/admin/technology-categories"
      />,
    ),
  );
  expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(12);
  expect(screen.getByRole("navigation", { name: "Pagination" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Open search" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Search by name" }), {
    target: { value: "category 25" },
  });
  expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
  expect(screen.queryByRole("navigation", { name: "Pagination" })).toBeNull();
});

it("opens the create and edit dialogs and links to the detail page", async () => {
  const user = userEvent.setup();
  render(
    wrap(
      <TaxonomyDirectory
        kind="area"
        items={areas}
        areas={areas}
        authority={authority}
        canCreate
        canUpdate
        canRemove={false}
      />,
    ),
  );
  await user.click(screen.getByRole("button", { name: "Create area" }));
  let dialog = screen.getByRole("dialog");
  expect(within(dialog).getAllByRole("heading", { name: "Create area" })).not.toHaveLength(0);
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "More actions" }));
  await user.click(await screen.findByRole("menuitem", { name: "Edit area" }));
  dialog = screen.getByRole("dialog");
  expect(within(dialog).getByRole("textbox", { name: /Name/ })).toHaveValue("Server applications");
});

vi.mock("@/lib/entity-action-query", () => ({
  queryEntityActionMenu: vi.fn((subject: EntityActionSubject) =>
    Promise.resolve(
      entityMenuResult(
        subject,
        [...publicActions.slice(0, -1), "edit", "delete", "report"],
        `/corporate/categories/${subject.id}`,
      ),
    ),
  ),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ refresh: vi.fn(), back: vi.fn(), replace: vi.fn() }),
}));
